#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NTVC-Vine-R Hito 06: piloto SUMO con puerta de seguridad cerrada por defecto.

MODOS: baseline (SUMO nominal), probe (Vine sin control), active (prueba EXPLORATORIA
limitada a via libre, con autorizaciones explicitas). El nucleo estadistico Hito02/03
NO se retoca. NUNCA ejecuta setSpeed, setSpeedMode, setTau, setImperfection,
setRoute, setStop ni cambia el escenario original. Solo active puede ejecutar
setAcceleration por UN unico paso SUMO, conservando speedMode=31.

PELIGRO METODOLOGICO: variar --step-length a 0.5 NO valida automaticamente la
transferencia POLIDriving -> SUMO. Resultados active: PRUEBA DE INTEGRACION,
no prueba de naturalismo/seguridad ni de resiliencia del sistema RL.

Instalar este archivo junto a scripts Hito02, Hito03, Hito04; ejecutar --self-test
antes de conectar a SUMO. No accede a Richard ni datos RAW, solo cohortes Hito01.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
from typing import Dict, Optional

import numpy as np
import pandas as pd

from ntvc_vine_r_03_integracion_cinematica_sumo import (
    ROOT, DATA, VARIANTS, ShadowHistory, CausalVineProposer,
    guard_step, fit_fold, read_artifacts, sha256,
)
from ntvc_vine_r_04_shadow_multivehiculo_rutas_corregidas import deterministic_seed, classify_constraints

VERSION = 'NTVC-Vine-R Hito06 Integracion Protegida v1'
DEFAULT_DATA = ROOT / 'resultados' / 'ntvc_vine_r_01_cohortes_movimiento_regenerado'
DEFAULT_OUTPUT = ROOT / 'resultados' / 'ntvc_vine_r_06_piloto_integracion_protegida'
FIT_SEED = 2026  # Misma reestimacion congelada Hito04/05 con seed SUMO 2026.
ACTIVE_ACK = 'EXPERIMENTAL_ONLY'
TIME_ACK = 'NOT_CALIBRATED'


def sumo_input_hashes(cfg):
    """Manifiesto de net, rutas y adicionales; no copia ni altera archivos.

    Algunas configuraciones pueden usar rutas dinamicas; se identifican como
    no resueltas y no deben declararse completas en el reporte final.
    """
    paths={str(cfg):sha256(cfg)}
    try:
        root=ET.parse(cfg).getroot()
        inputs=root.find('input')
        if inputs is None:return paths
        for e in inputs:
            if e.tag not in ('net-file','route-files','additional-files'):
                continue
            names=e.attrib.get('value','')
            for raw in names.split(','):
                name=raw.strip().strip('"')
                if not name:continue
                dep=Path(name)
                if not dep.is_absolute():dep=cfg.parent/dep
                dep=dep.resolve()
                paths[str(dep)]=sha256(dep) if dep.is_file() else 'UNRESOLVED'
    except ET.ParseError:
        paths['SUMOCFG_XML_PARSE']='UNRESOLVED'
    return dict(sorted(paths.items()))


def validate_args(args):
    if args.mode in ('probe', 'active') and args.variant not in VARIANTS:
        raise ValueError('probe/active requieren --variant moving_p2|vine_gaussian|vine_student.')
    if args.mode == 'active':
        if args.ack_active != ACTIVE_ACK or args.ack_time_scale != TIME_ACK:
            raise ValueError('active requiere --ack-active EXPERIMENTAL_ONLY '
                             '--ack-time-scale NOT_CALIBRATED; no es validacion cientifica.')
        if args.step_length is None or not (0.1 <= args.step_length <= 0.6):
            raise ValueError('active exige --step-length entre 0.1 y 0.6 segundos. '
                             'No se permite aplicar al dt SUMO=1 s sin un puente temporal.')
    if args.mode not in ('baseline','probe','active'):
        raise ValueError('Modo invalido.')
    if args.sumo_steps < 5 or args.max_vehicles < 1 or args.max_commands < 1:
        raise ValueError('sumo-steps >=5, max-vehicles >=1 y max-commands >=1.')
    if (args.bins_per_sign, args.max_fit, args.moving_min_kmh) != (8,2000,5.0):
        raise ValueError('Nucleo estadistico Hito02 congelado (8,2000,5.0).')
    if args.variant and args.mode == 'baseline':
        raise ValueError('baseline no debe tener --variant (no se ajusta modelo Vine).')
    for field in ('free_gap_m','follower_gap_m','distance_to_lane_end_m','tls_distance_m'):
        if getattr(args,field) < 0: raise ValueError(f'{field} debe ser no negativo.')


