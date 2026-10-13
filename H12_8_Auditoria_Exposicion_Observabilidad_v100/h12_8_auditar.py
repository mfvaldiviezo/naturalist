#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.8: análisis offline de exposición B1, instantes de decisión y estado PPO.

No importa SUMO, TraCI ni modelos; únicamente lee los JSON H12.7 originales.
NO atribuye cambios globales al semáforo B1 ni afirma resiliencia.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import uuid

SCHEMA = 'H12_8-v1.0'
SEGMENTS = {'queue_12': (0,12), 'wait_12': (12,24), 'pressure_4': (24,28),
            'phase_4': (28,32), 'phase_age_2': (32,34)}


def load_json(path):
    with Path(path).open('r',encoding='utf-8-sig') as f:
        return json.load(f,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('JSON nonfinite '+x)))


def require(cond, message):
    if not cond:
        raise ValueError('H12.8 FAIL-CLOSED: '+message)


def numeric(value, label):
    if isinstance(value,bool):
        raise ValueError(label+' bool no es un número')
    v=float(value)
    require(math.isfinite(v),label+' no finito')
    return v


def series_quality(values):
    nums=[numeric(v,'segmento 34D') for v in values]
    return {'min':min(nums),'max':max(nums),'nonzero':sum(abs(v)>1e-9 for v in nums),
            'max_abs':max(abs(v) for v in nums)}


def validate_and_extract(n,a):
    required=['result','model','checkpoint_sha256','inputs','n_decisions','n_microticks',
              'decisions','h12_7_diagnostic','microticks','trace_sha256','commands']
    for tag,doc in [('nominal',n),('activo',a)]:
        require(all(k in doc for k in required),tag+' campos obligatorios ausentes')
        require(doc['result']=='SMOKE_OK',tag+' SMOKE_OK ausente')
        require(len(doc['decisions'])==doc['n_decisions'] and len(doc['microticks'])==doc['n_microticks'],tag+' horizonte truncado')
        require(doc['h12_7_diagnostic']['b1_microticks'] is not None,tag+' telemetría B1 ausente')
        require(len(doc['h12_7_diagnostic']['b1_microticks'])==doc['n_microticks'],tag+' microticks B1 incompletos')
        require(doc['h12_7_diagnostic']['initial_state_34d'] is not None,tag+' estado inicial ausente')
        require(doc['mode']==('nominal' if tag=='nominal' else 'active'),tag+' modo inesperado')
    require(n['model']==a['model'],'modelo PPO diferente')
    require(n['checkpoint_sha256']==a['checkpoint_sha256'],'checkpoints diferentes')
    require(n['n_decisions']==a['n_decisions'] and n['n_microticks']==a['n_microticks'],'horizontes diferentes')
    require(n['n_microticks']==n['n_decisions']*10,'relación 10 microticks por decisión rota')
    require(n['commands']==0 and a['commands']>0,'comandos nominal/active inválidos')
    require(n['trace_sha256']!=a['trace_sha256'],'sin efecto cinemático registrado (SHA igual)')
    for k in ('net_sha256','routes_sha256','cfg_original_sha256'):
        require(n['inputs'][k]==a['inputs'][k],k+' no emparejado')
    require(n['h10_source_sha256']==a['h10_source_sha256'],'fuentes H10 distintas')
    for k in ('controlled_lanes_unique_raw','controlled_lanes_used_12','outgoing_lanes','green_phases'):
        require(n['h12_7_diagnostic'][k]==a['h12_7_diagnostic'][k],k+' distinto')
    for tag,d in [('nominal',n),('activo',a)]:
        for i,rec in enumerate(d['decisions']):
            require(rec['i']==i,tag+' índice decisión incorrecto')
            for f in ('state_before_34d','state_after_34d'):
                vec=rec[f]
                require(len(vec)==34,tag+' '+f+' != 34')
                for j,x in enumerate(vec): numeric(x,f'{tag} {f}[{i}][{j}]')
        for x in d['h12_7_diagnostic']['initial_state_34d']:
            numeric(x,tag+' estado inicial')
        for j,(row,traffic) in enumerate(zip(d['h12_7_diagnostic']['b1_microticks'],d['microticks'])):
            require(row['tick']==traffic['tick'],tag+' orden microtick erróneo')
            require(abs(numeric(row['time_s'],'tiempo')-numeric(traffic['time_s'],'tiempo'))<1e-7,tag+' tiempos internos incoherentes')
            require(row['n_b1']>=0 and row['halted_b1']>=0,tag+' vehículos negativos')
            require(row['halted_b1']<=row['n_b1'],tag+' detenidos > vehículos')
            require(row['n_b1']==sum(v['n'] for v in row['lanes']),tag+' conteo por carril inconsistente')
            require(row['halted_b1']==sum(v['halted'] for v in row['lanes']),tag+' detenciones por carril inconsistentes')
    for i,(x,y) in enumerate(zip(n['decisions'],a['decisions'])):
        require(abs(x['sim_time_s']-y['sim_time_s'])<1e-7,'tiempos de decisión distintos')
    for i,(x,y) in enumerate(zip(n['h12_7_diagnostic']['b1_microticks'],a['h12_7_diagnostic']['b1_microticks'])):
        require(abs(x['time_s']-y['time_s'])<1e-7,'B1 time alignment '+str(i))
    return n,a


