#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NTVC-Vine-R Hito 04: auditoria SUMO Shadow multivehiculo (SOLO LECTURA).

Reutiliza SIN MODIFICAR las funciones de ajuste y muestreo del Hito 03.
Admite los primeros N vehiculos que aparezcan (orden cronologico, desempate ID),
sin seleccion segun velocidad o futuro. Predice a_(t+1) cuando existen dos
aceleraciones observadas y velocidad actual >5 km/h; compara a_(t+1)
SOLO cuando se observa en el siguiente paso.

Las muestras generadas NO son predicciones optimas de MAE. Comparaciones
MAE/W1 son diagnosticas y agrupadas por vehiculo; no validacion final.
No ejecuta setSpeed, setAcceleration ni comandos de control.

Ejemplo desde revision_naturalista:
python .\\scripts\\ntvc_vine_r_04_sumo_shadow_multivehiculo.py --self-test
python .\\scripts\\ntvc_vine_r_04_sumo_shadow_multivehiculo.py --sumo-config "..\\traffic_project\\baselines\\pytsc\\pytsc\\scenarios\\sumo\\2x2_sumo_grid\\2x2_sumo_grid.sumocfg" --data-dir .\\resultados\\ntvc_vine_r_01_cohortes_movimiento_regenerado
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance
from ntvc_vine_r_03_integracion_cinematica_sumo import (
    ROOT, DATA, VARIANTS, ShadowHistory, CausalVineProposer, guard_step,
    read_artifacts, fit_fold, sha256,
)

VERSION='NTVC-Vine-R Hito04 Shadow Multi v1 + route-steps explicit'
DEFAULT_OUT=ROOT/'resultados'/'ntvc_vine_r_04_sumo_shadow_multivehiculo'


def deterministic_seed(global_seed,vehicle_id,step):
    payload=f'{global_seed}|{vehicle_id}|{step}'.encode('utf-8')
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], 'big')


def classify_constraints(speed_m_s, previous_a, proposed_a, dt, v_max, guard, amin=-4., amax=2.5, jmax=5.):
    """Desglosa el motivo de una correccion sin inferirlo del flag agregado."""
    l=max(amin,-speed_m_s/dt)
    u=min(amax,(v_max-speed_m_s)/dt)
    feasible=l<=u+1e-12
    physical=float(np.clip(proposed_a,l,u)) if feasible else float(l)
    tol=1e-9
    return dict(
        proposal_below_amin=bool(proposed_a<amin-tol),
        proposal_above_amax=bool(proposed_a>amax+tol),
        proposal_speed_lower=bool(proposed_a<(-speed_m_s/dt)-tol),
        proposal_speed_upper=bool(proposed_a>((v_max-speed_m_s)/dt)+tol),
        jerk_adjustment=bool(abs(guard['applied_a']-physical)>tol),
        speed_limit_infeasible=not feasible,
        allowed_speed_below_current=bool(v_max<speed_m_s-tol),
        delta_guard_m_s2=float(guard['applied_a']-proposed_a),
        previous_a=float(previous_a),
    )


def lookup_next(pending_by_vehicle, vehicle_id, current_time, observed_a, observed_speed):
    """Asocia cada propuesta SOLO a la observacion real del paso siguiente."""
    old=pending_by_vehicle.pop(vehicle_id, [])
    n=0
    for row in old:
        if abs(row['target_time_s']-current_time)<1e-6:
            row['observed_a_next']=float(observed_a)
            row['observed_speed_next_kmh']=float(observed_speed*3.6)
            row['next_observation_available']=True
            n+=1
        else:
            row['unmatched_reason']='time_step_mismatch'
    return n


