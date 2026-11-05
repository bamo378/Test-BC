"""Run on GitHub's server, publish ONLY encrypted measurements, never credentials."""
import argparse,json,os,re,sys,tempfile,urllib.error,urllib.request
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polyimmo.aurora import AuroraPortalAdapter,LOCAL
from polyimmo.collector import Point,ingest,run,utcnow
from polyimmo.db import connect
from polyimmo.history import backfill
from polyimmo.private_envelope import encrypt,decrypt

def previous_envelope():
    repo=os.environ.get('GITHUB_REPOSITORY','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Repository is required')
    owner,name=repo.split('/');url=f'https://{owner}.github.io/{name}/data/aurora.enc.json'
    try:
        with urllib.request.urlopen(url,timeout=30) as response:raw=response.read(10000001)
    except urllib.error.HTTPError as e:
        if e.code==404:return None
        raise OSError('Previous encrypted state unavailable') from None
    if len(raw)>10000000:raise ValueError('Encrypted state too large')
    return json.loads(raw)

def previous_state(password,local=None):
    envelope=json.loads(Path(local).read_text()) if local else previous_envelope()
    if envelope is None:return None
    value=decrypt(envelope,password)
    if value.get('format')!='polyimmo-aurora-v1':raise ValueError('Unexpected measurement snapshot')
    return value

def collect(output,password,previous=None,include_history=True):
    with tempfile.TemporaryDirectory(prefix='polyimmo-collector-') as tmp:
        db=connect(Path(tmp)/'private.sqlite3');ad=AuroraPortalAdapter()
        try:
            if previous:
                points=[Point('35546755','plant',metric,r['start_utc'],r['interval_seconds'],r['value'],r['unit']) for field,metric in [('aurora_daily','production_interval'),('aurora_power','power')] for r in previous.get(field,[])]
                if points:ingest(db,points)
                if previous.get('aurora'):
                    with db:db.execute('INSERT INTO portal_latest VALUES (?,?,?)',('35546755',previous['aurora']['fetched_at'],json.dumps(previous['aurora'])))
                success=previous.get('sync',{}).get('last_success')
                if success:
                    with db:db.execute('INSERT INTO sync_runs (started_at,finished_at,status) VALUES (?,?,?)',(success,success,'success'))
            status=run(ad,db);history=previous.get('history') if previous else None
            if status=='success' and not history and include_history:
                first=date(2023,1,1);last=ad.clock().astimezone(LOCAL).date()-timedelta(days=1)
                try:
                    hs,report=backfill(ad,db,first,last);history=dict(from_day=first.isoformat(),to_day=last.isoformat(),status=hs,finished_at=utcnow(),report=report)
                except Exception:history=dict(from_day=first.isoformat(),to_day=last.isoformat(),status='failed',finished_at=utcnow(),report=None)
            cutoff=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
            with db:db.execute("DELETE FROM measurements WHERE metric='power' AND start_utc<?",(cutoff,))
            rows=[dict(r) for r in db.execute('SELECT metric,start_utc,interval_seconds,value,unit FROM measurements ORDER BY start_utc')]
            latest=max((datetime.fromisoformat(r['start_utc'])+timedelta(seconds=r['interval_seconds']) for r in rows),default=None)
            last=db.execute('SELECT status,error_code,finished_at FROM sync_runs ORDER BY id DESC LIMIT 1').fetchone();success=db.execute("SELECT finished_at FROM sync_runs WHERE status='success' ORDER BY id DESC LIMIT 1").fetchone();portal=db.execute('SELECT payload FROM portal_latest WHERE plant_id=?',('35546755',)).fetchone()
            value=dict(format='polyimmo-aurora-v1',aurora_daily=[r for r in rows if r['metric']=='production_interval'],aurora_power=[r for r in rows if r['metric']=='power'],aurora=json.loads(portal[0]) if portal else None,history=history,sync=dict(validated=bool(portal),status=last['status'],error_code=last['error_code'],last_attempt=last['finished_at'],last_success=success[0] if success else None,latest_measurement=latest.isoformat() if latest else None,stale=status!='success',stale_after_seconds=10800))
            target=Path(output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(encrypt(value,password)));target.chmod(0o600)
            print('Encrypted measurement snapshot ready. Collection:',status,'daily points:',len(value['aurora_daily']),flush=True)
            return value
        finally:ad.close();db.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='_site/data/aurora.enc.json');p.add_argument('--previous');p.add_argument('--no-history',action='store_true');p.add_argument('--preserve-only',action='store_true');args=p.parse_args()
    try:
        if args.preserve_only:
            envelope=previous_envelope()
            if envelope is not None:
                target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(envelope))
            print('Existing encrypted snapshot preserved, if present.');raise SystemExit(0)
        password=os.environ.get('POLYIMMO_DATA_PASSWORD','');previous=previous_state(password,args.previous)
        collect(args.output,password,previous,not args.no_history)
    except Exception:
        print('Publication stopped: encrypted history, network or secret configuration unavailable. No credential details logged.',flush=True);raise SystemExit(2)
