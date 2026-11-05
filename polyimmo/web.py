"""Private dashboard and financial entry. Bind to loopback until an auth gateway is installed."""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from .db import connect
from .scenarios import router as scenario_router
from .ledger import router as ledger_router
from .financials import financial_overlay

app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
app.include_router(scenario_router)
app.include_router(ledger_router)
STATIC = Path(__file__).parent/'static'


@app.middleware('http')
async def secure_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    return response


@app.get('/healthz')
def health():
    db = connect()
    try:
        db.execute('SELECT 1').fetchone()
        validated=bool(db.execute('SELECT 1 FROM portal_latest WHERE plant_id=?',('35546755',)).fetchone())
        return {'status':'ok','aurora_validated':validated}
    finally:
        db.close()


@app.get('/api/dashboard')
def dashboard():
    db = connect()
    try:
        source = db.execute("SELECT value FROM settings WHERE key='active_excel'").fetchone()
        if not source:
            return JSONResponse({'status':'missing','message':'Aucun classeur importé.'},status_code=503)
        snapshot = json.loads(db.execute('SELECT payload FROM snapshots WHERE source_id=?',(source[0],)).fetchone()[0])
        logo=next((name for name in ('logo-polyimmo.svg','logo-polyimmo.png') if (STATIC/name).is_file()),None)
        snapshot['branding']={'logo_url':'/static/'+logo if logo else None}
        last = db.execute('SELECT status,error_code,finished_at FROM sync_runs ORDER BY id DESC LIMIT 1').fetchone()
        success = db.execute("SELECT finished_at FROM sync_runs WHERE status='success' ORDER BY id DESC LIMIT 1").fetchone()
        portal=db.execute('SELECT payload FROM portal_latest WHERE plant_id=?',('35546755',)).fetchone()
        snapshot['aurora']=json.loads(portal[0]) if portal else None
        history=db.execute('SELECT from_day,to_day,status,finished_at,payload FROM history_imports ORDER BY id DESC LIMIT 1').fetchone()
        snapshot['history']=dict(from_day=history['from_day'],to_day=history['to_day'],status=history['status'],finished_at=history['finished_at'],report=json.loads(history['payload']) if history['payload'] else None) if history else None
        measured=db.execute('SELECT metric,start_utc,interval_seconds,value,unit FROM measurements WHERE plant_id=? ORDER BY start_utc',('35546755',)).fetchall()
        snapshot['aurora_daily']=[dict(r) for r in measured if r['metric']=='production_interval']
        snapshot['aurora_power']=[dict(r) for r in measured if r['metric']=='power']
        point=max((datetime.fromisoformat(r['start_utc'])+timedelta(seconds=r['interval_seconds']) for r in measured),default=None)
        stale_after=int(os.environ.get('POLYIMMO_STALE_SECONDS','10800'))
        current=datetime.now(timezone.utc)
        stale=not success or (current-datetime.fromisoformat(success[0])).total_seconds()>stale_after
        if snapshot['aurora']:
            # Aggregate end is the requested query boundary, not proof of a last sample.
            # Freshness uses the end of an actually returned, closed measurement bucket.
            stale=stale or not point or (current-point).total_seconds()>stale_after
        invoices = db.execute('SELECT row_number,year,quarter,label,high_kwh,low_kwh,revenue_chf,other_chf,note FROM invoices WHERE source_id=? ORDER BY row_number',(source[0],)).fetchall()
        snapshot=financial_overlay(db,snapshot,[dict(row) for row in invoices])
        snapshot['sync'] = dict(validated=bool(portal),status=last['status'] if last else 'not_configured',
                                error_code=last['error_code'] if last else None,
                                last_attempt=last['finished_at'] if last else None,
                                last_success=success[0] if success else None,
                                latest_measurement=point.isoformat() if point else None,
                                stale=bool(stale),stale_after_seconds=stale_after)
        return snapshot
    finally:
        db.close()


@app.get('/')
def index():
    return FileResponse(STATIC/'index.html')


@app.get('/static/{name}')
def asset(name: str):
    if name not in ('app.js','model.js','charts.js','extras.js','entries.js','style.css','favicon.svg','logo-polyimmo.svg','logo-polyimmo.png') or not (STATIC/name).is_file():
        return JSONResponse({'detail':'Not found'},status_code=404)
    return FileResponse(STATIC/name)
