"""Monthly/quarterly GRD and bank entry, with revisions and overlap checks."""
import calendar
import hashlib
import json
import uuid
from datetime import date,datetime,timezone
from decimal import Decimal
from typing import Annotated,Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .db import connect
from .scenarios import mutation_guard

router=APIRouter()
Money=Annotated[Decimal,Field(ge=0,le=10000000,max_digits=12,decimal_places=2)]
Energy=Annotated[Decimal,Field(ge=0,le=100000000,max_digits=14,decimal_places=5)]
def today():return datetime.now(ZoneInfo('Europe/Zurich')).date()
def now():return datetime.now(timezone.utc).isoformat()

class Reading(BaseModel):
    model_config=ConfigDict(extra='forbid')
    year:int=Field(ge=2000,le=2200)
    period_kind:Literal['month','quarter']='month'
    month:int|None=Field(default=None,ge=1,le=12)
    quarter:int|None=Field(default=None,ge=1,le=4)
    source:Literal['GRD','bank','manual']='GRD'
    energy_mode:Literal['split','total','unknown']='unknown'
    high_kwh:Energy|None=None
    low_kwh:Energy|None=None
    total_kwh:Energy|None=None
    period_complete:bool=False
    expected_chf:Money|None=None
    received_chf:Money|None=None
    other_chf:Money|None=None
    payment_status:Literal['unknown','unpaid','partial','paid']='unknown'
    payment_date:date|None=None
    grd_reference:str=Field(default='',max_length=120)
    bank_reference:str=Field(default='',max_length=120)
    note:str=Field(default='',max_length=1500)

    @model_validator(mode='after')
    def coherent(self):
        if self.period_kind=='month':
            if self.month is None:raise ValueError('Le mois est requis')
            derived=(self.month-1)//3+1
            if self.quarter is not None and self.quarter!=derived:raise ValueError('Mois et trimestre incohérents')
            self.quarter=derived
        elif self.quarter is None:raise ValueError('Le trimestre est requis')
        if self.energy_mode=='split' and (self.high_kwh is None or self.low_kwh is None):raise ValueError('Renseignez les deux tarifs ou choisissez le volume total')
        if self.energy_mode=='total' and self.total_kwh is None:raise ValueError('Le volume total est requis')
        if self.energy_mode=='unknown' and self.period_complete:raise ValueError('Un relevé complet doit préciser son volume')
        if self.payment_status in ('paid','partial') and self.received_chf is None:raise ValueError('Le montant encaissé est requis')
        if self.payment_status=='unknown' and self.received_chf is not None:raise ValueError('Précisez le statut de l’encaissement')
        if self.payment_status=='unpaid' and self.received_chf not in (None,Decimal(0)):raise ValueError('Un paiement en attente ne peut pas avoir un encaissement positif')
        if self.payment_date and self.payment_date>today():raise ValueError('Une date bancaire future ne peut pas être un encaissement réalisé')
        return self

