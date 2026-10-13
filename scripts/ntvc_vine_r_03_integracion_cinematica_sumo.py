#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NTVC-Vine-R Hito 03: integracion cinematica y SUMO SHADOW (solo lectura).

Objetivos fijados previamente:
1) Misma Vine Gaussian/Student y kernel P2 de Hito 02, sin ajustes en TEST.
2) Arranques CAUSALES (solo velocidades presentes y pasadas; no velocidad futura).
3) Integracion de velocidad, aceleracion realmente aplicada y jerk; auditoria de
   restricciones; cese del submodelo al salir de v>5 km/h.
4) SUMO SHADOW opcional: observa TraCI y calcula propuestas; NUNCA aplica comandos
   de aceleracion, velocidad, speedMode o ruta a vehiculos.

NO es validacion completa del seguimiento vehicular. No hay lider/semáforo en el
modo offline. El dt de las ventanas procede del TEST y es EXOGENO, no predicho.
Todos los folds son exploratorios; Richard y sesion 20231229_151643 reservados.

Desde C:\\Proyecto_Tesis_Final_V1\\revision_naturalista:
  python .\\scripts\\ntvc_vine_r_03_integracion_cinematica_sumo.py --self-test
  python .\\scripts\\ntvc_vine_r_03_integracion_cinematica_sumo.py --mode offline --data-dir .\\resultados\\ntvc_vine_r_01_cohortes_movimiento_regenerado
  python .\\scripts\\ntvc_vine_r_03_integracion_cinematica_sumo.py --mode sumo-shadow --sumo-config RUTA.sumocfg --vehicle-id ID
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import numpy as np
import pandas as pd
from scipy.special import ndtr, ndtri
from scipy.stats import wasserstein_distance

from ntvc_vine_r_02_contraste_vine_en_marcha_corregido import (
    ROOT, DATA, read_artifacts, make_moving_pairs, get_fits, filehash,
)
from ntvc_v06_p2_estados_cuantiles import fit_kernel, verify_pairwise_jerk
from ntvc_v06_p93_puente_copula_estacionaria import (
    make_triples, backward_rank, sample_forwards, sample_discrete,
)

OUT = ROOT / 'resultados' / 'ntvc_vine_r_03_integracion_cinematica_sumo'
VARIANTS = ('moving_p2', 'vine_gaussian', 'vine_student')
EPS=1.e-10


def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
    return h.hexdigest().upper()


class CausalVineProposer:
    """Generador con estado de dos tiempos; su adaptacion a cambios fisicos es EXPLICITA.

    Inicializacion con dos aceleraciones YA observadas. Los uniformes de paso
    estan emparejados entre variantes (una extraccion por paso). Correcciones de
    seguridad se realimentan en el estado interno por inversion de la marginal.
    """
    def __init__(self,kernel,groups,variant,a_minus1,a_current,seed):
        if variant not in VARIANTS:raise ValueError('Variante desconocida')
        self.kernel=kernel;self.groups=groups;self.variant=variant
        self.rng=np.random.default_rng(int(seed))
        self.bp,self.zp=self.encode(a_minus1)
        self.bc,self.zc=self.encode(a_current)
        self.current_a=float(a_current)
        self.steps=0;self.feedback_resets=0

    def encode(self,a):
        m=self.kernel.marginal
        b=int(m.bin_of([a])[0])
        u=float(m.random_pit(np.array([b]),np.array([a],float),self.rng)[0])
        return b,float(ndtri(np.clip(u,EPS,1-EPS)))

    def propose(self):
        u=float(self.rng.random())
        if self.variant=='moving_p2':
            bn,within=sample_discrete(self.kernel.p[self.bc],u)
            r=float(self.kernel.rho_pairs[self.bc,bn])
            zn=float(r*self.zc+math.sqrt(max(EPS,1-r*r))*ndtri(within))
        else:
            group=('zero' if self.bc==self.kernel.marginal.zero_bin else
                   ('negative' if self.bc<self.kernel.marginal.zero_bin else 'positive'))
            fam='gaussian' if self.variant=='vine_gaussian' else 'student'
            pair=self.groups[group][fam]
            uback=backward_rank(self.kernel,self.bp,self.zp,self.bc,self.zc)
            uq=float(pair.hinv(uback,u))
            bn,zn=sample_forwards(self.kernel,self.bc,self.zc,uq)
        proposed=self.kernel.marginal.inverse_one(bn,float(ndtr(zn)))
        self._pending=(int(bn),float(zn),float(proposed))
        return float(proposed)

    def commit(self,applied):
        if not hasattr(self,'_pending'):raise RuntimeError('Primero propose()')
        bn,zn,proposed=self._pending
        self.bp,self.zp=self.bc,self.zc
        if math.isclose(float(applied),proposed,abs_tol=1.e-11,rel_tol=0.):
            self.bc,self.zc=bn,zn
        else:
            self.bc,self.zc=self.encode(applied)
            self.feedback_resets+=1
        self.current_a=float(applied)
        self.steps+=1
        del self._pending

    def observe_external(self,a):
        """Actualizacion con observacion TraCI, NO con prediccion hipotetica."""
        self.bp,self.zp=self.bc,self.zc
        self.bc,self.zc=self.encode(float(a))
        self.current_a=float(a)


