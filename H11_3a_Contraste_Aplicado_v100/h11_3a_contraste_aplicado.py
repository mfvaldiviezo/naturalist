#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H11.3a / puente de validacion aplicado PoliDriving--SUMO: solo lectura, sin ajuste.
Reutiliza H01 congelado y H11.2 telemetria pareada; NUNCA abre RAW ni Richard.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, math, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, wasserstein_distance

VER='H11.3a contrast applied v1.0'
DEV_SESSIONS={('alonso','20240103_141959'),('andres','20231222_134710'),
              ('andres','20231226_150915'),('pablo','20231123_094610'),('yolanda','20240111_185718')}
H01_SOURCE_SHA='ebbb8bebe69dbbb55858fcb8f8753a7f33aaad5ca78b57d4bba9fee669162c25'
MOVE_KMH=5.0
METRICS=('a','jerk')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for buf in iter(lambda:f.read(1<<20), b''):h.update(buf)
    return h.hexdigest()

def guarded_path(path, root, prefix='resultados'):
    p=Path(path).resolve(); root=Path(root).resolve(); allowed=root/prefix
    if not p.is_relative_to(allowed):
        raise ValueError(f'Ruta fuera de {allowed}: {p}')
    if not p.exists():raise FileNotFoundError(p)
    return p

def verify_h01(folder):
    folder=Path(folder); mf=folder/'manifest.json'; fp=folder/'cohortes_muestras_verificadas.csv'
    if not mf.is_file() or not fp.is_file():raise FileNotFoundError('H01: faltan manifest.json o cohortes_muestras_verificadas.csv')
    m=json.loads(mf.read_text(encoding='utf-8-sig'))
    if str(m.get('original_verified_sha256','')).lower()!=H01_SOURCE_SHA:
        raise ValueError('H01: no coincide SHA del CSV de desarrollo congelado')
    dig=m.get('file_sha256',{}).get(fp.name)
    if not dig or str(dig).lower()!=sha(fp):raise ValueError('H01: SHA del CSV de muestras no coincide')
    pairs={tuple(map(str,p)) for p in m.get('allowed_sessions', [])}
    if pairs!=DEV_SESSIONS:raise ValueError('H01: sesiones no corresponden exactamente al conjunto de desarrollo')
    header=set(pd.read_csv(fp,nrows=0).columns)
    required={'driver_id','session_id','segment_id','raw_row','a_t_m_s2','j_t_observed_m_s3','dt_t_s','speed_kmh','a_t_minus_1_m_s2'}
    if not required.issubset(header):raise ValueError('H01: campos ausentes: '+str(sorted(required-header)))
    return {'manifest_sha256':sha(mf),'csv_sha256':sha(fp),'csv':str(fp),'original_verified_sha256':H01_SOURCE_SHA}

def verify_h11(root, folder, condition):
    source=Path(root)/'H11_2c_Caracterizacion_Integral_v100'/'h11_2c_caracterizar.py'
    if not source.is_file():raise FileNotFoundError('Falta auditor H11.2c original para revalidar procedencia: '+str(source))
    spec=importlib.util.spec_from_file_location('h11_2c_procedencia',source)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    a=mod.verify_source(folder,condition,600)
    b=mod.verify_paired(folder,condition)
    if a['seed'] is not None and int(a['seed'])!=101:raise ValueError('Semilla H11 no es 101')
    return {'fuente':a,'pareado':b,'auditor_h11_2c_sha256':sha(source)}

