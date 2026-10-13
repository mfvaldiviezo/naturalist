#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditor de sensibilidad 15/30/50 v1.5. LEE resultados, NO corre SUMO.

Compara hash de tráfico para 0 y 15% con H09 v1.4.3 preservado.
Vincula oportunidades de movimiento a cruces del mismo episodio.
NO transforma conteos en P(infracción|opportunity) comparable a Quito.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean

SEEDS=(101,102,103,104,105)
PCTS=(0,15,30,50)

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for x in iter(lambda:f.read(1<<20),b''):h.update(x)
    return h.hexdigest()

def readcsv(p):
    with Path(p).open('r',encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def readjson(p):return json.loads(Path(p).read_text(encoding='utf-8'))

def oldfolder(old101,oldmultiseed,seed,pct):
    root=Path(old101) if seed==101 else Path(oldmultiseed)/f'seed_{seed}'
    return root/('baseline' if pct==0 else 'active_15_combinado')

def scan_run(path,seed,pct,oldroot):
    path=Path(path)
    man=readjson(path/'manifest_H09.json')
    expected='baseline' if pct==0 else 'active'
    if man.get('status')!='SUMO_EXECUTED_EXPLORATORY' or man['mode']!=expected:
        raise ValueError('Manifest incompleto o modo inesperado: '+str(path))
    if (int(man['seed'])!=seed or int(man['porcentaje_solicitado'])!=pct or
        int(man['pasos_requested'])!=600 or float(man['step_length_s'])!=0.5):
        raise ValueError('Semilla, porcentaje o reloj distintos: '+str(path))
    orig=man['original_hashes_sha256']
    expected_core={}
    for filename,sha in orig.items():
        fn=Path(filename)
        if not fn.exists() or digest(fn)!=sha:raise ValueError('Entrada original modificada: '+filename)
        if fn.name.endswith('.net.xml'):k='net'
        elif fn.name.endswith('.rou.xml'):k='routes'
        elif fn.suffix.lower()=='.sumocfg':k='sumocfg'
        else:continue
        expected_core[k]=sha
    if set(expected_core)!=set(('net','routes','sumocfg')):
        raise ValueError('Inputs núcleo incompletos')
    for filename,sha in man['generated_hashes_sha256'].items():
        fn=Path(filename)
        if not fn.exists() or digest(fn)!=sha:
            raise ValueError('Archivo generado alterado: '+filename)
    if digest(path/'trafico_h09.csv')!=man['traffic_sha256']:
        raise ValueError('Hash de tráfico del manifiesto incorrecto: '+str(path))
    events=readcsv(path/'eventos_h09.csv')
    traffic=readcsv(path/'trafico_h09.csv')
    cohort=readcsv(path/'cohorte_h09.csv')
    exposure=readcsv(path/'exposicion_h09.csv')
    if len(traffic)!=600:raise ValueError('Duración no comparable: '+str(path))
    assigned={r['vehicle_id'] for r in cohort if r['assigned']=='1'}
    roster={r['vehicle_id'] for r in cohort}
    if len(roster)!=300 or len(cohort)!=300 or len(assigned)!=pct*3:
        raise ValueError('Cohorte o porcentaje incorrectos: '+str(path))
    exp={r['vehicle_id']:r for r in exposure}
    if set(exp)!=assigned:raise ValueError('CSV de exposición inconsistente: '+str(path))
    numseen=sum(int(r['seen']) for r in exposure)
    numverified=sum(int(r['profile_verified']) for r in exposure)
    if not numseen==numverified==man['exposure_summary']['n_selected_seen']:
        raise ValueError('Perfil no verificado para observado')
    if pct==0 and (numseen!=0 or assigned):raise ValueError('Baseline contaminado')
    if pct==15 or pct==0:
        old=readjson(Path(oldroot)/'manifest_H09.json')
        if man['traffic_sha256']!=old['traffic_sha256']:
            raise ValueError('El observador H09 v1.5 modificó el tráfico respecto a H09 v1.4.3: '+str(path))
    identifiers=set();episodes=defaultdict(lambda:{'opps':set(),'exposures':set(),'cross':[], 'vehicles':set()})
    crossings=[];unmatched=0
    for row in events:
        typ=row['event_type'];phase=row['signal_state'];ep=row['measurement_id']
        if typ in ('tls_phase_exposure','tls_moving_opportunity'):
            if not ep or (typ,row['passage_id']) in identifiers:
                raise ValueError('Episodio sin id o evento duplicado')
            identifiers.add((typ,row['passage_id']))
            if typ=='tls_phase_exposure':episodes[ep]['exposures'].add(phase)
            else:episodes[ep]['opps'].add(phase)
            episodes[ep]['vehicles'].add(row['vehicle_id'])
        if typ=='stopline':crossings.append(row)
        if typ=='tls_crossing_link':
            if not ep:unmatched+=1
            else:episodes[ep]['cross'].append(row)
    if len(crossings)!=sum(r['event_type']=='tls_crossing_link' for r in events):
        raise ValueError('Cruces sin fila de enlace 1:1')
    if len(crossings)!=man['instrumental_stats']['stopline_events']:
        raise ValueError('Número de cruces inconsistente')
    n_selected_opps={p:0 for p in ('red','yellow','green')}
    n_all_opps={p:0 for p in ('red','yellow','green')}
    n_selected_exposures={p:0 for p in ('red','yellow','green')}
    n_all_exposures={p:0 for p in ('red','yellow','green')}
    n_linked_cross={p:0 for p in ('red','yellow')}
    unmatched_eligible={p:0 for p in ('red','yellow')}
    for episode,x in episodes.items():
        for phase in x['exposures']:
            n_all_exposures[phase]+=1
            if x['vehicles']<=assigned:n_selected_exposures[phase]+=1
        for phase in x['opps']:
            n_all_opps[phase]+=1
            if x['vehicles']<=assigned:n_selected_opps[phase]+=1
        for cr in x['cross']:
            state=cr['signal_state']
            if state in ('red','yellow') and cr['classification_quality']=='confirmed':
                if state in x['opps'] and x['vehicles']<=assigned:
                    n_linked_cross[state]+=1
                else:unmatched_eligible[state]+=1
    return {'seed':seed,'pct':pct,'n_roster':len(roster),'n_assigned':len(assigned),
      'n_selected_seen':numseen,'n_verified':numverified,'n_selected_never_seen':len(assigned)-numseen,
      'n_crossings':len(crossings),
      'red_crossings':sum(r['signal_state']=='red' and r['classification_quality']=='confirmed' for r in crossings),
      'yellow_crossings':sum(r['signal_state']=='yellow' and r['classification_quality']=='confirmed' for r in crossings),
      'unknown_crossings':sum(r['signal_state']=='unknown' for r in crossings),
      'exposure_red_all':n_all_exposures['red'],'exposure_yellow_all':n_all_exposures['yellow'],
      'exposure_red_selected':n_selected_exposures['red'],'exposure_yellow_selected':n_selected_exposures['yellow'],
      'moving_red_all':n_all_opps['red'],'moving_yellow_all':n_all_opps['yellow'],
      'moving_red_selected':n_selected_opps['red'],'moving_yellow_selected':n_selected_opps['yellow'],
      'linked_red_selected':n_linked_cross['red'],'linked_yellow_selected':n_linked_cross['yellow'],
      'red_cross_not_linked_to_moving_candidate':unmatched_eligible['red'],
      'yellow_cross_not_linked_to_moving_candidate':unmatched_eligible['yellow'],
      'unlinked_crossing_episodes':unmatched,
      'arrivals':sum(int(t['arrivals_step']) for t in traffic),
      'mean_speed_kmh':mean(float(t['mean_speed_kmh']) for t in traffic),
      'mean_halted':mean(float(t['n_halted']) for t in traffic),
      'traffic_sha256':man['traffic_sha256'],'core_hashes':expected_core,
      'selected_ids':sorted(assigned)}

def summarize(records):
    byseed=defaultdict(dict)
    for r in records:
        if r['pct'] in byseed[r['seed']]:raise ValueError('Run duplicada')
        byseed[r['seed']][r['pct']]=r
    if set(byseed)!=set(SEEDS) or any(set(a)!=set(PCTS) for a in byseed.values()):
        raise ValueError('Faltan semillas o niveles')
    # Cohortes anidadas e inputs idénticos en todas las semillas.
    allcores={tuple(sorted(d[0]['core_hashes'].items())) for d in byseed.values()}
    if len(allcores)!=1:raise ValueError('Inputs núcleo diferentes entre semillas')
    for seed,d in byseed.items():
        if not set(d[15]['selected_ids'])<=set(d[30]['selected_ids'])<=set(d[50]['selected_ids']):
            raise ValueError('Cohortes no anidadas: '+str(seed))
        if any(x['core_hashes']!=d[0]['core_hashes'] for x in d.values()):
            raise ValueError('Red/rutas/sumocfg distintos: '+str(seed))
    cols=['seed','pct','n_roster','n_assigned','n_selected_seen','n_verified',
      'n_selected_never_seen','n_crossings','red_crossings','yellow_crossings',
      'unknown_crossings','exposure_red_all','exposure_yellow_all','exposure_red_selected',
      'exposure_yellow_selected','moving_red_all','moving_yellow_all','moving_red_selected',
      'moving_yellow_selected','linked_red_selected','linked_yellow_selected',
      'red_cross_not_linked_to_moving_candidate','yellow_cross_not_linked_to_moving_candidate',
      'unlinked_crossing_episodes','arrivals','mean_speed_kmh','mean_halted','traffic_sha256']
    clean=[{k:r[k] for k in cols} for r in sorted(records,key=lambda x:(x['seed'],x['pct']))]
    paired=[]
    for seed,d in sorted(byseed.items()):
        for pct in (15,30,50):
            a=d[pct];b=d[0]
            paired.append({'seed':seed,'pct':pct,
                'delta_arrivals_vs_baseline':a['arrivals']-b['arrivals'],
                'delta_mean_speed_kmh_vs_baseline':a['mean_speed_kmh']-b['mean_speed_kmh'],
                'delta_mean_halted_vs_baseline':a['mean_halted']-b['mean_halted'],
                'delta_red_vs_baseline':a['red_crossings']-b['red_crossings'],
                'delta_yellow_vs_baseline':a['yellow_crossings']-b['yellow_crossings'],
                'selected_moving_red_candidates':a['moving_red_selected'],
                'selected_moving_yellow_candidates':a['moving_yellow_selected']})
    summary=[]
    for pct in PCTS:
        entries=[r for r in clean if r['pct']==pct]
        summary.append({'pct':pct,'n_seeds':5,
             'mean_arrivals':mean(r['arrivals'] for r in entries),
             'red_cross_sum':sum(r['red_crossings'] for r in entries),
             'yellow_cross_sum':sum(r['yellow_crossings'] for r in entries),
             'unknown_cross_sum':sum(r['unknown_crossings'] for r in entries),
             'selected_phase_red_sum':sum(r['exposure_red_selected'] for r in entries),
             'selected_phase_yellow_sum':sum(r['exposure_yellow_selected'] for r in entries),
             'selected_moving_red_sum':sum(r['moving_red_selected'] for r in entries),
             'selected_moving_yellow_sum':sum(r['moving_yellow_selected'] for r in entries),
             'selected_verified_sum':sum(r['n_verified'] for r in entries),
             'selected_assigned_sum':sum(r['n_assigned'] for r in entries)})
    return {'status':'H09_V15_SENSITIVITY_DESCRIPTIVE_NOT_QUITO_CALIBRATED',
        'scope':'HANGZHOU_4x4_OBSERVATIONAL_PROXY', 'seeds':list(SEEDS),
        'percentages':list(PCTS), 'runs':clean,'paired':paired,'summary':summary,
        'limitations':[
            'Proxy de oportunidad: primera observación en movimiento >=1 m/s dentro de 30 m de TLS, por episodio y color',
            'No equivale a probabilidad individual ni denominador del estudio de Quito',
            'Rojo/amarillo ambiguos se conservan como unknown',
            'Los cruces sin vínculo a episodio/oportunidad no se convierten en probabilidades',
            'Sin Vine, sin nuevas calibraciones empíricas, sin evaluación de agentes RL',
            'Intensidad de perfil fija: experimental y no calibrada',
            'Cinco semillas con una misma red/demanda: resultados exploratorios']}

def writecsv(path,rows):
    if path.exists():raise FileExistsError(path)
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--old101',type=Path,required=True)
    p.add_argument('--oldmultiseed',type=Path,required=True)
    p.add_argument('--output-prefix',type=Path,required=True)
    a=p.parse_args(argv)
    records=[]
    for seed in SEEDS:
        for pct in PCTS:
            dirname='baseline' if pct==0 else f'active_{pct}_combinado'
            path=a.root/f'seed_{seed}'/dirname
            prior=oldfolder(a.old101,a.oldmultiseed,seed,pct) if pct in (0,15) else None
            records.append(scan_run(path,seed,pct,prior))
    result=summarize(records)
    prefix=Path(a.output_prefix)
    paths=[prefix.with_suffix('.json'),Path(str(prefix)+'_por_semilla.csv'),
           Path(str(prefix)+'_contrastes.csv'),Path(str(prefix)+'_resumen.csv')]
    if any(x.exists() for x in paths):raise FileExistsError('Informe ya existe')
    prefix.parent.mkdir(parents=True,exist_ok=True)
    paths[0].write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    for path,key in zip(paths[1:],('runs','paired','summary')):writecsv(path,result[key])
    print('VALIDADAS',len(records),'corridas | semillas',list(SEEDS),'| niveles',list(PCTS))
    print('H09 V15',result['status'])
    for r in result['summary']:
        print('pct',r['pct'],'rojos',r['red_cross_sum'],'amarillos',r['yellow_cross_sum'],
              'candidatas_rojas_seleccionados',r['selected_moving_red_sum'],
              'exposicion_verificada',str(r['selected_verified_sum'])+'/'+str(r['selected_assigned_sum']))
    print('REPORTES',*[str(x) for x in paths])

if __name__=='__main__':main()