class ShadowHistory:
    """Acumula maximo dos aceleraciones fisicas realmente observadas."""
    def __init__(self):self.values=[]
    def reset(self):self.values=[]
    def push(self,a):
        if np.isfinite(a):self.values=(self.values+[float(a)])[-2:]
    @property
    def ready(self):return len(self.values)==2


def guard_step(v,a_previous,a_proposed,dt,amax=2.5,amin=-4.,jmax=5.,vmax=50/3.6):
    """Envolvente local cinematica. No representa seguridad ante lider/semaforo.

    PRIORIDAD: (1) rango a y v fisicos; (2) limite jerk si compatible con (1).
    Si son incompatibles, registra brecha de jerk en lugar de ocultarla.
    """
    if not all(np.isfinite(x) for x in (v,a_previous,a_proposed,dt,amin,amax,jmax,vmax)):
        raise ValueError('Entrada no finita')
    if dt<=0 or jmax<=0 or amin>=amax or vmax<=0 or v<0:
        raise ValueError('Restricciones invalidas')
    lower=max(amin,-v/dt)
    upper=min(amax,(vmax-v)/dt)
    # v>vmax al inicializar: frenar, nunca acelerar; registrar caso especial.
    if lower>upper+1e-12:
        applied=lower
        feasibility='speed_limit_infeasible'
    else:
        physical=float(np.clip(a_proposed,lower,upper))
        lo_j=a_previous-jmax*dt;hi_j=a_previous+jmax*dt
        lo=max(lower,lo_j);hi=min(upper,hi_j)
        if lo<=hi:
            applied=float(np.clip(physical,lo,hi));feasibility='feasible'
        else:
            applied=physical;feasibility='jerk_infeasible'
    vnext=max(0.,float(v+applied*dt))
    jerk=(applied-a_previous)/dt
    return dict(applied_a=float(applied),v_next_m_s=float(vnext),jerk_m_s3=float(jerk),
                intervened=bool(abs(applied-a_proposed)>1e-10),
                accel_or_speed_clamp=bool(a_proposed<lower-1e-10 or a_proposed>upper+1e-10),
                jerk_limit_breached=bool(abs(jerk)>jmax+1e-10),
                feasibility=feasibility)


def select_causal_windows(samples,window=40,max_windows=30):
    """Elegibilidad: exclusivamente pasado y velocidad en instante de arranque.

    Los dt FUTUROS proceden del TEST para sincronizar la simulacion exogena.
    NUNCA seleccionamos por velocidad futura ni observamos a futura antes de
    decidir entrada en la ventana. Se requiere segmento suficiente para comparar.
    """
    entries=[]
    data=samples.sort_values(['driver_id','session_id','segment_id','raw_row'],kind='stable')
    for (drv,ses,seg),g in data.groupby(['driver_id','session_id','segment_id'],sort=False):
        g=g.reset_index(drop=True)
        if len(g)<window+2:continue
        aa=g.a_t_m_s2.to_numpy(float)
        pp=g.a_t_minus_1_m_s2.to_numpy(float)
        if not np.allclose(aa[:-1],pp[1:],rtol=0,atol=1.e-7):
            raise RuntimeError(f'Segmento de aceleracion roto {ses}/{seg}')
        v=g.speed_kmh.to_numpy(float)
        for k in range(1,len(g)-window,window):
            # SÓLO velocidad k y k-1, no la velocidad de los 40 pasos futuros.
            if min(v[k-1],v[k])<=5.:continue
            dd=g.dt_t_s.iloc[k+1:k+1+window].to_numpy(float)
            if len(dd)!=window or not np.isfinite(dd).all() or (dd<=0).any():continue
            entries.append(dict(driver_id=drv,session_id=ses,segment_id=str(seg),
               start_row=int(g.raw_row.iloc[k]),a_previous=float(aa[k-1]),
               a_current=float(aa[k]),v_initial=float(v[k]/3.6),
               dt=dd,obs_a=aa[k+1:k+1+window].copy(),
               obs_v=v[k+1:k+1+window].copy()/3.6))
    # Submuestreo estratificado por conductor determinista, sin mirar el futuro.
    by_driver={}
    for e in entries:by_driver.setdefault(e['driver_id'],[]).append(e)
    out=[]
    for drv,es in by_driver.items():
        idx=np.linspace(0,len(es)-1,min(max_windows,len(es)),dtype=int)
        out.extend(es[i] for i in idx)
    return out


