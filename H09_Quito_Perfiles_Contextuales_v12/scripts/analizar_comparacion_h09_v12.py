#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compara pilotos H09 por corridas, SIN inferir tasas individuales empíricas de Quito.

Ejemplo:
 python analizar_comparacion_h09_v12.py --directorios resultados/h09_base_101 resultados/h09_probe_101 resultados/h09_active15_101
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import statistics
import sys


def read_dir(path):
    p=Path(path)
    manifest=json.loads((p/'manifest_H09.json').read_text(encoding='utf8'))
    if manifest.get('status')!='SUMO_EXECUTED_EXPLORATORY':
        raise ValueError('Corrida no ejecutada o no validada: '+str(path))
    with (p/'trafico_h09.csv').open(encoding='utf8',newline='') as f:
        rows=list(csv.DictReader(f))
    with (p/'eventos_h09.csv').open(encoding='utf-8-sig',newline='') as f:
        events=list(csv.DictReader(f))
    if not rows:raise ValueError('tráfico vacío')
    speed=[x for x in events if x['event_type']=='speed']
    good=[x for x in speed if float(x['limit_mps'])>0]
    reds=[x for x in events if x['event_type']=='stopline' and x['signal_state']=='red' and x['classification_quality']=='confirmed']
    yellow=[x for x in events if x['event_type']=='stopline' and x['signal_state']=='yellow' and x['classification_quality']=='confirmed']
    unkn=[x for x in events if x['event_type']=='stopline' and x['signal_state']=='unknown']
    invalid=[x for x in events if x['event_type']=='stopline' and x['classification_quality']=='confirmed' and x['signal_state']=='unknown']
    if invalid:raise ValueError('Eventos unknown fraudulentamente confirmados')
    return {'dirname':p.name,'mode':manifest['mode'],'pct':manifest['porcentaje_solicitado'],
            'family':manifest['familia'],'seed':manifest['seed'],
            'input_fingerprint':tuple(sorted(manifest['original_hashes_sha256'].values())),
            'traffic_sha256':manifest['traffic_sha256'],
            'mean_speed_kmh':round(statistics.mean(float(x['mean_speed_kmh']) for x in rows),4),
            'mean_halted':round(statistics.mean(int(x['n_halted']) for x in rows),4),
            'arrivals':sum(int(x['arrivals_step']) for x in rows),
            'n_speed':len(good),
            'speeding_count':sum(float(x['speed_mps'])>float(x['limit_mps']) for x in good),
            'speeding_pct':round(100*sum(float(x['speed_mps'])>float(x['limit_mps']) for x in good)/len(good),4) if good else None,
            'cross_red_confirmed':len(reds),'cross_yellow_confirmed':len(yellow),
            'cross_unknown':len(unkn),
            'n_crossings':sum(x['event_type']=='stopline' for x in events),
            'n_assigned':manifest['exposure_summary']['n_assigned'],
            'n_selected_seen':manifest['exposure_summary']['n_selected_seen'],
            'n_selected_verified_type':manifest['exposure_summary']['n_selected_verified_vtype'],
            'collision_reports':sum(int(x['collisions_step']) for x in rows),
            'teleport_reports':sum(int(x['teleports_start_step']) for x in rows),
            'steps':len(rows)}


def compare(paths):
    raw=[read_dir(x) for x in paths]
    if len(set(x['input_fingerprint'] for x in raw))!=1:
        raise ValueError('No comparar escenarios con archivos ORIGINALES distintos')
    if len(set((x['seed'],x['steps']) for x in raw))!=1:
        raise ValueError('Semillas / longitudes diferentes, comparación inválida')
    baseline=[x for x in raw if x['mode']=='baseline']
    probe=[x for x in raw if x['mode']=='probe']
    if len(baseline)!=1:raise ValueError('Es obligatorio UN baseline')
    if probe and any(x['traffic_sha256']!=baseline[0]['traffic_sha256'] for x in probe):
        raise ValueError('PROBE modificó el tráfico; bloquear evaluación')
    base=baseline[0]
    result=[]
    for x in raw:
        y={k:v for k,v in x.items() if k!='input_fingerprint'}
        y['delta_halted_vs_baseline']=round(x['mean_halted']-base['mean_halted'],4)
        y['delta_speed_kmh_vs_baseline']=round(x['mean_speed_kmh']-base['mean_speed_kmh'],4)
        y['delta_arrivals_vs_baseline']=x['arrivals']-base['arrivals']
        y['status']='DESCRIPTIVE_NOT_EMPIRICALLY_CALIBRATED_QUITO'
        result.append(y)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directorios',type=Path,nargs='+',required=True)
    p.add_argument('--salida-csv',type=Path,required=True)
    args=p.parse_args()
    if args.salida_csv.exists():raise FileExistsError(args.salida_csv)
    rows=compare(args.directorios)
    args.salida_csv.parent.mkdir(parents=True,exist_ok=True)
    with args.salida_csv.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    print('COMPARACIÓN DESCRIPTIVA. Quito NO validado; un único seed no basta.')
    print('CSV:',args.salida_csv)

if __name__=='__main__':main()
