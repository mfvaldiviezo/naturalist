#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.10 — Auditoria offline de las distribuciones PPO en estados 34D H12.9.

Solo lectura de fuentes/checkpoint/JSON. NO ejecuta SUMO, NO entrena,
NO altera checkpoint ni la codificacion heredada del entorno.
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

VERSION='H12.10-v1.0.1'
SEGMENTS={'cola_12':(0,12),'espera_12':(12,24),'presion_4':(24,28),'fase_4':(28,32),'edad_2':(32,34)}
MODELS={'ppo_ideal','ppo_chaos','ppo_coop_ideal','ppo_coop_chaos'}


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def finite(x):
    y=float(x)
    if not math.isfinite(y):
        raise ValueError('Numero no finito')
    return y


# Contrato REAL del TSCEnv heredado (tsc_framework/src/core/tsc_env.py):
# [0:32] cola, espera, presion clip, one-hot en [0,1].
# [32] edad de fase / MAX_PHASE_AGE (120 s), SIN clip: puede exceder 1.
# [33] clip de la misma edad a [0,1]. El Box original declara [0,1]^34,
# pero no refleja la salida real de _get_state() tras 120 s sin cambiar fase.
# No normalizar, truncar ni transformar ninguna observacion: el PPO recibio
# el valor original. Limite fisico de este piloto: horizonte 300/120 = 2.5.
PHASE_AGE_MAX_FOR_300S = 300.0 / 120.0
OBS_TOL = 1e-5


def obs34(value):
    if not isinstance(value,list) or len(value)!=34:
        raise ValueError('Se requieren exactamente 34 observaciones, sin relleno')
    out=[finite(x) for x in value]
    if any(x < -OBS_TOL or x > 1.0 + OBS_TOL for x in out[:32]):
        raise ValueError('Componente 0..31 fuera del rango esperado [0,1]')
    tau_raw, tau_clip = out[32:34]
    if tau_raw < -OBS_TOL or tau_raw > PHASE_AGE_MAX_FOR_300S + OBS_TOL:
        raise ValueError('Edad de fase / 120 fuera del horizonte H12.9 de 300 s')
    if tau_clip < -OBS_TOL or tau_clip > 1.0 + OBS_TOL:
        raise ValueError('Edad de fase recortada fuera de [0,1]')
    if abs(tau_clip - min(max(tau_raw, 0.0), 1.0)) > OBS_TOL:
        raise ValueError('Las dos componentes de edad de fase no corresponden al contrato TSCEnv')
    return out


def read_run(directory,mode):
    f=Path(directory)/mode/'piloto_h12_5.json'
    if not f.is_file():raise FileNotFoundError(str(f))
    d=json.loads(f.read_text(encoding='utf-8-sig'))
    if d.get('result')!='SMOKE_OK' or d.get('mode')!=mode:
        raise ValueError('Resultado no acreditado en '+mode)
    if (d.get('n_decisions'),d.get('n_microticks'),d.get('end_time_s'))!=(60,600,300.0):
        raise ValueError('Horizonte H12.9 no homologado en '+mode)
    if len(d.get('decisions',[]))!=60 or len(d.get('microticks',[]))!=600:
        raise ValueError('Registros incompletos en '+mode)
    for i,rec in enumerate(d['decisions']):
        if rec.get('i')!=i or int(rec.get('action',-1)) not in range(4):
            raise ValueError('Indice/accion invalida en '+mode)
        if abs(finite(rec.get('sim_time_s'))-(i+1)*5.0)>1e-6:
            raise ValueError('Tiempo de decision invalido en '+mode)
        obs34(rec.get('state_before_34d'))
        obs34(rec.get('state_after_34d'))
    dx=d.get('h12_7_diagnostic') or {}
    if len(dx.get('b1_microticks',[]))!=600:
        raise ValueError('Diagnostico B1 faltante en '+mode)
    phases=dx.get('green_phases')
    if not isinstance(phases,list) or not phases or any(not isinstance(x,int) for x in phases):
        raise ValueError('Fases verdes ausentes en '+mode)
    if any(int(r.get('collisions',0))>0 or int(r.get('teleports_start',0))>0 for r in d['microticks']):
        raise ValueError('Colision/teleport invalida en '+mode)
    return d