def simulate_window(kernel,groups,variant,entry,seed,args):
    proposer=CausalVineProposer(kernel,groups,variant,
                               entry['a_previous'],entry['a_current'],seed)
    a_prev=float(entry['a_current']);v=float(entry['v_initial'])
    series=[];exit_reason='window_complete'
    if v>args.max_speed_kmh/3.6:
        return series,'initial_above_configured_speed_limit',0
    for step,dt in enumerate(entry['dt']):
        if v<=args.moving_min_kmh/3.6:
            exit_reason='left_moving_domain';break
        proposed=proposer.propose()
        guard=guard_step(v,a_prev,proposed,float(dt),
                         amax=args.amax,amin=args.amin,jmax=args.jmax,
                         vmax=args.max_speed_kmh/3.6)
        applied=guard['applied_a']
        proposer.commit(applied)
        assert abs(guard['jerk_m_s3']-(applied-a_prev)/dt)<1e-10
        series.append(dict(step=step,dt_s=float(dt),speed_before_kmh=3.6*v,
                           proposed_a=proposed,**guard,
                           observed_a=float(entry['obs_a'][step]),
                           observed_speed_kmh=float(3.6*entry['obs_v'][step])))
        a_prev=applied;v=guard['v_next_m_s']
        if v<=args.moving_min_kmh/3.6:
            exit_reason='left_moving_domain';break
    return series,exit_reason,proposer.feedback_resets


def fit_fold(train,fold_seed,args,copula_seed=None):
    """Mismo protocolo H02 sin optimizacion LODO; reestimacion necesaria
    porque H02 no exportó parametros serializados."""
    tr,run=make_moving_pairs(train)
    kernel=fit_kernel(tr,args.bins_per_sign,seed=fold_seed,
                      min_pair=60,shrinkage=200)
    groups,tabs,nz=get_fits(tr,kernel,make_triples(tr),
                                 fold_seed*71 if copula_seed is None else copula_seed,
                                 args.max_fit)
    if kernel.stationary_check()>1e-9:raise RuntimeError('Kernel no estacionario')
    return kernel,groups,tabs,len(tr)


