import json
import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch
from fastapi.testclient import TestClient
from polyimmo.db import connect
from polyimmo.web import app


class MonthlyFinancialEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=self.tmp.name+'/financial.sqlite3'
        db=connect(self.path);self.identity='synthetic-source'
        years=[];cumulative=0
        with db:
            db.execute('INSERT INTO sources VALUES (?,?,?)',(self.identity,'2026-11-05T00:00Z','excel'))
            for year in [2024,2025,2026]:
                quarters=[1,2,3,4] if year<2026 else [1,2,3]
                for q in quarters:db.execute('INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?)',(self.identity,year*10+q,year,q,f'T{q}',100,0,10,None,None))
                cumulative+=len(quarters)*10
                years.append(dict(year=year,quarters=quarters,kwh=100*len(quarters),sales=10*len(quarters),other=0,charges=None,net_if_blank_charges_zero=10*len(quarters),cumulative_if_blank_charges_zero=cumulative,price_ct_kwh=10))
            snapshot=dict(sha256=self.identity,assumptions={'E5':2024,'E6':2025,'E14':20263},investment={'net':1000},years=years,projection=[{'year':y,'other':0} for y in range(2023,2053)],last_invoice_year=2026,last_invoice_quarter=3)
            self.initial=json.dumps(snapshot)
            db.execute('INSERT INTO snapshots VALUES (?,?)',(self.identity,self.initial));db.execute('INSERT INTO settings VALUES (?,?)',('active_excel',self.identity))
        db.close();self.env=patch.dict(os.environ,{'POLYIMMO_DB':self.path});self.env.start()
        self.clock=patch('polyimmo.ledger.today',return_value=date(2027,1,5));self.clock.start()
        self.client=TestClient(app);self.headers={'X-PolyImmo-Request':'1'}
        self.body=dict(year=2026,period_kind='month',month=10,source='GRD',energy_mode='total',total_kwh=100,period_complete=True,expected_chf=20,payment_status='unknown',grd_reference='SYNTHETIC-GRD')

    def tearDown(self):
        self.client.close();self.clock.stop();self.env.stop();self.tmp.cleanup()

    def add(self,body=None):
        r=self.client.post('/api/entries',json=body or self.body,headers=self.headers)
        self.assertEqual(r.status_code,201,r.text);return r.json()

    def test_bank_completes_existing_reading_without_counting_invoice_twice(self):
        row=self.add();before=self.client.get('/api/dashboard').json()
        self.assertEqual(before['years'][-1]['sales'],30)
        self.assertEqual(before['financials']['missing_bank_count'],1)
        self.assertEqual(before['years'][-1]['price_ct_kwh'],10)
        self.assertFalse(before['manual_quarters']['2026-T4']['financial_complete'])
        paid={**self.body,'received_chf':20,'payment_status':'paid','payment_date':'2026-11-05','bank_reference':'SYNTHETIC-BANK'}
        r=self.client.put('/api/entries/'+row['id'],json=paid,headers=self.headers);self.assertEqual(r.status_code,200,r.text)
        after=self.client.get('/api/dashboard').json()
        self.assertEqual(after['years'][-1]['sales'],50)
        self.assertEqual(after['years'][-1]['kwh'],400)
        self.assertEqual(after['financials']['missing_bank_count'],0)
        self.assertEqual(after['years'][-1]['price_ct_kwh'],12.5)
        self.assertEqual(len(self.client.get('/api/entries').json()['records']),1)
        db=connect(self.path);self.assertEqual(db.execute('SELECT payload FROM snapshots').fetchone()[0],self.initial);db.close()

    def test_overlap_duplicate_and_excel_period_are_rejected(self):
        self.add()
        self.assertEqual(self.client.post('/api/entries',json=self.body,headers=self.headers).status_code,409)
        quarter={**self.body,'period_kind':'quarter','month':None,'quarter':4}
        self.assertEqual(self.client.post('/api/entries',json=quarter,headers=self.headers).status_code,409)
        old={**self.body,'month':9}
        self.assertEqual(self.client.post('/api/entries',json=old,headers=self.headers).status_code,409)

    def test_three_complete_paid_months_close_quarter_and_update_reference_years(self):
        for month in [10,11,12]:self.add({**self.body,'month':month,'payment_status':'paid','received_chf':20})
        data=self.client.get('/api/dashboard').json()
        self.assertTrue(data['manual_quarters']['2026-T4']['financial_complete'])
        self.assertEqual(data['assumptions']['E14'],20264)
        self.assertEqual([data['assumptions']['E5'],data['assumptions']['E6']],[2025,2026])
        self.assertEqual(data['years'][-1]['sales'],90)
        body={'name':'Synthetic scenario','scenario':{'degradation':.005,'price':0,'expenses':0,'inflation':.01,'tariffs':{'overrides':{'2026-T4':8}}}}
        self.assertEqual(self.client.post('/api/scenarios',json=body,headers=self.headers).status_code,422)

    def test_unpaid_unknown_zero_and_total_only_remain_distinct(self):
        row=self.add();self.assertIsNone(row['received_chf']);self.assertIsNone(row['high_kwh']);self.assertEqual(float(row['energy_kwh']),100)
        paid={**self.body,'payment_status':'unpaid'}
        r=self.client.put('/api/entries/'+row['id'],json=paid,headers=self.headers);self.assertEqual(r.status_code,200)
        self.assertEqual(float(r.json()['received_chf']),0)
        invalid={**self.body,'received_chf':10}
        self.assertEqual(self.client.put('/api/entries/'+row['id'],json=invalid,headers=self.headers).status_code,422)

    def test_expenses_are_additive_archivable_and_restorable(self):
        charge={'expense_date':'2026-11-01','amount_chf':25,'category':'insurance','label':'Synthetic insurance'}
        r=self.client.post('/api/expenses',json=charge,headers=self.headers);self.assertEqual(r.status_code,201,r.text);rid=r.json()['id']
        data=self.client.get('/api/dashboard').json();self.assertEqual(data['years'][-1]['charges'],25);self.assertEqual(data['years'][-1]['net_if_blank_charges_zero'],5)
        self.assertEqual(self.client.post('/api/expenses',json=charge,headers=self.headers).status_code,409)
        self.assertEqual(self.client.delete('/api/expenses/'+rid,headers=self.headers).status_code,200)
        self.assertIsNone(self.client.get('/api/dashboard').json()['years'][-1]['charges'])
        self.assertEqual(self.client.post('/api/expenses/'+rid+'/restore',headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/dashboard').json()['years'][-1]['charges'],25)

    def test_reading_archive_preserves_a_revision_and_restores_without_duplicate(self):
        row=self.add();rid=row['id'];self.assertEqual(self.client.delete('/api/entries/'+rid,headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/entries').json()['records'],[])
        self.assertIsNotNone(self.client.get('/api/entries?include_archived=true').json()['records'][0]['deleted_at'])
        self.assertEqual(self.client.post('/api/entries/'+rid+'/restore',headers=self.headers).status_code,200)
        self.assertEqual(len(self.client.get('/api/entries').json()['records']),1)
        db=connect(self.path);self.assertEqual(db.execute('SELECT COUNT(*) FROM financial_revisions').fetchone()[0],3);db.close()

    def test_future_actual_readings_and_cross_origin_writes_are_rejected(self):
        with patch('polyimmo.ledger.today',return_value=date(2026,11,5)):
            future={**self.body,'month':12}
            self.assertEqual(self.client.post('/api/entries',json=future,headers=self.headers).status_code,422)
            incomplete={**self.body,'period_kind':'quarter','quarter':4,'month':None,'period_complete':True}
            self.assertEqual(self.client.post('/api/entries',json=incomplete,headers=self.headers).status_code,422)
        self.assertEqual(self.client.post('/api/entries',json=self.body).status_code,403)


if __name__=='__main__':unittest.main()