def check_pair(docs):
    n,p,a=(docs[x] for x in ('nominal','probe','active'))
    for key in ('model','checkpoint_sha256','h10_reference_path','h10_reference_n','h10_source_sha256'):
        if any(d.get(key)!=n.get(key) for d in (p,a)):
            raise ValueError('Emparejamiento roto: '+key)
    for key in ('net_sha256','routes_sha256','cfg_original_sha256'):
        if any(d.get('inputs',{}).get(key)!=n.get('inputs',{}).get(key) for d in (p,a)):
            raise ValueError('Entradas distintas: '+key)
    if n.get('trace_sha256')!=p.get('trace_sha256'):
        raise ValueError('Nominal/probe no identicos')
    if (n.get('commands'),p.get('commands'))!=(0,0) or int(a.get('commands',0))<1:
        raise ValueError('Condiciones de intervencion incorrectas')
    if a.get('trace_sha256')==n.get('trace_sha256'):
        raise ValueError('No hay efecto en la traza activa')
    vm=a.get('extra',{}).get('vine',{})
    if vm.get('n_commands')!=a.get('commands') or vm.get('n_commands_confirmed')!=a.get('commands') or vm.get('remaining_pending')!=0:
        raise ValueError('Comandos Vine no confirmados')
    for key in ('controlled_lanes_used_12','green_phases','outgoing_lanes'):
        val=n['h12_7_diagnostic'].get(key)
        if any(d['h12_7_diagnostic'].get(key)!=val for d in (p,a)):
            raise ValueError('Semantica de B1 cambia: '+key)
    for i in range(60):
        if obs34(n['decisions'][i]['state_before_34d'])!=obs34(p['decisions'][i]['state_before_34d']):
            raise ValueError('Nominal/probe difieren en observacion 34D')
        if n['decisions'][i]['action']!=p['decisions'][i]['action']:
            raise ValueError('Nominal/probe difieren en acciones')
    return True


def validate_probs(probabilities,n_actions=4):
    if len(probabilities)!=n_actions:
        raise ValueError('Distribucion de acciones incompatible')
    p=[finite(v) for v in probabilities]
    if any(v < -1e-8 or v>1+1e-8 for v in p) or abs(sum(p)-1)>1e-5:
        raise ValueError('Probabilidades fuera de simplex')
    return p


def shannon(p):
    p=validate_probs(p)
    return -sum(v*math.log(v) for v in p if v>0)


def js_divergence(p,q):
    p=validate_probs(p);q=validate_probs(q)
    m=[(x+y)/2 for x,y in zip(p,q)]
    def kl(x,y):return sum(a*math.log(a/b) for a,b in zip(x,y) if a>0)
    return (kl(p,m)+kl(q,m))/2


def total_variation(p,q):
    p=validate_probs(p);q=validate_probs(q)
    return sum(abs(a-b) for a,b in zip(p,q))/2


def phase_map(phases,n_actions=4):
    if not phases:
        raise ValueError('No hay fases verdes')
    return {a:int(phases[a%len(phases)]) for a in range(n_actions)}


def phase_probabilities(p,mapping):
    p=validate_probs(p)
    out={}
    for action,prob in enumerate(p):
        phase=str(mapping[action])
        out[phase]=out.get(phase,0.0)+prob
    return out


def margin(p):
    z=sorted(validate_probs(p),reverse=True)
    return z[0]-z[1]


def load_model(repo,checkpoint_path):
    root=Path(repo)/'tsc_framework'
    if not root.is_dir():raise NotADirectoryError(str(root))
    if str(root) not in sys.path:sys.path.insert(0,str(root))
    from src.rl_agent.sarg_policy import HSARGExtractor, CoopSARGExtractor  # noqa: F401
    from stable_baselines3 import PPO
    import torch  # noqa F401
    model=PPO.load(str(checkpoint_path),device='cpu')
    if model.observation_space.shape!=(34,) or model.action_space.n!=4:
        raise ValueError('Checkpoint no tiene contrato 34D/4 acciones')
    model.policy.set_training_mode(False)
    return model


def infer_probabilities(model,states):
    import numpy as np
    import torch
    records=[]
    for x in states:
        state=np.asarray(obs34(x),dtype=np.float32)
        with torch.no_grad():
            tensor,_=model.policy.obs_to_tensor(state)
            distribution=model.policy.get_distribution(tensor)
            base=getattr(distribution,'distribution',None)
            probs=getattr(base,'probs',None)
            if probs is None:
                raise RuntimeError('Checkpoint no produce distribucion categorica interpretable')
            p=validate_probs(probs.detach().cpu().numpy().reshape(-1).tolist())
        action,_=model.predict(state,deterministic=True)
        act=int(np.asarray(action).reshape(-1)[0])
        records.append({'p':p,'action':act})
    return records


