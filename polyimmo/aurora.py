"""Read-only portal adapter, verified against the dashboard CSV on 2026-11-05.

Uses the portal's normal login/session, not a FIMER API key. Credentials and
cookies remain in process memory; only measured values leave this adapter.
"""
import math
import os
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import httpx
from .collector import AuthExpired, Collection, NotConfigured, Point, RateLimited

BASE='https://www.auroravision.net'
ENERGY='/telemetry/v1/plants/35546755/energy/GenerationEnergy'
POWER='/telemetry/v1/plants/35546755/power/GenerationPower'
LOCAL=ZoneInfo('Europe/Zurich')
# Exact lower bound observed in the portal's lifetime request, NOT the physical commissioning date.
PORTAL_LIFETIME_START='2023-06-18T12:00:00.000Z'


def stamp(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')


def parsed(value):
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timezone_missing')
    return dt.astimezone(timezone.utc)


def value(row,unit,allow_negative=False):
    if row.get('units')!=unit or isinstance(row.get('value'),bool):
        raise ValueError('unexpected_unit')
    n=float(row['value'])
    if not math.isfinite(n) or (n<0 and not allow_negative):
        raise ValueError('invalid_value')
    return n


class AuroraPortalAdapter:
    def __init__(self,client=None,clock=None):
        self.client=client or httpx.Client(timeout=25,follow_redirects=False)
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.authenticated=False
        self.not_before=None

    def close(self):
        self.client.close()

    def _send(self,path,**kwargs):
        # Fixed HTTPS host; no redirects to an unvalidated identity or endpoint.
        now=self.clock().astimezone(timezone.utc)
        if self.not_before and now<self.not_before:
            raise RateLimited((self.not_before-now).total_seconds())
        try:
            r=self.client.get(BASE+path,**kwargs)
        except httpx.RequestError:
            raise OSError('portal_transport_error') from None
        if r.status_code==429 or (r.status_code==503 and r.headers.get('retry-after')):
            header=r.headers.get('retry-after','60')
            try:
                delay=float(header)
            except ValueError:
                try: delay=(parsedate_to_datetime(header)-now).total_seconds()
                except (TypeError,ValueError):delay=60
            delay=max(1,delay) if math.isfinite(delay) else 60
            self.not_before=now+timedelta(seconds=delay)
            raise RateLimited(delay)
        if 500<=r.status_code<600:
            raise OSError('portal_temporarily_unavailable')
        return r

    def _login(self):
        username=os.environ.get('AURORA_LOGIN')
        password=os.environ.get('AURORA_PASSWORD')
        if not username or not password:
            raise NotConfigured()
        r=self._send('/ums/v1/login',params={'setCookie':'true'},
                     auth=(username,password),headers={'Accept-Language':'fr'})
        if r.status_code!=200:
            raise AuthExpired()
        # EULA/password changes must never be accepted or performed automatically.
        data=r.json()
        if not isinstance(data,dict) or not isinstance(data.get('token'),str):
            raise AuthExpired()
        self.authenticated=True

    def _get(self,path,params):
        if not self.authenticated:
            self._login()
        r=self._send(path,params=params)
        if r.status_code in (301,302,303,307,308,401,403) or 'json' not in r.headers.get('content-type','').lower():
            # One normal reauthentication per request, no bypass and no retry loop on bad credentials.
            self.authenticated=False
            self._login()
            r=self._send(path,params=params)
        if r.status_code!=200 or 'json' not in r.headers.get('content-type','').lower():
            raise AuthExpired()
        data=r.json()
        if not isinstance(data,list):
            raise ValueError('invalid_portal_response')
        return data

    def daily_energy(self,start,end,allow_missing=False):
        """Read local calendar days; verify DST days with their exact portal aggregate."""
        start=start.astimezone(LOCAL);end=end.astimezone(LOCAL)
        rows=self._get(ENERGY,dict(agp='Day',afx='Delta',sdt=stamp(start+timedelta(milliseconds=999)),edt=stamp(end-timedelta(milliseconds=1))))
        by_date={};corrected=[];rejected=[]
        for row in rows:
            if row.get('value') is None:
                continue
            a=parsed(row['start']);local=a.astimezone(LOCAL)
            if a<start.astimezone(timezone.utc) or a>=end.astimezone(timezone.utc) or local.time()!=datetime.min.time():
                raise ValueError('unexpected_daily_alignment')
            expected_end=(local+timedelta(days=1)).astimezone(timezone.utc)
            if expected_end>end.astimezone(timezone.utc):raise ValueError('unexpected_energy_bounds')
            if parsed(row['end'])!=expected_end:
                exact=self._get(ENERGY,dict(agp='All',afx='Delta',sdt=stamp(a),edt=stamp(expected_end)))
                if len(exact)!=1 or exact[0].get('value') is None:
                    rejected.append(dict(day=local.date().isoformat(),reason='exact_day_unavailable'));continue
                row=exact[0]
                if parsed(row['start'])!=a or parsed(row['end'])!=expected_end:raise ValueError('unverified_daily_bounds')
                corrected.append(local.date().isoformat())
            try:n=value(row,'kilowatt-hours')
            except ValueError:
                if not allow_missing:raise
                rejected.append(dict(day=local.date().isoformat(),reason='invalid_energy_value'));continue
            day=local.date().isoformat()
            if day in by_date:raise ValueError('duplicate_daily_response')
            by_date[day]=Point('35546755','plant','production_interval',a.isoformat(),int((expected_end-a).total_seconds()),n,'kWh')
        expected={(start.date()+timedelta(days=d)).isoformat() for d in range((end.date()-start.date()).days)}
        missing=sorted(expected-set(by_date))
        if missing and not allow_missing:raise ValueError('daily_coverage_incomplete')
        return list(by_date.values()),dict(requested_days=len(expected),missing_days=missing,corrected_days=corrected,rejected=rejected)

    def fetch(self):
        now=self.clock().astimezone(timezone.utc)
        midnight=now.astimezone(LOCAL).replace(hour=0,minute=0,second=0,microsecond=0)
        start=midnight-timedelta(days=7)
        points,daily_report=self.daily_energy(start,midnight)
        periods=dict(today=midnight,week=midnight-timedelta(days=midnight.weekday()),month=midnight.replace(day=1))
        summary=dict(validated=True,plant_id='35546755',timezone='Europe/Zurich',fetched_at=stamp(now),
                     lifetime_lower_bound=PORTAL_LIFETIME_START,day_end=stamp(midnight+timedelta(days=1)),corrected_daily_bounds=daily_report['corrected_days'],totals={})
        periods['lifetime']=parsed(PORTAL_LIFETIME_START)
        for name,a in periods.items():
            data=self._get(ENERGY,dict(agp='All',afx='Delta',sdt=stamp(a),edt=stamp(now)))
            if not data or data[0].get('value') is None:
                summary['totals'][name]=None
                continue
            if len(data)!=1:
                raise ValueError('ambiguous_aggregate')
            row=data[0];end=parsed(row['end'])
            if parsed(row['start'])>end or end>now+timedelta(minutes=1):
                raise ValueError('invalid_aggregate_bounds')
            summary['totals'][name]=dict(kwh=value(row,'kilowatt-hours'),start=row['start'],end=row['end'],partial=True)
        power=self._get(POWER,dict(agp='Min15',afx='Avg',sdt=stamp(midnight-timedelta(days=1)),edt=stamp(midnight+timedelta(days=1)-timedelta(milliseconds=1))))
        missing_past=0
        for row in power:
            a,b=parsed(row['start']),parsed(row['end'])
            if b>now:
                continue  # Future and in-progress buckets are never imported as complete.
            if a<(midnight-timedelta(days=1)).astimezone(timezone.utc) or b<=a or (b-a).total_seconds()!=900:
                raise ValueError('invalid_power_bounds')
            if row.get('value') is None:
                missing_past+=1
                continue  # Missing values remain missing, never zero.
            points.append(Point('35546755','plant','power',a.isoformat(),900,value(row,'watts',allow_negative=True)/1000,'kW'))
        summary['power_missing_closed_intervals']=missing_past
        return Collection(points,summary)
