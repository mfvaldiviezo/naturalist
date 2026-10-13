#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.5: integración H10 v112 + H12.2, sin modificar originales.

Pares NOMINAL/PROBE o pilotos ACTIVE/H09/HYBRID cortos. No evalúa resiliencia.
Preparación H10 preserva ranking del baseline congelado de 600 pasos, semilla 101.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET

VERSION = 'H12.5-v1.0.0'
REL_SHA = {
    'H10_Vine_H09_Imprudencia_v112/scripts/piloto_hibrido_h10.py': '42a6fb5674307560688164c5ebbe7f06160a5df55b58c8fb021e1daac6211e7b',
    'H09_Quito_Perfiles_Contextuales_v12/scripts/piloto_perfiles_h09_v12.py': 'f7f9c40e94e6e2ac8f2d11eb3e38f345aff481cd463127eaacfcf84c611599e6',
    'H12_2_Puente_Gymnasium_Microtick_v100/h12_2_puente.py': '750afc8412fbb40c84b4f56e9ed70dced0a7973d8409bc627190789d12baf508',
    'scripts/ntvc_vine_r_08b_cuota_auditada.py': 'ee70a04c7f0b698309f7a637a8a0b2b5ddf18434ec3ab6c11dc3346a7a904943',
    'scripts/ntvc_vine_r_08_inyector_estres_porcentual.py': '514da8097c896abd5244b6ecfa43ec555904d0e0f53ce199d47adc06fddb59c1',
    'scripts/ntvc_vine_r_06_piloto_integracion_protegida.py': '574f29d52e43241907bad53e54b6d73c7fa506c5914683cc0c0672449f9846f5',
    'scripts/ntvc_vine_r_03_integracion_cinematica_sumo.py': '0f9041ace1ee38fceea99d21ad789c3aa1f1b8ba2ae1c39dd5d753cd6d7fe855',
    'scripts/ntvc_vine_r_04_shadow_multivehiculo_rutas_corregidas.py': '08a5383893798bcd65a40a0cb414bd17e07c95f3d6ed4305549827bfcb1e9d76',
}
H10_REFERENCE_STEPS = 600
MICROTICK_S = .5
DECISION_S = 5.


def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def validate_source(revision):
    checks = {}
    for rel, expected in REL_SHA.items():
        path = (revision / rel).resolve()
        if not path.is_file():
            raise FileNotFoundError('FUENTE H12.5 AUSENTE: '+str(path))
        actual = digest(path)
        if actual != expected:
            raise RuntimeError('SOURCE_CHANGED_FAIL_CLOSED '+rel+' esperado='+expected+' actual='+actual)
        checks[rel] = actual
    return checks


