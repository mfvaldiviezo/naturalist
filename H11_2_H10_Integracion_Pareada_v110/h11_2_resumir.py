#!/usr/bin/env python3
"""Descriptive H11.2 summary; no claims of Quito calibration or confirmed gridlock.

python h11_2_resumir.py --telemetria path/to/traci_... [--guardar]
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

def float_or_none(x):
    try:
        import math
        n=float(x)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError): return None

def lines(path):
    with path.open(encoding='utf-8',newline='') as f:
        yield from csv.DictReader(f)

def run(root):
    meta=json.loads((root/'manifest_h11_2.json').read_text(encoding='utf-8'))
    c=Counter()
    cohorts=Counter()
    ids={}
    for r in lines(root/'trayectorias_h11.csv'):
        c['vehicle_steps']+=1
        vid=r['vehicle_id'];cohort=r['cohort'];ids[vid]=cohort
        gap=float_or_none(r['gap_m']); head=float_or_none(r['headway_s']);ttc=float_or_none(r['ttc_s'])
        if gap is not None: c['gap_available']+=1
        if head is not None:
            c['headway_available']+=1
            if head<1.: c['headway_lt_1s_vehicle_steps']+=1
        if ttc is not None:
            c['ttc_finite_available']+=1
            if ttc<2.: c['ttc_lt_2s_vehicle_steps']+=1
        if r['above_posted_lane_limit'] in ('true','false'):
            c['speed_limit_available']+=1
            if r['above_posted_lane_limit']=='true': c['overspeed_vehicle_steps']+=1
        if r['tls_state']!='unknown': c['tls_available_vehicle_steps']+=1
        if r['jerk_observed_m_s3']!='': c['jerk_available']+=1
    event=Counter()
    unknown=[]
    for r in lines(root/'eventos_semaforicos_h11.csv'):
        event[(r['event_kind'],r['color_label'],r['cohort'])]+=1
        if r['color_label']=='unknown' and len(unknown)<10:
            unknown.append({'time_s':r['time_s'],'vehicle_id':r['vehicle_id'],'tls_id':r['tls_id'],'event_kind':r['event_kind']})
    inter=list(lines(root/'eventos_interseccion_h11.csv'))
    safety=Counter()
    for r in lines(root/'seguridad_h11.csv'):
        for fld in ('colliding_vehicles_count','teleport_start_count','emergency_stop_count'):
            if r[fld] != '': safety[fld]+=int(r[fld])
            else: safety['missing_'+fld]+=1
    for v in ids.values(): cohorts[v]+=1
    result={
       'model':'H11.2 descriptive only',
       'calibrated_quito':False,
       'steps':meta['observed_steps'],
       'unique_vehicles_seen':len(ids),
       'unique_vehicle_cohorts':dict(cohorts),
       'trajectory_coverage':dict(c),
       'signal_event_counts_by_kind_color_cohort':[
         {'event_kind':key[0],'color':key[1],'cohort':key[2],'n':v}
         for key,v in sorted(event.items())],
       'signal_unknown_examples':unknown,
       'internal_stop_candidates':len(inter),
       'gridlock_confirmed':False,
       'safety_counts_or_missing':dict(safety),
       'telemetry_errors':meta['telemetry_failures_or_missing'],
       'warnings':['NO equivaler pasos-vehiculo a conductores distintos.',
       'Cruces PROXY; NO establecer infracciones legales directamente.',
       'No inferir tasas de Quito sin observaciones externas.',
       'NO afirmar gridlock confirmado por detencion en carril interno.',
       'Headway y TTC se calculan para oportunidades con lider detectado; sus denominadores difieren.']}
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--telemetria',required=True,type=Path)
    p.add_argument('--guardar',action='store_true')
    a=p.parse_args()
    root=a.telemetria.resolve()
    result=run(root)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if a.guardar:
        dest=root/'resumen_h11_2.json'
        with dest.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False)
        print('RESUMEN',dest)

if __name__=='__main__': main()