def strictly_safe_context(traci, vid, args):
    """Condiciones CONSERVADORAS; desconocimiento -> abstencion, NO extrapolacion.

    Conserva speedMode SUMO 31, paso en circulacion, sin lider/seguidor cercanos,
    lejos de TLS y de final de carril, sin tramos internos de interseccion.
    La regla no demuestra seguridad fisica: solo reduce el dominio de actuacion.
    """
    veh = traci.vehicle
    try:
        if int(veh.getSpeedMode(vid)) != 31:
            return 'speed_mode_no_default', None
        if str(veh.getVehicleClass(vid)) != 'passenger':
            return 'class_not_passenger', None
        speed = float(veh.getSpeed(vid))
        aobs = float(veh.getAcceleration(vid))
        if not math.isfinite(speed) or not math.isfinite(aobs) or speed <= args.moving_min_kmh/3.6:
            return 'not_moving', None
        lane = str(veh.getLaneID(vid))
        if not lane or lane.startswith(':'):
            return 'internal_or_unknown_lane', None
        left = float(traci.lane.getLength(lane)) - float(veh.getLanePosition(vid))
        if not math.isfinite(left) or left <= args.distance_to_lane_end_m:
            return 'near_lane_end', None
        next_tls = veh.getNextTLS(vid)
        if next_tls is None:
            return 'unknown_next_tls', None
        if any(float(tls[2]) <= args.tls_distance_m for tls in next_tls):
            return 'near_tls', None
        leader = veh.getLeader(vid, max(100.0, args.free_gap_m))
        if leader and str(leader[0]):
            gap = float(leader[1])
            if not math.isfinite(gap) or gap <= args.free_gap_m:
                return 'leader_near', None
        follower = veh.getFollower(vid, max(100.0,args.follower_gap_m))
        if follower and str(follower[0]):
            gap = float(follower[1])
            if not math.isfinite(gap) or gap <= args.follower_gap_m:
                return 'follower_near', None
        allowed = min(float(veh.getAllowedSpeed(vid)), args.max_speed_kmh/3.6)
        if not math.isfinite(allowed) or allowed <= 0 or speed > allowed+1.e-7:
            return 'invalid_or_exceeded_speed_limit', None
        return 'eligible', {'speed':speed,'a_current':aobs,'speed_limit':allowed,
                            'free_lane_m':left}
    except (Exception,):
        return 'missing_or_invalid_safety_telemetry', None


def sim_counts(sim, need_safety):
    out={}
    for name, getter in (
        ('collisions','getCollidingVehiclesNumber'),
        ('teleport_start','getStartingTeleportNumber'),
        ('arrived','getArrivedNumber'),
        ('departed','getDepartedNumber'),
    ):
        fun=getattr(sim,getter,None)
        if fun is None:
            if need_safety and name in ('collisions','teleport_start'):
                raise RuntimeError(f'SUMO no ofrece {getter}: active se cancela (fail closed).')
            out[name]=None
        else:
            try:out[name]=int(fun())
            except Exception as exc:
                if need_safety and name in ('collisions','teleport_start'):
                    raise RuntimeError(f'Telemetria de seguridad {getter} no disponible.') from exc
                out[name]=None
    return out