def summarize(docs,outputs,checkpoint_sha):
    check_pair(docs)
    nominal=docs['nominal']['decisions'];active=docs['active']['decisions']
    mapping=phase_map(docs['nominal']['h12_7_diagnostic']['green_phases'])
    for mode in ('nominal','probe','active'):
        if len(outputs[mode])!=60:
            raise ValueError('Probabilidades truncadas '+mode)
        for i,rec in enumerate(outputs[mode]):
            validate_probs(rec['p'])
            if rec['action']!=docs[mode]['decisions'][i]['action']:
                raise ValueError('PREDICCION NO REPRODUCIBLE '+mode+' decision='+str(i))
    recs=[]
    for i,(x,y) in enumerate(zip(nominal,active)):
        n=outputs['nominal'][i];a=outputs['active'][i]
        pn=phase_probabilities(n['p'],mapping);pa=phase_probabilities(a['p'],mapping)
        diff_idx=[j for j,(v,w) in enumerate(zip(x['state_before_34d'],y['state_before_34d'])) if abs(v-w)>1e-8]
        recs.append({'i':i,'decision_time_s':x['sim_time_s']-5.0,
                     'end_time_s':x['sim_time_s'],
                     'n_state_components_different':len(diff_idx),
                     'affected_segments':[name for name,(lo,hi) in SEGMENTS.items() if any(lo<=j<hi for j in diff_idx)],
                     'nominal_action':n['action'],'active_action':a['action'],
                     'nominal_p':n['p'],'active_p':a['p'],
                     'nominal_physical_phase':mapping[n['action']],
                     'active_physical_phase':mapping[a['action']],
                     'nominal_entropy_nats':shannon(n['p']),
                     'active_entropy_nats':shannon(a['p']),
                     'nominal_top_margin':margin(n['p']),
                     'active_top_margin':margin(a['p']),
                     'total_variation':total_variation(n['p'],a['p']),
                     'jensen_shannon_nats':js_divergence(n['p'],a['p']),
                     'phase_probability_nominal':pn,'phase_probability_active':pa,
                     'phase_total_variation':sum(abs(pn[k]-pa[k]) for k in pn)/2})
    affected=[r for r in recs if r['n_state_components_different']>0]
    policy_different=[r for r in affected if r['total_variation']>1e-7]
    probediff=max(total_variation(outputs['nominal'][i]['p'],outputs['probe'][i]['p']) for i in range(60))
    if probediff>1e-7:raise ValueError('Nominal/probe generan distribuciones PPO distintas')
    def mean(seq):return sum(seq)/len(seq) if seq else 0.0
    report={'status':'H12_10_POLITICA_OFFLINE_OK','version':VERSION,
            'model':docs['nominal']['model'],'checkpoint_sha256':checkpoint_sha,
            'decisions':60,'states_different':len(affected),
            'actions_different':sum(r['nominal_action']!=r['active_action'] for r in recs),
            'physical_phases_different':sum(r['nominal_physical_phase']!=r['active_physical_phase'] for r in recs),
            'policy_probs_different_among_changed_states':len(policy_different),
            'policy_probs_diff_threshold_tv':1e-7,
            'max_total_variation':max(r['total_variation'] for r in recs),
            'mean_total_variation_on_changed_states':mean([r['total_variation'] for r in affected]),
            'max_js_divergence_nats':max(r['jensen_shannon_nats'] for r in recs),
            'max_phase_total_variation':max(r['phase_total_variation'] for r in recs),
            'mean_entropy_nominal_nats':mean([r['nominal_entropy_nats'] for r in recs]),
            'mean_entropy_active_nats':mean([r['active_entropy_nats'] for r in recs]),
            'min_argmax_margin_nominal':min(r['nominal_top_margin'] for r in recs),
            'min_argmax_margin_active':min(r['active_top_margin'] for r in recs),
            'observation_box_mismatch':{mode: {'n_decisions_with_age_raw_gt_one':sum(d['state_before_34d'][32]>1.0+OBS_TOL for d in docs[mode]['decisions']), 'max_phase_age_feature_raw':max(d['state_before_34d'][32] for d in docs[mode]['decisions'])} for mode in ('nominal','probe','active')},
            'action_count_nominal':dict(Counter(str(r['nominal_action']) for r in recs)),
            'action_count_active':dict(Counter(str(r['active_action']) for r in recs)),
            'action_to_physical_phase':{str(k):v for k,v in mapping.items()},
            'unique_phases':len(set(mapping.values())),
            'max_probe_nominal_total_variation':probediff,
            'top_decisions_by_probability_change':sorted(recs,key=lambda r:r['total_variation'],reverse=True)[:10],
            'per_decision':recs,
            'limits':['Una semilla; no demuestra robustez, generalizacion ni calidad del controlador',
                      'Las probabilidades son de la politica heredada, no del algoritmo sobre fases corregidas',
                      'Probabilidades agregadas por fase solo son descriptivas: PPO elige argmax de 4 acciones',
                      'Estado heredado repite carriles, deja outgoing vacio; fases amarillas no homologadas',
                      'No ejecuta SUMO ni verifica semantica de entrenamiento',
                      'ADVERTENCIA: TSCEnv declara Box [0,1]^34 pero devuelve edad_de_fase/120 sin clip en la posicion 32; el reporte conserva esos valores tal como los recibio PPO']}
    return report


