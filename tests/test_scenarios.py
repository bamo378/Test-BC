import json
import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from polyimmo.db import connect
from polyimmo.web import app


class SavedScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=self.temp.name+'/scenario.sqlite3'
        db=connect(self.path)
        snapshot={'assumptions':{'E14':20263},'projection':[{'year':y} for y in range(2023,2053)]}
        with db:
            db.execute('INSERT INTO sources VALUES (?,?,?)',('synthetic-source','2026-11-05T00:00:00Z','excel'))
            db.execute('INSERT INTO snapshots VALUES (?,?)',('synthetic-source',json.dumps(snapshot)))
            db.execute('INSERT INTO settings VALUES (?,?)',('active_excel','synthetic-source'))
        db.close()
        self.env=patch.dict(os.environ,{'POLYIMMO_DB':self.path});self.env.start()
        self.client=TestClient(app)
        self.body={'name':'Scénario synthétique','scenario':{'degradation':.005,'price':0,'expenses':1000,'inflation':.01,'tariffs':{'seasonal':{'1':7.5},'overrides':{'2026-T4':0,'2028-T2':12}},'replacementYear':2035,'replacementCost':15000}}
        self.headers={'X-PolyImmo-Request':'1'}

    def tearDown(self):
        self.client.close();self.env.stop();self.temp.cleanup()

    def test_scenario_roundtrip_preserves_zero_specific_rates_and_survives_new_connection(self):
        r=self.client.post('/api/scenarios',json=self.body,headers=self.headers)
        self.assertEqual(r.status_code,201,r.text)
        rows=self.client.get('/api/scenarios').json()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['scenario']['tariffs']['overrides']['2026-T4'],0)
        with TestClient(app) as other:
            self.assertEqual(other.get('/api/scenarios').json()[0]['id'],r.json()['id'])
        self.assertEqual(self.client.delete('/api/scenarios/'+r.json()['id'],headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/scenarios').json(),[])

    def test_historical_out_of_horizon_and_non_numeric_rates_are_rejected(self):
        for overrides in [{'2025-T1':8},{'2053-T1':8},{'2027-T5':8},{'2027-T1':'not-a-rate'}]:
            body=json.loads(json.dumps(self.body));body['scenario']['tariffs']['overrides']=overrides
            self.assertEqual(self.client.post('/api/scenarios',json=body,headers=self.headers).status_code,422)
        self.assertEqual(self.client.get('/api/scenarios').json(),[])

    def test_mutations_reject_cross_origin_and_missing_request_header(self):
        self.assertEqual(self.client.post('/api/scenarios',json=self.body).status_code,403)
        self.assertEqual(self.client.post('/api/scenarios',json=self.body,headers={**self.headers,'Origin':'https://untrusted.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/scenarios').json(),[])

    def test_past_replacement_year_and_unrecognized_fields_are_rejected(self):
        body=json.loads(json.dumps(self.body));body['scenario']['replacementYear']=2025
        self.assertEqual(self.client.post('/api/scenarios',json=body,headers=self.headers).status_code,422)
        body=json.loads(json.dumps(self.body));body['scenario']['unrecognized']='not permitted'
        self.assertEqual(self.client.post('/api/scenarios',json=body,headers=self.headers).status_code,422)


if __name__=='__main__':unittest.main()
