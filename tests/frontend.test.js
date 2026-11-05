import test from 'node:test';
import assert from 'node:assert/strict';
import {localMidnight,seriesFor,financeSeries,financialRows,projectScenario,irr,csvText,compareSeries,quarterBases} from '../polyimmo/static/model.js';

test('local dates preserve the 25-hour autumn daylight saving day',()=>{
 assert.equal(localMidnight('2026-10-26')-localMidnight('2026-10-25'),25*3600000);
 assert.equal(localMidnight('2026-03-30')-localMidnight('2026-03-29'),23*3600000);
});
test('hourly power requires all four quarters and preserves negative observations',()=>{
 const a=Date.parse('2026-11-04T10:00:00Z'),rows=Array.from({length:4},(_,i)=>({start_utc:new Date(a+i*900000).toISOString(),interval_seconds:900,value:i===0?-4:4,unit:'kW'}));
 const result=seriesFor({aurora_power:rows},'power','2026-11-04','2026-11-04','hour');
 assert.equal(result.length,1);assert.equal(result[0].value,2);
 assert.equal(seriesFor({aurora_power:rows.slice(1)},'power','2026-11-04','2026-11-04','hour').length,0);
});
test('monthly energy with missing days is marked partial and never filled with zero',()=>{
 const rows=[1,2].map(d=>({start_utc:`2026-11-0${d}T00:00:00+01:00`,interval_seconds:86400,value:25,unit:'kWh'}));
 const r=seriesFor({aurora_daily:rows},'energy','2026-11-01','2026-11-30','month');
 assert.equal(r.length,1);assert.equal(r[0].value,50);assert.equal(r[0].partial,true);assert.equal(r[0].days,2);
});
test('finance filters honor the year and search while missing quarters remain absent',()=>{
 const data={years:[{year:2025},{year:2026}],invoices:[{year:2025,quarter:1,label:'Février',revenue_chf:12},{year:2026,quarter:2,label:'Avril',revenue_chf:0}]};
 assert.equal(financialRows(data,'2025','fevrier').length,1);
 assert.equal(financialRows(data,'2026','fevrier').length,0);
 const series=financeSeries(data,'2026');assert.equal(series[0].value,null);assert.equal(series[1].value,0);
});
function fixture(){const invoices=[];for(let year=2023;year<=2026;year++)for(let q=1;q<=4;q++)invoices.push({year,quarter:q,revenue_chf:10,high_kwh:50,low_kwh:50});return {invoices,investment:{net:1000},assumptions:{E5:2024,E6:2025,E14:20263,E11:null,E12:null},years:[2023,2024,2025,2026].map(year=>({year,charges:null})),projection:Array.from({length:30},(_,i)=>({year:2023+i,other:0,status:i<3?'Réel':'Projeté'}))};}
test('scenario adjusts future quarters while preserving historical cashflows',()=>{
 const data=fixture(),defaults={degradation:0,price:0,expenses:0,inflation:0},base=projectScenario(data,defaults),changed=projectScenario(data,{...defaults,expenses:100,price:-.05});
 assert.equal(base.profit,200);assert.equal(base.years.length,30);
 assert.deepEqual(base.years.slice(0,3),changed.years.slice(0,3));
 assert.ok(changed.profit<base.profit);assert.equal(changed.payback,null);
 assert.equal(projectScenario(data,defaults).profit,200);
});
test('IRR uses an initial investment distinct from the first annual flow',()=>{
 assert.ok(Math.abs(irr([-100,110])-.1)<1e-10);assert.equal(irr([100,110]),null);assert.equal(irr([-100,-20]),null);
});
test('CSV export retains true negative numbers and neutralizes spreadsheet formulas',()=>{
 const text=csvText([['=HYPERLINK("bad")',-12,null,'a,b']]);
 assert.ok(text.includes("'=HYPERLINK"));assert.ok(text.includes(',-12,,'));assert.ok(text.includes('"a,b"'));
});

