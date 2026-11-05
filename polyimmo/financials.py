"""Merge local financial entries without modifying the imported Excel snapshot."""
import json
from collections import defaultdict

def number(value):
    return float(value) if value is not None else None

def active_entries(db,source_id):
    return db.execute('SELECT * FROM manual_records WHERE source_id=? AND deleted_at IS NULL ORDER BY period_start,created_at',(source_id,)).fetchall()

def quarter_states(db,source_id):
    groups=defaultdict(list)
    for row in active_entries(db,source_id):
        data=json.loads(row['payload']);groups[(data['year'],data['quarter'])].append(data)
    result={}
    for (year,q),rows in groups.items():
        months=set()
        for r in rows:
            if r['period_complete']:
                months.update([r['month']] if r['period_kind']=='month' else range((q-1)*3+1,q*3+1))
        energy_complete=len(months)==3
        result[f'{year}-T{q}']={
            'energy_complete':energy_complete,
            'financial_complete':energy_complete and all(r['payment_status']=='paid' for r in rows),
            'known_energy_kwh':sum(number(r.get('energy_kwh')) or 0 for r in rows),
            'known_received_chf':sum(number(r.get('received_chf')) or 0 for r in rows),
            'energy_known_count':sum(r.get('energy_kwh') is not None for r in rows),
            'bank_known_count':sum(r.get('received_chf') is not None for r in rows),
            'missing_bank_count':sum(r['payment_status']=='unknown' for r in rows),
            'records':len(rows)
        }
    return result

def financial_overlay(db,snapshot,legacy):
    source_id=snapshot['sha256'];records=active_entries(db,source_id)
    expenses=db.execute('SELECT * FROM manual_expenses WHERE source_id=? AND deleted_at IS NULL ORDER BY expense_date',(source_id,)).fetchall()
    last=snapshot.get('assumptions',{}).get('E14')
    snapshot['excel_last_quarter']=last
    snapshot['manual_quarters']=quarter_states(db,source_id)
    snapshot['complete_quarters']={f"{r['year']}-T{q}":True for r in snapshot['years'] for q in r['quarters']}
    snapshot['complete_quarters'].update({key:True for key,value in snapshot['manual_quarters'].items() if value['financial_complete']})
    snapshot['invoices']=list(legacy)
    snapshot['financials']={'records':len(records),'expenses':len(expenses),'missing_bank_count':0,'partial_quarters':[],
                            'locked_until':last,'last_modified':None,'received_known_chf':0,'expected_known_chf':0}
    if not records and not expenses:return snapshot
    additions=[];changed=[]
    for row in records:
        r=json.loads(row['payload']);changed.append(row['updated_at'])
        label=(r['period_start'][:7] if r['period_kind']=='month' else f"T{r['quarter']} {r['year']}")
        additions.append(dict(row_number=None,record_id=row['id'],origin='manual',year=r['year'],quarter=r['quarter'],
                              label=label,high_kwh=number(r.get('high_kwh')),low_kwh=number(r.get('low_kwh')),
                              energy_kwh=number(r.get('energy_kwh')),revenue_chf=number(r.get('received_chf')),
                              other_chf=number(r.get('other_chf')),expected_chf=number(r.get('expected_chf')),
                              note=r.get('note'),payment_status=r['payment_status'],period_complete=r['period_complete']))
    snapshot['invoices'].extend(additions)
    snapshot['invoices'].sort(key=lambda r:(r['year'],r['quarter'],r.get('label') or ''))
    expense_by_year=defaultdict(float)
    for row in expenses:
        r=json.loads(row['payload']);expense_by_year[int(row['expense_date'][:4])]+=float(r['amount_chf']);changed.append(row['updated_at'])
    years=sorted(set([r['year'] for r in snapshot['years']]+[r['year'] for r in additions]+list(expense_by_year)))
    original={r['year']:r for r in snapshot['years']};annual=[];cumulative=0
    for year in years:
        rows=[r for r in snapshot['invoices'] if r['year']==year]
        energy=sum(r['energy_kwh'] if r.get('energy_kwh') is not None else (r.get('high_kwh') or 0)+(r.get('low_kwh') or 0) for r in rows)
        sales=sum(r.get('revenue_chf') or 0 for r in rows);other=sum(r.get('other_chf') or 0 for r in rows)
        initial_charges=original.get(year,{}).get('charges')
        charges=(initial_charges or 0)+expense_by_year[year] if initial_charges is not None or year in expense_by_year else None
        net=sales+other-(charges or 0);cumulative+=net
        settled=[r for r in rows if r.get('revenue_chf') is not None and (r.get('origin')!='manual' or r.get('payment_status')=='paid')
                 and (r.get('energy_kwh') is not None or r.get('high_kwh') is not None or r.get('low_kwh') is not None)]
        settled_kwh=sum(r['energy_kwh'] if r.get('energy_kwh') is not None else (r.get('high_kwh') or 0)+(r.get('low_kwh') or 0) for r in settled)
        settled_sales=sum(r.get('revenue_chf') or 0 for r in settled)
        annual.append(dict(year=year,kwh=energy,sales=sales,other=other,charges=charges,
                           net_if_blank_charges_zero=net,cumulative_if_blank_charges_zero=cumulative,
                           quarters=sorted({r['quarter'] for r in rows}),price_ct_kwh=settled_sales/settled_kwh*100 if settled_kwh else None,
                           missing_bank_count=sum(r.get('payment_status')=='unknown' for r in rows)))
    snapshot['years']=annual
    for projected in snapshot['projection']:
        year=projected['year'];projected['other']=sum(r.get('other_chf') or 0 for r in snapshot['invoices'] if r['year']==year)
    if isinstance(last,(int,float)):
        complete={(r['year'],q) for r in original.values() for q in r['quarters']}
        complete.update((int(key[:4]),int(key[-1])) for key,value in snapshot['manual_quarters'].items() if value['financial_complete'])
        complete_years=[year for year in years if all((year,q) in complete for q in (1,2,3,4))]
        if len(complete_years)>=2:snapshot['assumptions']['E5'],snapshot['assumptions']['E6']=complete_years[-2:]
        contiguous=int(last)
        while True:
            year,q=divmod(contiguous,10);following=(year+1,1) if q==4 else (year,q+1)
            if following not in complete:break
            contiguous=following[0]*10+following[1]
        snapshot['assumptions']['E14']=contiguous
    if snapshot['invoices']:
        latest=max((r['year'],r['quarter']) for r in snapshot['invoices']);snapshot['last_invoice_year'],snapshot['last_invoice_quarter']=latest
    snapshot['financials'].update(missing_bank_count=sum(r['payment_status']=='unknown' for r in additions),
        partial_quarters=[key for key,value in snapshot['manual_quarters'].items() if not value['financial_complete']],
        last_modified=max(changed) if changed else None,
        received_known_chf=sum(r.get('revenue_chf') or 0 for r in additions),expected_known_chf=sum(r.get('expected_chf') or 0 for r in additions))
    return snapshot
