import os
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import httpx
from polyimmo.aurora import AuroraPortalAdapter,LOCAL,parsed,stamp,ENERGY,POWER
from polyimmo.collector import RateLimited


class AuroraAdapterTests(unittest.TestCase):
    def test_wrong_portal_dst_end_is_replaced_by_an_exact_25_hour_aggregate(self):
        adapter=AuroraPortalAdapter(clock=lambda:datetime(2026,10,27,tzinfo=timezone.utc))
        calls=[]
        def get(path,params):
            calls.append(params)
            if params['agp']=='Day':return [dict(value=100,units='kilowatt-hours',start='2026-10-24T22:00:00Z',end='2026-10-25T22:00:00Z')]
            return [dict(value=109.284,units='kilowatt-hours',start='2026-10-24T22:00:00Z',end='2026-10-25T23:00:00Z')]
        adapter._get=get
        try:points,report=adapter.daily_energy(datetime(2026,10,25,tzinfo=LOCAL),datetime(2026,10,26,tzinfo=LOCAL))
        finally:adapter.close()
        self.assertEqual(points[0].interval_seconds,90000)
        self.assertEqual(points[0].value,109.284)
        self.assertEqual(report['corrected_days'],['2026-10-25'])
        self.assertEqual(calls[1]['edt'],'2026-10-25T23:00:00.000Z')

    def test_unavailable_exact_dst_day_is_not_normalized_or_filled_with_zero(self):
        adapter=AuroraPortalAdapter(clock=lambda:datetime(2026,10,27,tzinfo=timezone.utc))
        adapter._get=lambda path,params:[dict(value=100,units='kilowatt-hours',start='2026-10-24T22:00:00Z',end='2026-10-25T22:00:00Z')] if params['agp']=='Day' else []
        try:
            points,report=adapter.daily_energy(datetime(2026,10,25,tzinfo=LOCAL),datetime(2026,10,26,tzinfo=LOCAL),allow_missing=True)
            self.assertEqual(points,[]);self.assertEqual(report['missing_days'],['2026-10-25'])
            with self.assertRaises(ValueError):adapter.daily_energy(datetime(2026,10,25,tzinfo=LOCAL),datetime(2026,10,26,tzinfo=LOCAL))
        finally:adapter.close()

    def test_portal_schema_units_dst_missing_future_and_reauthentication(self):
        now=datetime(2026,10,27,11,5,tzinfo=timezone.utc)
        login_count=0;first_energy=True;methods=[]
        def response(request):
            nonlocal login_count,first_energy
            methods.append(request.method)
            if request.url.path=='/ums/v1/login':
                login_count+=1
                return httpx.Response(200,json={'token':'synthetic-session'})
            q=dict(request.url.params)
            if request.url.path==ENERGY:
                if first_energy:
                    first_energy=False
                    return httpx.Response(401,json={'error':'synthetic-expired-session'})
                if q['agp']=='Day':
                    a=parsed(q['sdt']).astimezone(LOCAL).replace(microsecond=0)
                    return httpx.Response(200,json=[dict(value=10.5,units='kilowatt-hours',start=stamp(a+timedelta(days=d)),end=stamp(a+timedelta(days=d+1))) for d in range(7)])
                return httpx.Response(200,json=[dict(value=7.25,units='kilowatt-hours',start=q['sdt'],end=q['edt'])])
            if request.url.path==POWER:
                a=parsed(q['sdt'])
                return httpx.Response(200,json=[
                    dict(value=-12.5,units='watts',start=stamp(a),end=stamp(a+timedelta(minutes=15))),
                    dict(start=stamp(a+timedelta(minutes=15)),end=stamp(a+timedelta(minutes=30))),
                    dict(value=2000,units='watts',start=stamp(now-timedelta(minutes=5)),end=stamp(now+timedelta(minutes=10))),
                    dict(start=stamp(now+timedelta(hours=1)),end=stamp(now+timedelta(hours=2)))])
            raise AssertionError('unexpected route')
        with patch.dict(os.environ,{'AURORA_LOGIN':'synthetic-login','AURORA_PASSWORD':'synthetic-password'}):
            adapter=AuroraPortalAdapter(httpx.Client(transport=httpx.MockTransport(response)),clock=lambda:now)
            try:batch=adapter.fetch()
            finally:adapter.close()
        self.assertEqual(login_count,2)
        self.assertEqual(set(methods),{'GET'})
        energy=[p for p in batch.points if p.metric=='production_interval']
        power=[p for p in batch.points if p.metric=='power']
        self.assertEqual(len(energy),7)
        self.assertIn(90000,[p.interval_seconds for p in energy])
        self.assertEqual(len(power),1)
        self.assertEqual(power[0].value,-0.0125)
        self.assertEqual(batch.summary['power_missing_closed_intervals'],1)
        self.assertTrue(all(p.normalized() for p in batch.points))

    def test_rate_limit_is_honored_without_another_http_request(self):
        calls=[]
        def response(request):
            calls.append(request.url.path)
            return httpx.Response(429,headers={'Retry-After':'7200'})
        adapter=AuroraPortalAdapter(httpx.Client(transport=httpx.MockTransport(response)))
        try:
            with self.assertRaises(RateLimited) as first:adapter._send('/ums/v1/login')
            self.assertEqual(first.exception.retry_after,7200)
            with self.assertRaises(RateLimited):adapter._send('/ums/v1/login')
            self.assertEqual(len(calls),1)
        finally:adapter.close()


if __name__=='__main__':unittest.main()