def markdown(r):
    lines=['# H12.10 — Auditoria offline de sensibilidad de politica PPO','',
          '**Estado:** '+r['status']+' · Modelo `'+r['model']+'` · 300 s · seed 101',
          '**Checkpoint SHA-256:** `'+r['checkpoint_sha256']+'`','',
          '| Indicador | Resultado |','|---|---:|',
          f"| Decisiones analizadas | {r['decisions']} |",
          f"| Estados nominal/activo diferentes | {r['states_different']} |",
          f"| Estados cambiados con probabilidades PPO distintas (TV > 1e-7) | {r['policy_probs_different_among_changed_states']} |",
          f"| Acciones PPO distintas | {r['actions_different']} |",
          f"| Fases fisicas diferentes | {r['physical_phases_different']} |",
          f"| Maximo cambio en distribucion de 4 acciones (TV) | {r['max_total_variation']:.10g} |",
          f"| TV medio de estados modificados | {r['mean_total_variation_on_changed_states']:.10g} |",
          f"| Maximo cambio en distribucion agrupada de fases (TV) | {r['max_phase_total_variation']:.10g} |",
          f"| Maximo Jensen–Shannon (nats) | {r['max_js_divergence_nats']:.10g} |",
          f"| Entropia media nominal / Vine (nats) | {r['mean_entropy_nominal_nats']:.8g} / {r['mean_entropy_active_nats']:.8g} |",
          f"| Margen minimo de la mejor accion nominal / Vine | {r['min_argmax_margin_nominal']:.8g} / {r['min_argmax_margin_active']:.8g} |",
          f"| Maxima diferencia nominal-probe (TV) | {r['max_probe_nominal_total_variation']:.10g} |",'',
          '## Discordancia de rango en la observacion heredada',
          '- El Box anunciado exige [0,1] en todas las posiciones, pero la componente 32 (edad/120) no se recorta y puede superar 1 a partir de los 120 s sin transicion de fase.',
          '- Estados de ENTRADA fuera del Box por edad no recortada: '+', '.join(f"{mode}: {data['n_decisions_with_age_raw_gt_one']}/60 (max {data['max_phase_age_feature_raw']:.6g})" for mode,data in r['observation_box_mismatch'].items()),
          '- Se analizaron los valores archivados SIN clipping ni renormalizacion. La compatibilidad de entrenamiento del checkpoint no se demuestra con ello.',
          '', '## Acciones equivalentes',
          '- Mapeo PPO → fase SUMO: '+', '.join(f'{k}→{v}' for k,v in r['action_to_physical_phase'].items()),
          f"- Fases fisicas diferentes: {r['unique_phases']} (no 4)",
          '- La politica PPO selecciona la maxima probabilidad entre 4 acciones; agrupar probabilidades por fase **no cambia** ese mecanismo.','',
          '## Decisiones con mayor cambio de probabilidades',
          '| Decision | t inicio (s) | 34D componentes distintas | TV | JS (nats) | Accion N/V | Prob. accion 0 N/V |',
          '|---:|---:|---:|---:|---:|:---:|---:|']
    for x in r['top_decisions_by_probability_change']:
        lines.append(f"| {x['i']} | {x['decision_time_s']:.1f} | {x['n_state_components_different']} | {x['total_variation']:.8g} | {x['jensen_shannon_nats']:.8g} | {x['nominal_action']}/{x['active_action']} | {x['nominal_p'][0]:.6g}/{x['active_p'][0]:.6g} |")
    lines+=['','## Interpretacion','- Un cambio de estado con accion identica NO es prueba de insensibilidad de la politica: consultar cambios de probabilidades y margenes.',
            '- Si hay 39 observaciones diferentes pero TV cercano a 0, la red puede ser localmente insensible ante esos estados (diagnostico, no prueba universal).',
            '- Si TV > 0 pero la accion no cambia, existe respuesta probabilistica sin cambio de argmax; la equivalencia de acciones reduce las fases fisicas disponibles.',
            '', '## Limites',*('- '+x for x in r['limits']),'']
    return '\n'.join(lines)