def run_offline(samples,args):
    all_steps=[];summary=[];fit_rows=[];folds=[]
    for fold,driver in enumerate(sorted(samples.driver_id.unique()),1):
        tr=samples[samples.driver_id.ne(driver)].copy().reset_index(drop=True)
        te=samples[samples.driver_id.eq(driver)].copy().reset_index(drop=True)
        k,groups,tabs,n_pairs=fit_fold(tr,args.seed+fold,args,
                                       copula_seed=args.seed+fold*71)
        tabs.insert(0,'driver_left_out',driver);fit_rows.append(tabs)
        entries=select_causal_windows(te,args.window,args.max_windows)
        folds.append(dict(driver_left_out=driver,n_starts=len(entries),n_training_pairs=n_pairs,
                          n_test_samples=len(te),stationary_check=k.stationary_check()))
        print(f'FOLD {fold}/4 {driver}: starts_causales={len(entries)} '
              f'train_pairs={n_pairs} '
              f'Student(-/0/+)='+','.join(groups[g]['student'].family for g in ('negative','zero','positive')),
              flush=True)
        for wi,entry in enumerate(entries):
            for si in range(args.seeds):
                common_seed=args.seed+fold*100003+wi*701+si*31
                runs={}
                for variant in VARIANTS:
                    seq,reason,resets=simulate_window(k,groups,variant,entry,common_seed,args)
                    runs[variant]=(seq,reason,resets)
                # Igual soporte temporal para las tres variantes.
                common=min(len(runs[v][0]) for v in VARIANTS)
                for variant,(seq,reason,resets) in runs.items():
                    for rec in seq:
                        all_steps.append(dict(driver_left_out=driver,session_id=entry['session_id'],
                                              segment_id=entry['segment_id'],start_row=entry['start_row'],
                                              window_id=wi,seed=si,variant=variant,
                                              common_prefix=rec['step']<common,**rec))
                    cseq=seq[:common]
                    a=np.array([p['applied_a'] for p in cseq],float)
                    j=np.array([p['jerk_m_s3'] for p in cseq],float)
                    dt=np.array([p['dt_s'] for p in cseq],float)
                    if len(a):verify_pairwise_jerk(a,j,entry['a_current'],dt)
                    obsa=entry['obs_a'][:common]
                    obsj=(obsa-np.r_[entry['a_current'],obsa[:-1]])/dt if common else np.empty(0)
                    summary.append(dict(driver_left_out=driver,session_id=entry['session_id'],
                      segment_id=entry['segment_id'],start_row=entry['start_row'],window_id=wi,
                      seed=si,variant=variant,n_steps=len(seq),common_prefix_steps=common,
                      exit_reason=reason,feedback_resets=resets,
                      fraction_intervened=np.mean([r['intervened'] for r in seq]) if seq else np.nan,
                      fraction_jerk_infeasible=np.mean([r['jerk_limit_breached'] for r in seq]) if seq else np.nan,
                      fraction_speed_or_accel_cap=np.mean([r['accel_or_speed_clamp'] for r in seq]) if seq else np.nan,
                      w_accel_common=float(wasserstein_distance(a,obsa)) if common>=2 else np.nan,
                      w_jerk_common=float(wasserstein_distance(j,obsj)) if common>=2 else np.nan,
                      speed_initial_kmh=entry['v_initial']*3.6))
    return pd.DataFrame(all_steps),pd.DataFrame(summary),pd.concat(fit_rows,ignore_index=True),pd.DataFrame(folds)


def sumo_shadow(samples,args):
    """No usa vehiculo observado para entrenar. No emite setAcceleration ni setSpeed."""
    if not args.sumo_config or not args.vehicle_id:
        raise ValueError('sumo-shadow exige --sumo-config y --vehicle-id')
    config=Path(args.sumo_config).resolve()
    if not config.is_file():raise FileNotFoundError(config)
    # Un solo ajuste TRAIN de desarrollo: la version SUMO no evalua a Richard.
    kernel,groups,tabs,n_pairs=fit_fold(samples,args.seed+100,args,
                                        copula_seed=args.seed+100*71)
    try:
        import traci
    except ImportError:
        home=os.environ.get('SUMO_HOME')
        if home:sys.path.append(str(Path(home)/'tools'))
        try:import traci
        except ImportError as e:
            raise RuntimeError('No encuentro traci. Instalar SUMO y definir SUMO_HOME o instalar paquete traci.') from e
    import shutil
    binary=args.sumo_binary or shutil.which('sumo')
    if not binary:raise RuntimeError('No se encontro ejecutable sumo; pasa --sumo-binary RUTA')
    call=[str(binary),'-c',str(config),'--seed',str(args.seed)]
    rows=[];h=ShadowHistory();active=False
    traci.start(call)
    try:
        for step in range(args.sumo_steps):
            traci.simulationStep()
            ids=set(traci.vehicle.getIDList())
            if args.vehicle_id not in ids:
                h.reset();active=False
                rows.append(dict(step=step,vehicle_id=args.vehicle_id,status='not_present'))
                if traci.simulation.getMinExpectedNumber()==0:break
                continue
            v=float(traci.vehicle.getSpeed(args.vehicle_id))
            a=float(traci.vehicle.getAcceleration(args.vehicle_id))
            dt=float(traci.simulation.getDeltaT())
            try:vlim=float(traci.vehicle.getAllowedSpeed(args.vehicle_id))
            except Exception:vlim=args.max_speed_kmh/3.6
            try:leader=traci.vehicle.getLeader(args.vehicle_id)
            except Exception:leader=None
            gap=float(leader[1]) if leader else np.nan
            t=float(traci.simulation.getTime())
            if not np.isfinite(v) or not np.isfinite(a) or dt<=0:
                raise RuntimeError('Valores TraCI no validos')
            # Tras leer (v_t, a_t), formulamos una propuesta para a_(t+1).
            # Nunca puntuamos a_t con la velocidad del propio instante t.
            if v<=args.moving_min_kmh/3.6:
                h.reset();active=False
                rows.append(dict(step=step,time_s=t,vehicle_id=args.vehicle_id,
                                 status='fallback_sumo',speed_kmh=v*3.6,
                                 observed_a=a,leader_gap_m=gap))
                continue
            h.push(a)
            if h.ready:
                for variant in VARIANTS:
                    proposer=CausalVineProposer(kernel,groups,variant,h.values[-2],h.values[-1],
                                               args.seed+step*31)
                    proposed=proposer.propose()
                    guard=guard_step(v,h.values[-1],proposed,dt,
                        amax=args.amax,amin=args.amin,jmax=args.jmax,
                        vmax=min(vlim,args.max_speed_kmh/3.6))
                    rows.append(dict(step=step,time_s=t,vehicle_id=args.vehicle_id,
                        status='SHADOW_NO_CONTROL',variant=variant,
                        speed_kmh=v*3.6,observed_a=a,leader_gap_m=gap,
                        proposed_a_next_step=proposed,target_time_s=t+dt,**guard))
                active=True
            else:
                rows.append(dict(step=step,time_s=t,vehicle_id=args.vehicle_id,
                    status='warming_history',speed_kmh=v*3.6,observed_a=a,
                    leader_gap_m=gap))
    finally:
        traci.close()
    return pd.DataFrame(rows),tabs,dict(n_training_pairs=n_pairs,
        sumo_config_path=str(config),vehicle_id=args.vehicle_id,
        control_commands_sent=0,mode='SUMO shadow; no modifica vehiculos')


