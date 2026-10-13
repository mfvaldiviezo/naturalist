#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.9 — Control de exposición, nominal/probe/Vine, 300 s / semilla 101.

NO es un experimento de resiliencia ni introduce una nueva definición de estado.
Reutiliza H12.5 y H12.7 en memoria con comprobación de SHA. Los fuentes,
checkpoints, red, ruta y cohorte original permanecen inmutables.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
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

VERSION='H12.9-v1.0.1'
REL_H125=Path('H12_5_Integracion_Vine_Gymnasium_v100/h12_5_integrar.py')
REL_H127=Path('H12_7_Diagnostico_Estado_B1_v100/h12_7_estado_b1.py')
SHA_H125='2d09fa9c918a1e0837805983c60a7c19565495a04dca9a1f0824bc7599fb4430'
# Current SHA of H12.7 checked against its original source package below.
SHA_H127='0ac1f79e9a500af81a206bd735fe348be0bf12d8f80d5311a9a4449bc520c891'
SEGMENTS={'cola_12':(0,12),'espera_12':(12,24),'presion_4':(24,28),'fase_4':(28,32),'edad_2':(32,34)}


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as fh:
        for block in iter(lambda: fh.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def replace_once(text, before, after):
    if text.count(before)!=1:
        raise RuntimeError('H12.9 FAIL-CLOSED: ancla ausente o ambigua '+repr(before[:95]))
    return text.replace(before,after,1)


def extend_h127_text(text):
    """Extiende la instrumentación leída, sin modificar los métodos RL ni Vine."""
    text=replace_once(text,
        "if not 2 <= args.rl_steps <= 20:",
        "if not 2 <= args.rl_steps <= 60:")
    text=replace_once(text,
        "p.error('Se requieren 2..20 decisiones PPO por piloto')",
        "p.error('Se requieren 2..60 decisiones PPO por piloto')")
    text=replace_once(text,
        'self.h127_b1_lanes=[];self.h127_b1_microticks=[]',
        'self.h127_b1_lanes=[];self.h127_b1_microticks=[]\n'
        '        self.h129_vine_ids=set();self.h129_h09_ids=set()')
    text=replace_once(text,
        '            self.h127_b1_microticks.append({"tick":int(tick),"time_s":row["time_s"],',
        '            b1_ids=set()\n'
        '            for lane in self.h127_b1_lanes:\n'
        '                b1_ids.update(map(str,traci.lane.getLastStepVehicleIDs(lane)))\n'
        '            b1_speeds={v:float(traci.vehicle.getSpeed(v)) for v in sorted(b1_ids)}\n'
        '            self.h127_b1_microticks.append({"tick":int(tick),"time_s":row["time_s"],')
    text=replace_once(text,
        '                "lanes":local})',
        '                "lanes":local,\n'
        '                "b1_mean_speed_m_s":sum(b1_speeds.values())/len(b1_speeds) if b1_speeds else 0.0,\n'
        '                "vine_selected_speeds_m_s":{v:b1_speeds[v] for v in sorted(b1_ids & self.h129_vine_ids)},\n'
        '                "vine_selected_b1":sorted(b1_ids & self.h129_vine_ids),\n'
        '                "h09_selected_b1":sorted(b1_ids & self.h129_h09_ids)})')
    text=replace_once(text,
        '    hook=H10Hook(mode,injector,h09sel)',
        "    hook=H10Hook(mode,injector,h09sel)\n"
        "    hook.h129_vine_ids=set(coh['selected_vine'])\n"
        "    hook.h129_h09_ids=set(coh['selected_h09'])")
    ast.parse(text)
    return text


def load_source_overlay(root):
    h125=root/REL_H125;h127=root/REL_H127
    for path, expected in [(h125,SHA_H125),(h127,SHA_H127)]:
        if not path.is_file():
            raise FileNotFoundError('FUENTE AUSENTE: '+str(path))
        if expected and sha256(path)!=expected:
            raise RuntimeError('SOURCE_CHANGED_FAIL_CLOSED: '+str(path))
    # H12.7 owns a SHA check of H12.5 and the exact, static 34D instrumentation.
    spec=importlib.util.spec_from_file_location('_h129_h127_'+uuid.uuid4().hex,h127)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module;spec.loader.exec_module(module)
    if module.EXPECTED_H125_SHA256!=SHA_H125:
        raise RuntimeError('SHA H12.5 guard H12.7 inconsistente')
    core=module.patch_h125(h125.read_text(encoding='utf-8-sig'))
    patched=extend_h127_text(core)
    overlay=types.ModuleType('_h129_h125_overlay_'+uuid.uuid4().hex)
    overlay.__file__=str(h125)
    sys.modules[overlay.__name__]=overlay
    exec(compile(patched,str(h125),'exec'),overlay.__dict__)
    return overlay,{'h125_sha256':sha256(h125),'h127_sha256':sha256(h127),
                    'overlay_sha256':hashlib.sha256(patched.encode('utf-8')).hexdigest()}


def finite(n):
    v=float(n)
    if not math.isfinite(v):
        raise RuntimeError('NUMERICO NO FINITO')
    return v


def load_result(folder,mode):
    f=Path(folder)/mode/'piloto_h12_5.json'
    if not f.is_file():raise FileNotFoundError(str(f))
    d=json.loads(f.read_text(encoding='utf-8-sig'))
    if d.get('result')!='SMOKE_OK' or d.get('mode')!=mode:
        raise RuntimeError('SMOKE O MODO NO VALIDO '+mode)
    if d.get('n_decisions')!=60 or d.get('n_microticks')!=600:
        raise RuntimeError('HORIZONTE NO VALIDO '+mode)
    if len(d['decisions'])!=60 or len(d['microticks'])!=600:
        raise RuntimeError('REGISTROS TRUNCADOS '+mode)
    dx=d.get('h12_7_diagnostic')
    if not dx or len(dx.get('b1_microticks',[]))!=600:
        raise RuntimeError('B1 / 34D NO DISPONIBLES '+mode)
    if len(dx.get('initial_state_34d',[]))!=34:
        raise RuntimeError('ESTADO INICIAL MALFORMADO '+mode)
    for rec in d['decisions']:
        for field in ('state_before_34d','state_after_34d'):
            a=rec.get(field)
            if not isinstance(a,list) or len(a)!=34 or not all(math.isfinite(float(x)) for x in a):
                raise RuntimeError('ESTADO 34D INVALIDO '+mode)
    return d


def pair_integrity(nom,probe,active):
    docs={'nominal':nom,'probe':probe,'active':active}
    for key in ('model','checkpoint_sha256','h10_reference_path','h10_reference_n','h10_source_sha256'):
        if any(doc.get(key)!=nom.get(key) for doc in docs.values()):
            raise RuntimeError('EMPAREJAMIENTO FALLIDO: '+key)
    for key in ('net_sha256','routes_sha256','cfg_original_sha256'):
        if any(doc['inputs'].get(key)!=nom['inputs'].get(key) for doc in docs.values()):
            raise RuntimeError('EMPAREJAMIENTO ENTRADAS: '+key)
    if nom['trace_sha256']!=probe['trace_sha256']:
        raise RuntimeError('FAIL: NOMINAL Y PROBE NO IDENTICOS')
    if nom['commands']!=0 or probe['commands']!=0 or active['commands']<=0:
        raise RuntimeError('FAIL: INTERVENCIONES INCORRECTAS')
    if active['trace_sha256']==nom['trace_sha256']:
        raise RuntimeError('FAIL: NO SE OBSERVA EFECTO CINEMATICO GLOBAL')
    md=active.get('extra',{}).get('vine',{})
    if md.get('n_commands')!=active['commands'] or md.get('n_commands_confirmed')!=active['commands'] or md.get('remaining_pending')!=0:
        raise RuntimeError('FAIL: COMANDOS VINE SIN CONFIRMACION')
    for name,d in docs.items():
        if any(r.get('collisions',0) or r.get('teleports_start',0) for r in d['microticks']):
            raise RuntimeError('FAIL: COLISION / TELEPORT '+name)
        if d['end_time_s']!=300.0:
            raise RuntimeError('FAIL: HORIZONTE NO COMPLETO '+name)
        if d['h12_7_diagnostic']['controlled_lanes_used_12']!=nom['h12_7_diagnostic']['controlled_lanes_used_12']:
            raise RuntimeError('FAIL: CONTROLLED LANES DISTINTOS '+name)
        if d['h12_7_diagnostic']['green_phases']!=nom['h12_7_diagnostic']['green_phases']:
            raise RuntimeError('FAIL: FASES DISTINTAS '+name)
    return True


def metrics(doc):
    rows=doc['h12_7_diagnostic']['b1_microticks']
    d=doc['decisions']
    selected={x for r in rows for x in r['vine_selected_b1']}
    return {'ticks_b1_vehicles':sum(int(r['n_b1'])>0 for r in rows),
            'ticks_b1_halted':sum(int(r['halted_b1'])>0 for r in rows),
            'ticks_b1_wait':sum(finite(r['waiting_b1_s'])>0 for r in rows),
            'b1_vehicle_ticks':sum(int(r['n_b1']) for r in rows),
            'ticks_with_selected_vine_in_b1':sum(bool(r['vine_selected_b1']) for r in rows),
            'unique_selected_vine_in_b1':len(selected),
            'max_b1_vehicles':max(int(r['n_b1']) for r in rows),
            'mean_b1_speed_m_s_time_avg':sum(finite(r['b1_mean_speed_m_s']) for r in rows)/len(rows),
            'decisions_queue_nonzero':sum(finite(x['queue'])>0 for x in d),
            'decisions_delay_nonzero':sum(finite(x['delay_proxy'])>0 for x in d),
            'decisions_reward_nonzero':sum(abs(finite(x['reward']))>1e-9 for x in d),
            'action_frequencies':dict(Counter(str(x['action']) for x in d)),
            'commands':doc['commands']}


def compare(nom,probe,active):
    pair_integrity(nom,probe,active)
    n=nom['h12_7_diagnostic']['b1_microticks'];a=active['h12_7_diagnostic']['b1_microticks']
    boundary_changes=[]; b1_changes=[]; b1_speed_changes=[]; vine_speed_changes=[];segments=Counter()
    for i,(x,y) in enumerate(zip(nom['decisions'],active['decisions'])):
        if x['i']!=y['i'] or abs(finite(x['sim_time_s'])-finite(y['sim_time_s']))>1e-8:
            raise RuntimeError('DECS NO EMPAREJADAS')
        counts={}
        for label,(lo,hi) in SEGMENTS.items():
            counts[label]=sum(abs(finite(u)-finite(v))>1e-8 for u,v in zip(x['state_before_34d'][lo:hi],y['state_before_34d'][lo:hi]))
        segments.update({k:1 for k,v in counts.items() if v})
        if any(counts.values()):
            boundary_changes.append({'index':i,'time_s':x['sim_time_s'],'segments':counts})
    action_diff=[i for i,(x,y) in enumerate(zip(nom['decisions'],active['decisions'])) if x['action']!=y['action']]
    for rn,ra in zip(n,a):
        if rn['tick']!=ra['tick'] or abs(finite(rn['time_s'])-finite(ra['time_s']))>1e-8:
            raise RuntimeError('B1 DESALINEADO')
        if abs(finite(rn['b1_mean_speed_m_s'])-finite(ra['b1_mean_speed_m_s']))>1e-8:
            b1_speed_changes.append(rn['time_s'])
        for vid in set(rn['vine_selected_speeds_m_s']) & set(ra['vine_selected_speeds_m_s']):
            if abs(finite(rn['vine_selected_speeds_m_s'][vid])-finite(ra['vine_selected_speeds_m_s'][vid]))>1e-8:
                vine_speed_changes.append((rn['time_s'],vid))
        if (rn['n_b1']!=ra['n_b1'] or rn['halted_b1']!=ra['halted_b1'] or
            abs(finite(rn['waiting_b1_s'])-finite(ra['waiting_b1_s']))>1e-8):
            b1_changes.append({'tick':rn['tick'],'time_s':rn['time_s'],
                                'nom_n':rn['n_b1'],'active_n':ra['n_b1'],
                                'nom_halted':rn['halted_b1'],'active_halted':ra['halted_b1']})
    return {'status':'H12_9_EXTENDED_OK','version':VERSION,
            'checkpoint_sha256':nom['checkpoint_sha256'],'model':nom['model'],
            'duration_s':300,'seed':101,'decisions':60,'microticks':600,
            'nominal_probe_identical':True,'vine_confirmed':active['commands'],
            'global_kinematics_changed':True,
            'metrics':{k:metrics(v) for k,v in [('nominal',nom),('probe',probe),('active',active)]},
            'b1_local_aggregate_microticks_different':len(b1_changes),
            'first_b1_aggregate_difference':b1_changes[0]['time_s'] if b1_changes else None,
            'b1_local_mean_speed_microticks_different':len(b1_speed_changes),
            'b1_selected_vine_speed_records_different':len(vine_speed_changes),
            'first_b1_local_speed_difference':b1_speed_changes[0] if b1_speed_changes else None,
            'obs34d_boundaries_different':len(boundary_changes),
            'obs34d_segment_boundaries_different':dict(segments),
            'first_obs34d_difference':boundary_changes[0]['time_s'] if boundary_changes else None,
            'actions_different':len(action_diff),
            'action_indices_different':action_diff,
            'representation':{'unique_lanes':len(set(nom['h12_7_diagnostic']['controlled_lanes_unique_raw'])),
                              'lanes_12':nom['h12_7_diagnostic']['controlled_lanes_used_12'],
                              'outgoing_lanes':nom['h12_7_diagnostic']['outgoing_lanes'],
                              'green_phases':nom['h12_7_diagnostic']['green_phases']},
            'limitations':['300 s/semilla única, NO inferencia estadística de resiliencia',
                           'Estado 34D y mapa de acciones heredados; no corregir sin reentrenar',
                           'No se homologa aquí el tiempo amarillo ni SOTA multiagente',
                           'No demuestra representatividad poblacional de Quito']}


def markdown(r):
    lines=['# H12.9 — Exposición de Vine ante PPO, 300 segundos','',
           '**Estado:** '+r['status']+' · **Modelo:** `'+r['model']+'` · seed 101',
           '**Nominal y probe idénticos:** sí. **Comandos Vine confirmados:** '+str(r['vine_confirmed']),
           '**Cambio cinemático global:** sí.', '',
           '| Indicador | Nominal | Probe | Vine activo |','|---|---:|---:|---:|']
    labels={'ticks_b1_vehicles':'Microticks B1 con vehículos',
            'ticks_b1_halted':'Microticks B1 con detenidos',
            'ticks_b1_wait':'Microticks B1 con espera',
            'b1_vehicle_ticks':'Vehículo-microticks en B1',
            'ticks_with_selected_vine_in_b1':'Microticks con cohorte Vine presente en B1',
            'unique_selected_vine_in_b1':'Vehículos Vine distintos presentes en B1',
            'decisions_queue_nonzero':'Decisiones con cola local no nula',
            'decisions_delay_nonzero':'Decisiones con espera local no nula',
            'decisions_reward_nonzero':'Decisiones con recompensa no nula',
            'commands':'Comandos aplicados',
            'mean_b1_speed_m_s_time_avg':'Velocidad media temporal local B1 (m/s)'}
    for key,lab in labels.items():
        lines.append('| '+lab+' | '+' | '.join(str(r['metrics'][m][key]) for m in ('nominal','probe','active'))+' |')
    lines+=['','## Sensibilidad de estado/acción',
            f"- Microticks con diferencias en agregados B1: {r['b1_local_aggregate_microticks_different']} de 600",
            f"- Primer cambio agregado B1: {r['first_b1_aggregate_difference']}",
            f"- Microticks con velocidad media B1 diferente: {r['b1_local_mean_speed_microticks_different']}",
            f"- Registros velocidad individual Vine en B1 diferentes: {r['b1_selected_vine_speed_records_different']}",
            f"- Primer cambio de velocidad B1: {r['first_b1_local_speed_difference']}",
            f"- Decisiones con entrada 34D diferente: {r['obs34d_boundaries_different']} de 60",
            f"- Primera diferencia 34D: {r['first_obs34d_difference']}",
            f"- Segmentos de observación afectados: {r['obs34d_segment_boundaries_different']}",
            f"- Decisiones semafóricas diferentes: {r['actions_different']} de 60",
            f"- Frecuencia acciones nominal: {r['metrics']['nominal']['action_frequencies']}",
            f"- Frecuencia acciones activo: {r['metrics']['active']['action_frequencies']}",
            '', '## Contrato heredado que NO se ha corregido',
            f"- Fases verdes: {r['representation']['green_phases']}",
            f"- Carriles únicos B1: {r['representation']['unique_lanes']}; 12 posiciones del estado original", 
            f"- Carriles salientes: {len(r['representation']['outgoing_lanes'])} (estado heredado)",
            '', '## Límites', *('- '+x for x in r['limitations']), '']
    return '\n'.join(lines)


def run_simulation(args):
    root=args.revision_root.resolve();repo=args.repo_root.resolve()
    if args.seed!=101 or args.rl_steps!=60:
        raise RuntimeError('H12.9 limitado a 300 s y seed=101 por referencia H08/H10 congelada')
    if args.max_commands<1 or args.max_commands>100:
        raise RuntimeError('max_commands fuera de 1..100')
    if not repo.is_dir() or not root.is_dir():
        raise NotADirectoryError('Repositorios ausentes')
    base,shas=load_source_overlay(root)
    sources=base.validate_source(root)
    h10,ctx,params=base.make_h10_context(root,args)
    h10.verify_sources(ctx[12])
    ck=repo/'tsc_framework/outputs/models'/f'{args.model}.zip'
    if not ck.is_file():raise FileNotFoundError(ck)
    print('H12.9 | PLAN VALIDADO | fuentes',len(sources),
          '| checkpoint',sha256(ck)[:16], '| H08 referencia',len(ctx[10]),
          '| Vine/H09:',len(ctx[11]['selected_vine']),len(ctx[11]['selected_h09']))
    if args.mode=='plan':
        print('PLAN_OK: no se ha abierto SUMO ni generado nuevos resultados.');return 0
    if args.ack_active!='EXPERIMENTAL_ONLY' or args.ack_time_scale!='NOT_CALIBRATED':
        raise RuntimeError('acknowledgments ACTIVE / escala temporal requeridos')
    folder=root/'resultados'/('h12_9_exposicion_300s_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=False)
    try:
        p=base.parse(['--revision-root',str(root),'--repo-root',str(repo),
          '--mode','active','--model',args.model,'--seed',str(args.seed),
          '--rl-steps',str(args.rl_steps),'--tls-id',args.tls_id,
          '--max-commands',str(args.max_commands),
          '--ack-active',args.ack_active,'--ack-time-scale',args.ack_time_scale])
        output={}
        for mode in ('nominal','probe','active'):
            dst=folder/mode;dst.mkdir()
            print('INICIANDO',mode,'300s ->',dst,flush=True)
            output[mode]=base.run_one(mode,root,repo,p,h10,ctx,params,dst)
            if mode=='probe':
                base.assert_probe_pair(output['nominal'],output['probe'])
            if mode=='active':
                pair_integrity(output['nominal'],output['probe'],output['active'])
        report=compare(output['nominal'],output['probe'],output['active'])
        report['sha_manifest']=shas
        (folder/'dictamen_h12_9.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        (folder/'dictamen_h12_9.md').write_text(markdown(report),encoding='utf-8')
        print('H12_9_EXTENDED_OK: comandos',report['vine_confirmed'],
              '| B1 local diffs',report['b1_local_aggregate_microticks_different'],
              '| obs 34D diff',report['obs34d_boundaries_different'],
              '| PPO actions diff',report['actions_different'])
        print('INFORME',folder)
        return 0
    except Exception as exc:
        (folder/'ERROR_h12_9.json').write_text(json.dumps({'type':type(exc).__name__,
            'error':str(exc),'traceback':traceback.format_exc()},indent=2,ensure_ascii=False),encoding='utf-8')
        print('FALLO H12.9:',str(exc),'\nDIR',folder,file=sys.stderr)
        return 2


def parse(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision-root',type=Path,default=Path('.'))
    p.add_argument('--repo-root',type=Path)
    p.add_argument('--mode',choices=('plan','run','analyze'),default='plan')
    p.add_argument('--results-dir',type=Path,help='Para mode analyze: carpeta con nominal/probe/active')
    p.add_argument('--model',default='ppo_ideal',choices=('ppo_ideal','ppo_chaos','ppo_coop_ideal','ppo_coop_chaos'))
    p.add_argument('--tls-id',default='B1')
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--rl-steps',type=int,default=60)
    p.add_argument('--max-commands',type=int,default=100)
    p.add_argument('--data-dir',type=Path,default=None)
    p.add_argument('--reference-baseline-dir',type=Path,default=None)
    p.add_argument('--ack-active',default='')
    p.add_argument('--ack-time-scale',default='')
    return p.parse_args(argv)


def main(argv=None):
    a=parse(argv)
    if a.mode=='analyze':
        if not a.results_dir:raise RuntimeError('--results-dir requerido en analyze')
        n=load_result(a.results_dir,'nominal');p=load_result(a.results_dir,'probe');v=load_result(a.results_dir,'active')
        r=compare(n,p,v);out=Path(a.results_dir)
        (out/'dictamen_h12_9.json').write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
        (out/'dictamen_h12_9.md').write_text(markdown(r),encoding='utf-8')
        print(r['status'],out);return 0
    if not a.repo_root:raise RuntimeError('--repo-root requerido para plan/run')
    return run_simulation(a)

if __name__=='__main__':
    raise SystemExit(main())
