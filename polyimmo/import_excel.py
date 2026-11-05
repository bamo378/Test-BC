"""Read-only, repeatable Excel import. Never executes workbook instructions/macros."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import openpyxl
from .db import connect


def now():
    return datetime.now(timezone.utc).isoformat()


def number(value):
    return Decimal(str(value)) if value is not None else Decimal(0)


def chart_inventory(chart):
    # Retain all chart references, titles and options without dumping verbose reprs.
    from xml.etree.ElementTree import tostring
    return dict(type=type(chart).__name__,
                series_xml=tostring(chart.to_tree(), encoding='unicode'),
                title_xml=tostring(chart.title.to_tree(),encoding='unicode') if chart.title else None,
                x_axis_title_xml=tostring(chart.x_axis.title.to_tree(),encoding='unicode') if chart.x_axis.title else None,
                y_axis_title_xml=tostring(chart.y_axis.title.to_tree(),encoding='unicode') if chart.y_axis.title else None)


def audit(workbook, cached):
    sheets = []
    for sheet in workbook:
        cells = []
        for row in sheet:
            for cell in row:
                if cell.value is not None:
                    cells.append(dict(address=cell.coordinate, value=cell.value,
                                      type=cell.data_type,
                                      cached=cached[sheet.title][cell.coordinate].value,
                                      number_format=cell.number_format))
        sheets.append(dict(name=sheet.title, rows=sheet.max_row, columns=sheet.max_column,
                           state=sheet.sheet_state, cells=cells,
                           formulas=sum(c['type'] == 'f' for c in cells),
                           merged=[str(x) for x in sheet.merged_cells.ranges],
                           charts=[chart_inventory(ch) for ch in sheet._charts],
                           validations=[dict(range=str(d.sqref), type=d.type,
                                             formula1=d.formula1, formula2=d.formula2)
                                        for d in sheet.data_validations.dataValidation]))
    return dict(sheets=sheets, external_links=len(workbook._external_links),
                defined_names=list(workbook.defined_names))


def import_workbook(path, db_path=None, audit_path=None):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    w = openpyxl.load_workbook(path, data_only=False)
    v = openpyxl.load_workbook(path, data_only=True)
    if audit_path:
        target = Path(audit_path)
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with target.open('w',encoding='utf-8') as f:
            json.dump(audit(w,v),f,ensure_ascii=False,default=str,indent=2)
        target.chmod(0o600)
    rows = []
    totals = {}
    for r in range(5, 401):
        s = w['Saisie']
        if s[f'A{r}'].value is None:
            continue
        year = s[f'A{r}'].value
        q = s[f'B{r}'].value
        if not isinstance(year, int) or q not in ('T1','T2','T3','T4'):
            raise ValueError(f'Saisie!A{r}:B{r}: période non valide')
        high, low, revenue, other = [s[f'{c}{r}'].value for c in 'DEHI']
        energy = number(high) + number(low)
        cached_energy = v['Saisie'][f'F{r}'].value
        if cached_energy not in (None, '') and abs(number(cached_energy)-energy) > Decimal('0.00001'):
            raise ValueError(f'Saisie!F{r}: formule et résultat mémorisé divergent')
        rows.append((digest,r,year,int(q[1]),s[f'C{r}'].value,high,low,revenue,other,s[f'K{r}'].value))
        item = totals.setdefault(year,dict(year=year,kwh=Decimal(0),sales=Decimal(0),other=Decimal(0),quarters=set()))
        item['kwh'] += energy
        item['sales'] += number(revenue)
        item['other'] += number(other)
        item['quarters'].add(int(q[1]))
    years = []
    cumulative = Decimal(0)
    investment = v['Investissement']
    cost = number(investment['C10'].value)
    for year, item in sorted(totals.items()):
        r = 5 + year - investment['C13'].value
        charge = w['Synthèse annuelle'][f'F{r}'].value
        net = item['sales'] + item['other'] - number(charge)
        cumulative += net
        # Validate actual sums against existing cached annual results.
        for col, actual in [('C',item['kwh']),('D',item['sales']),('E',item['other']),('G',net)]:
            cache = v['Synthèse annuelle'][f'{col}{r}'].value
            if cache is None or abs(number(cache)-actual) > Decimal('0.00001'):
                raise ValueError(f'Synthèse annuelle!{col}{r}: résultat à recalculer dans Excel')
        years.append(dict(year=year,kwh=float(item['kwh']),sales=float(item['sales']),
                          other=float(item['other']),charges=charge,net_if_blank_charges_zero=float(net),
                          cumulative_if_blank_charges_zero=float(cumulative),
                          quarters=sorted(item['quarters']),
                          price_ct_kwh=float(item['sales']/item['kwh']*100) if item['kwh'] else None))
    p = v['Projection 30 ans']
    projection = [dict(zip(('year','status','q1','q2','q3','q4','sales','other','kwh','charges','net','cumulative','profit','depreciation','accounting','irr_flow'),
                          [p.cell(r,c).value for c in range(1,17)])) for r in range(22,52)]
    archive = [(digest,r,v['Archive courbes 2023'].cell(r,1).value.isoformat(),v['Archive courbes 2023'].cell(r,2).value)
               for r in range(13,v['Archive courbes 2023'].max_row+1)]
    payload = dict(source='Excel utilisateur',sha256=digest,imported_at=now(),
                   investment=dict(ex_tax=investment['C4'].value,vat_rate=investment['C5'].value,
                                   vat=investment['C6'].value,gross=investment['C7'].value,
                                   subsidy=investment['C8'].value,net=float(cost),
                                   commissioning_year=investment['C13'].value,kwp=investment['C14'].value),
                   years=years,projection=projection,
                   assumptions={cell:p[cell].value for cell in ('E5','E6','E7','E8','E9','E10','E11','E12','E13','E14')},
                   projection_summary={cell:p[cell].value for cell in ('P14','P15','P16','P17','P18')},
                   last_invoice_year=max(totals),last_invoice_quarter=max(totals[max(totals)]['quarters']),
                   archive=dict(rows=len(archive),first_local=archive[0][2],last_local=archive[-1][2],
                                timezone='Non précisé dans le fichier',metric='Énergie refoulée GESA (kWh)'))
    db = connect(db_path)
    try:
        with db:
            if db.execute('SELECT 1 FROM sources WHERE id=?',(digest,)).fetchone():
                return dict(status='already_imported',invoices=len(rows),archive_rows=len(archive))
            db.execute('INSERT INTO sources VALUES (?,?,?)',(digest,payload['imported_at'],'excel'))
            db.executemany('INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
            db.executemany('INSERT INTO grid_archive VALUES (?,?,?,?)', archive)
            db.execute('INSERT INTO snapshots VALUES (?,?)',(digest,json.dumps(payload,ensure_ascii=False)))
            db.execute("INSERT INTO settings VALUES ('active_excel',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(digest,))
    finally:
        db.close()
    return dict(status='imported',invoices=len(rows),archive_rows=len(archive),years=len(years))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Importer le classeur privé, sans le modifier')
    parser.add_argument('workbook')
    parser.add_argument('--audit',default='.local/excel-audit.json')
    args = parser.parse_args()
    print(json.dumps(import_workbook(args.workbook,audit_path=args.audit),ensure_ascii=False))
