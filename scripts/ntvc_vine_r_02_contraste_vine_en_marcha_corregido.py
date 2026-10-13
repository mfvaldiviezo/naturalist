#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NTVC-Vine-R / HITO 02: comparacion gaussiana vs Student-t en marcha.

Este experimento usa SOLO los artefactos Hito 01, con hashes validados.
No accede a CSV RAW, Richard ni a sesiones reservadas. No reabre decisiones
estructurales. Estima un primer arbol estacionario P2 de marcha y compara dos
SEGUNDOS arboles D-Vine identicos salvo la familia:
 Gaussian (rho MLE TRAIN) vs Student(4/8) (rho MLE, df TRAIN BIC).
Tambien mantiene independencia C2 para comprobar el valor de la memoria.

ADVERTENCIA: La poblacion esta condicionada retrospectivamente a que las
velocidades de t-2,t-1,t sean >5km/h. El entrenamiento/evaluacion NO prueban
prediccion causal del cruce de regimenes ni pueden extrapolar a SUMO sin un
modelo de transicion de regimen fisico. La ley estacionaria es DEL SUBMODELO
de marcha, no del proceso de velocidad condicionado.

Comandos (desde revision_naturalista):
  python .\\scripts\\ntvc_vine_r_02_contraste_vine_en_marcha.py --self-test
  python .\\scripts\\ntvc_vine_r_02_contraste_vine_en_marcha.py
Dependencias locales: P1, P2, P9.3, S01, S02, scipy, pandas, numpy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

from ntvc_v06_p2_estados_cuantiles import fit_kernel, simulate_bins, metrics, verify_pairwise_jerk
from ntvc_v06_p1_copula_estacionaria import select_training_windows
from ntvc_v06_p93_puente_copula_estacionaria import (
    make_triples, backward_rank, sample_backwards, sample_forwards, sample_discrete,
)
from ntvc_vine_s01_dvine_mixta_estacionaria import (
    Pair, clip01, make_observable_ranks, obs_logratio, slice_data,
    fit_second_tree,
)
from ntvc_vine_s02_centro_cero_intervalos import (
    zero_center_observed_data, fit_zero_tree,
)
from scipy.special import ndtr, ndtri

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'resultados'/'ntvc_vine_r_01_cohortes_movimiento'
OUT=ROOT/'resultados'/'ntvc_vine_r_02_contraste_vine_en_marcha'
EXPECTED_DEV={'alonso','andres','pablo','yolanda'}
FROZEN_SHA='EBBB8BEBE69DBBB55858FCB8F8753A7F33AAAD5CA78B57D4BBA9FEE669162C25'
ALLOWED_SESSIONS={('alonso','20240103_141959'),('andres','20231222_134710'),
                  ('andres','20231226_150915'),('pablo','20231123_094610'),
                  ('yolanda','20240111_185718')}
VARIANTS=('moving_p2','vine_indep2','vine_gaussian','vine_student')
REQ={'driver_id','session_id','segment_id','raw_row','a_t_m_s2',
     'a_t_minus_1_m_s2','dt_t_s','j_t_observed_m_s3',
     'speed_kmh','speed_class'}


