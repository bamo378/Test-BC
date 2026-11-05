import json,tempfile,unittest
from pathlib import Path
from polyimmo.private_envelope import encrypt,decrypt
from scripts.build_pages import build
class PagesTests(unittest.TestCase):
 def test_private_snapshot_requires_password_and_rejects_tampering(self):
  value={'format':'synthetic','measurements':[1,2],'private_note':'fixture-only'};envelope=encrypt(value,'synthetic-password-2026');self.assertNotIn('fixture-only',json.dumps(envelope));self.assertEqual(decrypt(envelope,'synthetic-password-2026'),value)
  with self.assertRaises(Exception):decrypt(envelope,'incorrect-password')
  envelope['data']=envelope['data'][:-5]+'AAAAA'
  with self.assertRaises(Exception):decrypt(envelope,'synthetic-password-2026')
 def test_static_build_has_relative_assets_and_no_private_source_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   build(tmp);p=Path(tmp);index=(p/'index.html').read_text();self.assertIn('data-hosting="github-pages"',index);self.assertIn('./polyimmo/static/app.js',index);self.assertTrue((p/'.nojekyll').exists());self.assertTrue((p/'polyimmo/static/logo-polyimmo.png').exists());self.assertFalse((p/'.local').exists());self.assertFalse(list(p.rglob('*.sqlite3')));self.assertFalse(list(p.rglob('*.xlsx')))
 def test_collector_failure_keeps_encrypted_history_and_last_success(self):
  from unittest.mock import patch
  from datetime import datetime,timedelta,timezone
  from polyimmo.collector import Point,Collection,AuthExpired
  from scripts.collect_pages import collect
  class Adapter:
   def fetch(self):
    now=datetime.now(timezone.utc)
    return Collection([Point('35546755','plant','power',(now-timedelta(minutes=30)).isoformat(),900,12.5,'kW')],{'fetched_at':now.isoformat(),'validated':True})
   def close(self):pass
  class Expired(Adapter):
   def fetch(self):raise AuthExpired()
  with tempfile.TemporaryDirectory() as tmp:
   with patch('scripts.collect_pages.AuroraPortalAdapter',Adapter):first=collect(Path(tmp)/'first.json','synthetic-password-2026',include_history=False)
   with patch('scripts.collect_pages.AuroraPortalAdapter',Expired):second=collect(Path(tmp)/'second.json','synthetic-password-2026',first,False)
   self.assertEqual(second['sync']['status'],'reauth_required');self.assertEqual(second['sync']['last_success'],first['sync']['last_success']);self.assertEqual(second['aurora_power'],first['aurora_power']);self.assertEqual(decrypt(json.loads((Path(tmp)/'second.json').read_text()),'synthetic-password-2026'),second)
