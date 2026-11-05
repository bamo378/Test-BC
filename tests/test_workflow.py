"""Synthetic fixtures only; they never populate the private development database."""
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import openpyxl
from fastapi.testclient import TestClient
from polyimmo.db import connect
from polyimmo.collector import Point, AuthExpired, ingest, run
from polyimmo.import_excel import import_workbook
from polyimmo.web import app


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name)/'private.sqlite3')
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def point(self, value=3.5, stamp='2026-10-25T02:15:00+02:00'):
        return Point('35546755','synthetic-device','production_interval',stamp,900,value,'kWh')

    def test_duplicate_is_upsert_and_correction_keeps_revision(self):
        ingest(self.db,[self.point(),self.point()])
        ingest(self.db,[self.point()])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],1)
        ingest(self.db,[self.point(4)])
        self.assertEqual(self.db.execute('SELECT value FROM measurements').fetchone()[0],4)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM measurement_revisions').fetchone()[0],1)

    def test_batch_validation_prevents_partial_import(self):
        with self.assertRaises(ValueError):
            ingest(self.db,[self.point(),self.point(-1,'2026-10-25T03:00:00+02:00')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],0)

    def test_conflicting_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            ingest(self.db,[self.point(),self.point(9)])

    def test_daylight_saving_repeated_hour_is_distinct(self):
        ingest(self.db,[self.point(stamp='2026-10-25T02:15:00+02:00'),self.point(stamp='2026-10-25T02:15:00+01:00')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],2)
        with self.assertRaises(ValueError):
            ingest(self.db,[self.point(stamp='2026-10-25T02:15:00')])

    def test_session_expiry_stops_without_storing_exception_text(self):
        class Expired:
            def fetch(self):
                raise AuthExpired('synthetic-secret-must-not-be-retained')
        self.assertEqual(run(Expired(),self.db),'reauth_required')
        row = self.db.execute('SELECT * FROM sync_runs').fetchone()
        self.assertEqual(row['error_code'],'session_expired')
        self.assertNotIn('synthetic-secret',str(dict(row)))

    def test_retry_then_success_and_later_failure_preserves_last_success(self):
        point=self.point()
        class Flaky:
            calls=0
            def fetch(self):
                self.calls+=1
                if self.calls<3:
                    raise OSError('synthetic network failure')
                return [point]
        waits=[]
        self.assertEqual(run(Flaky(),self.db,waits.append),'success')
        self.assertEqual(waits,[1,2])
        class Bad:
            def fetch(self): return []
        self.assertEqual(run(Bad(),self.db),'failed')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sync_runs WHERE status='success'").fetchone()[0],1)

    def workbook(self):
        path=Path(self.tmp.name)/'synthetic.xlsx'
        w=openpyxl.Workbook();w.remove(w.active)
        for name in ['Mode d\'emploi','Tableau de bord','Saisie','Synthèse annuelle','Projection 30 ans','Investissement','Archive courbes 2023']:
            w.create_sheet(name)
        for cell,value in {'C4':150,'C5':0,'C6':0,'C7':150,'C8':50,'C10':100,'C13':2023}.items():
            w['Investissement'][cell]=value
        for cell,value in {'A5':2023,'B5':'T2','C5':'Fixture synthétique','D5':5,'E5':2,'F5':7,'H5':2}.items():
            w['Saisie'][cell]=value
        for cell,value in {'C5':7,'D5':2,'E5':0,'G5':2}.items():
            w['Synthèse annuelle'][cell]=value
        w['Archive courbes 2023']['A13']=datetime(2023,4,1,0,15)
        w['Archive courbes 2023']['B13']=1
        w.save(path)
        return path

    def test_excel_repeatable_and_annual_totals_validated(self):
        path=self.workbook()
        self.assertEqual(import_workbook(path,self.path)['status'],'imported')
        self.assertEqual(import_workbook(path,self.path)['status'],'already_imported')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM invoices').fetchone()[0],1)
        payload=json.loads(self.db.execute('SELECT payload FROM snapshots').fetchone()[0])
        self.assertIsNone(payload['years'][0]['charges'])
        self.assertEqual(payload['years'][0]['kwh'],7)
        w=openpyxl.load_workbook(path);w['Synthèse annuelle']['C5']=999;w.save(path)
        with self.assertRaises(ValueError): import_workbook(path,self.path)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sources').fetchone()[0],1)

    def test_http_dashboard_and_absent_online_data(self):
        import_workbook(self.workbook(),self.path)
        with patch.dict(os.environ,{'POLYIMMO_DB':self.path}),TestClient(app) as client:
            page=client.get('/')
            self.assertEqual(page.status_code,200)
            self.assertIn('frame-ancestors',page.headers['content-security-policy'])
            data=client.get('/api/dashboard').json()
            self.assertIsNone(data['sync']['last_success'])
            self.assertTrue(data['sync']['stale'])
            self.assertFalse(data['sync']['validated'])
            self.assertEqual(len(data['invoices']),1)
            self.assertEqual(client.get('/static/secret').status_code,404)


if __name__=='__main__': unittest.main()
