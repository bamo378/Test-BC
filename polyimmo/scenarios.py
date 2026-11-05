"""Validated business scenarios; no portal credentials or settings are accepted."""
import json
import re
import uuid
from datetime import datetime,timezone
from typing import Annotated
from pydantic import BaseModel,ConfigDict,Field,model_validator
from fastapi import APIRouter,HTTPException,Request
from .db import connect
from .financials import quarter_states

router=APIRouter()
Rate=Annotated[float,Field(ge=-1000,le=1000,allow_inf_nan=False)]

class Tariffs(BaseModel):
    model_config=ConfigDict(extra='forbid')
    seasonal:dict[str,Rate]=Field(default_factory=dict,max_length=4)
    overrides:dict[str,Rate]=Field(default_factory=dict,max_length=120)

    @model_validator(mode='after')
    def keys(self):
        if any(k not in ('1','2','3','4') for k in self.seasonal):raise ValueError('Invalid season')
        if any(not re.fullmatch(r'\d{4}-T[1-4]',k) for k in self.overrides):raise ValueError('Invalid quarter')
        return self

class Scenario(BaseModel):
    model_config=ConfigDict(extra='forbid')
    degradation:float=Field(ge=0,le=.2,allow_inf_nan=False)
    price:float=Field(gt=-1,le=1,allow_inf_nan=False)
    expenses:float=Field(ge=0,le=1000000,allow_inf_nan=False)
    inflation:float=Field(ge=0,le=1,allow_inf_nan=False)
    tariffs:Tariffs=Field(default_factory=Tariffs)
    replacementYear:int|None=Field(default=None,ge=2000,le=2200)
    replacementCost:float|None=Field(default=None,ge=0,le=1000000,allow_inf_nan=False)

class SaveScenario(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=80)
    scenario:Scenario

def mutation_guard(request):
    # Cross-origin pages cannot add this header without an explicitly granted CORS preflight.
    if request.headers.get('x-polyimmo-request')!='1':raise HTTPException(403,'Requête non autorisée')
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):raise HTTPException(403,'Origine non autorisée')

def source(db,scenario):
    row=db.execute("SELECT value FROM settings WHERE key='active_excel'").fetchone()
    if not row:raise HTTPException(409,'Classeur de référence indisponible')
    snapshot=json.loads(db.execute('SELECT payload FROM snapshots WHERE source_id=?',(row[0],)).fetchone()[0])
    last=snapshot['assumptions'].get('E14')
    horizon=[r['year'] for r in snapshot['projection'] if isinstance(r.get('year'),int)]
    if not isinstance(last,(int,float)) or not horizon:raise HTTPException(409,'Périodes de projection non disponibles')
    manual=quarter_states(db,row[0])
    for key in scenario.tariffs.overrides:
        year,quarter=key.split('-T');code=int(year)*10+int(quarter)
        if code<=last or int(year) not in horizon or manual.get(key,{}).get('financial_complete'):raise HTTPException(422,'Un tarif spécifique doit concerner un trimestre projeté')
    if scenario.replacementYear is not None and (scenario.replacementYear not in horizon or scenario.replacementYear*10+4<=last):
        raise HTTPException(422,'Le remplacement doit concerner une année projetée')
    return row[0]

def packed(row):
    return dict(id=row['id'],name=row['name'],scenario=json.loads(row['payload']),source_id=row['source_id'],created_at=row['created_at'],updated_at=row['updated_at'])

@router.get('/api/scenarios')
def list_scenarios():
    db=connect()
    try:return [packed(r) for r in db.execute('SELECT * FROM scenarios ORDER BY updated_at DESC')]
    finally:db.close()

@router.post('/api/scenarios',status_code=201)
def save_scenario(body:SaveScenario,request:Request):
    mutation_guard(request);db=connect()
    try:
        identity=source(db,body.scenario)
        if db.execute('SELECT COUNT(*) FROM scenarios').fetchone()[0]>=100:raise HTTPException(409,'Limite de 100 scénarios atteinte')
        name=body.name.strip()
        if not name:raise HTTPException(422,'Le nom est requis')
        sid=uuid.uuid4().hex;now=datetime.now(timezone.utc).isoformat()
        with db:db.execute('INSERT INTO scenarios VALUES (?,?,?,?,?,?)',(sid,name,body.scenario.model_dump_json(),identity,now,now))
        return packed(db.execute('SELECT * FROM scenarios WHERE id=?',(sid,)).fetchone())
    finally:db.close()

@router.delete('/api/scenarios/{sid}')
def delete_scenario(sid:str,request:Request):
    mutation_guard(request);db=connect()
    try:
        with db:deleted=db.execute('DELETE FROM scenarios WHERE id=?',(sid,)).rowcount
        if not deleted:raise HTTPException(404,'Scénario inconnu')
        return {'deleted':True}
    finally:db.close()