def state_summary(doc):
    diag=doc['h12_7_diagnostic'];dec=doc['decisions']
    vectors=[diag['initial_state_34d']]+[d['state_after_34d'] for d in dec]
    return {
        'distinct_full_vectors':len({tuple(round(numeric(v,'state'),9) for v in x) for x in vectors}),
        'n_traffic_segments_nonzero_per_decision':[
            {name:sum(abs(numeric(x,'state'))>1e-9 for x in d['state_after_34d'][lo:hi])
             for name,(lo,hi) in SEGMENTS.items()}
            for d in dec],
        'segments':{name:{'any_nonzero':any(abs(numeric(x,'state'))>1e-9 for vec in vectors for x in vec[lo:hi]),
                          'ever_changes':any(any(abs(numeric(v[i],'state')-numeric(vectors[0][i],'state'))>1e-8 for i in range(lo,hi)) for v in vectors[1:]),
                          'max_abs':max(abs(numeric(x,'state')) for vec in vectors for x in vec[lo:hi])}
                    for name,(lo,hi) in SEGMENTS.items()},
    }


def compare(n,a):
    validate_and_extract(n,a)
    dn=n['h12_7_diagnostic']; da=a['h12_7_diagnostic']
    rn=dn['b1_microticks'];ra=da['b1_microticks']
    different=[]
    for x,y in zip(rn,ra):
        entry={'time_s':x['time_s'],'tick':x['tick'],
               'n_diff':y['n_b1']-x['n_b1'],
               'halt_diff':y['halted_b1']-x['halted_b1'],
               'wait_diff':numeric(y['waiting_b1_s'],'wait')-numeric(x['waiting_b1_s'],'wait')}
        entry['changed']=bool(entry['n_diff'] or entry['halt_diff'] or abs(entry['wait_diff'])>1e-8)
        different.append(entry)
    boundaries=[]
    for i,(xn,xa) in enumerate(zip(n['decisions'],a['decisions'])):
        tn=numeric(xn['sim_time_s'],'decision time')
        matches=[j for j,r in enumerate(rn) if abs(numeric(r['time_s'],'tick time')-tn)<1e-7]
        require(len(matches)==1,'Decisión sin microtick exacto en t='+str(tn))
        j=matches[0];rnom=rn[j];ract=ra[j]
        before_diff=sum(abs(float(x)-float(y))>1e-8 for x,y in zip(xn['state_before_34d'],xa['state_before_34d']))
        after_diff=sum(abs(float(x)-float(y))>1e-8 for x,y in zip(xn['state_after_34d'],xa['state_after_34d']))
        boundaries.append({'decision':i,'time_s':tn,'tick':int(rnom['tick']),
           'nom_b1_vehicles':rnom['n_b1'],'active_b1_vehicles':ract['n_b1'],
           'nom_b1_halted':rnom['halted_b1'],'active_b1_halted':ract['halted_b1'],
           'nom_b1_wait_s':rnom['waiting_b1_s'],'active_b1_wait_s':ract['waiting_b1_s'],
           'nom_queue_metric':xn['queue'],'active_queue_metric':xa['queue'],
           'nom_delay_metric':xn['delay_proxy'],'active_delay_metric':xa['delay_proxy'],
           'nom_reward':xn['reward'],'active_reward':xa['reward'],
           'nom_action':xn['action'],'active_action':xa['action'],
           'before_34d_diff_count':before_diff,'after_34d_diff_count':after_diff,
           'mismatch_nom_halt_vs_queue':rnom['halted_b1']>0 and abs(numeric(xn['queue'],'queue'))<1e-8,
           'mismatch_active_halt_vs_queue':ract['halted_b1']>0 and abs(numeric(xa['queue'],'queue'))<1e-8,
           'mismatch_nom_wait_vs_delay':numeric(rnom['waiting_b1_s'],'wait')>1e-8 and abs(numeric(xn['delay_proxy'],'delay'))<1e-8,
           'mismatch_active_wait_vs_delay':numeric(ract['waiting_b1_s'],'wait')>1e-8 and abs(numeric(xa['delay_proxy'],'delay'))<1e-8})
    lanes=dn['controlled_lanes_used_12'];unique=dn['controlled_lanes_unique_raw'];green=dn['green_phases']
    require(len(lanes)==12,'esperados 12 carriles usados en representación heredada')
    require(len(green)>0,'fases verdes no disponibles')
    action_to_phase={str(action):green[action%len(green)] for action in range(4)}
    result={
      'status':'H12_8_OFFLINE_OK','version':SCHEMA,
      'model':n['model'],'n_decisions':n['n_decisions'],'n_microticks':n['n_microticks'],
      'nominal_trace_sha256':n['trace_sha256'],'active_trace_sha256':a['trace_sha256'],
      'active_commands':a['commands'],
      'exposure':{
        'nominal_ticks_with_vehicles':sum(r['n_b1']>0 for r in rn),
        'active_ticks_with_vehicles':sum(r['n_b1']>0 for r in ra),
        'nominal_ticks_with_halted':sum(r['halted_b1']>0 for r in rn),
        'active_ticks_with_halted':sum(r['halted_b1']>0 for r in ra),
        'nominal_ticks_with_wait':sum(numeric(r['waiting_b1_s'],'wait')>1e-8 for r in rn),
        'active_ticks_with_wait':sum(numeric(r['waiting_b1_s'],'wait')>1e-8 for r in ra),
        'n_microticks_B1_count_difference':sum(r['n_diff']!=0 for r in different),
        'n_microticks_B1_halt_difference':sum(r['halt_diff']!=0 for r in different),
        'n_microticks_B1_wait_difference':sum(abs(r['wait_diff'])>1e-8 for r in different),
        'first_B1_aggregate_difference_s':next((r['time_s'] for r in different if r['changed']),None),
        'n_decision_boundaries_with_halted_nom':sum(r['nom_b1_halted']>0 for r in boundaries),
        'n_decision_boundaries_with_halted_active':sum(r['active_b1_halted']>0 for r in boundaries),
        'n_decision_boundaries_with_wait_nom':sum(numeric(r['nom_b1_wait_s'],'wait')>1e-8 for r in boundaries),
        'n_decision_boundaries_with_wait_active':sum(numeric(r['active_b1_wait_s'],'wait')>1e-8 for r in boundaries),
        'n_halt_queue_inconsistencies':sum(r['mismatch_nom_halt_vs_queue'] or r['mismatch_active_halt_vs_queue'] for r in boundaries),
        'n_wait_delay_inconsistencies':sum(r['mismatch_nom_wait_vs_delay'] or r['mismatch_active_wait_vs_delay'] for r in boundaries),
        'n_decision_boundary_34d_differences':sum(r['after_34d_diff_count']>0 for r in boundaries),
        'n_decision_boundary_action_differences':sum(r['nom_action']!=r['active_action'] for r in boundaries)
      },
      'representation':{
        'controlled_unique_raw_count':len(unique),'controlled_lanes_unique_raw':unique,
        'controlled_lanes_12':lanes,
        'controlled_lanes_unique_in_12':len(set(lanes)),
        'lane_multiplicities':dict(Counter(lanes)),
        'outgoing_lanes_count':len(dn['outgoing_lanes']),
        'green_phase_indices':green,
        'action_to_sumo_phase':action_to_phase,
        'unique_phase_targets':len(set(action_to_phase.values())),
        'nominal_actions':dict(Counter(str(d['action']) for d in n['decisions'])),
        'active_actions':dict(Counter(str(d['action']) for d in a['decisions'])),
        'nominal_states':state_summary(n),
        'active_states':state_summary(a)
      },
      'boundaries':boundaries,
      'microtick_local_differences':different,
      'limitations':[
        'No es inferencia de resiliencia ni calibración poblacional a Quito.',
        'No identifica la localización de vehículos Vine por ID; H12.7 no guardó IDs en B1.',
        'Las perturbaciones globales pueden no coincidir con microticks de decisión PPO.',
        'No puede corregir la semántica 34D ni asegurar validez de checkpoints entrenados.',
        'Revisar interverdes/amarillos y protocolos multiintersección antes de comparar SOTA.'
      ]
    }
    return result


