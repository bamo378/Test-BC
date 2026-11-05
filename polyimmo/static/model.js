export const ZONE='Europe/Zurich';
const dayFormat=new Intl.DateTimeFormat('en-CA',{timeZone:ZONE,year:'numeric',month:'2-digit',day:'2-digit'});
export function localDay(value){const parts=Object.fromEntries(dayFormat.formatToParts(new Date(value)).map(p=>[p.type,p.value]));return `${parts.year}-${parts.month}-${parts.day}`;}
export function addDay(day,n){const d=new Date(`${day}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);}
export function localMidnight(day){const [y,m,d]=day.split('-').map(Number),base=Date.UTC(y,m-1,d);let t=base;const f=new Intl.DateTimeFormat('en-GB',{timeZone:ZONE,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});for(let i=0;i<3;i++){const p=Object.fromEntries(f.formatToParts(new Date(t)).map(x=>[x.type,x.value]));t=base-(Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,+p.minute,+p.second)-t);}return t;}
export function seriesFor(data,metric,from,to,resolution){
  if(!from||!to||from>to)return [];
  const source=metric==='power'?data.aurora_power:data.aurora_daily;
  let rows=(source||[]).filter(r=>{const day=localDay(r.start_utc);return day>=from&&day<=to;}).map(r=>({start:Date.parse(r.start_utc),end:Date.parse(r.start_utc)+r.interval_seconds*1000,value:r.value,unit:r.unit,partial:false})).sort((a,b)=>a.start-b.start);
  if(metric==='power'&&resolution==='hour'){
    const groups=new Map();for(const r of rows){const key=Math.floor(r.start/3600000)*3600000;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
    rows=[...groups.entries()].filter(([t,rs])=>rs.length===4&&rs.every((r,i)=>r.start===t+i*900000&&r.end-r.start===900000)).map(([t,rs])=>({start:t,end:t+3600000,value:rs.reduce((n,r)=>n+r.value,0)/4,unit:'kW',partial:false}));
  }
  if(metric==='energy'&&['week','month'].includes(resolution)){
    const groups=new Map();for(const row of rows){let day=localDay(row.start),key=day.slice(0,7);if(resolution==='week'){const weekday=(new Date(day+'T12:00:00Z').getUTCDay()+6)%7;key=addDay(day,-weekday);}if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}
    rows=[...groups.entries()].map(([key,rs])=>{const first=resolution==='week'?key:key+'-01';let next;if(resolution==='week')next=addDay(first,7);else{const d=new Date(first+'T12:00:00Z');d.setUTCMonth(d.getUTCMonth()+1);next=d.toISOString().slice(0,10);}const expected=Math.round((Date.parse(next+'T12:00Z')-Date.parse(first+'T12:00Z'))/86400000);return {start:localMidnight(first),end:localMidnight(next),value:rs.reduce((n,r)=>n+r.value,0),unit:'kWh',partial:rs.length<expected,days:rs.length};});
  }
  return rows;
}
export function financialRows(data,year='all',query=''){
  const normalize=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();const q=normalize(query).trim();
  return (data.invoices||[]).map((r,index)=>({...r,index})).filter(r=>(year==='all'||r.year===Number(year))&&(!q||normalize(`${r.year} T${r.quarter} ${r.label} ${r.note||''}`).includes(q)));
}
export function invoiceEnergy(row){return row.energy_kwh!=null?Number(row.energy_kwh):row.high_kwh==null&&row.low_kwh==null?null:(row.high_kwh??0)+(row.low_kwh??0);}
export function financeSeries(data,year='all'){
  const years=year==='all'?data.years.map(y=>y.year):[Number(year)];const rows=[];
  for(const y of years)for(let q=1;q<=4;q++){const entries=financialRows(data,String(y)).filter(r=>r.quarter===q),partial=!!data.manual_quarters?.[`${y}-T${q}`]&&!data.manual_quarters[`${y}-T${q}`].financial_complete;rows.push({start:Date.UTC(y,(q-1)*3,1),end:Date.UTC(y,q*3,1),value:entries.some(r=>r.revenue_chf!=null)?entries.reduce((n,r)=>n+(r.revenue_chf??0),0):null,partial,unit:'CHF',label:`T${q} ${y}${partial?' · partiel':''}`});}
  return rows;
}
export function irr(flows){
  if(!flows.some(v=>v<0)||!flows.some(v=>v>0))return null;
  const npv=r=>flows.reduce((s,v,i)=>s+v/(1+r)**i,0);let a=-.99,b=10,fa=npv(a),fb=npv(b);
  if(!Number.isFinite(fa)||fa*fb>0)return null;
  for(let i=0;i<120;i++){const m=(a+b)/2,fm=npv(m);if(fa*fm>0){a=m;fa=fm;}else b=m;}return (a+b)/2;
}
export function quarterBases(data){
 const refs=[data.assumptions.E5,data.assumptions.E6];
 return [1,2,3,4].map(q=>{const samples=refs.map(year=>data.invoices.filter(r=>r.year===year&&r.quarter===q));const volumeKnown=samples.every(rows=>rows.some(r=>invoiceEnergy(r)!=null));const salesKnown=samples.every(rows=>rows.some(r=>r.revenue_chf!=null));const kwh=volumeKnown?samples.reduce((sum,rows)=>sum+rows.reduce((n,r)=>n+(invoiceEnergy(r)??0),0),0)/2:null;const sales=salesKnown?samples.reduce((sum,rows)=>sum+rows.reduce((n,r)=>n+(r.revenue_chf??0),0),0)/2:null;return {quarter:q,kwh,sales,rateCt:kwh>0&&sales!=null?sales/kwh*100:null};});
}
export function projectedRate(data,scenario,year,quarter){
 const override=scenario.tariffs?.overrides?.[`${year}-T${quarter}`];
 if(override!=null&&override!=='')return {rateCt:Number(override),source:'Saisie spécifique'};
 const seasonal=scenario.tariffs?.seasonal?.[quarter],base=quarterBases(data)[quarter-1].rateCt;
 const rate=seasonal!=null&&seasonal!==''?Number(seasonal):base;
 return {rateCt:rate==null?null:rate*(1+scenario.price)**(year-data.assumptions.E6),source:seasonal!=null&&seasonal!==''?'Tarif saisonnier + évolution':'Référence financière + évolution'};
}
export function projectScenario(data,scenario){
 const {degradation,price,expenses,inflation}=scenario;
 for(const v of [degradation,price,expenses,inflation])if(!Number.isFinite(v))throw new Error('Hypothèse non numérique');
 if(degradation<0||degradation>=1||price<=-1||expenses<0||inflation<=-1)throw new Error('Hypothèse hors limites');
 const ref2=data.assumptions.E6,last=data.assumptions.E14,cost=data.investment.net,base=quarterBases(data),quarters=[];
 let cumulative=0;
 const years=data.projection.map(original=>{const year=original.year,n=year-ref2;let sales=0,kwh=0;
  for(let q=1;q<=4;q++){
   const info=data.manual_quarters?.[`${year}-T${q}`],historical=year*10+q<=(data.excel_last_quarter??last)||info?.financial_complete===true;let volume,revenue,rateCt,rateSource;
   if(historical){const rows=data.invoices.filter(r=>r.year===year&&r.quarter===q);volume=rows.reduce((s,r)=>s+(invoiceEnergy(r)??0),0);revenue=rows.reduce((s,r)=>s+(r.revenue_chf??0),0);rateCt=volume?revenue/volume*100:null;rateSource=info?'Réalisé GRD / banque':'Prix réalisé Excel';}
   else{volume=base[q-1].kwh==null?null:base[q-1].kwh*(1-degradation)**n;const rate=projectedRate(data,scenario,year,q);rateCt=rate.rateCt;rateSource=rate.source;if(rateCt!=null&&(!Number.isFinite(rateCt)||Math.abs(rateCt)>1000))throw new Error('Tarif hors limites');revenue=volume===0?0:volume==null||rateCt==null?null:volume*rateCt/100;}
   quarters.push({year,quarter:q,key:`${year}-T${q}`,historical,kwh:volume,sales:revenue,rateCt,rateSource,manualPartial:!!info&&!historical,knownEnergy:info?.energy_known_count?info.known_energy_kwh:null,knownReceived:info?.bank_known_count?info.known_received_chf:null});
   sales=sales==null||revenue==null?null:sales+revenue;kwh=kwh==null||volume==null?null:kwh+volume;
  }
  const entered=data.years.find(y=>y.year===year)?.charges??0;
  let charges=year<=ref2?entered:Math.max(entered,expenses*(1+inflation)**n);
  const replacementYear=Object.hasOwn(scenario,'replacementYear')?scenario.replacementYear:data.assumptions.E11,replacementCost=(Object.hasOwn(scenario,'replacementCost')?scenario.replacementCost:data.assumptions.E12)??0;
  if(!Number.isFinite(replacementCost)||replacementCost<0)throw new Error('Coût de remplacement non valide');
  if(year*10+4>last&&replacementYear===year)charges+=replacementCost;
  const other=original.other??0,net=sales==null?null:sales+other-charges;cumulative=cumulative==null||net==null?null:cumulative+net;
  const qs=quarters.filter(r=>r.year===year),hasManual=qs.some(r=>data.manual_quarters?.[r.key]);
  const status=hasManual?(qs.every(q=>q.historical)?'Réel':qs.some(q=>q.historical||q.manualPartial)?'Partiel':'Projeté'):original.status;
  return {year,status,sales,kwh,charges,other,net,cumulative,profit:cumulative==null?null:cumulative-cost};
 });
 const complete=years.every(y=>y.net!=null);
 return {years,quarters,complete,profit:years.at(-1)?.profit??null,cash:years.at(-1)?.cumulative??null,payback:years.find(y=>y.profit!=null&&y.profit>=0)?.year??null,irr:complete?irr([-cost,...years.map(y=>y.net)]):null};
}
export function previousPeriod(from,to,period='custom'){
 const count=Math.round((Date.parse(to+'T12:00Z')-Date.parse(from+'T12:00Z'))/86400000)+1;
 if(period==='month'){const d=new Date(from+'T12:00Z');d.setUTCMonth(d.getUTCMonth()-1);const start=d.toISOString().slice(0,10),end=addDay(from,-1);return {from:start,to:end};}
 if(period==='year'){return {from:(Number(from.slice(0,4))-1)+'-01-01',to:(Number(to.slice(0,4))-1)+'-12-31'};}
 return {from:addDay(from,-count),to:addDay(to,-count)};
}
export function compareSeries(data,metric,from,to,resolution,period,rows,now=Date.now()){
 const previous=previousPeriod(from,to,period),old=seriesFor(data,metric,previous.from,previous.to,resolution),dayIndex=(t,origin)=>Math.round((Date.parse(localDay(t)+'T12:00Z')-Date.parse(origin+'T12:00Z'))/86400000);
 const timePart=t=>new Intl.DateTimeFormat('en-GB',{timeZone:ZONE,hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(t));
 const key=(r,origin)=>resolution==='month'?Number(localDay(r.start).slice(5,7)):resolution==='week'?Math.floor(dayIndex(r.start,origin)/7):`${dayIndex(r.start,origin)}:${metric==='power'?timePart(r.start):'day'}`;
 const map=new Map();for(const r of old){const k=key(r,previous.from);if(!map.has(k))map.set(k,[]);map.get(k).push(r);}
 const overlay=[];let allMatched=true;for(const r of rows){const matches=map.get(key(r,from)),match=matches?.shift();if(match){overlay.push({...match,start:r.start,end:r.end,originalStart:match.start,originalEnd:match.end,label:`Période précédente · ${localDay(match.start)}`});}else allMatched=false;}
 let coverage=false;
 if(metric==='power'){const cutoff=Math.min(localMidnight(addDay(to,1)),Math.floor(now/900000)*900000),expected=Math.max(0,(cutoff-localMidnight(from))/900000);const raw=seriesFor(data,'power',from,to,'15m');coverage=raw.length===expected&&expected>0;if(resolution==='hour')coverage=coverage&&rows.length>0&&rows.every((r,i)=>i===0||r.start===rows[i-1].end);}
 else{const end=to<localDay(now)?to:addDay(localDay(now),-1),expected=from<=end?Math.round((Date.parse(end+'T12:00Z')-Date.parse(from+'T12:00Z'))/86400000)+1:0;coverage=seriesFor(data,'energy',from,to,'day').length===expected&&expected>0&&!rows.some(r=>r.partial);}
 const complete=coverage&&allMatched&&rows.length>0&&!overlay.some(r=>r.partial);const a=rows.reduce((n,r)=>n+r.value,0),b=overlay.reduce((n,r)=>n+r.value,0);
 return {previous,overlay,complete,change:complete&&b!==0?(a/b-1)*100:null,matched:overlay.length};
}
export function csvText(rows){const cell=v=>{if(v==null)return '';let s=String(v);if(typeof v!=='number'&&/^[\s]*[=+\-@]|^[\t\r]/.test(s))s="'"+s;return /[",\n\r]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;};return '\ufeff'+rows.map(row=>row.map(cell).join(',')).join('\r\n');}
