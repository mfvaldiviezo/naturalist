#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.7: auditoría de observaciones 34D y sensores B1 en nominal/Vine.

No cambia scripts originales, checkpoints, red, rutas ni parámetros H10.
Copia y amplía IN MEMORY H12.5 v1.0 con lecturas TraCI adicionales.
La comparación de hashes de tráfico contra H12.5 detecta interferencias.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import traceback
import types
import uuid

EXPECTED_H125_SHA256 = '2d09fa9c918a1e0837805983c60a7c19565495a04dca9a1f0824bc7599fb4430'
H125_REL = 'H12_5_Integracion_Vine_Gymnasium_v100/h12_5_integrar.py'
SEGMENTS = {'cola_12': (0,12), 'espera_12': (12,24), 'presion_4': (24,28),
            'fase_4': (28,32), 'edad_2': (32,34)}

PATCHES = [
    (
        'self.rows=[];self.h09_seen=set();self.h09_verified=set()',
        'self.rows=[];self.h09_seen=set();self.h09_verified=set()\n'
        '        self.h127_b1_lanes=[];self.h127_b1_microticks=[]',
    ),
    (
        '        self.rows.append(row)\n        if self.h09_ids:',
        '        self.rows.append(row)\n'
        '        if self.h127_b1_lanes:\n'
        '            local=[]\n'
        '            for lane in self.h127_b1_lanes:\n'
        '                local.append({"lane":lane,\n'
        '                     "n":int(traci.lane.getLastStepVehicleNumber(lane)),\n'
        '                     "halted":int(traci.lane.getLastStepHaltingNumber(lane)),\n'
        '                     "wait_s":float(traci.lane.getWaitingTime(lane))})\n'
        '            self.h127_b1_microticks.append({"tick":int(tick),"time_s":row["time_s"],\n'
        '                "n_b1":sum(x["n"] for x in local),\n'
        '                "halted_b1":sum(x["halted"] for x in local),\n'
        '                "waiting_b1_s":sum(x["wait_s"] for x in local),\n'
        '                "lanes":local})\n'
        '        if self.h09_ids:',
    ),
    (
        '        state,_=env.reset(seed=args.seed)\n        start=float(module.traci.simulation.getTime())',
        '        state,_=env.reset(seed=args.seed)\n'
        '        raw_lanes=list(module.traci.trafficlight.getControlledLanes(args.tls_id))\n'
        '        hook.h127_b1_lanes=list(dict.fromkeys(env._controlled_lanes))\n'
        '        if not hook.h127_b1_lanes:\n'
        '            raise RuntimeError("B1 no expone carriles controlados")\n'
        '        diagnostic={"tls_id":args.tls_id,\n'
        '          "controlled_lanes_raw":raw_lanes,\n'
        '          "controlled_lanes_unique_raw":list(dict.fromkeys(raw_lanes)),\n'
        '          "controlled_lanes_used_12":list(env._controlled_lanes),\n'
        '          "outgoing_lanes":list(env._outgoing_lanes),\n'
        '          "green_phases":list(env._green_phases),\n'
        '          "initial_state_34d":list(map(float,state)),\n'
        '          "b1_microticks":hook.h127_b1_microticks}\n'
        '        start=float(module.traci.simulation.getTime())',
    ),
    (
        '            action=int(np.asarray(action).reshape(-1)[0])\n            state,reward,terminated,truncated,info=env.step(action)',
        '            action=int(np.asarray(action).reshape(-1)[0])\n'
        '            state_before=list(map(float,state))\n'
        '            state,reward,terminated,truncated,info=env.step(action)\n'
        '            state_after=list(map(float,state))',
    ),
    (
        "                   'terminated':bool(terminated),'truncated':bool(truncated)})",
        "                   'terminated':bool(terminated),'truncated':bool(truncated),\n"
        "                   'state_before_34d':state_before,'state_after_34d':state_after})",
    ),
    (
        "    (out/'piloto_h12_5.json').write_text(json.dumps(result,ensure_ascii=False,",
        "    result['h12_7_diagnostic']=diagnostic\n"
        "    (out/'piloto_h12_5.json').write_text(json.dumps(result,ensure_ascii=False,",
    ),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def patch_h125(src: str) -> str:
    """Intervenciones limitadas, estáticas y fail-closed sobre copia en memoria."""
    for old,new in PATCHES:
        if src.count(old)!=1:
            raise RuntimeError('H12.7 FAIL-CLOSED: ancla inesperada o ambigua '+repr(old[:55]))
        src=src.replace(old,new,1)
    ast.parse(src)
    return src


def load_h125(root: Path):
    path=root/H125_REL
    if not path.is_file():
        raise FileNotFoundError('H12.5 no está extraído en revision_naturalista: '+str(path))
    actual=sha256(path)
    if actual!=EXPECTED_H125_SHA256:
        raise RuntimeError('H12.7 SOURCE_CHANGED_FAIL_CLOSED H12.5 sha='+actual)
    text=patch_h125(path.read_text(encoding='utf-8-sig'))
    mod=types.ModuleType('_h127_overlay_'+uuid.uuid4().hex)
    mod.__file__=str(path)
    sys.modules[mod.__name__]=mod
    exec(compile(text,str(path),'exec'),mod.__dict__)
    return mod


def obs_differences(a,b,tol=1e-8):
    if len(a)!=34 or len(b)!=34:
        raise ValueError('Solo observaciones 34D, sin truncar o rellenar')
    if any(not math.isfinite(float(x)) for x in [*a,*b]):
        raise ValueError('Observación no finita')
    idx=[i for i,(x,y) in enumerate(zip(a,b)) if abs(float(x)-float(y))>tol]
    return {'n_diff':len(idx),'indices':idx,
            'segments':{key:[i for i in idx if lo<=i<hi]
                        for key,(lo,hi) in SEGMENTS.items()},
            'max_abs_diff':max([abs(float(x)-float(y)) for x,y in zip(a,b)],default=0.)}


def analyze(nom,active):
    if nom['model']!=active['model'] or nom['checkpoint_sha256']!=active['checkpoint_sha256']:
        raise RuntimeError('H12.7 NOT_PAIRED_MODEL')
    if (nom['n_decisions'],nom['n_microticks'])!=(active['n_decisions'],active['n_microticks']):
        raise RuntimeError('H12.7 NOT_PAIRED_HORIZON')
    for key in ('net_sha256','routes_sha256','cfg_original_sha256'):
        if nom['inputs'][key]!=active['inputs'][key]:
            raise RuntimeError('H12.7 NOT_PAIRED_'+key)
    if nom['h10_source_sha256'] != active['h10_source_sha256']:
        raise RuntimeError('H12.7 NOT_PAIRED_SOURCES')
    if nom['commands']!=0 or active['commands']<1:
        raise RuntimeError('H12.7 ACTIVE_OR_NOMINAL_COMMANDS_INVALID')
    reports=[]
    for i,(a,b) in enumerate(zip(nom['decisions'],active['decisions'])):
        if a['i']!=i or b['i']!=i or a['sim_time_s']!=b['sim_time_s']:
            raise RuntimeError('H12.7 NOT_PAIRED_DECISION_TIMES')
        diff=obs_differences(a['state_before_34d'],b['state_before_34d'])
        after=obs_differences(a['state_after_34d'],b['state_after_34d'])
        reports.append({'i':i,'time_s':a['sim_time_s'],
            'action_nom':a['action'],'action_vine':b['action'],
            'queue_nom':a['queue'],'queue_vine':b['queue'],
            'observation_diff':diff,'observation_after_diff':after})
    n_micro=nom['n_microticks']
    diagnostic_nom=nom['h12_7_diagnostic'];diagnostic_active=active['h12_7_diagnostic']
    rows_n=diagnostic_nom['b1_microticks'];rows_a=diagnostic_active['b1_microticks']
    if len(rows_n)!=n_micro or len(rows_a)!=n_micro:
        raise RuntimeError('H12.7 MISSING_B1_MICROTICKS')
    for a,b in zip(rows_n,rows_a):
        if (a['tick'],a['time_s'])!=(b['tick'],b['time_s']):
            raise RuntimeError('H12.7 B1_TICKS_NOT_PAIRED')
    return {
        'result':'H12_7_DIAGNOSTICO_OK',
        'model':nom['model'],'n_decisions':nom['n_decisions'],'n_microticks':n_micro,
        'nominal_trace_sha256':nom['trace_sha256'],
        'active_trace_sha256':active['trace_sha256'],
        'active_commands_confirmed':active['extra'].get('n_commands_confirmed'),
        'same_actions':all(x['action_nom']==x['action_vine'] for x in reports),
        'n_decisions_obs_different':sum(x['observation_diff']['n_diff']>0 for x in reports),
        'n_decisions_actions_different':sum(x['action_nom']!=x['action_vine'] for x in reports),
        'first_decision_obs_diff':next((x['i'] for x in reports if x['observation_diff']['n_diff']>0),None),
        'n_poststep_obs_different':sum(x['observation_after_diff']['n_diff']>0 for x in reports),
        'b1_nominal_ticks_with_vehicles':sum(x['n_b1']>0 for x in rows_n),
        'b1_active_ticks_with_vehicles':sum(x['n_b1']>0 for x in rows_a),
        'b1_nominal_ticks_with_halted':sum(x['halted_b1']>0 for x in rows_n),
        'b1_active_ticks_with_halted':sum(x['halted_b1']>0 for x in rows_a),
        'b1_nominal_max_vehicles':max(x['n_b1'] for x in rows_n),
        'b1_active_max_vehicles':max(x['n_b1'] for x in rows_a),
        'controlled_lanes_unique_raw':diagnostic_nom['controlled_lanes_unique_raw'],
        'controlled_lanes_used_12':diagnostic_nom['controlled_lanes_used_12'],
        'outgoing_lanes':diagnostic_nom['outgoing_lanes'],
        'green_phases':diagnostic_nom['green_phases'],
        'decisions':reports,
        'limits':['Instrumentación de solo lectura; no prueba robustez','B1 no equivale a toda la red',
                  'Observaciones y checkpoints son de arquitectura heredada',
                  'No homologado tiempo amarillo / acciones para SOTA']
    }


def render_md(r):
    first=r['first_decision_obs_diff']
    head=["# H12.7 — Auditoría real del estado 34D de B1", "",
        '**Estado:** '+r['result'],
        f"**Controlador:** `{r['model']}` · {r['n_decisions']} decisiones · {r['n_microticks']} microticks",
        f"**Comandos activos confirmados:** {r['active_commands_confirmed']}",
        f"**Observaciones distintas antes de decisión:** {r['n_decisions_obs_different']}/{r['n_decisions']}",
        f"**Acciones diferentes:** {r['n_decisions_actions_different']}/{r['n_decisions']}",
        f"**Primera decisión con observación distinta:** {first if first is not None else 'ninguna'}",
        f"**Estados posteriores distintos:** {r['n_poststep_obs_different']}/{r['n_decisions']}", "",
        '## Exposición local en B1 (no global)',
        f"- Microticks con vehículos: nominal {r['b1_nominal_ticks_with_vehicles']}/{r['n_microticks']} vs activo {r['b1_active_ticks_with_vehicles']}/{r['n_microticks']}",
        f"- Microticks con detenidos: nominal {r['b1_nominal_ticks_with_halted']} vs activo {r['b1_active_ticks_with_halted']}",
        f"- Máximo de vehículos simultáneos en B1: nominal {r['b1_nominal_max_vehicles']} vs activo {r['b1_active_max_vehicles']}",
        f"- Carriles únicos crudos de B1: {len(r['controlled_lanes_unique_raw'])}",
        f"- Carriles usados en la observación 12D: {len(r['controlled_lanes_used_12'])}; únicos {len(set(r['controlled_lanes_used_12']))}",
        f"- Carriles salientes en TSCEnv: {len(r['outgoing_lanes'])} (vacío implica que la 'presión' no resta salientes)",
        f"- Fases verdes detectadas: {r['green_phases']}", "",
        '## Comparación del vector de entrada por decisión',
        '| Decisión | t fin (s) | Acción N/V | Entrada 34D distinta | Salida 34D distinta | Segmentos distintos de entrada |',
        '|---:|---:|:---:|---:|---:|---|']
    for d in r['decisions']:
        seg=', '.join(f"{k}:{len(v)}" for k,v in d['observation_diff']['segments'].items() if v)
        head.append(f"| {d['i']} | {d['time_s']:.1f} | {d['action_nom']}/{d['action_vine']} | {d['observation_diff']['n_diff']} | {d['observation_after_diff']['n_diff']} | {seg or 'ninguno'} |")
    head+=['','## Interpretación y límites',
        '- Cero diferencias de acciones no implica entradas 34D iguales; leer la columna de observaciones.',
        '- Si B1 no tiene vehículos durante el horizonte, los ceros de cola/recompensa podrían ser reales para esta intersección.',
        '- Si B1 tiene detenidos pero espera/cola permanecen cero, corresponde investigar el mapeo de carriles y las lecturas.',
        '- Para pruebas de resiliencia son necesarios tráfico con exposición efectiva, horizonte suficiente y semillas independientes.',
        '- Los datos observados provienen del piloto y no de una calibración poblacional a Quito.', '']
    return '\n'.join(head)


def parse(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision-root',type=Path,default=Path('.'))
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--model',default='ppo_ideal')
    p.add_argument('--rl-steps',type=int,default=12)
    p.add_argument('--tls-id',default='B1')
    p.add_argument('--max-commands',type=int,default=30)
    p.add_argument('--old-nominal',type=Path,required=True,
                   help='Informe nominal H12.5 previo: verificar invariancia exacta de traza')
    p.add_argument('--old-active',type=Path,required=True,
                   help='Informe active H12.5 previo: verificar invariancia exacta de traza')
    p.add_argument('--ack-active',default='')
    p.add_argument('--ack-time-scale',default='')
    return p.parse_args(argv)


def run(argv=None):
    args=parse(argv)
    if args.ack_active!='EXPERIMENTAL_ONLY' or args.ack_time_scale!='NOT_CALIBRATED':
        raise RuntimeError('Se exigen flags explícitos de modo activo experimental y escala no calibrada')
    root=args.revision_root.resolve();repo=args.repo_root.resolve()
    if not root.is_dir() or not repo.is_dir():raise NotADirectoryError('Rutas inválidas')
    for old in [args.old_nominal,args.old_active]:
        if not old.is_file(): raise FileNotFoundError('Informe previo ausente '+str(old))
    prev_nom=json.loads(args.old_nominal.read_text(encoding='utf-8-sig'))
    prev_act=json.loads(args.old_active.read_text(encoding='utf-8-sig'))
    if prev_nom['n_decisions']!=args.rl_steps or prev_act['n_decisions']!=args.rl_steps:
        raise RuntimeError('Los informes previos tienen horizontes distintos')
    if prev_nom['model']!=args.model or prev_act['model']!=args.model:
        raise RuntimeError('Modelo previo no coincide')
    source=load_h125(root)
    args_h=source.parse(['--revision-root',str(root),'--repo-root',str(repo),
        '--mode','active','--model',args.model,'--seed',str(args.seed),
        '--rl-steps',str(args.rl_steps),'--tls-id',args.tls_id,
        '--max-commands',str(args.max_commands),'--ack-active',args.ack_active,
        '--ack-time-scale',args.ack_time_scale])
    sys.dont_write_bytecode=True
    sources=source.validate_source(root)
    h10,ctx,params=source.make_h10_context(root,args_h)
    h10.verify_sources(ctx[12])
    out=root/'resultados'/('h12_7_estado_b1_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(parents=True,exist_ok=False)
    try:
        results=[]
        for mode in ('nominal','active'):
            folder=out/mode;folder.mkdir(exist_ok=False)
            print('INICIANDO H12.7',mode,'->',folder,flush=True)
            result=source.run_one(mode,root,repo,args_h,h10,ctx,params,folder)
            old=prev_nom if mode=='nominal' else prev_act
            if result['trace_sha256']!=old['trace_sha256']:
                raise RuntimeError('H12.7 INVARIANCIA FALLIDA '+mode+': traza instrumentada difiere de H12.5 original')
            results.append(result)
        assessment=analyze(*results)
        (out/'analisis_estado_b1.json').write_text(json.dumps(assessment,indent=2,ensure_ascii=False),encoding='utf-8')
        (out/'dictamen_estado_b1.md').write_text(render_md(assessment),encoding='utf-8')
        (out/'manifest_h12_7.json').write_text(json.dumps({'base_h125_sha256':EXPECTED_H125_SHA256,
            'source_sha256':sources,'previous_nominal_trace_sha256':prev_nom['trace_sha256'],
            'previous_active_trace_sha256':prev_act['trace_sha256']},indent=2),encoding='utf-8')
        print('H12_7_DIAGNOSTICO_OK',flush=True)
        print('B1_MICROTICKS_CON_VEHICULOS',assessment['b1_nominal_ticks_with_vehicles'],
              assessment['b1_active_ticks_with_vehicles'],flush=True)
        print('OBS_34D_DIFERENTES',assessment['n_decisions_obs_different'],'DE',assessment['n_decisions'],flush=True)
        print('ACCIONES_DIFERENTES',assessment['n_decisions_actions_different'],flush=True)
        print('INFORME',out,flush=True)
        return 0
    except Exception as e:
        (out/'ERROR_h12_7.json').write_text(json.dumps({'error':type(e).__name__,
            'message':str(e),'traceback':traceback.format_exc()},indent=2),encoding='utf-8')
        print('H12.7 FALLÓ:',type(e).__name__,str(e),file=sys.stderr)
        print('EVIDENCIA PARCIAL:',out,file=sys.stderr)
        return 2

if __name__=='__main__':
    try:raise SystemExit(run())
    except Exception as e:
        print('H12.7 PREFLIGHT FALLÓ:',type(e).__name__,str(e),file=sys.stderr)
        raise SystemExit(2)
