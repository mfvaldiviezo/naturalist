#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditor de factorial SxV H09 v1.3: placebo, S, V, SV y controles previos.

No infiere causalidad estadística de una semilla. No modifica datos de entrada,
y se abstiene ante eventos de cruce unknown. No equipara tasas Quito/Hangzhou.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean

RUNS={
 'baseline':'baseline',
 'probe':'probe',
 'placebo':'active_15_placebo',
 'S':'active_15_semaforos',
 'V':'active_15_velocidad',
 'SV':'active_15_semaforos_velocidad',
 'combinado':'active_15_combinado',
}
EXPECTED_PARAMS={
 'placebo':{'tau':1.0},
 'S':{'jmDriveAfterYellowTime':1.5,'jmDriveAfterRedTime':0.5},
 'V':{'speedFactor':1.15},
 'SV':{'speedFactor':1.15,'jmDriveAfterYellowTime':1.5,'jmDriveAfterRedTime':0.5},
 'combinado':{'tau':0.9,'minGap':1.2,'speedFactor':1.15,'jmDriveAfterYellowTime':1.5,'jmDriveAfterRedTime':0.5,'jmIgnoreKeepClearTime':0.0},
}

def rows_from(path):
    with Path(path).open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def metrics(traffic, events):
    if not traffic:raise ValueError('Archivo de tráfico vacío')
    speed=[e for e in events if e.get('event_type')=='speed' and float(e.get('limit_mps') or 0)>0]
    crossing=[e for e in events if e.get('event_type')=='stopline']
    unknown=[e for e in crossing if e.get('signal_state')=='unknown']
    red=[e for e in crossing if e.get('signal_state')=='red' and e.get('classification_quality')=='confirmed']
    yellow=[e for e in crossing if e.get('signal_state')=='yellow' and e.get('classification_quality')=='confirmed']
    invalid=[e for e in crossing if e.get('signal_state')=='unknown' and e.get('classification_quality')=='confirmed']
    if invalid:raise ValueError('Cruce unknown marcado confirmed: invalida medición')
    return {
       'mean_speed_kmh':round(mean(float(x['mean_speed_kmh']) for x in traffic),6),
       'mean_halted':round(mean(int(x['n_halted']) for x in traffic),6),
       'arrivals':sum(int(x['arrivals_step']) for x in traffic),
       'speed_n':len(speed),
       'speed_exceed_n':sum(float(e['speed_mps'])>float(e['limit_mps']) for e in speed),
       'speed_exceed_pct':round(100*sum(float(e['speed_mps'])>float(e['limit_mps']) for e in speed)/len(speed),6) if speed else None,
       'crossings':len(crossing),'red_confirmed':len(red),'yellow_confirmed':len(yellow),
       'unknown':len(unknown),
       'collisions':sum(int(x['collisions_step']) for x in traffic),
       'teleports':sum(int(x['teleports_start_step']) for x in traffic),
       'n_steps':len(traffic),
       'red_rate_proxy_lower_pct':round(100*len(red)/len(crossing),6) if crossing else None,
       'red_rate_proxy_upper_pct':round(100*(len(red)+len(unknown))/len(crossing),6) if crossing else None,
    }

def find_core_hashes(manifest):
    """Excluye sólo JSON config perfiles, que se manipula deliberadamente.

    Compara sumocfg, net.xml y routes.xml por sufijos verificables. Rechaza
    rutas ambiguas o falta de exactamente tres archivos núcleo.
    """
    found={}
    for path,digest in manifest['original_hashes_sha256'].items():
        path=Path(path)
        suffix=path.suffix.lower()
        if suffix=='.sumocfg':kind='sumocfg'
        elif path.name.endswith('.net.xml'):kind='network'
        elif path.name.endswith('.rou.xml'):kind='routes'
        elif suffix=='.json':continue
        else:raise ValueError('Entrada desconocida: '+str(path))
        if kind in found:raise ValueError('Más de un '+kind)
        found[kind]=digest
    if set(found)!={'sumocfg','network','routes'}:raise ValueError('Faltan inputs núcleo: '+repr(found))
    return found

def read_run(root,label):
    path=Path(root)/RUNS[label]
    manifest=json.loads((path/'manifest_H09.json').read_text(encoding='utf-8'))
    if manifest.get('status')!='SUMO_EXECUTED_EXPLORATORY':raise ValueError('Corrida incompleta: '+str(path))
    if manifest['mode']!=('baseline' if label=='baseline' else 'probe' if label=='probe' else 'active'):
        raise ValueError('Modo incorrecto '+label)
    if label in EXPECTED_PARAMS and manifest.get('profile_parameters')!=EXPECTED_PARAMS[label]:
        raise ValueError('Parámetros distintos a los del factorial: '+label+' '+str(manifest.get('profile_parameters')))
    exposure=manifest['exposure_summary']
    if label not in ('baseline','probe'):
        if manifest['porcentaje_solicitado']!=15:raise ValueError('Porcentaje no es 15: '+label)
        if exposure['n_assigned']!=45 or exposure['n_selected_verified_vtype']!=45:
            raise ValueError('Perfil sin corroborar 45/45: '+label)
    for name in ('trafico_h09.csv','eventos_h09.csv','cohorte_h09.csv'):
        fp=path/name
        expected=manifest.get('generated_hashes_sha256',{}).get(str(fp))
        # Path absoluta al crear los manifiestos; aceptar equivalencia por ruta resuelta.
        if expected is None:
            hits=[d for k,d in manifest.get('generated_hashes_sha256',{}).items() if Path(k).name==name]
            if len(hits)!=1:raise ValueError('Hash generado no registrado: '+str(fp))
            expected=hits[0]
        if sha_file(fp)!=expected:raise ValueError('Archivo generado modificado: '+str(fp))
    traffic=rows_from(path/'trafico_h09.csv')
    events=rows_from(path/'eventos_h09.csv')
    data={'label':label,'mode':manifest['mode'],'seed':manifest['seed'],
          'core_hashes':find_core_hashes(manifest),
          'traffic_hash':manifest['traffic_sha256'],
          'profile_parameters':manifest.get('profile_parameters'),
          'cohort':{row['vehicle_id'] for row in rows_from(path/'cohorte_h09.csv') if row['assigned']=='1'},
          'n_roster':exposure['n_roster'],
          'n_verified':exposure['n_selected_verified_vtype'],
          'n_seen':exposure['n_selected_seen']}
    data.update(metrics(traffic,events))
    if data['traffic_hash']!=sha_file(path/'trafico_h09.csv'):
        raise ValueError('Hash traffic manifest no coincide '+label)
    return data