def self_test():
    import ntvc_vine_r_02_contraste_vine_en_marcha_corregido as h02
    h02.self_test()
    # Un modelo con piezas reales; no necesita archivos del usuario.
    rng=np.random.default_rng(32);records=[]
    for drv in ('alonso','andres','pablo','yolanda'):
        a=np.where(rng.random(650)<.18,0.,rng.normal(0,.65,650))
        for i in range(1,len(a)):
            records.append(dict(driver_id=drv,session_id='synthetic_'+drv,segment_id='s',
              raw_row=7*i,a_t_m_s2=a[i],a_t_minus_1_m_s2=a[i-1],
              dt_t_s=.3,j_t_observed_m_s3=(a[i]-a[i-1])/.3,
              speed_kmh=30.,speed_class='marcha_gt5'))
    samples=pd.DataFrame(records)
    k,groups,tab,n=fit_fold(samples,28,argparse.Namespace(seed=11,bins_per_sign=2,max_fit=200))
    aa=sample=samples[samples.driver_id=='alonso'].copy()
    windows=select_causal_windows(aa,window=20,max_windows=5)
    assert windows
    args=argparse.Namespace(moving_min_kmh=5.,amax=2.5,amin=-4.,jmax=5.,max_speed_kmh=50.)
    for ent in windows[:2]:
        for v in VARIANTS:
            s,reason,reset=simulate_window(k,groups,v,ent,39,args)
            assert len(s)>0
            assert all(x['v_next_m_s']>=0 and np.isfinite(x['jerk_m_s3']) for x in s)
            ap=np.array([x['applied_a'] for x in s]);jj=np.array([x['jerk_m_s3'] for x in s]);dts=np.array([x['dt_s'] for x in s])
            verify_pairwise_jerk(ap,jj,ent['a_current'],dts)
            assert sum(int(x['intervened']) for x in s)==reset
    hard=guard_step(.1,3.,-10.,.2,amax=2.5,amin=-4.,jmax=.1,vmax=13.)
    assert hard['intervened'] and hard['jerk_limit_breached'] and hard['v_next_m_s']>=0
    # Regresion real de causalidad: modificar velocidades FUTURAS a un
    # inicio elegido no puede hacerlo inadmisible retrospectivamente.
    al=samples[samples.driver_id=='alonso'].copy().reset_index(drop=True)
    initial=select_causal_windows(al,20,1000)[0]
    key=initial['start_row']
    k0=int(np.flatnonzero(al.raw_row.to_numpy()==key)[0])
    altered=al.copy()
    altered.loc[k0+1:k0+20,'speed_kmh']=0.
    altered_windows=select_causal_windows(altered,20,1000)
    assert any(x['start_row']==key for x in altered_windows)
    print('SELF-TEST OK: fit H02 congelado, propuesta Vine causal, seguridad, feedback, jerk, salida marcha')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--mode',choices=['offline','sumo-shadow'],default='offline')
    ap.add_argument('--data-dir',type=Path,default=DATA)
    ap.add_argument('--output',type=Path,default=OUT)
    ap.add_argument('--window',type=int,default=40)
    ap.add_argument('--max-windows',type=int,default=30)
    ap.add_argument('--seeds',type=int,default=2)
    ap.add_argument('--seed',type=int,default=2026)
    ap.add_argument('--bins-per-sign',type=int,default=8)
    ap.add_argument('--max-fit',type=int,default=2000)
    ap.add_argument('--moving-min-kmh',type=float,default=5.)
    ap.add_argument('--max-speed-kmh',type=float,default=50.)
    ap.add_argument('--amin',type=float,default=-4.)
    ap.add_argument('--amax',type=float,default=2.5)
    ap.add_argument('--jmax',type=float,default=5.)
    ap.add_argument('--sumo-config',type=Path)
    ap.add_argument('--sumo-binary',type=str)
    ap.add_argument('--vehicle-id',type=str)
    ap.add_argument('--sumo-steps',type=int,default=1000)
    args=ap.parse_args()
    if args.self_test:return self_test()
    if args.window<10 or args.max_windows<1 or args.seeds<1 or args.max_fit<100 or args.sumo_steps<1:
        ap.error('Parametros de protocolo fuera de rango')
    if args.moving_min_kmh!=5 or args.bins_per_sign!=8 or args.max_fit!=2000:
        ap.error('Hito03 usa protocolo Hito02 congelado: velocidad 5, bins 8, max_fit 2000')
    samples,manifest=read_artifacts(args.data_dir)
    output=args.output
    output.mkdir(parents=True,exist_ok=True)
    if args.mode=='offline':
        steps,windows,fit,folds=run_offline(samples,args)
        files={'trazas_cinematicas.csv':steps,'ventanas_causales.csv':windows,
               'familias_train.csv':fit,'diagnostico_folds.csv':folds}
        for name,d in files.items():d.to_csv(output/name,index=False,float_format='%.12g')
        print('\nCOBERTURA CINEMATICA CAUSAL POR VARIANTE:')
        if windows.empty:
            raise RuntimeError('Ninguna ventana con inicio causal valida; revise diagnostico de segmentos.')
        mm=windows.groupby('variant').agg(
            n_windows=('n_steps','size'),mean_steps=('n_steps','mean'),
            mean_common_steps=('common_prefix_steps','mean'),
            frac_intervened=('fraction_intervened','mean'),
            frac_jerk_infeasible=('fraction_jerk_infeasible','mean'),
            frac_outside_moving=('exit_reason', lambda s: float(np.mean(s=='left_moving_domain'))),
            w_accel_common=('w_accel_common','mean'),
            w_jerk_common=('w_jerk_common','mean')).reset_index()
        print(mm.to_string(index=False,float_format=lambda x:f'{x:.6f}'))
        print('AVISO: dt futuro EXOGENO; score sobre prefijo comun censurado, NO validacion causal de SUMO.')
    else:
        rows,fit,meta=sumo_shadow(samples,args)
        rows.to_csv(output/'sumo_shadow_trazas.csv',index=False,float_format='%.12g')
        fit.to_csv(output/'sumo_shadow_familias_train.csv',index=False)
        print(f'SUMO SHADOW: {len(rows)} observaciones; 0 comandos de control de vehiculos.')
    manifesto=dict(version='NTVC-Vine-R Hito03 v1',
                   mode=args.mode,data_manifest_sha256=sha256(args.data_dir/'manifest.json'),
                   allowed_sessions=manifest['allowed_sessions'],
                   reserved='Richard and 20231229_151643 not accessed',
                   model='Mismo ajuste Hito02 (refit TRAIN porque no se serializo), sin tuning TEST',
                   sumo_control='SHADOW only, no commands to vehicles',
                   future_speed='Nunca selecciona entrada de ventanas por velocidad futura',
                   offline_dt='Observado futuro solo como reloj exogeno, no previsto',
                   limits={'amin':args.amin,'amax':args.amax,'jmax':args.jmax,
                           'vmax_kmh':args.max_speed_kmh},
                   parameters={k:getattr(args,k) for k in ('seed','window','max_windows','seeds','max_fit','bins_per_sign')},
                   files_sha256={f.name:sha256(f) for f in output.glob('*.csv')})
    (output/'manifest_hito03.json').write_text(json.dumps(manifesto,indent=2,ensure_ascii=False),encoding='utf-8')
    print('ARCHIVOS:',output.resolve())

if __name__=='__main__':main()
