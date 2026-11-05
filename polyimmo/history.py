"""Controlled read-only backfill. Missing historical values never become zero."""
import argparse
import fcntl
import json
import os
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from .aurora import AuroraPortalAdapter,LOCAL,ENERGY,stamp,value
from .collector import ingest,utcnow
from .db import connect

def backfill(adapter,db,start_day,end_day):
    if end_day>=adapter.clock().astimezone(LOCAL).date() or end_day<start_day:
        raise ValueError('Only completed calendar days can be backfilled')
    with db:run_id=db.execute('INSERT INTO history_imports (started_at,from_day,to_day,status) VALUES (?,?,?,?)',(utcnow(),start_day.isoformat(),end_day.isoformat(),'running')).lastrowid
    summaries=[];current=start_day
    try:
        while current<=end_day:
            stop=min(date(current.year+1,1,1),end_day+timedelta(days=1))
            start=datetime.combine(current,datetime.min.time(),LOCAL);end=datetime.combine(stop,datetime.min.time(),LOCAL)
            points,report=adapter.daily_energy(start,end,allow_missing=True)
            if points:ingest(db,points)
            aggregate=None
            if points:
                rows=adapter._get(ENERGY,dict(agp='All',afx='Delta',sdt=stamp(start),edt=stamp(end)))
                if len(rows)==1 and rows[0].get('value') is not None:aggregate=value(rows[0],'kilowatt-hours')
            total=sum(p.value for p in points)
            verified=not report['missing_days'] and aggregate is not None and abs(total-aggregate)<.01
            summaries.append(dict(year=current.year,from_day=current.isoformat(),to_day=(stop-timedelta(days=1)).isoformat(),
                points=len(points),measured_kwh=total if points else None,aggregate_kwh=aggregate,
                verified_complete=verified,**report))
            current=stop
        status='success' if all(s['verified_complete'] for s in summaries) else 'partial'
        payload=dict(periods=summaries,points=sum(s['points'] for s in summaries),
                     missing_days=sum(len(s['missing_days']) for s in summaries),
                     corrected_days=[d for s in summaries for d in s['corrected_days']])
        with db:db.execute('UPDATE history_imports SET finished_at=?,status=?,payload=? WHERE id=?',(utcnow(),status,json.dumps(payload),run_id))
        return status,payload
    except Exception:
        with db:db.execute('UPDATE history_imports SET finished_at=?,status=?,payload=? WHERE id=?',(utcnow(),'failed',json.dumps({'code':'historical_import_incomplete','completed_periods':summaries}),run_id))
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Reprendre l’historique quotidien Aurora en lecture seule')
    parser.add_argument('--start',type=date.fromisoformat,required=True)
    parser.add_argument('--end',type=date.fromisoformat)
    args=parser.parse_args();ad=AuroraPortalAdapter();db=connect()
    lock=Path(os.environ.get('POLYIMMO_DB','.local/polyimmo.sqlite3')).with_suffix('.history.lock')
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        status,report=backfill(ad,db,args.start,args.end or ad.clock().astimezone(LOCAL).date()-timedelta(days=1))
        print('Historical import:',status,'measured days:',report['points'],'unavailable days:',report['missing_days'],flush=True)
        for period in report['periods']:
            print(period['year'],'measured days',period['points'],'of',period['requested_days'],'energy kWh',period['measured_kwh'],'aggregate check',period['verified_complete'],flush=True)
    except Exception:
        print('Historical import stopped; controlled failure recorded, no credentials logged.',flush=True)
        raise SystemExit(2)
    finally:
        ad.close();db.close();os.close(fd)