def filehash(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()


def read_artifacts(data_dir, require_hash=True):
    p=data_dir/'cohortes_muestras_verificadas.csv'
    m=data_dir/'manifest.json'
    if not p.is_file() or not m.is_file():
        raise FileNotFoundError('Primero ejecutar Hito 01; faltan manifest.json o cohortes_muestras_verificadas.csv')
    manifest=json.loads(m.read_text(encoding='utf-8'))
    # Hito 01 serializa SHA-256 hexadecimal en MAYUSCULAS; hashlib.hexdigest()
    # devuelve minusculas. Normalizar ambas representaciones SIN omitir la
    # comprobacion criptografica (la comparacion es insensible solo al caso).
    if require_hash:
        recorded_hashes=manifest.get('file_sha256',{})
        expected_files=(
            'vine_marcha_triples_desarrollo.csv',
            'cohortes_muestras_verificadas.csv',
            'resumen_cohortes_por_sesion.csv',
            'folds_lodo_desarrollo.json',
        )
        for filename in expected_files:
            file_path=data_dir/filename
            expected=recorded_hashes.get(filename)
            if not file_path.is_file() or not isinstance(expected,str) or len(expected)!=64:
                raise RuntimeError(f'Archivo/hash ausente o invalido en Hito 01: {filename}')
            actual=filehash(file_path)
            if actual.casefold()!=expected.casefold():
                raise RuntimeError(
                    f'SHA256 no coincide para {filename}: '
                    f'manifiesto={expected.upper()}, archivo={actual.upper()}'
                )
        print('INTEGRIDAD HITO 01 OK: 4 archivos SHA256 verificados (hex mayus/minus normalizado).',flush=True)
    if manifest.get('original_verified_sha256','').upper()!=FROZEN_SHA:
        raise RuntimeError('Manifiesto Hito 01 no verifica el CSV congelado')
    if {tuple(map(str,x)) for x in manifest.get('allowed_sessions',[])}!=ALLOWED_SESSIONS:
        raise RuntimeError('Manifiesto con sesiones diferentes de las autorizadas')
    df=pd.read_csv(p,dtype={'driver_id':str,'session_id':str,'segment_id':str})
    if not REQ.issubset(df.columns):raise RuntimeError(f'Faltan columnas: {REQ-set(df.columns)}')
    if (set(df.driver_id)!=EXPECTED_DEV or df.session_id.nunique()!=5 or len(df)!=62398
            or set(zip(df.driver_id,df.session_id))!=ALLOWED_SESSIONS):
        raise RuntimeError('Cohortes no son exactamente el desarrollo permitido')
    if df.session_id.eq('20231229_151643').any() or df.driver_id.str.lower().eq('richard').any():
        raise RuntimeError('Datos reservados presentes en cohortes')
    if not np.isfinite(df[['a_t_m_s2','dt_t_s','speed_kmh']].to_numpy(float)).all():
        raise RuntimeError('Valores no finitos')
    if (df.dt_t_s<=0).any():raise RuntimeError('dt no positivo')
    return df,manifest


def make_moving_pairs(samples,min_run=4):
    """Transforma runs observados v>5 en cadenas P2, sin cruzar limites.

    El primer punto de cada run no define transicion intrarrun: se excluye.
    Cada observacion consecutiva restante aparece UNA sola vez (sin ponderar
    triples superpuestos). Los triples entrenables necesitan >=4 puntos.
    """
    samples=samples.sort_values(['driver_id','session_id','segment_id','raw_row'],kind='stable')
    records=[];diagn=[]
    for (driver,session,seg),g in samples.groupby(['driver_id','session_id','segment_id'],sort=False):
        g=g.sort_values('raw_row',kind='stable').reset_index(drop=True)
        mm=g.speed_kmh.to_numpy(float)>5.0
        edges=np.flatnonzero(np.r_[True,mm[1:]!=mm[:-1],True])
        for ordinal,(st,en) in enumerate(zip(edges[:-1],edges[1:])):
            if not mm[st]:continue
            if en-st<min_run:continue
            sub=g.iloc[st:en].reset_index(drop=True)
            a=sub.a_t_m_s2.to_numpy(float)
            pa=sub.a_t_minus_1_m_s2.to_numpy(float)
            dt=sub.dt_t_s.to_numpy(float)
            if not np.allclose(pa[1:],a[:-1],rtol=0,atol=1e-7):
                raise RuntimeError('Cadena rota en run de marcha')
            key=f'{session}_{seg}_{ordinal}'
            for k in range(1,len(sub)):
                records.append(dict(driver_id=driver,session_id=session,segment_id=key,
                    original_row_t=int(sub.raw_row.iloc[k]),a_t_m_s2=float(a[k]),
                    a_t_minus_1_m_s2=float(a[k-1]),dt_t_s=float(dt[k]),
                    j_t_observed_m_s3=float((a[k]-a[k-1])/dt[k]),
                    speed_kmh=float(sub.speed_kmh.iloc[k]),
                    pre_step_speed_kmh=float(sub.speed_kmh.iloc[k-1])))
            diagn.append(dict(driver_id=driver,session_id=session,run_id=key,
                              n_samples=len(sub),n_pairs=len(sub)-1,n_triples=max(0,len(sub)-3)))
    frame=pd.DataFrame.from_records(records)
    runs=pd.DataFrame.from_records(diagn)
    if frame.empty:raise RuntimeError('Sin parejas de marcha: revisar origen')
    if frame[['driver_id','session_id','segment_id','original_row_t']].duplicated().any():
        raise RuntimeError('Parejas duplicadas')
    return frame,runs


def get_fits(train,kernel,train_triples,seed,max_fit):
    active,tab_a=fit_second_tree(train,kernel,train_triples,seed,max_fit,'fixed')
    zero,tab_z,n_zero=fit_zero_tree(train,kernel,train_triples,seed+131,max_fit)
    tabs=pd.concat([tab_a,tab_z],ignore_index=True)
    groups={}
    for name in ('negative','positive','zero'):
        rows=tabs[tabs.group.eq(name)].copy()
        student=rows[rows.family.isin(['student4','student8'])].sort_values('bic').iloc[0]
        gaussian=rows[rows.family.eq('gaussian')].iloc[0]
        groups[name]={
            'gaussian':Pair('gaussian',float(gaussian.rho)),
            'student':Pair(str(student.family),float(student.rho)),
            'indep':Pair('indep'),
        }
        tabs.loc[tabs.group.eq(name),'selected_student_family']=str(student.family)
    return groups,tabs,n_zero


def generate(kernel,groups,variant,dt,start_accel,seed,stationary=False):
    if variant not in VARIANTS:raise ValueError('Variante desconocida')
    rng=np.random.default_rng(seed)
    m=kernel.marginal
    dt=np.asarray(dt,float)
    if not (np.isfinite(dt).all() and (dt>0).all()):raise ValueError('dt invalido')
    if variant=='moving_p2':
        return simulate_bins(kernel,start_accel,dt,rng,'bins_copula',stationary)
    if stationary:
        bc,_=sample_discrete(m.pi,float(rng.random()))
        zc=float(rng.standard_normal())
        ap=float(m.inverse_one(bc,float(ndtr(zc))))
    else:
        ap=float(start_accel)
        bc=int(m.bin_of([ap])[0]);uc=float(m.random_pit([bc],[ap],rng)[0])
        zc=float(ndtri(clip01(uc)))
    bp,zp=sample_backwards(kernel,bc,zc,rng)
    a=np.empty(len(dt),float);j=np.empty(len(dt),float)
    for t,delta in enumerate(dt):
        group='zero' if bc==m.zero_bin else ('negative' if bc<m.zero_bin else 'positive')
        fam='indep' if variant=='vine_indep2' else ('gaussian' if variant=='vine_gaussian' else 'student')
        pair=groups[group][fam]
        backwards=backward_rank(kernel,bp,zp,bc,zc)
        q=float(pair.hinv(backwards,float(rng.random())))
        bn,zn=sample_forwards(kernel,bc,zc,q)
        an=m.inverse_one(bn,float(ndtr(zn)))
        a[t]=an;j[t]=(an-ap)/delta
        ap=an;bp,zp=bc,zc;bc,zc=bn,zn
    verify_pairwise_jerk(a,j,float(start_accel) if not stationary else float(a[0]-j[0]*dt[0]),dt)
    return a,j


def score_groups(test,kernel,groups,triples,seed,driver):
    d1=make_observable_ranks(test,kernel,triples,seed)
    d0=zero_center_observed_data(test,kernel,triples,seed+19)
    out=[]
    for name,data in [('negative',d1),('positive',d1),('zero',d0)]:
        mask=np.ones(len(data['sign']),bool) if name=='zero' else data['sign']==name
        dd=slice_data(data,mask)
        if not len(dd['sign']):continue
        ref=np.zeros(len(dd['sign']),float)
        lr_g=obs_logratio(groups[name]['gaussian'],dd)
        lr_s=obs_logratio(groups[name]['student'],dd)
        out.append(dict(driver_left_out=driver,group=name,
                        n_test_triples=len(dd['sign']),
                        n_test_segments=len(set(dd['segment'])),
                        student_family=groups[name]['student'].family,
                        gauss_mean_neglog=-float(np.mean(lr_g)),
                        student_mean_neglog=-float(np.mean(lr_s)),
                        student_minus_gaussian=-float(np.mean(lr_s-lr_g)),
                        conditional_score_only=True))
    return out


def evaluate(dev,args):
    diagnostics=[];fits_all=[];scores=[];win_rows=[];long_rows=[]
    for fold,driver in enumerate(sorted(dev.driver_id.unique()),1):
        train=dev[dev.driver_id.ne(driver)].reset_index(drop=True)
        test=dev[dev.driver_id.eq(driver)].reset_index(drop=True)
        n_train_triples=len(make_triples(train));n_test_triples=len(make_triples(test))
        kernel=fit_kernel(train,args.bins_per_sign,seed=args.seed+fold,
                          min_pair=60,shrinkage=200)
        groups,fits,nz=get_fits(train,kernel,make_triples(train),
                                  args.seed+fold*71,args.max_fit)
        fits.insert(0,'driver_left_out',driver);fits_all.append(fits)
        scores+=score_groups(test,kernel,groups,make_triples(test),
                             args.seed+fold*211,driver)
        windows=select_training_windows(test,args.window,args.max_windows)
        for wi,(_,_,win) in enumerate(windows):
            dts=win.dt_t_s.to_numpy(float); oa=win.a_t_m_s2.to_numpy(float)
            oj=win.j_t_observed_m_s3.to_numpy(float)
            a0=float(win.a_t_minus_1_m_s2.iloc[0])
            speed0=float(win.pre_step_speed_kmh.iloc[0])
            for si in range(args.seeds):
                seed=args.seed+fold*1000301+wi*3331+si*51
                for variant in VARIANTS:
                    aa,jj=generate(kernel,groups,variant,dts,a0,seed)
                    rec=metrics(aa,jj,oa,oj,kernel.p95_a,kernel.p95_j)
                    velocity=speed0/3.6+np.cumsum(aa*dts)
                    win_rows.append(dict(driver_left_out=driver,window_id=wi,
                        segment_id=str(win.segment_id.iloc[0]),seed=si,variant=variant,
                        n_steps=len(win),
                        initial_speed_kmh=speed0,
                        fraction_integrated_speed_below5=float(np.mean(velocity<=5/3.6)),
                        fraction_integrated_speed_negative=float(np.mean(velocity<0)),
                        **rec))
        if args.long_steps>0:
            durations=np.random.default_rng(args.seed+fold*999).choice(
                train.dt_t_s.to_numpy(float),args.long_steps,replace=True)
            for si in range(args.seeds):
                for variant in VARIANTS:
                    aa,jj=generate(kernel,groups,variant,durations,0.,args.seed+fold*30301+si*101,
                                   stationary=True)
                    rec=metrics(aa,jj,train.a_t_m_s2.to_numpy(float),
                                train.j_t_observed_m_s3.to_numpy(float),kernel.p95_a,kernel.p95_j)
                    long_rows.append(dict(driver_left_out=driver,variant=variant,seed=si,
                                           **rec))
        diag=dict(driver_left_out=driver,n_train_pairs=len(train),n_test_pairs=len(test),
                  n_train_triples=n_train_triples,n_test_triples=n_test_triples,
                  n_train_zero_center=nz,n_windows=len(windows),
                  stationary_p2_residual=kernel.stationary_check(),
                  n_bins=kernel.marginal.n_bins)
        diagnostics.append(diag)
        print(f'FOLD {fold}/4 {driver}: train_pairs={len(train)} test_pairs={len(test)} '
              f'triples={n_test_triples} ventanas={len(windows)} '
              f'Vine Student (-/0/+)='+','.join(groups[z]['student'].family for z in ['negative','zero','positive']),flush=True)
    return (pd.DataFrame(diagnostics),pd.concat(fits_all,ignore_index=True),
            pd.DataFrame(scores),pd.DataFrame(win_rows),pd.DataFrame(long_rows))


def summarize(df,metrics_list):
    if df.empty:return pd.DataFrame()
    per_driver=df.groupby(['driver_left_out','variant'])[metrics_list].mean().reset_index()
    return per_driver.groupby('variant')[metrics_list].mean().reset_index()


def self_test():
    # Regresion: Hito 01 usa hash en mayusculas y Hito 02 en minusculas.
    # Un SHA-256 valido no debe fallar por diferencia de representacion.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='ntvc_h02_sha_') as temp:
        tempdir=Path(temp)
        payload=b'NTVC-Vine-R Hito 01 hash case regression\n'
        h=hashlib.sha256(payload).hexdigest()
        assert h.upper().casefold()==h.lower().casefold()
        assert h.upper()!=h.lower()  # El test detectaria comparacion literal.
        for name in ('vine_marcha_triples_desarrollo.csv',
                     'cohortes_muestras_verificadas.csv',
                     'resumen_cohortes_por_sesion.csv',
                     'folds_lodo_desarrollo.json'):
            (tempdir/name).write_bytes(payload)
            assert filehash(tempdir/name).casefold()==h.upper().casefold()
        (tempdir/'cohortes_muestras_verificadas.csv').write_bytes(b'altered')
        assert filehash(tempdir/'cohortes_muestras_verificadas.csv').casefold()!=h.upper().casefold()
    rng=np.random.default_rng(2610);rs=[]
    for d in ['alonso','andres','pablo','yolanda']:
        a=rng.choice([-1.0,-.6,-.25,0.0,.25,.65,1.0],size=950,
                     p=[.08,.12,.18,.18,.18,.16,.1])
        v=np.full(len(a),45.0)
        v[190:207]=0.;v[500:513]=3.
        for k in range(len(a)):
            rs.append(dict(driver_id=d,session_id='synthetic_'+d,segment_id='s1',
                           raw_row=k*7+13,a_t_m_s2=float(a[k]),
                           a_t_minus_1_m_s2=float(a[k-1]) if k else float(a[k]),
                           dt_t_s=.3,j_t_observed_m_s3=(a[k]-a[k-1])/.3 if k else 0.,
                           speed_kmh=float(v[k]),speed_class='marcha_gt5' if v[k]>5 else 'detenido_le1'))
    frame,runs=make_moving_pairs(pd.DataFrame(rs),4)
    assert frame.driver_id.nunique()==4 and len(runs)>=8
    assert frame.a_t_m_s2.eq(0).any()
    assert not (frame.pre_step_speed_kmh<=5).any()
    # Ningun extremo temporal de run puede cruzar parada.
    assert frame.groupby(['driver_id','segment_id']).speed_kmh.min().gt(5).all()
    train=frame[frame.driver_id!='alonso'].reset_index(drop=True)
    test=frame[frame.driver_id=='alonso'].reset_index(drop=True)
    assert len(make_triples(train))>100
    ker=fit_kernel(train,2,seed=7,min_pair=10,shrinkage=30)
    groups,tabs,nz=get_fits(train,ker,make_triples(train),7,250)
    assert nz>0
    assert set(groups)=={'negative','zero','positive'}
    scores=score_groups(test,ker,groups,make_triples(test),2026,'alonso')
    assert len(scores)==3 and all(np.isfinite(v['student_minus_gaussian']) for v in scores)
    for name in VARIANTS:
        aa,jj=generate(ker,groups,name,np.full(100,.3),float(test.a_t_minus_1_m_s2.iloc[0]),55)
        verify_pairwise_jerk(aa,jj,float(test.a_t_minus_1_m_s2.iloc[0]),np.full(100,.3))
    print('SELF-TEST OK: movimiento, exclusión de paradas, kernel, D-Vine Student/Gaussian, score y jerk')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--data-dir',type=Path,default=DATA)
    ap.add_argument('--output',type=Path,default=OUT)
    ap.add_argument('--window',type=int,default=40)
    ap.add_argument('--max-windows',type=int,default=30)
    ap.add_argument('--seeds',type=int,default=2)
    ap.add_argument('--max-fit',type=int,default=2000)
    ap.add_argument('--bins-per-sign',type=int,default=8)
    ap.add_argument('--long-steps',type=int,default=3000)
    ap.add_argument('--seed',type=int,default=2026)
    args=ap.parse_args()
    if args.self_test:return self_test()
    if args.seeds<1 or args.window<10 or args.max_windows<1 or args.max_fit<100 or args.long_steps<0:
        ap.error('Opciones fuera de rango')
    samples,manifest=read_artifacts(args.data_dir)
    dev,runs=make_moving_pairs(samples)
    if dev.driver_id.nunique()!=4:raise RuntimeError('Cuatro conductores de desarrollo requeridos')
    print(f'COHORTE: Hito01 triples={manifest.get("n_moving_triples", "desconocido")}, '
          f'Hito02 triples={len(make_triples(dev))} (sin ponderar parejas superpuestas).',flush=True)
    diag,fits,score,win,long=evaluate(dev,args)
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    files={
        'auditoria_runs.csv':runs,
        'diagnostico_folds.csv':diag,
        'seleccion_familias_train.csv':fits,
        'score_condicional_lodo.csv':score,
        'ventanas_diagnostico.csv':win,
        'simulaciones_largas_train_only.csv':long,
    }
    for name,d in files.items():d.to_csv(out/name,index=False,float_format='%.12g')
    score_s=score.groupby('group').agg(n_drivers=('driver_left_out','nunique'),
                     delta_student_gauss=('student_minus_gaussian','mean')).reset_index()
    met=['w_accel','w_jerk','p_zero_abs_error','tail_a_abs_error','tail_j_abs_error',
         'fraction_integrated_speed_below5']
    print('\nDELTA CONDICIONAL Student - Gaussian (negativo favorece Student):')
    print(score_s.to_string(index=False,float_format=lambda q:f'{q:.6f}'))
    print('\nPOR CONDUCTOR Y CONTEXTO:')
    print(score[['driver_left_out','group','n_test_triples','student_family','student_minus_gaussian']].to_string(index=False,float_format=lambda q:f'{q:.6f}'))
    print('\nVENTANAS DE MOVIMIENTO OBSERVADAS (diagnostico retrospectivo):')
    print(summarize(win,met).to_string(index=False,float_format=lambda q:f'{q:.6f}') if not win.empty else 'No hay ventanas suficientes con los parámetros fijados')
    if not long.empty:
        print('\nSIMULACION AUTONOMA LARGA TRAIN-only (submodelo marcha; NO velocidad física):')
        print(summarize(long,['w_accel','w_jerk','p_zero_abs_error']).to_string(index=False,float_format=lambda q:f'{q:.6f}'))
    audit={'protocol':'Hito02: Gauss vs Student en segundo arbol, marcha observada',
           'data_manifest_sha256':filehash(args.data_dir/'manifest.json'),
           'data_sha256':filehash(args.data_dir/'cohortes_muestras_verificadas.csv'),
           'drivers':sorted(dev.driver_id.unique()),'n_pairs_unique':len(dev),
           'n_moving_runs':len(runs),'n_triples_usable':len(make_triples(dev)),
           'n_triples_hito01':int(manifest.get('n_moving_triples',-1)),
           'qualification':'Condicionado en velocidades FUTURAS observadas; NO es evaluacion causal de una politica',
           'external_test':'Richard nunca leido; sesion alonso reservada nunca leida',
           'parameters':vars(args) | {'data_dir':str(args.data_dir),'output':str(args.output)},
           'outputs':{name:filehash(out/name) for name in files}}
    (out/'manifest.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print('\nARCHIVOS:',out.resolve())
    print('NO entrenar mas familias ni revisar el holdout despues de esta prueba; LODO exploratorio.')

if __name__=='__main__':main()