def load_h01(path):
    cols=['driver_id','session_id','segment_id','raw_row','a_t_m_s2','a_t_minus_1_m_s2','j_t_observed_m_s3','dt_t_s','speed_kmh']
    x=pd.read_csv(path,usecols=cols)
    pairs=set(zip(x.driver_id.astype(str), x.session_id.astype(str)))
    if pairs != DEV_SESSIONS:raise ValueError('H01: sesion reservada/inesperada o falta una de desarrollo')
    if x[cols].isna().any().any():raise ValueError('H01: no se permiten nulos en datos verificados')
    for c in ['a_t_m_s2','a_t_minus_1_m_s2','j_t_observed_m_s3','dt_t_s','speed_kmh']:
        x[c]=pd.to_numeric(x[c],errors='raise')
        if not np.isfinite(x[c].to_numpy()).all():raise ValueError('H01: no finitos '+c)
    if (x.dt_t_s<=0).any() or (x.speed_kmh<0).any():raise ValueError('H01: dt o velocidad invalida')
    if x.duplicated(['driver_id','session_id','segment_id','raw_row']).any():raise ValueError('H01: ID de muestra duplicado')
    x=x.sort_values(['driver_id','session_id','segment_id','raw_row'],kind='stable').reset_index(drop=True)
    # Solo pares de observaciones verificadas y consecutivas dentro de un segmento.
    key=['driver_id','session_id','segment_id']; prev=x.groupby(key,sort=False)
    same=prev.cumcount()>0
    prev_speed=prev.speed_kmh.shift(1)
    prev_a=prev.a_t_m_s2.shift(1)
    continuity=same & (np.abs(x.a_t_minus_1_m_s2-prev_a)<=1e-6)
    x['a']=x.a_t_m_s2;x['jerk']=x.j_t_observed_m_s3
    x['moving_a']=x.speed_kmh>MOVE_KMH
    x['moving_j']=x.moving_a & prev_speed.gt(MOVE_KMH) & continuity
    x['source']='PoliDriving_desarrollo';x['cohort']='desarrollo'
    x['entity']=x.driver_id+'|'+x.session_id
    x['dt']=x.dt_t_s
    x['segment']=x.segment_id.astype(str)
    x['adjacent_pair']=continuity
    return x[['source','cohort','entity','segment','adjacent_pair','a','jerk','dt','moving_a','moving_j','speed_kmh']]

def load_h11(path, condition):
    cols=['vehicle_id','time_s','dt_s','cohort','speed_m_s','accel_m_s2','jerk_observed_m_s3']
    x=pd.read_csv(Path(path)/'trayectorias_h11.csv',usecols=cols,low_memory=False)
    required=['vehicle_id','time_s','dt_s','cohort','speed_m_s','accel_m_s2']
    if x[required].isna().any().any():raise ValueError(condition+': ausencias en columnas criticas')
    if x.duplicated(['vehicle_id','time_s']).any():raise ValueError('H11: muestras repetidas')
    for c in ['time_s','dt_s','speed_m_s','accel_m_s2']:
        if not np.isfinite(x[c].to_numpy(dtype=float)).all():raise ValueError('H11: no finitos')
    if (x.dt_s<=0).any() or (x.speed_m_s<0).any():raise ValueError('H11: dt/velocidad invalido')
    x=x.sort_values(['vehicle_id','time_s'],kind='stable').reset_index(drop=True)
    grp=x.groupby('vehicle_id',sort=False)
    prev_t=grp.time_s.shift(1);prev_speed=grp.speed_m_s.shift(1)
    adjacent=np.isclose(x.time_s-prev_t, x.dt_s,rtol=0,atol=1e-5)
    if condition=='nominal' and set(x.cohort.unique())!={'unclassified'}:raise ValueError('nominal: cohortes activas inesperadas')
    if condition=='hibrido_contextual' and 'unclassified' in set(x.cohort.unique()):raise ValueError('hibrido: hay cohortes sin clasificar')
    x['a']=x.accel_m_s2;x['jerk']=x.jerk_observed_m_s3
    x['speed_kmh']=x.speed_m_s*3.6
    x['moving_a']=x.speed_kmh>MOVE_KMH
    x['moving_j']=x.moving_a & prev_speed.gt(MOVE_KMH/3.6) & adjacent & x.jerk.notna()
    x['source']=condition;x['entity']=x.vehicle_id.astype(str);x['dt']=x.dt_s
    x['segment']='observado';x['adjacent_pair']=adjacent
    return x[['source','cohort','entity','segment','adjacent_pair','a','jerk','dt','moving_a','moving_j','speed_kmh','time_s']]

def get_command_times(path):
    rows=pd.read_csv(path,usecols=['vehicle_id','target_time_s','command_issued'])
    times=defaultdict(set)
    for row in rows.itertuples(index=False):
        if str(row.command_issued).strip().lower()=='true':
            t=float(row.target_time_s)
            if not math.isfinite(t):raise ValueError('Tiempo Vine no finito')
            times[str(row.vehicle_id)].add(round(t,6))
    return times

