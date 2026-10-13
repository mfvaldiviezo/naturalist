#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria offline de CSV H09 existente. No inicia SUMO ni modifica archivos fuente."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

REQUIRED={'event_type','vehicle_id','site_id','passage_id','signal_state','classification_quality',
          'phase_prev','phase_current','time_s','lane_prev','lane_current'}

def file_hash(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def audit(path):
    path=Path(path)
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames is None or not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError('Cabecera CSV incompleta: '+str(REQUIRED-set(reader.fieldnames or [])))
        rows=list(reader)
    stop=[x for x in rows if x['event_type']=='stopline']
    speed=[x for x in rows if x['event_type']=='speed']
    ids=[(x.get('run_id',''),x.get('seed',''),x['passage_id']) for x in rows]
    if len(set(ids))!=len(ids):raise ValueError('Passage IDs repetidos; posible doble conteo')
    by_site={}
    for site in sorted({x['site_id'] for x in stop}):
        ss=[x for x in stop if x['site_id']==site]
        by_site[site]={'n':len(ss),'estados':dict(Counter(x['signal_state'] for x in ss)),
                       'vehiculos_distintos':len({x['vehicle_id'] for x in ss})}
    unknown=[x for x in stop if x['signal_state']=='unknown']
    transitions=Counter(f"{x['phase_prev']}->{x['phase_current']}" for x in unknown)
    ambiguous=[{'vehicle_id':x['vehicle_id'],'site_id':x['site_id'],'time_s':x['time_s'],
                'phase_prev':x['phase_prev'],'phase_current':x['phase_current'],
                'distance_prev_m':x.get('distance_prev_m'),'reason':x.get('reason')} for x in unknown]
    n=len(stop)
    return {'file':str(path.resolve()),'input_sha256':file_hash(path),
       'stopline_events':n,'different_vehicles':len({x['vehicle_id'] for x in stop}),
       'speed_samples':len(speed),'classification':dict(Counter(x['signal_state'] for x in stop)),
       'unknown_fraction':len(unknown)/n if n else None,
       'unknown_transitions':dict(transitions),'sites':by_site,
       'uncertain_event_details':ambiguous,
       'limitation':'proxy_crossings; no ground-truth red-light violation test and no Quito-harmonized denominator'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eventos',required=True,type=Path)
    p.add_argument('--salida',type=Path)
    args=p.parse_args()
    report=audit(args.eventos)
    print(json.dumps({k:v for k,v in report.items() if k!='uncertain_event_details'},indent=2,ensure_ascii=False))
    if args.salida:
        if args.salida.exists():raise FileExistsError(f'Se protege salida anterior: {args.salida}')
        args.salida.parent.mkdir(parents=True,exist_ok=True)
        args.salida.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print('Informe generado:',args.salida)
if __name__=='__main__':main()
