import json
import tempfile
import unittest
from datetime import date,datetime,timezone
from polyimmo.aurora import AuroraPortalAdapter
from polyimmo.db import connect
from polyimmo.history import backfill


class HistoricalImportTests(unittest.TestCase):
    def test_absent_historical_days_are_reported_without_inserting_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(tmp+'/history.sqlite3');adapter=AuroraPortalAdapter(clock=lambda:datetime(2026,11,5,tzinfo=timezone.utc))
            adapter._get=lambda path,params:[{'start':'2025-06-01T22:00:00Z','end':'2025-06-02T22:00:00Z'}]
            try:
                status,report=backfill(adapter,db,date(2025,6,1),date(2025,6,2))
                self.assertEqual(status,'partial');self.assertEqual(report['points'],0);self.assertEqual(report['missing_days'],2)
                self.assertIsNone(report['periods'][0]['measured_kwh'])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],0)
            finally:adapter.close();db.close()

    def test_historical_replay_and_aggregate_match_are_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(tmp+'/history.sqlite3');adapter=AuroraPortalAdapter(clock=lambda:datetime(2026,11,5,tzinfo=timezone.utc))
            def get(path,params):return [{'start':'2026-11-02T23:00:00Z','end':'2026-11-03T23:00:00Z','value':12.5,'units':'kilowatt-hours'}]
            adapter._get=get
            try:
                first,report=backfill(adapter,db,date(2026,11,3),date(2026,11,3))
                second,_=backfill(adapter,db,date(2026,11,3),date(2026,11,3))
                self.assertEqual(first,'success');self.assertEqual(second,'success')
                self.assertTrue(report['periods'][0]['verified_complete'])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],1)
            finally:adapter.close();db.close()


if __name__=='__main__':unittest.main()