class Expense(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expense_date:date
    category:Literal['maintenance','insurance','cleaning','grid_fees','other']='other'
    amount_chf:Money
    label:str=Field(min_length=1,max_length=120)
    reference:str=Field(default='',max_length=120)
    note:str=Field(default='',max_length=1500)

def basis(db):
    row=db.execute("SELECT value FROM settings WHERE key='active_excel'").fetchone()
    if not row:raise HTTPException(409,'Importez d’abord le classeur de référence')
    snapshot=json.loads(db.execute('SELECT payload FROM snapshots WHERE source_id=?',(row[0],)).fetchone()[0])
    return row[0],snapshot

def prepared_reading(body):
    month=body.month if body.period_kind=='month' else (body.quarter-1)*3+1
    end_month=month if body.period_kind=='month' else month+2
    first=date(body.year,month,1);last=date(body.year,end_month,calendar.monthrange(body.year,end_month)[1])
    if first>today():raise HTTPException(422,'Les relevés réalisés ne peuvent pas concerner une période future')
    if body.period_complete and last>today():raise HTTPException(422,'Une période non terminée doit rester partielle')
    data=body.model_dump(mode='json');data['period_start']=first.isoformat();data['period_end']=last.isoformat()
    data['energy_kwh']=str(body.high_kwh+body.low_kwh) if body.energy_mode=='split' else str(body.total_kwh) if body.energy_mode=='total' else None
    if body.energy_mode!='split':data['high_kwh']=None;data['low_kwh']=None
    if body.energy_mode!='total':data['total_kwh']=None
    if body.payment_status=='unpaid':data['received_chf']='0'
    return data

def validate_overlap(db,identity,snapshot,data,exclude=None):
    last=snapshot['assumptions'].get('E14')
    if isinstance(last,(int,float)) and data['year']*10+data['quarter']<=last:raise HTTPException(409,'Cette période appartient à l’historique Excel. N’ajoutez pas un doublon ; corrigez la source séparément.')
    hit=db.execute('SELECT id FROM manual_records WHERE source_id=? AND deleted_at IS NULL AND period_start<=? AND period_end>=? AND id!=?',
                   (identity,data['period_end'],data['period_start'],exclude or '')).fetchone()
    if hit:raise HTTPException(409,'Un relevé couvre déjà cette période. Complétez le relevé existant, notamment pour la banque.')

def pack(row):
    result=json.loads(row['payload']);result.update(id=row['id'],created_at=row['created_at'],updated_at=row['updated_at'],deleted_at=row['deleted_at'])
    return result

def revision(db,kind,rid,action,old,new):
    db.execute('INSERT INTO financial_revisions (record_type,record_id,action,old_payload,new_payload,changed_at) VALUES (?,?,?,?,?,?)',(kind,rid,action,old,new,now()))

@router.get('/api/entries')
def entries(include_archived:bool=False):
    db=connect()
    try:
        identity,snapshot=basis(db)
        condition='' if include_archived else ' AND deleted_at IS NULL'
        records=[pack(r) for r in db.execute('SELECT * FROM manual_records WHERE source_id=?'+condition+' ORDER BY period_start DESC,created_at DESC',(identity,))]
        expenses=[pack(r) for r in db.execute('SELECT * FROM manual_expenses WHERE source_id=?'+condition+' ORDER BY expense_date DESC,created_at DESC',(identity,))]
        return dict(records=records,expenses=expenses,locked_until=snapshot['assumptions'].get('E14'))
    finally:db.close()

@router.post('/api/entries',status_code=201)
@router.put('/api/entries/{rid}')
def save_reading(body:Reading,request:Request,rid:str|None=None):
    mutation_guard(request);data=prepared_reading(body);db=connect()
    try:
        identity,snapshot=basis(db);existing=db.execute('SELECT * FROM manual_records WHERE id=? AND source_id=? AND deleted_at IS NULL',(rid,identity)).fetchone() if rid else None
        if rid and not existing:raise HTTPException(404,'Relevé inconnu')
        payload=json.dumps(data,ensure_ascii=False,sort_keys=True);timestamp=now()
        with db:
            # Acquire the write lock before checking overlaps, including concurrent submissions.
            db.execute('UPDATE settings SET value=value WHERE key=?',('active_excel',))
            validate_overlap(db,identity,snapshot,data,rid)
            if existing:
                db.execute('UPDATE manual_records SET period_start=?,period_end=?,payload=?,updated_at=? WHERE id=?',(data['period_start'],data['period_end'],payload,timestamp,rid))
                revision(db,'reading',rid,'update',existing['payload'],payload)
            else:
                rid=uuid.uuid4().hex;db.execute('INSERT INTO manual_records VALUES (?,?,?,?,?,?,?,NULL)',(rid,identity,data['period_start'],data['period_end'],payload,timestamp,timestamp));revision(db,'reading',rid,'create',None,payload)
        return pack(db.execute('SELECT * FROM manual_records WHERE id=?',(rid,)).fetchone())
    finally:db.close()

@router.post('/api/expenses',status_code=201)
@router.put('/api/expenses/{rid}')
def save_expense(body:Expense,request:Request,rid:str|None=None):
    mutation_guard(request)
    if body.expense_date>today():raise HTTPException(422,'Une charge future appartient à la projection, pas aux charges réalisées')
    db=connect()
    try:
        identity,snapshot=basis(db);data=body.model_dump(mode='json');payload=json.dumps(data,ensure_ascii=False,sort_keys=True);fingerprint=hashlib.sha256(payload.encode()).hexdigest();timestamp=now()
        existing=db.execute('SELECT * FROM manual_expenses WHERE id=? AND source_id=? AND deleted_at IS NULL',(rid,identity)).fetchone() if rid else None
        if rid and not existing:raise HTTPException(404,'Charge inconnue')
        if not body.label.strip():raise HTTPException(422,'Le libellé est requis')
        with db:
            db.execute('UPDATE settings SET value=value WHERE key=?',('active_excel',))
            if db.execute('SELECT 1 FROM manual_expenses WHERE source_id=? AND fingerprint=? AND deleted_at IS NULL AND id!=?',(identity,fingerprint,rid or '')).fetchone():raise HTTPException(409,'Cette charge est déjà enregistrée')
            if existing:
                db.execute('UPDATE manual_expenses SET expense_date=?,fingerprint=?,payload=?,updated_at=? WHERE id=?',(body.expense_date.isoformat(),fingerprint,payload,timestamp,rid));revision(db,'expense',rid,'update',existing['payload'],payload)
            else:
                rid=uuid.uuid4().hex;db.execute('INSERT INTO manual_expenses VALUES (?,?,?,?,?,?,?,NULL)',(rid,identity,body.expense_date.isoformat(),fingerprint,payload,timestamp,timestamp));revision(db,'expense',rid,'create',None,payload)
        return pack(db.execute('SELECT * FROM manual_expenses WHERE id=?',(rid,)).fetchone())
    finally:db.close()

@router.delete('/api/entries/{rid}')
@router.delete('/api/expenses/{rid}')
def archive(rid:str,request:Request):
    mutation_guard(request);kind='expense' if request.url.path.startswith('/api/expenses') else 'reading';table='manual_expenses' if kind=='expense' else 'manual_records';db=connect()
    try:
        identity,_=basis(db);row=db.execute(f'SELECT * FROM {table} WHERE id=? AND source_id=? AND deleted_at IS NULL',(rid,identity)).fetchone()
        if not row:raise HTTPException(404,'Élément inconnu')
        with db:db.execute(f'UPDATE {table} SET deleted_at=?,updated_at=? WHERE id=?',(now(),now(),rid));revision(db,kind,rid,'archive',row['payload'],None)
        return {'archived':True}
    finally:db.close()

@router.post('/api/entries/{rid}/restore')
@router.post('/api/expenses/{rid}/restore')
def restore(rid:str,request:Request):
    mutation_guard(request);kind='expense' if request.url.path.startswith('/api/expenses') else 'reading';table='manual_expenses' if kind=='expense' else 'manual_records';db=connect()
    try:
        identity,snapshot=basis(db)
        with db:
            db.execute('UPDATE settings SET value=value WHERE key=?',('active_excel',))
            row=db.execute(f'SELECT * FROM {table} WHERE id=? AND source_id=? AND deleted_at IS NOT NULL',(rid,identity)).fetchone()
            if not row:raise HTTPException(404,'Élément archivé inconnu')
            if kind=='reading':validate_overlap(db,identity,snapshot,json.loads(row['payload']),rid)
            elif db.execute('SELECT 1 FROM manual_expenses WHERE source_id=? AND fingerprint=? AND deleted_at IS NULL',(identity,row['fingerprint'])).fetchone():raise HTTPException(409,'Une charge identique est déjà active')
            db.execute(f'UPDATE {table} SET deleted_at=NULL,updated_at=? WHERE id=?',(now(),rid));revision(db,kind,rid,'restore',None,row['payload'])
        return {'restored':True}
    finally:db.close()