def simulate_shadow(args, kernel, groups, traci):
    histories={}
    admitted=set()
    pending={}
    rows=[]
    steps_done=0
    count_seen=0
    total_eligible_instants=0
    for step in range(args.sumo_steps):
        traci.simulationStep()
        steps_done+=1
        t=float(traci.simulation.getTime())
        dt=float(traci.simulation.getDeltaT())
        if not np.isfinite(dt) or dt<=0:
            raise RuntimeError('SUMO devolvio un DeltaT no valido.')
        ids=sorted(set(traci.vehicle.getIDList()))
        count_seen+=len(ids)
        # Sin filtrar por velocidad, duracion ni resultados futuros.
        for vid in ids:
            if len(admitted)>=args.max_vehicles:break
            admitted.add(vid)
        active=set(ids).intersection(admitted)
        # Los vehiculos ausentes no vuelven a usar historia previa.
        for vid in list(histories):
            if vid not in active:
                histories.pop(vid,None)
                # Pendientes sin proxima observacion permanecen censurados.
                pending.pop(vid,None)
        for vid in sorted(active):
            v=float(traci.vehicle.getSpeed(vid))
            a=float(traci.vehicle.getAcceleration(vid))
            if not np.isfinite(v) or not np.isfinite(a) or v<0:
                raise RuntimeError(f'Valores de velocidad/aceleracion no validos: {vid}')
            lookup_next(pending,vid,t,a,v)
            if v<=args.moving_min_kmh/3.6:
                histories.pop(vid,None)
                continue
            h=histories.setdefault(vid,ShadowHistory())
            h.push(a)
            if not h.ready:continue
            total_eligible_instants+=1
            try:
                vlim=float(traci.vehicle.getAllowedSpeed(vid))
                if not np.isfinite(vlim) or vlim<=0:raise ValueError('nonpositive allowedSpeed')
            except Exception:
                vlim=args.max_speed_kmh/3.6
            vmax=min(vlim,args.max_speed_kmh/3.6)
            try:leader=traci.vehicle.getLeader(vid)
            except Exception:leader=None
            leader_gap=float(leader[1]) if leader else np.nan
            seed=deterministic_seed(args.seed,vid,step)
            new_rows=[]
            for variant in VARIANTS:
                proposer=CausalVineProposer(kernel,groups,variant,h.values[-2],h.values[-1],seed)
                proposed=proposer.propose()
                guard=guard_step(v,h.values[-1],proposed,dt,
                    amax=args.amax,amin=args.amin,jmax=args.jmax,vmax=vmax)
                constraints=classify_constraints(v,h.values[-1],proposed,dt,vmax,guard,
                    amin=args.amin,amax=args.amax,jmax=args.jmax)
                rec=dict(
                    scenario=str(args.sumo_config),seed=args.seed,
                    vehicle_id=vid,variant=variant,step=step,time_s=t,
                    target_time_s=t+dt,dt_s=dt,speed_kmh=v*3.6,
                    allowed_speed_kmh=vmax*3.6,observed_a=a,
                    leader_gap_m=leader_gap,proposed_a=proposed,
                    applied_a=guard['applied_a'],intervened=guard['intervened'],
                    guard_feasibility=guard['feasibility'],
                    jerk_limit_breached=guard['jerk_limit_breached'],
                    observed_a_next=np.nan,observed_speed_next_kmh=np.nan,
                    next_observation_available=False,unmatched_reason='',
                    **constraints,
                )
                rows.append(rec);new_rows.append(rec)
            pending[vid]=new_rows
        if traci.simulation.getMinExpectedNumber()==0:
            break
    return pd.DataFrame(rows),dict(
        n_steps_executed=steps_done,n_unique_admitted=len(admitted),
        n_active_vehicle_step_observations=count_seen,
        n_eligible_vehicle_steps=total_eligible_instants,
        n_control_commands=0,
    )