def compare(root):
    runs={k:read_run(root,k) for k in RUNS}
    seeds={r['seed'] for r in runs.values()}
    if len(seeds)!=1:raise ValueError('Semillas mezcladas: '+str(seeds))
    rosters={r['n_roster'] for r in runs.values()}
    if len(rosters)!=1:raise ValueError('Demandas distintas: '+str(rosters))
    cores={tuple(sorted(x['core_hashes'].items())) for x in runs.values()}
    if len(cores)!=1:raise ValueError('Entradas originales de SUMO distintas (cfg/net/rutas)')
    steps={r['n_steps'] for r in runs.values()}
    if len(steps)!=1:raise ValueError('Duraciones efectivas diferentes')
    if runs['baseline']['traffic_hash']!=runs['probe']['traffic_hash']:
        raise ValueError('Baseline y probe generan CSV de tráfico diferentes')
    cohorts=[(k,v['cohort']) for k,v in runs.items() if k not in ('baseline','probe')]
    if len({frozenset(x) for _,x in cohorts})!=1:raise ValueError('Cohortes de conductores difieren entre familias')
    if len(next(iter(cohorts))[1])!=45:raise ValueError('La cohorte no tiene 45 vehículos')
    placebo_bitwise=(runs['baseline']['traffic_hash']==runs['placebo']['traffic_hash'])
    indicators=('arrivals','mean_halted','mean_speed_kmh','speed_exceed_pct','red_confirmed','yellow_confirmed','unknown')
    terms={}
    # I=S+V-P corregida por placebo. Sólo exploratoria en semilla única.
    for key in indicators:
        if any(runs[n][key] is None for n in ('placebo','S','V','SV')):
            terms[key]=None
        else:
            terms[key]=round(runs['SV'][key]-runs['S'][key]-runs['V'][key]+runs['placebo'][key],6)
    printrows=[]
    for label,run in runs.items():
        r={k:v for k,v in run.items() if k not in ('cohort','core_hashes','traffic_hash','profile_parameters')}
        r['delta_arrivals_vs_baseline']=run['arrivals']-runs['baseline']['arrivals']
        r['delta_halted_vs_baseline']=round(run['mean_halted']-runs['baseline']['mean_halted'],6)
        r['delta_speed_vs_baseline']=round(run['mean_speed_kmh']-runs['baseline']['mean_speed_kmh'],6)
        printrows.append(r)
    status='PLACEBO_BITWISE_IDENTICAL' if placebo_bitwise else 'PLACEBO_DIFFERS_FROM_BASELINE_IN_TRAFFIC_SHA256'
    return {'status':status,'seed':next(iter(seeds)),'cohort_n':45,
            'core_hashes':runs['baseline']['core_hashes'],
            'rows':printrows,
            'exploratory_factorial_interaction':terms,
            'limits':['Cruces stopline proxy; no mismos denominadores Quito',
                      'Intervalos red proxy son limites logicos suponiendo unknown totalmente red o no red, NO intervalos de confianza',
                      'Solo una semilla; no prueba causalidad ni significación',
                      'Placebo vType tau nominal puede modificar flujo; inspeccionar status',
                      'Exceso velocidad es proporción de muestras; no vehículos individuales',
                      'No se asignan probabilidades individuales a partir de Quito']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output-prefix',type=Path,required=True)
    args=p.parse_args()
    result=compare(args.root)
    json_path=Path(str(args.output_prefix)+'.json')
    csv_path=Path(str(args.output_prefix)+'.csv')
    if json_path.exists() or csv_path.exists():raise FileExistsError('La salida ya existe; no sobrescribir')
    args.output_prefix.parent.mkdir(parents=True,exist_ok=True)
    json_path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    with csv_path.open('w',encoding='utf-8',newline='') as f:
        cols=list(result['rows'][0]);w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(result['rows'])
    print(json.dumps({'status':result['status'],'seed':result['seed'],
                      'cohort_n':result['cohort_n'],'interaction':result['exploratory_factorial_interaction'],
                      'rows':result['rows']},indent=2,ensure_ascii=False))
    print('REPORTE:',json_path,csv_path)
    print('ESTATUS: comparación factorial exploratoria, Quito sin calibrar')

if __name__=='__main__':main()