def execute(args):
    folder=Path(args.h129_dir).resolve();repo=Path(args.repo_root).resolve()
    docs={m:read_run(folder,m) for m in ('nominal','probe','active')}
    check_pair(docs)
    model_name=docs['nominal'].get('model')
    if model_name not in MODELS:
        raise ValueError('Modelo PPO no reconocido')
    checkpoint=repo/'tsc_framework/outputs/models'/f'{model_name}.zip'
    if not checkpoint.is_file():raise FileNotFoundError(str(checkpoint))
    checkpoint_hash=sha256(checkpoint)
    if checkpoint_hash.lower()!=str(docs['nominal']['checkpoint_sha256']).lower():
        raise ValueError('CHECKPOINT_SHA256_MISMATCH, abortando')
    phases=docs['nominal']['h12_7_diagnostic']['green_phases']
    age_max=max(d['state_before_34d'][32] for d in docs['nominal']['decisions'])
    violations=sum(d['state_before_34d'][32]>1.0+OBS_TOL for d in docs['nominal']['decisions'])
    print('H12.10 | BOX_CONTRACT_WARNING | nominal valores de edad/120 > 1:',violations,'/60 | max',format(age_max,'.6g'),flush=True)
    print('H12.10 | ARCHIVOS VALIDADOS | decisiones 60 | checkpoint',checkpoint_hash[:16],
          '| fases',phases,'| nominal/probe OK',flush=True)
    if args.mode=='plan':
        print('H12_10_PLAN_OK: solo lectura; SUMO no ejecutado.');return 0
    model=load_model(repo,checkpoint)
    infer={mode:infer_probabilities(model,[r['state_before_34d'] for r in d['decisions']]) for mode,d in docs.items()}
    report=summarize(docs,infer,checkpoint_hash)
    output_root=Path(args.results_root).resolve()
    if not output_root.is_dir():raise NotADirectoryError(str(output_root))
    dest=output_root/('h12_10_politica_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    dest.mkdir(parents=True,exist_ok=False)
    (dest/'dictamen_h12_10.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (dest/'dictamen_h12_10.md').write_text(markdown(report),encoding='utf-8')
    import csv
    with (dest/'probabilidades_pareadas.csv').open('w',newline='',encoding='utf-8') as f:
        columns=['decision','time_s','changed_state','nom_action','vine_action','nom_phase','vine_phase','tv','js_nats','tv_phases'] + [f'prob_nom_{i}' for i in range(4)] + [f'prob_vine_{i}' for i in range(4)]
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for row in report['per_decision']:
            record={'decision':row['i'],'time_s':row['decision_time_s'],'changed_state':row['n_state_components_different'],
                'nom_action':row['nominal_action'],'vine_action':row['active_action'],
                'nom_phase':row['nominal_physical_phase'],'vine_phase':row['active_physical_phase'],
                'tv':row['total_variation'],'js_nats':row['jensen_shannon_nats'],'tv_phases':row['phase_total_variation']}
            record.update({f'prob_nom_{i}':v for i,v in enumerate(row['nominal_p'])})
            record.update({f'prob_vine_{i}':v for i,v in enumerate(row['active_p'])})
            w.writerow(record)
    print('H12_10_POLITICA_OFFLINE_OK | estados distintos',report['states_different'],
          '| probabilidades distintas',report['policy_probs_different_among_changed_states'],
          '| acciones distintas',report['actions_different'],
          '| TV max',format(report['max_total_variation'],'.6g'),flush=True)
    print('INFORME',dest)
    return 0


def parse(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--h129-dir',type=Path,required=True,help='Directorio H12.9 con nominal/probe/active')
    p.add_argument('--repo-root',type=Path,required=True,help='Repositorio local, solo lectura')
    p.add_argument('--mode',choices=('plan','analyze'),default='plan')
    p.add_argument('--results-root',type=Path,default=Path('resultados'))
    return p.parse_args(argv)


def main(argv=None):
    try:return execute(parse(argv))
    except Exception as e:
        print('H12.10 FAIL-CLOSED:',type(e).__name__,str(e),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