def aggregate_metrics(rows):
    if rows.empty:return pd.DataFrame(),pd.DataFrame()
    matched=rows.loc[rows['next_observation_available']].copy()
    summary=[]
    for variant,g in rows.groupby('variant',sort=False):
        gm=matched[matched.variant==variant]
        if len(gm):
            y=gm.observed_a_next.to_numpy(float)
            p=gm.proposed_a.to_numpy(float)
            ap=gm.applied_a.to_numpy(float)
            persistence=gm.observed_a.to_numpy(float)
            mae_p=float(np.mean(np.abs(p-y)))
            mae_a=float(np.mean(np.abs(ap-y)))
            mae_persist=float(np.mean(np.abs(persistence-y)))
            w1=float(wasserstein_distance(p,y))
            w1_a=float(wasserstein_distance(ap,y))
        else:mae_p=mae_a=mae_persist=w1=w1_a=np.nan
        summary.append(dict(variant=variant,n_proposals=len(g),n_matched=len(gm),
            n_vehicles=g.vehicle_id.nunique(),n_vehicles_matched=gm.vehicle_id.nunique(),
            matched_fraction=len(gm)/len(g),
            fraction_intervened=float(g.intervened.mean()),
            fraction_speed_upper=float(g.proposal_speed_upper.mean()),
            fraction_speed_lower=float(g.proposal_speed_lower.mean()),
            fraction_jerk_adjustment=float(g.jerk_adjustment.mean()),
            fraction_speed_infeasible=float(g.speed_limit_infeasible.mean()),
            fraction_accel_limits=float((g.proposal_below_amin|g.proposal_above_amax).mean()),
            mae_sample=mae_p,mae_guard=mae_a,mae_persistence=mae_persist,
            w1_sample=w1,w1_guard=w1_a))
    pervehicle=[]
    for (vid,variant),g in matched.groupby(['vehicle_id','variant'],sort=True):
        y=g.observed_a_next.to_numpy(float)
        pervehicle.append(dict(vehicle_id=vid,variant=variant,n_matched=len(g),
            mae_sample=float(np.mean(np.abs(g.proposed_a.to_numpy(float)-y))),
            mae_guard=float(np.mean(np.abs(g.applied_a.to_numpy(float)-y))),
            mae_persistence=float(np.mean(np.abs(g.observed_a.to_numpy(float)-y))),
            fraction_intervened=float(g.intervened.mean()),
            mean_speed_kmh=float(g.speed_kmh.mean()),
            dt_s=float(g.dt_s.median())))
    return pd.DataFrame(summary),pd.DataFrame(pervehicle)