def label_actuation(hyb,actions):
    x=hyb.copy()
    x['actuacion']=[round(float(t),6) in actions.get(str(v),set()) for v,t in zip(x.entity,x.time_s)]
    if (x.loc[x.actuacion,'cohort'].isin(['neither','h09_only'])).any():
        raise ValueError('Accion directa Vine detectada fuera de cohortes Vine')
    return x

def calc(x, key, mask):
    vals=x.loc[mask,key].dropna().to_numpy(float)
    if not len(vals):return None
    return {'n':int(len(vals)),'mean':float(np.mean(vals)),'std':float(np.std(vals)),
            'p05':float(np.quantile(vals,.05)),'p50':float(np.median(vals)),
            'p95':float(np.quantile(vals,.95)),'p99_abs':float(np.quantile(np.abs(vals),.99)),
            'zero_exact_fraction':float(np.mean(vals==0))}

def metric_compare(reference,simulated,key,mask_ref,mask_sim,label):
    r=reference.loc[mask_ref,key].dropna().to_numpy(float)
    s=simulated.loc[mask_sim,key].dropna().to_numpy(float)
    if len(r)<30 or len(s)<30:
        return {'grupo':label,'variable':key,'n_polidriving':len(r),'n_sumo':len(s),'wasserstein':None,'ks':None,'nota':'POCAS_MUESTRAS'}
    return {'grupo':label,'variable':key,'n_polidriving':len(r),'n_sumo':len(s),
            'wasserstein':float(wasserstein_distance(r,s)),
            'ks':float(ks_2samp(r,s,method='asymp').statistic),
            'nota':'DESCRIPTIVO_DOMINIOS_DIFERENTES_NO_INFERENCIA'}


def temporal_descriptive(data):
    # Primero correlaciones dentro de sesion/conductor o vehiculo: nunca puente entre entidades/segmentos.
    acfs=[]; zeros=[]; pairs=0
    if data.empty:return {'lag1_acf_macro':None,'lag1_units':0,'lag1_pairs':0,'zero_run_p95_seconds':None,'zero_runs':0}
    for _,g in data.groupby(['entity','segment'],sort=False):
        g=g.copy()
        if 'time_s' in g:
            g['adj_calc']=g.adjacent_pair & np.isclose(g.time_s.diff(),g.dt,rtol=0,atol=1e-5)
        else:
            g['adj_calc']=g.adjacent_pair
        ok=g.moving_a & g.moving_a.shift(1,fill_value=False) & g.adj_calc
        pp=g.loc[ok,'a'].shift(0).to_numpy(float)
        prev=g['a'].shift(1).loc[ok].to_numpy(float)
        pairs+=len(pp)
        if len(pp)>=3 and np.std(pp)>1e-9 and np.std(prev)>1e-9:
            c=float(np.corrcoef(prev,pp)[0,1])
            if np.isfinite(c):acfs.append(c)
        run=0.
        # Duracion observada por muestra; no incluye tiempo de reaccion ni huecos sin medir.
        for row in g.itertuples(index=False):
            if bool(row.moving_a) and float(row.a)==0:
                if run and not bool(row.adj_calc):zeros.append(run);run=0.
                run+=float(row.dt)
            elif run:
                zeros.append(run);run=0.
        if run:zeros.append(run)
    return {'lag1_acf_macro':float(np.mean(acfs)) if acfs else None,'lag1_units':len(acfs),'lag1_pairs':pairs,
            'zero_run_p95_seconds':float(np.quantile(zeros,.95)) if zeros else None,'zero_runs':len(zeros)}

