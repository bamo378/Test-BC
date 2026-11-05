"""Read-only collection, atomic imports, retries and controlled error reporting.

The Aurora adapter follows the portal requests verified against its CSV export.
"""
import math
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from .db import connect


class AuthExpired(Exception):
    pass


class NotConfigured(Exception):
    pass


class RateLimited(OSError):
    def __init__(self,retry_after):
        self.retry_after=retry_after


@dataclass
class Collection:
    points: list['Point']
    summary: dict


class PortalAdapter(Protocol):
    def fetch(self) -> list['Point']: ...


@dataclass(frozen=True)
class Point:
    plant_id: str
    device_id: str
    metric: str
    start_utc: str
    interval_seconds: int
    value: float
    unit: str

    def normalized(self):
        units = {'production_interval':'kWh','production_counter':'kWh','power':'kW'}
        if self.plant_id != '35546755' or not self.device_id:
            raise ValueError('unexpected_scope')
        if units.get(self.metric) != self.unit:
            raise ValueError('invalid_metric_or_unit')
        if not math.isfinite(self.value) or (self.value < 0 and self.metric != 'power'):
            raise ValueError('invalid_value')
        if not isinstance(self.interval_seconds,int) or self.interval_seconds < 0:
            raise ValueError('invalid_interval')
        if self.metric == 'production_interval' and self.interval_seconds == 0:
            raise ValueError('missing_interval')
        stamp = datetime.fromisoformat(self.start_utc)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('timezone_required')
        stamp = stamp.astimezone(timezone.utc).isoformat()
        return (self.plant_id,self.device_id,self.metric,stamp,self.interval_seconds,float(self.value),self.unit)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def ingest(db, points):
    """Validate everything before a single atomic upsert. Never sum mixed resolutions."""
    batch = {}
    for point in points:
        row = point.normalized()
        key = row[:5]
        if key in batch and batch[key] != row:
            raise ValueError('conflicting_duplicate')
        batch[key] = row
    if not batch:
        raise ValueError('empty_response')
    stamp = utcnow()
    with db:
        for row in batch.values():
            old = db.execute('SELECT value,unit FROM measurements WHERE plant_id=? AND device_id=? AND metric=? AND start_utc=? AND interval_seconds=?',row[:5]).fetchone()
            if old and old['unit'] != row[6]:
                raise ValueError('unit_changed')
            if old and old['value'] != row[5]:
                db.execute('INSERT INTO measurement_revisions (plant_id,device_id,metric,start_utc,interval_seconds,old_value,new_value,changed_at) VALUES (?,?,?,?,?,?,?,?)',(*row[:5],old['value'],row[5],stamp))
            db.execute('INSERT INTO measurements VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(plant_id,device_id,metric,start_utc,interval_seconds) DO UPDATE SET value=excluded.value,retrieved_at=excluded.retrieved_at',(*row,stamp))
    return len(batch)


def run(adapter, db, sleeper=time.sleep):
    started = utcnow()
    with db:
        run_id = db.execute('INSERT INTO sync_runs (started_at,status) VALUES (?,?)',(started,'running')).lastrowid
    status, code, count = 'failed', None, 0
    for attempt in range(3):
        try:
            result = adapter.fetch()
            count = ingest(db,result.points if isinstance(result,Collection) else result)
            if isinstance(result,Collection):
                with db:
                    db.execute('INSERT INTO portal_latest VALUES (?,?,?) ON CONFLICT(plant_id) DO UPDATE SET fetched_at=excluded.fetched_at,payload=excluded.payload',
                               ('35546755',utcnow(),json.dumps(result.summary)))
            status = 'success'
            break
        except AuthExpired:
            status,code = 'reauth_required','session_expired'
            break
        except NotConfigured:
            status,code = 'blocked','credentials_unavailable'
            break
        except (OSError,TimeoutError) as e:
            code = 'rate_limited' if isinstance(e,RateLimited) else 'network_error'
            delay=getattr(e,'retry_after',2**attempt)
            if delay>60:
                break
            if attempt < 2:
                sleeper(delay)
        except Exception:
            # Exception text may contain URLs, headers or credentials: never retain it.
            code = 'invalid_response'
            break
    with db:
        db.execute('UPDATE sync_runs SET finished_at=?,status=?,error_code=?,points=? WHERE id=?',
                   (utcnow(),status,None if status=='success' else code,count,run_id))
    return status


if __name__ == '__main__':
    import argparse
    import fcntl
    import os
    from pathlib import Path
    from .aurora import AuroraPortalAdapter
    from .collector import run as collect_run
    parser=argparse.ArgumentParser(description='Collecte en lecture seule du portail Aurora Vision')
    parser.add_argument('--loop',action='store_true')
    parser.add_argument('--interval',type=int,default=3600)
    args=parser.parse_args()
    if args.interval<300:
        parser.error('intervalle minimum : 300 secondes')
    lock_path=Path(os.environ.get('POLYIMMO_DB','.local/polyimmo.sqlite3')).with_suffix('.collector.lock')
    lock_path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(lock_path,os.O_WRONLY|os.O_CREAT,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print('Un collecteur est déjà actif.')
        raise SystemExit(3)
    adapter=AuroraPortalAdapter()
    try:
        while True:
            db=connect()
            try:
                state=collect_run(adapter,db)
            finally:
                db.close()
            print(utcnow(),'collecte',state,flush=True)
            if not args.loop:
                raise SystemExit(0 if state=='success' else 2)
            time.sleep(args.interval)
    finally:
        adapter.close()
        os.close(fd)