test('a future quarterly tariff changes only that quarter and zero is a real override',()=>{
 const d=fixture(),s={degradation:0,price:0,expenses:0,inflation:0},base=projectScenario(d,s);
 const changed=projectScenario(d,{...s,tariffs:{seasonal:{},overrides:{'2026-T4':20,'2025-T1':999}}});
 assert.equal(changed.profit,base.profit+10);
 assert.deepEqual(changed.years.slice(0,3),base.years.slice(0,3));
 assert.equal(changed.quarters.find(r=>r.key==='2026-T4').sales,20);
 assert.equal(changed.quarters.find(r=>r.key==='2025-T1').rateCt,10);
 const zero=projectScenario(d,{...s,tariffs:{overrides:{'2026-T4':0}}});
 assert.equal(zero.quarters.find(r=>r.key==='2026-T4').sales,0);
 assert.equal(zero.profit,base.profit-10);
});
test('explicit future rates have priority over seasonal rates and annual growth',()=>{
 const s={degradation:0,price:.1,expenses:0,inflation:0,tariffs:{seasonal:{'2':8},overrides:{'2028-T2':12}}},result=projectScenario(fixture(),s);
 assert.equal(result.quarters.find(q=>q.key==='2028-T2').rateCt,12);
 assert.equal(result.quarters.find(q=>q.key==='2028-T2').sales,12);
 assert.ok(Math.abs(result.quarters.find(q=>q.key==='2027-T2').rateCt-8*1.1**2)<1e-10);
 assert.equal(result.quarters.find(q=>q.key==='2025-T2').rateCt,10);
});
test('reference tariffs are volume weighted and missing reference energy stays unavailable',()=>{
 const d=fixture();d.invoices.find(r=>r.year===2024&&r.quarter===1).revenue_chf=30;
 assert.equal(quarterBases(d)[0].rateCt,20);
 d.invoices=d.invoices.filter(r=>!(r.quarter===2&&[2024,2025].includes(r.year)));
 const s={degradation:0,price:0,expenses:0,inflation:0,tariffs:{overrides:{'2027-T2':15}}},r=projectScenario(d,s);
 assert.equal(r.quarters.find(q=>q.key==='2027-T2').kwh,null);
 assert.equal(r.quarters.find(q=>q.key==='2027-T2').sales,null);
 assert.equal(r.complete,false);assert.equal(r.profit,null);assert.equal(r.irr,null);
});
test('future inverter replacement is deducted without changing historical flows',()=>{
 const s={degradation:0,price:0,expenses:0,inflation:0},base=projectScenario(fixture(),s),changed=projectScenario(fixture(),{...s,replacementYear:2028,replacementCost:500});
 assert.equal(changed.profit,base.profit-500);assert.equal(changed.years.find(y=>y.year===2028).charges,500);
 assert.deepEqual(changed.years.slice(0,3),base.years.slice(0,3));
});
test('comparison uses only a common window and suppresses percentages for missing observations',()=>{
 const raw=[];for(const [date,n,value]of [['2026-11-04',96,4],['2026-11-05',48,5]])for(let i=0;i<n;i++)raw.push({start_utc:new Date(localMidnight(date)+i*900000).toISOString(),interval_seconds:900,value,unit:'kW'});
 const d={aurora_power:raw},rows=seriesFor(d,'power','2026-11-05','2026-11-05','15m'),now=Date.parse('2026-11-05T11:00:00Z');
 const comparison=compareSeries(d,'power','2026-11-05','2026-11-05','15m','today',rows,now);
 assert.equal(comparison.complete,true);assert.equal(comparison.change,25);assert.equal(comparison.overlay.length,48);
 d.aurora_power=raw.filter(r=>Date.parse(r.start_utc)<localMidnight('2026-11-05')||Date.parse(r.start_utc)>=localMidnight('2026-11-05')+3600000);
 const incomplete=compareSeries(d,'power','2026-11-05','2026-11-05','hour','today',seriesFor(d,'power','2026-11-05','2026-11-05','hour'),now);
 assert.equal(incomplete.complete,false);assert.equal(incomplete.change,null);
});

test('partial manual months are not added twice to a quarterly forecast, complete quarters lock tariffs',()=>{
 const d=fixture(),s={degradation:0,price:0,expenses:0,inflation:0,tariffs:{overrides:{'2026-T4':50}}};
 d.excel_last_quarter=20263;d.invoices=d.invoices.filter(r=>!(r.year===2026&&r.quarter===4));
 d.invoices.push({year:2026,quarter:4,energy_kwh:20,high_kwh:null,low_kwh:null,revenue_chf:3,origin:'manual'});
 d.manual_quarters={'2026-T4':{financial_complete:false,known_energy_kwh:20,known_received_chf:3,energy_known_count:1,bank_known_count:1}};
 const partial=projectScenario(d,s).quarters.find(q=>q.key==='2026-T4');
 assert.equal(partial.historical,false);assert.equal(partial.sales,50);assert.equal(partial.knownReceived,3);assert.equal(partial.manualPartial,true);
 d.manual_quarters['2026-T4'].financial_complete=true;
 const closed=projectScenario(d,s).quarters.find(q=>q.key==='2026-T4');
 assert.equal(closed.historical,true);assert.equal(closed.sales,3);assert.equal(closed.kwh,20);assert.equal(closed.rateCt,15);
});