def run_experiment(args, traci, kernel=None, groups=None):
    """Necesita una conexion TraCI YA abierta. No hace modificaciones de archivos.

    Propuestas son independientes por paso y se condicionan al par de aceleraciones
    realmente observadas (no se inyecta futuro en el estado). Emparejamiento t+dt.
    """
    counts=Counter()
    admitted=set()
    history:Dict[str,ShadowHistory]={}
    rows=[];fleet=[];pending={}
    command_count=0; collision_halt=False
    for step in range(args.sumo_steps):
        traci.simulationStep()
        sim=traci.simulation
        t=float(sim.getTime());dt=float(sim.getDeltaT())
        if not math.isfinite(dt) or dt<=0: raise RuntimeError('DeltaT invalido de SUMO.')
        if args.mode=='active' and not (0.1<=dt<=0.6):
            raise RuntimeError(f'SUMO DeltaT={dt} fuera del rango experimental activo autorizado.')
        ids=sorted(set(traci.vehicle.getIDList()))
        for vid in ids:
            if len(admitted)>=args.max_vehicles: break
            admitted.add(vid)
        active=set(ids)&admitted
        for vid in list(history):
            if vid not in active:
                history.pop(vid,None)
        for vid,rec in list(pending.items()):
            if vid in active:
                rec['observed_a_next']=float(traci.vehicle.getAcceleration(vid))
                rec['observed_speed_next_kmh']=float(traci.vehicle.getSpeed(vid))*3.6
                rec['matched_t_plus_dt']=abs(rec['target_time_s']-t)<1.e-5
            else:
                rec['matched_t_plus_dt']=False
            pending.pop(vid,None)
        sample_speeds=np.array([float(traci.vehicle.getSpeed(vid)) for vid in ids],dtype=float)
        if not np.isfinite(sample_speeds).all():
            raise RuntimeError('SUMO reporta velocidades no finitas.')
        curr=sim_counts(sim,need_safety=(args.mode=='active'))
        if args.mode=='active' and ((curr['collisions'] or 0)>0 or (curr['teleport_start'] or 0)>0):
            collision_halt=True
        fleet.append(dict(step=step, time_s=t,dt_s=dt,n_active_vehicles=len(ids),
            n_halted_vehicles=int(np.sum(sample_speeds<0.1)),
            mean_speed_kmh=float(np.mean(sample_speeds)*3.6) if len(ids) else np.nan,
            **curr))
        if args.mode!='baseline':
            for vid in sorted(active):
                v=float(traci.vehicle.getSpeed(vid))
                a=float(traci.vehicle.getAcceleration(vid))
                if not np.isfinite(v) or not np.isfinite(a) or v<=args.moving_min_kmh/3.6:
                    history.pop(vid,None)
                    counts['not_moving']+=1
                    continue
                h=history.setdefault(vid,ShadowHistory())
                h.push(a)
                if not h.ready:
                    counts['history_insufficient']+=1
                    continue
                reason, ctx=strictly_safe_context(traci,vid,args)
                counts[reason]+=1
                if reason!='eligible':continue
                seed=deterministic_seed(args.seed,vid,step)
                proposer=CausalVineProposer(kernel,groups,args.variant,h.values[-2],h.values[-1],seed)
                proposed=float(proposer.propose())
                guard=guard_step(ctx['speed'],h.values[-1],proposed,dt,
                    amin=args.amin,amax=args.amax,jmax=args.jmax,vmax=ctx['speed_limit'])
                breakdown=classify_constraints(ctx['speed'],h.values[-1],proposed,dt,
                    ctx['speed_limit'],guard,amin=args.amin,amax=args.amax,jmax=args.jmax)
                target=float(guard['applied_a'])
                row=dict(mode=args.mode,variant=args.variant,seed=args.seed,
                    step=step,time_s=t,target_time_s=t+dt,vehicle_id=vid,
                    observed_a=a,speed_kmh=3.6*v,proposed_a=proposed,
                    guarded_a=target,guard_reason=guard['feasibility'],
                    guard_intervened=bool(guard['intervened']),
                    delta_from_current_a=float(target-a),
                    observed_a_next=np.nan,observed_speed_next_kmh=np.nan,
                    matched_t_plus_dt=False,command_issued=False,
                    action_decision='',**breakdown)
                if guard['feasibility']!='feasible' or guard['jerk_limit_breached']:
                    row['action_decision']='guard_infeasible'
                elif abs(target-a)>args.max_command_delta_a:
                    row['action_decision']='proposal_too_far_from_nominal'
                elif args.mode=='probe':
                    counts['action_viable']+=1
                    row['action_decision']='probe_only'
                    pending[vid]=row
                elif collision_halt:
                    row['action_decision']='safety_halt_collision_or_teleport'
                elif command_count>=args.max_commands:
                    row['action_decision']='total_command_quota'
                else:
                    counts['action_viable']+=1
                    # Unica instruccion capaz de alterar el trafico. El speedMode
                    # original se EXIGE 31 y NUNCA se cambia. SUMO conserva las
                    # protecciones de car-following/semáforo.
                    traci.vehicle.setAcceleration(vid,target,dt)
                    command_count+=1
                    row['command_issued']=True
                    row['action_decision']='command_issued'
                    pending[vid]=row
                rows.append(row)
        if sim.getMinExpectedNumber()==0:break
    viable_vehicles={r['vehicle_id'] for r in rows
        if r['action_decision'] in ('probe_only','command_issued')}
    meta=dict(mode=args.mode,variant=args.variant,seed=args.seed,fit_seed=FIT_SEED,
        n_steps=len(fleet),n_admitted=len(admitted),n_safety_eligible=int(counts['eligible']),
        n_action_viable=int(counts['action_viable']),n_action_viable_vehicles=len(viable_vehicles),
        n_commands=command_count,safety_halt=collision_halt,
        reasons=dict(counts),remaining_pending=len(pending))
    return pd.DataFrame(rows),pd.DataFrame(fleet),meta


