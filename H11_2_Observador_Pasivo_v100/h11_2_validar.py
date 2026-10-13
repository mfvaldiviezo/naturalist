#!/usr/bin/env python3
"""Validate integrity of a finished H11.2 telemetria directory, read only."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

def rows(path):
    with path.open(newline='',encoding='utf-8') as f: yield from csv.DictReader(f)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--telemetria',type=Path,required=True)
    p.add_argument('--expected-steps',type=int)
    args=p.parse_args()
    source=args.telemetria.resolve()
    man=json.loads((source/'manifest_h11_2.json').read_text(encoding='utf-8'))
    for name,expected_hash in man['outputs_sha256'].items():
        file=source/name
        actual=hashlib.sha256(file.read_bytes()).hexdigest()
        if actual != expected_hash: raise AssertionError(f'Hash no coincide: {file}')
    safety=list(rows(source/'seguridad_h11.csv'))
    n=len(safety)
    if n!=man['observed_steps']: raise AssertionError('Numero de pasos != manifest')
    if args.expected_steps is not None and n!=args.expected_steps:
        raise AssertionError(f'Pasos esperados={args.expected_steps}, observados={n}')
    times=[];steps=set()
    for r in safety:
        index=int(r['step']); t=float(r['time_s'])
        if not math.isfinite(t) or t<=0 or index in steps:
            raise AssertionError('Tiempo invalido o indice de paso repetido')
        steps.add(index);times.append(t)
    if any(y<=x for x,y in zip(times,times[1:])):
        raise AssertionError('Tiempo no creciente')
    c=Counter()
    for r in rows(source/'trayectorias_h11.csv'):
        c['rows']+=1
        if float(r['speed_m_s'])<0: c['negative_speed']+=1
        if r['cohort'] not in ('both','vine_only','h09_only','neither','unclassified'):
            raise AssertionError('Cohorte invalida')
    if c['rows']!=man['counts'].get('trajectory_rows',0):
        raise AssertionError('Filas de trayectorias inconsistentes')
    print('H11.2 VALIDADO: SHA256, pasos, monotonia temporal, filas y cohortes')
    print('PASOS:',n,'FILAS:',c['rows'],'VELOCIDADES_NEGATIVAS:',c['negative_speed'])
    print('FALLAS CONSULTAS OPCIONALES:',man['telemetry_failures_or_missing'])
    print('ADVERTENCIA: mediciones solo estructurales, sin calibracion de Quito.')

if __name__=='__main__': main()