def self_test():
    # Verificacion del desglose de seguridad, paso de tiempo y asociacion futura.
    from ntvc_vine_r_03_integracion_cinematica_sumo import guard_step as original_guard
    g=original_guard(v=12.5,a_previous=0.1,a_proposed=1.3,dt=1.,vmax=13.,amin=-4.,amax=2.5,jmax=5.)
    d=classify_constraints(12.5,0.1,1.3,1.,13.,g)
    assert g['intervened'] and d['proposal_speed_upper'] and not d['proposal_above_amax']
    g2=original_guard(v=8.,a_previous=0.,a_proposed=2.,dt=.1,vmax=13.,amin=-4.,amax=2.5,jmax=1.)
    d2=classify_constraints(8.,0.,2.,.1,13.,g2,jmax=1.)
    assert g2['intervened'] and d2['jerk_adjustment'] and not d2['proposal_speed_upper']
    pending={'veh':[{'target_time_s':3.,'observed_a_next':np.nan,
                     'next_observation_available':False}]}
    assert lookup_next(pending,'veh',3.,-0.4,7.)==1
    assert pending=={}
    assert deterministic_seed(2026,'0',1)==deterministic_seed(2026,'0',1)
    assert deterministic_seed(2026,'0',1)!=deterministic_seed(2026,'1',1)
    # Tabla de pares: una fila por variante y prediccion, matches independientes.
    small=[]
    for i in range(3):
        for variant in VARIANTS:
            small.append(dict(vehicle_id=str(i),variant=variant,
                  next_observation_available=True,observed_a_next=0.,
                  proposed_a=0.2,applied_a=0.1,observed_a=0.,intervened=True,
                  proposal_speed_upper=True,proposal_speed_lower=False,
                  jerk_adjustment=False,speed_limit_infeasible=False,
                  proposal_below_amin=False,proposal_above_amax=False,
                  speed_kmh=30.,dt_s=1.))
    su,pv=aggregate_metrics(pd.DataFrame(small))
    assert len(su)==3 and len(pv)==9 and (su.n_matched==3).all()
    # TraCI simulado: verificar que se usa a_(t+1), se registran censuras y
    # no se ejecuta ni siquiera accidentalmente un comando de control.
    class FakeVehicle:
        def __init__(self,parent):self.parent=parent
        def getIDList(self):return ['vehA'] if self.parent.t in (1,2,3) else []
        def getSpeed(self,vid):return 10.
        def getAcceleration(self,vid):return .1*self.parent.t
        def getAllowedSpeed(self,vid):return 13.
        def getLeader(self,vid):return None
        def setSpeed(self,*_):raise AssertionError('PROHIBIDO setSpeed')
        def setAcceleration(self,*_):raise AssertionError('PROHIBIDO setAcceleration')
    class FakeSimulation:
        def __init__(self,parent):self.parent=parent
        def getTime(self):return float(self.parent.t)
        def getDeltaT(self):return 1.
        def getMinExpectedNumber(self):return 1
    class FakeTraci:
        def __init__(self):
            self.t=0;self.vehicle=FakeVehicle(self);self.simulation=FakeSimulation(self)
        def simulationStep(self):self.t+=1
    class FakeProposer:
        def __init__(self,*_):pass
        def propose(self):return .2
    old_class=globals()['CausalVineProposer']
    try:
        globals()['CausalVineProposer']=FakeProposer
        aa=argparse.Namespace(sumo_steps=4,max_vehicles=1,
            moving_min_kmh=5.,seed=2026,max_speed_kmh=50.,
            amin=-4.,amax=2.5,jmax=5.,sumo_config='synthetic.sumocfg')
        frame,meta=simulate_shadow(aa,None,None,FakeTraci())
        assert len(frame)==6 and frame.next_observation_available.sum()==3
        assert meta['n_control_commands']==0 and meta['n_unique_admitted']==1
        assert np.allclose(frame[frame.next_observation_available].observed_a_next.to_numpy(float), .3)
    finally:
        globals()['CausalVineProposer']=old_class
    print('SELF-TEST OK: restricciones, matching t+1, semillas, agregacion, TraCI simulado y cero control.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--data-dir',type=Path,default=DATA)
    ap.add_argument('--sumo-config',type=Path)
    ap.add_argument('--sumo-binary',type=str)
    ap.add_argument('--route-steps',type=float,default=None,
                    help='Valor de --route-steps de SUMO. Para Hangzhou usar 0; no modifica archivos originales.')
    ap.add_argument('--output',type=Path,default=DEFAULT_OUT)
    ap.add_argument('--max-vehicles',type=int,default=40)
    ap.add_argument('--sumo-steps',type=int,default=1000)
    ap.add_argument('--seed',type=int,default=2026)
    ap.add_argument('--bins-per-sign',type=int,default=8)
    ap.add_argument('--max-fit',type=int,default=2000)
    ap.add_argument('--moving-min-kmh',type=float,default=5.)
    ap.add_argument('--max-speed-kmh',type=float,default=50.)
    ap.add_argument('--amin',type=float,default=-4.)
    ap.add_argument('--amax',type=float,default=2.5)
    ap.add_argument('--jmax',type=float,default=5.)
    args=ap.parse_args()
    if args.self_test:return self_test()
    if args.sumo_config is None:ap.error('Debe suministrar --sumo-config con una ruta real.')
    if args.max_vehicles<1 or args.sumo_steps<1:ap.error('max-vehicles y sumo-steps deben ser positivos.')
    if args.route_steps is not None and (not math.isfinite(args.route_steps) or args.route_steps<0):
        ap.error('--route-steps debe ser un numero no negativo.')
    if (args.bins_per_sign,args.max_fit,args.moving_min_kmh)!=(8,2000,5.):
        ap.error('Nucleo Hito02 congelado: bins=8 max_fit=2000 moving_min=5.')
    cfg=args.sumo_config.resolve()
    if not cfg.is_file():raise FileNotFoundError(cfg)
    args.sumo_config=cfg
    samples,data_manifest=read_artifacts(args.data_dir)
    kernel,groups,tabs,n_pairs=fit_fold(samples,args.seed+100,args,copula_seed=args.seed+100*71)
    try:
        import traci
    except ImportError:
        import os
        home=os.environ.get('SUMO_HOME')
        if home:sys.path.append(str(Path(home)/'tools'))
        import traci
    binary=args.sumo_binary or shutil.which('sumo')
    if not binary:raise RuntimeError('SUMO no esta en PATH; indique --sumo-binary.')
    cmd=[str(binary),'-c',str(cfg),'--seed',str(args.seed)]
    if args.route_steps is not None:
        cmd+=['--route-steps',str(args.route_steps)]
    print('COMANDO SUMO:', ' '.join(cmd),flush=True)
    print('SUMO SOLO LECTURA:',str(cfg),flush=True)
    traci.start(cmd)
    try:rows,metadata=simulate_shadow(args,kernel,groups,traci)
    finally:traci.close()
    if rows.empty:
        raise RuntimeError('No hubo propuestas; revise duracion, flota o umbral de velocidad.')
    summary,pervehicle=aggregate_metrics(rows)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    files={
        'sumo_shadow_multi_trazas.csv':rows,
        'sumo_shadow_multi_resumen.csv':summary,
        'sumo_shadow_multi_por_vehiculo.csv':pervehicle,
        'sumo_shadow_multi_familias_train.csv':tabs,
    }
    for name,df in files.items():df.to_csv(output/name,index=False,float_format='%.12g')
    info=dict(version=VERSION,source_hito03='Funciones importadas del Hito03 sin modificaciones',
        data_manifest_sha256=sha256(args.data_dir/'manifest.json'),
        original_sumo_config=str(cfg),sumo_binary=str(binary),
        sumo_route_steps=args.route_steps, sumo_command=cmd,
        restricted_holdouts='Sin acceso Richard o Alonso 20231229_151643',
        n_training_pairs=n_pairs,**metadata,
        design={'selection':'Primeros N ID que aparecen, sin mirar velocidades ni futuro',
                'prediction':'Muestra aleatoria condicional un paso adelante',
                'training':'Todas las sesiones de desarrollo autorizadas; TRAIN-only',
                'independence':'No asumir pasos consecutivos independientes',
                'timesteps':'DeltaT de SUMO (no calibrado contra dt POLIDriving)',
                'control':'NINGUNO'},
        params={'seed':args.seed,'max_vehicles':args.max_vehicles,
                'sumo_steps':args.sumo_steps,'route_steps':args.route_steps,'amin':args.amin,
                'amax':args.amax,'jmax':args.jmax,
                'max_speed_kmh':args.max_speed_kmh},
        sha256={name:sha256(output/name) for name in files},
    )
    (output/'manifest_hito04.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\nRESUMEN HITO04 MULTIVEHICULO:')
    print(summary.to_string(index=False,float_format=lambda n:f'{n:.5f}'))
    print('\nPASOS SUMO:',metadata['n_steps_executed'],
          'VEHICULOS ADMITIDOS:',metadata['n_unique_admitted'],
          'COMANDOS CONTROL:',metadata['n_control_commands'])
    print('ARCHIVOS:',output)
    print('AVISO: pruebas exploratorias Shadow. Ningun vehiculo controlado; dt SUMO no recalibrado.')


if __name__=='__main__':main()