def fmt(x): return '—' if x is None else str(x)


def render_markdown(r):
    e=r['exposure'];s=r['representation'];b=r['boundaries']
    lines=[
        '# H12.8 — Auditoría offline de exposición y observabilidad B1','',
        '**Estado:** '+r['status']+' · Modelo `'+r['model']+'` · '+str(r['n_decisions'])+' decisiones · '+str(r['n_microticks'])+' microticks.','',
        '## Exposición local y diferencias nominal–Vine','',
        '| Indicador | Resultado |','|---|---:|',
        f"| Microticks con vehículos, nominal/activo | {e['nominal_ticks_with_vehicles']}/{e['active_ticks_with_vehicles']} |",
        f"| Microticks con detenidos, nominal/activo | {e['nominal_ticks_with_halted']}/{e['active_ticks_with_halted']} |",
        f"| Microticks con espera registrada, nominal/activo | {e['nominal_ticks_with_wait']}/{e['active_ticks_with_wait']} |",
        f"| Microticks con diferencia de número de vehículos en B1 | {e['n_microticks_B1_count_difference']} |",
        f"| Microticks con diferencia de detenidos en B1 | {e['n_microticks_B1_halt_difference']} |",
        f"| Microticks con diferencia de espera en B1 | {e['n_microticks_B1_wait_difference']} |",
        f"| Primera diferencia agregada B1 | {fmt(e['first_B1_aggregate_difference_s'])} s |",
        f"| Decisiones con B1 detenido (nominal/activo) | {e['n_decision_boundaries_with_halted_nom']}/{e['n_decision_boundaries_with_halted_active']} |",
        f"| Decisiones con B1 esperando (nominal/activo) | {e['n_decision_boundaries_with_wait_nom']}/{e['n_decision_boundaries_with_wait_active']} |",
        f"| Discrepancias detenidos B1 > 0 y cola TSCEnv = 0 | {e['n_halt_queue_inconsistencies']} |",
        f"| Discrepancias espera B1 > 0 y demora TSCEnv = 0 | {e['n_wait_delay_inconsistencies']} |",
        f"| Observaciones 34D distintas en frontera de decisión | {e['n_decision_boundary_34d_differences']} |",
        f"| Acciones semafóricas distintas | {e['n_decision_boundary_action_differences']} |",
        '', '## Semántica del estado y acciones','',
        f"- Carriles crudos únicos de B1: **{s['controlled_unique_raw_count']}**; usados en 12D: **{s['controlled_lanes_unique_in_12']} únicos**.",
        '- Repeticiones de carriles (nombre → cantidad): '+', '.join('`'+str(k)+'`='+str(v) for k,v in s['lane_multiplicities'].items()),
        f"- Carriles salientes calculados: **{s['outgoing_lanes_count']}**. La presión no implementa plenamente entrantes menos salientes.",
        '- Fases verdes detectadas: '+str(s['green_phase_indices']),
        '- Mapeo acción PPO → fase SUMO: '+', '.join(str(k)+'→'+str(v) for k,v in s['action_to_sumo_phase'].items())+'.',
        f"- Objetivos semafóricos distintos disponibles: **{s['unique_phase_targets']}** para un espacio de 4 acciones.",
        '- Frecuencia de acciones nominal: '+str(s['nominal_actions'])+'; activo: '+str(s['active_actions'])+'.',
        f"- Estados completos distintos (incluyendo edad de fase), nominal/activo: {s['nominal_states']['distinct_full_vectors']}/{s['active_states']['distinct_full_vectors']}.",
        '', '## Actividad por decisión y consistencia de sensores','',
        '| t (s) | Veh N/A | Det N/A | Espera N/A (s) | Cola N/A | 34D dif. | Acción N/A |',
        '|---:|---:|---:|---:|---:|---:|:---:|',
    ]
    for x in b:
        lines.append(f"| {x['time_s']:.1f} | {x['nom_b1_vehicles']}/{x['active_b1_vehicles']} | {x['nom_b1_halted']}/{x['active_b1_halted']} | {float(x['nom_b1_wait_s']):.3f}/{float(x['active_b1_wait_s']):.3f} | {float(x['nom_queue_metric']):.3f}/{float(x['active_queue_metric']):.3f} | {x['after_34d_diff_count']} | {x['nom_action']}/{x['active_action']} |")
    lines+=['','## Interpretación condicional','']
    if e['n_halt_queue_inconsistencies'] or e['n_wait_delay_inconsistencies']:
        lines.append('- **ALERTA SENSOR:** en fronteras de decisión hay detención/espera medida en B1 y métricas TSCEnv = 0. Investigar carriles y secuencia de lectura. No entrenar ni evaluar resiliencia hasta resolverlo.')
    else:
        lines.append('- No se observó una discrepancia detenidos→cola ni espera→demora en fronteras de decisión. Los ceros pueden ser reales en esos instantes; eso no valida la semántica 34D.')
    if e['n_microticks_B1_count_difference']+e['n_microticks_B1_halt_difference']+e['n_microticks_B1_wait_difference']==0:
        lines.append('- Las magnitudes agregadas B1 observadas en cada microtick no se distinguen entre nominal y Vine. Esto no prueba ausencia de cambios cinemáticos individuales ni de otros carriles de la red.')
    elif e['n_decision_boundary_34d_differences']==0:
        lines.append('- B1 presenta diferencias agregadas en algunos microticks, pero no modificó los 34 valores observados en las decisiones: existe una posible pérdida de información temporal o por agregación.')
    else:
        lines.append('- Se detectaron diferencias en observaciones 34D; revisar acciones y política sin atribuir automáticamente adaptación.')
    lines +=['- **Limitación estructural:** el espacio 4D de acciones no representa cuatro fases verdes independientes cuando hay solo dos fases detectadas; esto requiere homologación con los checkpoints y SOTA.',
             '- **No cambiar ahora la codificación de estados/acciones del checkpoint** sin examinar las configuraciones de entrenamiento y repetir la validación.',
             '', '## Límites del informe']
    lines += ['- '+x for x in r['limitations']]
    lines.append('')
    return '\n'.join(lines)


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--h127-dir',type=Path,required=True,help='Carpeta de resultados h12_7_estado_b1_*')
    p.add_argument('--results-root',type=Path,default=Path('resultados'))
    args=p.parse_args(argv)
    folder=args.h127_dir.resolve()
    nom_file=folder/'nominal/piloto_h12_5.json';active_file=folder/'active/piloto_h12_5.json'
    require(nom_file.is_file() and active_file.is_file(),'se requieren JSON originales H12.7 nominal y activo')
    analysis_file=folder/'analisis_estado_b1.json'
    require(analysis_file.is_file(),'análisis acreditado H12.7 no encontrado')
    existing=load_json(analysis_file)
    require(existing.get('result')=='H12_7_DIAGNOSTICO_OK','H12.7 sin diagnóstico OK')
    nom=load_json(nom_file);active=load_json(active_file)
    require(existing['nominal_trace_sha256']==nom['trace_sha256'] and existing['active_trace_sha256']==active['trace_sha256'], 'archivos H12.7 no coinciden con análisis previo')
    require(existing['active_commands_confirmed']==active['commands'],'comandos H12.7 no confirmados')
    report=compare(nom,active)
    report['input_sha256']={str(q.resolve()):hashlib.sha256(q.read_bytes()).hexdigest() for q in (nom_file,active_file,analysis_file)}
    root=args.results_root.resolve();root.mkdir(parents=True,exist_ok=True)
    dst=root/('h12_8_offline_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6]);dst.mkdir(exist_ok=False)
    (dst/'auditoria_h12_8.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (dst/'dictamen_h12_8.md').write_text(render_markdown(report),encoding='utf-8')
    print('H12_8_OFFLINE_OK')
    print('B1_MICROTICKS_DIFERENTES',sum(x['changed'] for x in report['microtick_local_differences']))
    print('DIFERENCIAS_34D',report['exposure']['n_decision_boundary_34d_differences'])
    print('DISCREPANCIAS_SENSORES',report['exposure']['n_halt_queue_inconsistencies'],report['exposure']['n_wait_delay_inconsistencies'])
    print('INFORME',dst)
    return 0


if __name__=='__main__':
    try:sys.exit(run())
    except Exception as exc:
        print('H12.8 BLOQUEADO:',type(exc).__name__,str(exc),file=sys.stderr)
        sys.exit(2)