def summarize(root, h01, nom, hib, act, verify_only=False):
    integrity={'h01':verify_h01(h01),
               'nominal':verify_h11(root,nom,'nominal'),
               'hibrido':verify_h11(root,hib,'hibrido_contextual'),
               'vine_actions_sha256':sha(act)}
    # Chequear esquema de acciones sin leer datos privados de test.
    ahead=set(pd.read_csv(act,nrows=0).columns)
    if not {'vehicle_id','command_issued','target_time_s'}.issubset(ahead):raise ValueError('Acciones Vine no reconocidas')
    if verify_only:return integrity,None,None
    real=load_h01(Path(h01)/'cohortes_muestras_verificadas.csv')
    n=load_h11(nom,'nominal');h=label_actuation(load_h11(hib,'hibrido_contextual'),get_command_times(act))
    groups={'nominal':n,'hibrido_todos':h}
    for group in ('both','h09_only','vine_only','neither'):
        groups['hibrido_'+group]=h[h.cohort==group]
    groups['hibrido_vine_actuado']=h[h.actuacion]
    report=[]; dists=[]
    def stats(data,label):
        rec={'grupo':label,'filas':len(data),'vehiculos_o_sesiones':int(data.entity.nunique()),
             'muestras_a_marcha':int(data.moving_a.sum()),'pares_jerk_marcha':int(data.moving_j.sum()),
             'dt_median_s':float(data.dt.median()) if len(data) else None,
             'nota':'Muestra observacional; usuarios/sesiones no independientes por fila'}
        rec.update(temporal_descriptive(data))
        for key,mask in [('a',data.moving_a),('jerk',data.moving_j)]:
            st=calc(data,key,mask)
            for field in ('mean','std','p05','p50','p95','p99_abs','zero_exact_fraction'):
                rec[f'{key}_{field}']=None if st is None else st[field]
        return rec
    report.append(stats(real,'PoliDriving_desarrollo_5_sesiones'))
    for name,group in groups.items():
        report.append(stats(group,name))
        for metric,mref,msim in [('a',real.moving_a,group.moving_a),('jerk',real.moving_j,group.moving_j)]:
            dists.append(metric_compare(real,group,metric,mref,msim,name))
    summary={'version':VER,'calibrated_quito':False,'modelo_ajustado':False,'test_richard_abierto':False,
             'notes':['H01 desarrollo exclusivamente: Richard y Alonso 20231229_151643 excluidos',
                      'Comparaciones ex-post observacionales por v>5 km/h; no validacion causal',
                      'Diferencia de muestreo y adquisicion PoliDriving vs SUMO: comparar dt_median_s y no confundir W1 con fidelidad temporal',
                      'Poblaciones y distribuciones de velocidades/entornos diferentes; W1 y KS descriptivos',
                      'Vine-actuado: solo muestras en t+dt donde se emitio comando directo; no se atribuye causalidad',
                      'La masa exacta a=0 depende de precision y sensor; no imponer igualdad fisica',
                      'No se reentreno, recalibro ni ejecuto SUMO'],
             'integridad':integrity,
             'counts':{'polidriving':len(real),'nominal':len(n),'hibrido':len(h),'vine_targets_con_muestra':int(h.actuacion.sum()),
                       'vehiculos_efectivamente_comandados':int(h.loc[h.actuacion,'entity'].nunique())}}
    return summary,pd.DataFrame(report),pd.DataFrame(dists)

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path('.'))
    ap.add_argument('--h01',type=Path)
    ap.add_argument('--nom',type=Path,required=True)
    ap.add_argument('--hib',type=Path,required=True)
    ap.add_argument('--vine-actions',type=Path,required=True)
    ap.add_argument('--guardar',action='store_true')
    ap.add_argument('--out',type=Path)
    a=ap.parse_args(argv)
    root=a.root.resolve()
    if a.h01:h01=guarded_path(a.h01,root)
    else:
        folders=[root/'resultados'/'ntvc_vine_r_01_cohortes_movimiento_regenerado',root/'resultados'/'ntvc_vine_r_01_cohortes_movimiento']
        h01=next((p for p in folders if (p/'manifest.json').is_file()),None)
        if h01 is None:raise FileNotFoundError('No se encontro H01 congelado en las dos rutas conocidas')
    nom=guarded_path(a.nom,root);hib=guarded_path(a.hib,root);act=guarded_path(a.vine_actions,root)
    expected_actions=(hib.parent/'hibrido_contextual'/'acciones_hito08.csv').resolve()
    if act!=expected_actions:raise ValueError('Acciones Vine deben proceder del mismo brazo observado del hibrido H11.2: '+str(expected_actions))
    if a.out and not a.guardar:ap.error('--out requiere --guardar')
    print('=== H11.3a / CONTRASTE CINEMATICO APLICADO | SOLO LECTURA ===')
    print('H01:',h01)
    integrity,_,_=summarize(root,h01,nom,hib,act,verify_only=True)
    print('INTEGRIDAD H01: OK (desarrollo congelado; reserva excluida)')
    print('INVARIANZA:',integrity['nominal']['pareado']['status'],'/',integrity['hibrido']['pareado']['status'])
    print('H11.2: 600 pasos por escenario / SEMILLA 101')
    print('NO SE REPROCESA PoliDriving, NO SE REENTRENA Vine, NO SE ABRE Richard')
    if not a.guardar:
        print('PREFLIGHT COMPLETO. Usa --guardar para contraste descriptivo de aceleracion/jerk aplicados.')
        return
    summary,metrics,dists=summarize(root,h01,nom,hib,act)
    print('MUESTRAS:',summary['counts'])
    print('\nESTADISTICOS DE MOVIMIENTO:')
    print(metrics[['grupo','filas','muestras_a_marcha','pares_jerk_marcha','dt_median_s','a_p95','jerk_p99_abs','lag1_acf_macro','zero_run_p95_seconds']].to_string(index=False))
    print('\nDISTANCIAS DE DISTRIBUCION (NO CALIBRACION):')
    print(dists[['grupo','variable','n_polidriving','n_sumo','wasserstein','ks']].to_string(index=False))
    out=a.out.resolve() if a.out else root/'resultados'/('h11_3a_contraste_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if not out.is_relative_to(root/'resultados') or out.exists():raise ValueError('La carpeta nueva debe estar dentro de resultados y no existir')
    out.mkdir(parents=True)
    metrics.to_csv(out/'metricas_cinematica_h11_3a.csv',index=False)
    dists.to_csv(out/'distancias_h11_3a.csv',index=False)
    summary['sha_salida']={'metricas_cinematica_h11_3a.csv':sha(out/'metricas_cinematica_h11_3a.csv'),
                           'distancias_h11_3a.csv':sha(out/'distancias_h11_3a.csv')}
    (out/'manifiesto_h11_3a.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    text=['# H11.3a — Contraste aplicado PoliDriving–SUMO (descriptivo)',
          '', '**Fuente:** cinco sesiones de desarrollo H01 auditadas; Richard y reserva Alonso no se abrieron.',
          '**Integridad:** SHA H01 y H11.2, invariancia pareada revalidados.',
          '**Alcance:** distribuciones de aceleracion y jerk observados, sin ajustar modelos, sin SUMO nuevo.',
          '', f"Registros: H01 {summary['counts']['polidriving']}; SUMO nominal {summary['counts']['nominal']}; híbrido {summary['counts']['hibrido']}.",
          '', '## Observaciones metodológicas obligatorias',
          'La frecuencia de medición de PoliDriving no necesariamente coincide con 0,5 s en SUMO. Jerk es especialmente sensible al intervalo. Los contrastes W1 y KS son descriptivos entre dominios y velocidades diferentes: no acreditan representatividad en Quito.',
          'El lag-1 se calcula dentro de sesiones/vehiculos sin unir segmentos; los dos dominios tienen distinta frecuencia. Las rachas cero se miden en segundos observados y dependen de cuantizacion/sensor.',
          'Vine actuado significa pasos con orden efectiva; es una muestra condicionada y seleccionada por cuota/elegibilidad. No equivale a una muestra independiente ni permite atribucion causal.',
          'Las trayectorias controladas por SUMO son el resultado combinado de mecanismos vType, car-following, límites y red. No representan muestras libres del núcleo Vine.',
          'La cinemática naturalista es solo una dimensión; H09/semáforos/gridlock requieren otras referencias.',
          '', '## Próximo análisis, sin reiterar anteriores',
          'Comparar por contexto de velocidad y por episodio completo, jerarquizar sesiones/conductores y diferenciar propuestas Vine, comandos y aceleraciones observadas. Solo después definir calibración o ensayos multisemilla.',
          '', f'Carpeta de resultados: `{out}`']
    (out/'informe_h11_3a.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print('H11.3a REPORTE:',out)
    print('AVISO: SOLO DESCRIPTIVO; no se ha acreditado validez empirica de Quito')

if __name__=='__main__':main()