def self_test():
    common=dict(mode='active',variant='vine_student',ack_active=ACTIVE_ACK,
        ack_time_scale=TIME_ACK,step_length=.5,sumo_steps=6,max_vehicles=2,
        max_commands=6,bins_per_sign=8,max_fit=2000,moving_min_kmh=5.,
        free_gap_m=60.,follower_gap_m=60.,distance_to_lane_end_m=60.,
        tls_distance_m=80.,max_speed_kmh=50.,max_command_delta_a=.8,
        amin=-4.,amax=2.5,jmax=5.,seed=101)
    args=argparse.Namespace(**common)
    validate_args(args)
    bad=argparse.Namespace(**{**common,'ack_active':''})
    try:validate_args(bad)
    except ValueError:pass
    else:raise AssertionError('Active sin confirmacion fue autorizado.')
    bad=argparse.Namespace(**{**common,'step_length':1.})
    try:validate_args(bad)
    except ValueError:pass
    else:raise AssertionError('Active con dt=1 fue autorizado.')
    class FakeVehicle:
        def __init__(self,parent):self.p=parent;self.commands=[]
        def getIDList(self):return ['car']
        def getSpeed(self,vid):return 8.
        def getAcceleration(self,vid):return .1
        def getSpeedMode(self,vid):return self.p.mode
        def getVehicleClass(self,vid):return 'passenger'
        def getLaneID(self,vid):return 'lane'
        def getLanePosition(self,vid):return 10.
        def getNextTLS(self,vid):return []
        def getLeader(self,vid,dist=100):return None
        def getFollower(self,vid,dist=100):return None
        def getAllowedSpeed(self,vid):return 13.
        def setAcceleration(self,vid,a,duration):self.commands.append((vid,a,duration))
        def setSpeed(self,*args):raise AssertionError('PROHIBIDO setSpeed')
        def setSpeedMode(self,*args):raise AssertionError('PROHIBIDO cambiar speedMode')
    class FakeLane:
        def getLength(self,lane):return 300.
    class FakeSimulation:
        def __init__(self,parent):self.p=parent
        def getTime(self):return .5*self.p.t
        def getDeltaT(self):return .5
        def getCollidingVehiclesNumber(self):return 0
        def getStartingTeleportNumber(self):return 0
        def getArrivedNumber(self):return 0
        def getDepartedNumber(self):return 1 if self.p.t==1 else 0
        def getMinExpectedNumber(self):return 1
    class FakeTraci:
        def __init__(self,mode=31):
            self.t=0;self.mode=mode
            self.vehicle=FakeVehicle(self);self.lane=FakeLane()
            self.simulation=FakeSimulation(self)
        def simulationStep(self):self.t+=1
    class FakeProposer:
        def __init__(self,*args):pass
        def propose(self):return .2
    old=globals()['CausalVineProposer']
    try:
        globals()['CausalVineProposer']=FakeProposer
        for mode,expected in [('baseline',0),('probe',0),('active',5)]:
            a=argparse.Namespace(**{**common,'mode':mode,
                        'variant':None if mode=='baseline' else 'vine_student'})
            f=FakeTraci()
            rows,fleet,meta=run_experiment(a,f)
            assert len(f.vehicle.commands)==expected==meta['n_commands']
            assert len(fleet)==6
            if mode=='active':
                assert rows.command_issued.sum()==5
                assert rows.matched_t_plus_dt.sum()==4
            elif mode=='probe':
                assert rows.matched_t_plus_dt.sum()==4
                assert not rows.command_issued.any()
            else:
                assert not len(rows) or not rows.command_issued.any()
        f=FakeTraci(mode=0)
        rows,fleet,meta=run_experiment(args,f)
        assert not f.vehicle.commands and meta['reasons']['speed_mode_no_default']>0
        # La deteccion de eventos de seguridad cancela comandos; no cambia el modo.
    finally:
        globals()['CausalVineProposer']=old
    print('SELF-TEST OK: baseline=0, probe=0, active controlado, autorizaciones, '
          'dt restringido, speedMode=31, observacion siguiente y no setSpeed.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--mode',choices=('baseline','probe','active'),default='probe')
    ap.add_argument('--variant',choices=VARIANTS)
    ap.add_argument('--ack-active',default='')
    ap.add_argument('--ack-time-scale',default='')
    ap.add_argument('--sumo-config',type=Path)
    ap.add_argument('--sumo-binary',type=str)
    ap.add_argument('--route-steps',type=float,default=None)
    ap.add_argument('--step-length',type=float,default=None)
    ap.add_argument('--data-dir',type=Path,default=DEFAULT_DATA)
    ap.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    ap.add_argument('--sumo-steps',type=int,default=600)
    ap.add_argument('--max-vehicles',type=int,default=5)
    ap.add_argument('--max-commands',type=int,default=30)
    ap.add_argument('--seed',type=int,default=101)
    ap.add_argument('--bins-per-sign',type=int,default=8)
    ap.add_argument('--max-fit',type=int,default=2000)
    ap.add_argument('--moving-min-kmh',type=float,default=5.)
    ap.add_argument('--max-speed-kmh',type=float,default=50.)
    ap.add_argument('--amin',type=float,default=-4.)
    ap.add_argument('--amax',type=float,default=2.5)
    ap.add_argument('--jmax',type=float,default=5.)
    ap.add_argument('--free-gap-m',type=float,default=60.)
    ap.add_argument('--follower-gap-m',type=float,default=60.)
    ap.add_argument('--distance-to-lane-end-m',type=float,default=60.)
    ap.add_argument('--tls-distance-m',type=float,default=80.)
    ap.add_argument('--max-command-delta-a',type=float,default=.8)
    args=ap.parse_args()
    if args.self_test:return self_test()
    validate_args(args)
    if args.sumo_config is None:ap.error('Falta --sumo-config.')
    cfg=args.sumo_config.resolve()
    if not cfg.is_file():raise FileNotFoundError(cfg)
    out=args.output.resolve()
    approved_root=(ROOT/'resultados').resolve()
    if out==approved_root or approved_root not in out.parents:
        raise RuntimeError('Por seguridad, --output debe ser una carpeta nueva DENTRO de revision_naturalista/resultados.')
    if out.exists():
        raise FileExistsError(f'La carpeta de salida ya existe; use una nueva: {out}')
    kernel=groups=tabs=n_pairs=manifest_data=None
    if args.mode in ('probe','active'):
        samples,manifest_data=read_artifacts(args.data_dir)
        kernel,groups,tabs,n_pairs=fit_fold(samples,FIT_SEED+100,args,
            copula_seed=FIT_SEED+100*71)
    try:import traci
    except ImportError:
        import os
        home=os.environ.get('SUMO_HOME')
        if home:sys.path.insert(0,str(Path(home)/'tools'))
        import traci
    binary=args.sumo_binary or shutil.which('sumo')
    if not binary:raise RuntimeError('SUMO no esta en PATH; indique --sumo-binary.')
    # Preparar salida ANTES de arrancar SUMO y redirigir cualquier fichero
    # solicitado por .sumocfg / ficheros adicionales. Proteger traffic_project.
    out.mkdir(parents=True,exist_ok=False)
    prefix=str(out/'sumo_')
    command=[str(binary),'-c',str(cfg),'--seed',str(args.seed),
             '--output-prefix',prefix]
    if args.route_steps is not None:
        if args.route_steps<0:raise ValueError('route-steps negativo.')
        command+=['--route-steps',str(args.route_steps)]
    if args.step_length is not None:
        command+=['--step-length',str(args.step_length)]
    print('COMANDO SUMO:', ' '.join(command),flush=True)
    print('MODALIDAD:',args.mode,'VARIANTE:',args.variant,'NÚCLEO FIT_SEED:',FIT_SEED,flush=True)
    if args.mode=='active':print('AVISO: INTERVENCION EXPERIMENTAL SUMO (no validacion naturalista).',flush=True)
    else:print('SUMO OBSERVACIONAL: NINGUN COMANDO DE CONTROL.',flush=True)
    traci.start(command)
    try:rows,fleet,meta=run_experiment(args,traci,kernel,groups)
    finally:traci.close()
    rows.to_csv(out/'acciones_hito06.csv',index=False,float_format='%.12g')
    fleet.to_csv(out/'trafico_hito06.csv',index=False,float_format='%.12g')
    produced=['acciones_hito06.csv','trafico_hito06.csv']
    if tabs is not None:
        tabs.to_csv(out/'familias_hito06_train.csv',index=False)
        produced.append('familias_hito06_train.csv')
    sim_files={f.name:sha256(f) for f in out.glob('sumo_*') if f.is_file()}
    manifest=dict(version=VERSION,source_sumo_config=str(cfg),sumo_command=command,
        sumo_output_prefix=prefix,sumo_generated_files_sha256=sim_files,
        sumo_binary=str(binary),source_sumo_sha256=sha256(cfg),
        sumo_scenario_input_sha256=sumo_input_hashes(cfg),
        frozen_hito03_sha256=sha256(Path(__file__).resolve().parent/'ntvc_vine_r_03_integracion_cinematica_sumo.py'),
        frozen_hito04_sha256=sha256(Path(__file__).resolve().parent/'ntvc_vine_r_04_shadow_multivehiculo_rutas_corregidas.py'),
        frozen_hito01_manifest_sha256=sha256(args.data_dir/'manifest.json') if args.mode!='baseline' else None,
        n_training_pairs=n_pairs,metadata=meta,output_sha256={p:sha256(out/p) for p in produced},
        params={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()
                if k not in ('ack_active','ack_time_scale')},
        caveats=['No modifica datos originales ni abre Richard',
            'No ejecuta setSpeed ni modifica speedMode=31',
            'La escala de tiempo POLIDriving-SUMO NO esta calibrada',
            'La seleccion de via libre limita validez externa',
            'Este prototipo no mide por si solo efecto causal ni seguridad real'])
    (out/'manifest_hito06.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RESUMEN HITO06:',json.dumps(meta,ensure_ascii=False),flush=True)
    print('SALIDA:',out,flush=True)
    if args.mode=='active' and meta['n_commands']==0:
        print('PUERTA ABIERTA TECNICAMENTE, PERO 0 INTERVENCIONES: NO HAY EVIDENCIA DE CONTROL.',flush=True)

if __name__=='__main__':main()