def import_py(path, alias):
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise RuntimeError('No se pudo importar '+str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_h10_context(revision, args):
    h10 = import_py(revision/'H10_Vine_H09_Imprudencia_v112/scripts/piloto_hibrido_h10.py',
                    '_h125_h10_'+uuid.uuid4().hex)
    # Los requisitos de H10: baseline H08 de 600 pasos, mismo dt y misma semilla.
    params = argparse.Namespace(root=revision, vine_scripts=revision/'scripts',
             reference_baseline_dir=args.reference_baseline_dir,
             data_dir=args.data_dir, steps=H10_REFERENCE_STEPS,
             dt=MICROTICK_S, seed=args.seed, max_commands=args.max_commands)
    ctx = h10.prepare(params)
    h10.verify_sources(ctx[12])
    return h10, ctx, params


def verify_vehicle_demand(original, candidate, selected):
    """H09 solo puede cambiar 'type' para la cohorte autorizada; toda ruta/demanda permanece."""
    a = ET.parse(original).getroot()
    b = ET.parse(candidate).getroot()
    def encode(root):
        out = {}
        for v in root.findall('vehicle'):
            id_ = v.get('id')
            if not id_ or id_ in out:
                raise RuntimeError('IDs originales/convertidos duplicados o vacíos')
            attrs = dict(v.attrib)
            children = tuple(ET.tostring(x,encoding='unicode') for x in v)
            out[id_] = (attrs,children)
        return out
    original_map=encode(a)
    rewritten_map=encode(b)
    if original_map.keys()!=rewritten_map.keys():
        raise RuntimeError('H09 CAMBIO DEMANDA: vehículos no coinciden')
    for id_, (attrs,children) in original_map.items():
        candidate_attrs,candidate_children=rewritten_map[id_]
        if id_ in selected:
            candidate_attrs=dict(candidate_attrs)
            if candidate_attrs.pop('type',None)!='H09_EXPLORATORIO_V12':
                raise RuntimeError('H09 vType incorrecto en vehículo seleccionado')
            # H09 v12 permite asignación solo a tipos DEFAULT_VEHTYPE implícitos.
            if attrs.get('type','DEFAULT_VEHTYPE')!='DEFAULT_VEHTYPE':
                raise RuntimeError('H09 vehículo seleccionado no era tipo default')
            baseline_attrs=dict(attrs);baseline_attrs.pop('type',None)
            if baseline_attrs!=candidate_attrs or children!=candidate_children:
                raise RuntimeError('H09 CAMBIO DEMANDA: ruta/salida/atributos modificados')
        elif attrs!=candidate_attrs or children!=candidate_children:
            raise RuntimeError('H09 CAMBIO DEMANDA: vehículo no seleccionado fue modificado')
    actual={v.get('id') for v in b.findall('vehicle') if v.get('type')=='H09_EXPLORATORIO_V12'}
    if actual != set(selected):
        raise RuntimeError('Asignación H09 no equivale a cohorte congelada')
    return {'vehicles_unchanged':len(original_map),'h09_assigned':len(actual)}


def create_overlay_config(cfg_original, net, routes, dst):
    """Copiar configuración original sin alterar su red, demanda o simulación; salidas en resultados."""
    tree=ET.parse(cfg_original)
    root=tree.getroot()
    inp=root.find('input')
    if inp is None:
        raise RuntimeError('SUMOCFG H10 sin input')
    if inp.find('additional-files') is not None:
        raise RuntimeError('No admite additional-files: conservar contrato H10')
    for tag,p in [('net-file',net),('route-files',routes)]:
        el=inp.find(tag)
        if el is None: raise RuntimeError('SUMOCFG H10 sin '+tag)
        el.set('value',str(Path(p).resolve()))
    # Evitar cualquier efecto lateral del SUMOCFG heredado en archivos originales.
    output=root.find('output')
    if output is not None:
        root.remove(output)
    tree.write(dst,encoding='utf-8',xml_declaration=True)
    return {'cfg_original_sha256':digest(cfg_original),
            'cfg_overlay_sha256':digest(dst),'net_sha256':digest(net),
            'routes_sha256':digest(routes), 'outputs_xml_removed':output is not None}


def make_injector(h10,ctx,params,kind,horizon_s):
    _,h08b,h08,h06,_,_,_,_,_,_,ranked,coh,_,_ = ctx
    if kind not in ('probe','active','hybrid'):
        return None
    cfg=h10.build_vine_config(h08,params,'hibrido_protegido' if kind=='hybrid' else 'vine_protegido')
    # La ventana terminal se cierra ANTES del final para garantizar t+dt observado.
    cfg=replace(cfg,mode='probe' if kind=='probe' else 'active',
                end_time=min(cfg.end_time,horizon_s-MICROTICK_S))
    cfg.validate()
    if cfg.end_time <= 0:
        raise RuntimeError('Horizonte insuficiente para Vine')
    kernel,groups,_,_,_ = h08.load_frozen_cohorts(params.data_dir or h06.DEFAULT_DATA,cfg)
    vine_ids=set(coh['selected_vine'])
    if not vine_ids or not vine_ids.issubset(set(ranked)):
        raise RuntimeError('Vine no tiene cohorte H08 válida')
    return h08b.FixedRosterInjector(cfg,kernel,groups,ranked,vine_ids)


def snapshot(traci, tick):
    """Telemetría posterior al microtick, ANTES de programar la intervención del siguiente."""
    sim=traci.simulation
    ids=sorted(map(str,traci.vehicle.getIDList()))
    speeds=[]; accelerations=[]; vehicle_parts=[]
    for vid in ids:
        v=float(traci.vehicle.getSpeed(vid));a=float(traci.vehicle.getAcceleration(vid))
        if not math.isfinite(v) or not math.isfinite(a):
            raise RuntimeError('Telemetría no finita')
        speeds.append(v);accelerations.append(a)
        vehicle_parts.append((vid,format(v,'.12g'),format(a,'.12g')))
    body=json.dumps(vehicle_parts,ensure_ascii=False,separators=(',',':'))
    return {'tick':int(tick),'time_s':float(sim.getTime()),'n_active':len(ids),
      'mean_speed_kmh':float(sum(speeds)/len(speeds)*3.6) if ids else 0.,
      'n_halted':sum(v<0.1 for v in speeds),
      'arrivals':int(sim.getArrivedNumber()),'departures':int(sim.getDepartedNumber()),
      'collisions':int(sim.getCollidingVehiclesNumber()),
      'teleports_start':int(sim.getStartingTeleportNumber()),
      'vehicle_kinematics_sha256':hashlib.sha256(body.encode('utf-8')).hexdigest()}


class H10Hook:
    """Lecturas primero, H08b.on_step después; cero simulationStep propio."""
    def __init__(self,kind,injector=None,h09_ids=()):
        self.kind=kind;self.injector=injector
        self.h09_ids=set(h09_ids)
        self.rows=[];self.h09_seen=set();self.h09_verified=set()
    def on_step(self,traci,tick):
        row=snapshot(traci,tick)
        self.rows.append(row)
        if self.h09_ids:
            ids=set(map(str,traci.vehicle.getIDList()))
            exposed=ids & self.h09_ids
            self.h09_seen.update(exposed)
            for vid in exposed:
                if str(traci.vehicle.getTypeID(vid))=='H09_EXPLORATORIO_V12':
                    self.h09_verified.add(vid)
                else:
                    raise RuntimeError('H09 RUNTIME TYPE MISMATCH '+str(vid))
        if self.injector is not None:
            self.injector.on_step(traci,tick)
    def trace_hash(self):
        payload=json.dumps(self.rows,sort_keys=True,ensure_ascii=False,
                           separators=(',',':'),allow_nan=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()
    def finalize(self):
        info={'trace_sha256':self.trace_hash(),'n_snapshots':len(self.rows),
              'h09_seen':len(self.h09_seen),'h09_verified':len(self.h09_verified)}
        if self.injector is not None:
            actions,fleet,assignment,meta=self.injector.results()
            info['vine']=meta
            info['n_commands_confirmed']=int(meta['n_commands_confirmed'])
            info['n_commands']=int(meta['n_commands'])
            info['pending']=int(meta['remaining_pending'])
            info['_frames']=(actions,fleet,assignment)
        return info


def assert_probe_pair(nom,pro):
    if nom['result']!='SMOKE_OK' or pro['result']!='SMOKE_OK':
        raise RuntimeError('SMOKE NO EXITOSO')
    if nom['n_decisions']!=pro['n_decisions'] or nom['n_microticks']!=pro['n_microticks']:
        raise RuntimeError('INVARIANCIA: horizontes diferentes')
    if nom['trace_sha256']!=pro['trace_sha256']:
        raise RuntimeError('INVARIANCIA FALLIDA: tráfico nominal/probe diferente')
    if int(pro['commands']) or int(nom['commands']):
        raise RuntimeError('INVARIANCIA: nominal/probe contienen comandos')
    return {'status':'PAREADO_NOMINAL_PROBE_OK',
            'traffic_sha256':nom['trace_sha256'],'decisions':nom['n_decisions'],
            'microticks':nom['n_microticks']}


def run_one(mode,root,repo,args,h10,ctx,params,out):
    bridge_mod=import_py(root/'H12_2_Puente_Gymnasium_Microtick_v100/h12_2_puente.py',
                         '_h125_bridge_'+uuid.uuid4().hex)
    # La fuente TSCEnv se verifica contra el blob git fijado en H12.2.
    source=bridge_mod.audited_source_path(repo)
    source_sha=bridge_mod.git_blob_sha(source)
    patched=bridge_mod.exact_patch(source.read_text(encoding='utf-8-sig'),source_sha)
    _,_,_,h06,h09,profile,_,planned,explicit,_,_,coh,sources,_=ctx
    cfg_original,net,routes=h09.original_inputs(ctx[0]['cfg'])
    has_h09=mode in ('h09','hybrid')
    h09sel=set(coh['selected_h09']) if has_h09 else set()
    route_used=routes
    h09_audit=None
    if has_h09:
        tree,planned2,explicit2=h09.read_roster(routes,H10_REFERENCE_STEPS*MICROTICK_S)
        if set(planned2)!=set(planned):raise RuntimeError('CAMBIO DE ROSTER EN H09')
        route_used=h09.clone_route(tree,explicit2,h09sel,profile,out/'rutas_h09.rou.xml')
        h09_audit=h10.verify_route_assignment(route_used,planned,h09sel)
        h09_audit.update(verify_vehicle_demand(routes,route_used,h09sel))
    cfg=out/'escenario_h12_5.sumocfg'
    input_info=create_overlay_config(cfg_original,net,route_used,cfg)
    bridge_mod.input_manifest(cfg)
    # Preparación de artefactos Vine originales SIN reconstruir el modelo desde crudos.
    injector=make_injector(h10,ctx,params,mode,args.rl_steps*DECISION_S)
    hook=H10Hook(mode,injector,h09sel)
    bridge_mode='probe' if mode=='probe' else 'active' if injector else 'nominal'
    bridge=bridge_mod.MicrotickBridge(bridge_mode,hook,
                         max_commands=args.max_commands,microtick_s=MICROTICK_S)
    if str(repo/'tsc_framework') not in sys.path:
        sys.path.insert(0,str(repo/'tsc_framework'))
    from stable_baselines3 import PPO
    from src.rl_agent.sarg_policy import HSARGExtractor, CoopSARGExtractor  # noqa F401
    import numpy as np
    overlay=out/'tsc_env_h12_5_overlay.py'
    overlay.write_text(patched,encoding='utf-8')
    module=import_py(overlay,'_h125_tsc_'+uuid.uuid4().hex)
    path=repo/'tsc_framework/outputs/models'/f'{args.model}.zip'
    if not path.is_file():raise FileNotFoundError('Checkpoint '+str(path))
    model=PPO.load(str(path),device='cpu')
    if model.observation_space.shape!=(34,) or model.action_space.n!=4:
        raise RuntimeError('CKP: dimensiones incompatibles')
    env=None;decisions=[];start=None
    try:
        env=module.TSCEnv(sumocfg_path=cfg,tls_id=args.tls_id,
                          delta_t=5,max_steps=args.rl_steps,seed=args.seed,
                          enable_traci_chaos=False)
        env._h12_log_path=str(out/'sumo_stderr.log')
        env._h12_after_microtick=bridge.after_microtick
        state,_=env.reset(seed=args.seed)
        start=float(module.traci.simulation.getTime())
        for decision in range(args.rl_steps):
            if tuple(state.shape)!=(34,) or not np.isfinite(state).all():
                raise RuntimeError('Estado PPO sin 34D finitos')
            action,_=model.predict(state,deterministic=True)
            action=int(np.asarray(action).reshape(-1)[0])
            state,reward,terminated,truncated,info=env.step(action)
            sim=float(info.get('sim_time',float('nan')))
            if abs(sim-(start+(decision+1)*DECISION_S))>1.e-6:
                raise RuntimeError('Contrato RL 5s roto')
            decisions.append({'i':decision,'action':action,'reward':float(reward),
                   'sim_time_s':sim,'phase':int(info.get('phase',-1)),
                   'queue':float(info.get('total_queue',float('nan'))),
                   'delay_proxy':float(info.get('delay',float('nan'))),
                   'gini':float(info.get('gini',float('nan'))),
                   'terminated':bool(terminated),'truncated':bool(truncated)})
            if terminated or truncated:break
    finally:
        if env is not None:env.close()
    if len(decisions)!=args.rl_steps or bridge.after_calls!=args.rl_steps*10:
        raise RuntimeError('SIMULACION INCOMPLETA o doble microtick')
    data=hook.finalize()
    frames=data.pop('_frames',None)
    if len(hook.rows)!=bridge.after_calls:
        raise RuntimeError('Cantidad de mediciones no corresponde a microticks')
    if frames:
        actions,fleet,assignment=frames
        # Las tablas originales H08 se guardan exclusivamente en resultados de esta corrida.
        actions.to_csv(out/'acciones_h08b.csv',index=False)
        fleet.to_csv(out/'trafico_h08b.csv',index=False)
        assignment.to_csv(out/'asignaciones_h08b.csv',index=False)
        if data['n_commands_confirmed']!=data['n_commands'] or data['pending']:
            raise RuntimeError('ACCIONES VINE SIN CONFIRMACION t+dt')
    if mode in ('probe','nominal','h09') and bridge.command_count!=0:
        raise RuntimeError('Comandos en un escenario sin Vine activo')
    if mode in ('active','hybrid') and data.get('n_commands',0)<1:
        raise RuntimeError('SIN COMANDOS: piloto active no demuestra inyección')
    if data.get('n_commands',0)!=bridge.command_count:
        raise RuntimeError('DESACUERDO entre conteo de comandos puente/H08b')
    if has_h09 and data['h09_verified']!=data['h09_seen']:
        raise RuntimeError('H09 SELECTED TYPES NO VERIFICADOS')
    # Par final: evita atribuciones de métricas RL a una corrida corta.
    result={'result':'SMOKE_OK','mode':mode,'model':args.model,
        'checkpoint_sha256':digest(path),'n_decisions':len(decisions),
        'n_microticks':bridge.after_calls,'start_time_s':start,
        'end_time_s':hook.rows[-1]['time_s'],'commands':bridge.command_count,
        'trace_sha256':data['trace_sha256'],'inputs':input_info,
        'h09_route_audit':h09_audit,'h10_reference_path':str(ctx[9]),
        'h10_reference_n':len(ctx[10]),'h09_selected_n':len(h09sel),
        'vine_assigned_n':len(coh['selected_vine']) if injector else 0,
        'h10_source_sha256':sources,'decisions':decisions,
        'microticks':hook.rows,'command_records':bridge.command_records,
        'extra':data,
        'limits':['PILOTO, no evidencia de resiliencia ni representatividad Quito',
                  'Control semafórico B1, transiciones amarillas heredadas no homologadas',
                  'Presupuesto de entrenamiento entre PPO no equiparado']}
    (out/'piloto_h12_5.json').write_text(json.dumps(result,ensure_ascii=False,
              indent=2,allow_nan=False),encoding='utf-8')
    h10.verify_sources(sources)
    return result


def parse(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision-root',type=Path,default=Path('.'))
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--mode',choices=('plan','pair','active','h09','hybrid'),default='plan')
    p.add_argument('--model',choices=('ppo_ideal','ppo_chaos','ppo_coop_ideal','ppo_coop_chaos'),default='ppo_ideal')
    p.add_argument('--tls-id',default='B1')
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--rl-steps',type=int,default=4)
    p.add_argument('--max-commands',type=int,default=30)
    p.add_argument('--data-dir',type=Path,default=None)
    p.add_argument('--reference-baseline-dir',type=Path,default=None)
    p.add_argument('--ack-active',default='')
    p.add_argument('--ack-time-scale',default='')
    args=p.parse_args(argv)
    if args.seed!=101:
        p.error('H12.5 v1 preserva solo seed=101 de referencia H10; otras semillas exigen baseline H08 propio')
    if not 2 <= args.rl_steps <= 20:
        p.error('Se requieren 2..20 decisiones PPO por piloto')
    if args.max_commands<1 or args.max_commands>100:
        p.error('max-commands debe estar entre 1 y 100')
    if args.mode in ('active','h09','hybrid') and (
         args.ack_active!='EXPERIMENTAL_ONLY' or args.ack_time_scale!='NOT_CALIBRATED'):
        p.error('Para intervención se exigen --ack-active EXPERIMENTAL_ONLY y --ack-time-scale NOT_CALIBRATED')
    return args


def main(argv=None):
    args=parse(argv)
    root=args.revision_root.resolve();repo=args.repo_root.resolve()
    if not root.is_dir() or not repo.is_dir():raise NotADirectoryError('Revisión/repo no accesible')
    sys.dont_write_bytecode=True
    sources=validate_source(root)
    h10,ctx,params=make_h10_context(root,args)
    model=repo/'tsc_framework/outputs/models'/f'{args.model}.zip'
    if not model.is_file():raise FileNotFoundError(model)
    print('H12.5 | FUENTES VALIDADAS:',len(sources),'| H10 baseline:',str(ctx[9]))
    print('H08 referencia:',len(ctx[10]),'| VINE 15%:',len(ctx[11]['selected_vine']),
          '| H09 15%:',len(ctx[11]['selected_h09']))
    print('PPO:',args.model,'| 34D/4 acciones ya verificados en H12.1')
    print('Se utilizará la red/ruta H10 auditada, NO la demanda mínima H12.2.')
    if args.mode=='plan':
        print('PLAN_OK: cero archivos escritos; solo lectura de entradas e importaciones originales.')
        return 0
    results=root/'resultados'
    results.mkdir(exist_ok=True)
    out=results/('h12_5_'+args.mode+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(exist_ok=False)
    try:
        def run(label):
            loc=out/label;loc.mkdir(exist_ok=False)
            print('INICIANDO',label,'OUTPUT',str(loc),flush=True)
            return run_one(label,root,repo,args,h10,ctx,params,loc)
        if args.mode=='pair':
            nom=run('nominal');pro=run('probe')
            check=assert_probe_pair(nom,pro)
            (out/'pareado_h12_5.json').write_text(json.dumps(check,indent=2),encoding='utf-8')
            print('PAIR_OK:',check['decisions'],'decisiones; SHA trafico nominal=probe',check['traffic_sha256'])
        else:
            result=run(args.mode)
            print('SMOKE_OK:',result['n_decisions'],'decisiones;',result['n_microticks'],
                  'microticks;',result['commands'],'comandos; 0..',result['end_time_s'],'s')
        (out/'manifest_fuentes.json').write_text(json.dumps({'version':VERSION,'sources':sources,
             'model':str(model),'model_sha256':digest(model),'seed':args.seed},indent=2),encoding='utf-8')
        print('INFORME:',out)
        return 0
    except Exception as e:
        (out/'ERROR_h12_5.json').write_text(json.dumps({'type':type(e).__name__,
            'message':str(e),'traceback':traceback.format_exc()},ensure_ascii=False,indent=2),encoding='utf-8')
        print('H12.5 FALLO:',type(e).__name__,str(e),file=sys.stderr)
        print('DIAGNÓSTICO:',out)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
