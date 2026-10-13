#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H11.3a / Contraste cinemático POR VELOCIDAD + comandos con líder, SOLO LECTURA.

Reutiliza obligatoriamente H11_3a_Contraste_Aplicado_v100 para verificar H01/H11.2.
No abre Richard, no reentrena, no arranca SUMO ni modifica resultados anteriores.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance, ks_2samp

VERSION='H11.3a bandas velocidad y comandos v1.0'
BIN_LABELS=('05_20','20_40','40_60','gt60')
MIN_DIST_SAMPLES=30
MIN_PAIRED_SAMPLES=10
GROUP_COHORTS=('both','vine_only','h09_only','neither')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20), b''):
            h.update(chunk)
    return h.hexdigest()


def import_parent(root):
    script=Path(root)/'H11_3a_Contraste_Aplicado_v100'/'h11_3a_contraste_aplicado.py'
    if not script.is_file():
        raise FileNotFoundError('Falta el auditor original H11.3a: '+str(script))
    spec=importlib.util.spec_from_file_location('h113a_frozen_parent',script)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod,script


def assign_speed_bins(df):
    """Abierto en 5 km/h, cerrado a derecha; 60 km/h es banda 40-60."""
    x=df.copy()
    x['speed_bin']=pd.cut(x.speed_kmh, bins=[5.,20.,40.,60.,math.inf],
                          labels=BIN_LABELS, right=True)
    return x


def column_statistics(df,metric,selection):
    vals=df.loc[selection,metric].dropna().to_numpy(float)
    if not len(vals):
        return dict(n=0,entities=0,dt_median_s=None,mean=None,std=None,
                    p05=None,p50=None,p95=None,p99_abs=None,p_abs_le_005=None,
                    p_abs_le_010=None)
    if not np.isfinite(vals).all():raise ValueError('Métrica cinemática no finita')
    units=df.loc[selection & df[metric].notna(),'entity'].nunique()
    dtvals=df.loc[selection & df[metric].notna(),'dt'].to_numpy(float)
    return dict(n=int(len(vals)),entities=int(units),dt_median_s=float(np.median(dtvals)),
                mean=float(np.mean(vals)),std=float(np.std(vals)),
                p05=float(np.quantile(vals,.05)),p50=float(np.median(vals)),
                p95=float(np.quantile(vals,.95)),p99_abs=float(np.quantile(np.abs(vals),.99)),
                p_abs_le_005=float(np.mean(np.abs(vals)<=.05)),
                p_abs_le_010=float(np.mean(np.abs(vals)<=.10)))


def compare_bin(ref,sim,metric,bin_label):
    mr=ref.speed_bin.eq(bin_label) & (ref.moving_a if metric=='a' else ref.moving_j)
    ms=sim.speed_bin.eq(bin_label) & (sim.moving_a if metric=='a' else sim.moving_j)
    r=ref.loc[mr,metric].dropna().to_numpy(float)
    s=sim.loc[ms,metric].dropna().to_numpy(float)
    nref_ent=ref.loc[mr,'entity'].nunique()
    nsim_ent=sim.loc[ms,'entity'].nunique()
    result=dict(n_ref=len(r),n_sim=len(s),ref_units=int(nref_ent),sim_units=int(nsim_ent),
                wasserstein=None,ks=None,status='')
    if len(r)<MIN_DIST_SAMPLES or len(s)<MIN_DIST_SAMPLES:
        result['status']='INSUFFICIENT_SUPPORT'
    else:
        result['wasserstein']=float(wasserstein_distance(r,s))
        result['ks']=float(ks_2samp(r,s,method='asymp').statistic)
        result['status']='DESCRIPTIVE_ONLY'
    return result


def enrich_nominal_cohorts(nom,hib):
    pairs=hib[['entity','cohort']].drop_duplicates()
    if pairs.entity.duplicated().any():raise ValueError('Híbrido: vehículo con cohortes múltiples')
    nom=nom.drop(columns=['cohort']).merge(pairs,on='entity',how='left',validate='many_to_one')
    nom['cohort']=nom.cohort.fillna('not_in_hybrid')
    return nom


def cohorts_for_contrast(nom,hib):
    groups={'nominal_todos':nom,'hibrido_todos':hib}
    for c in GROUP_COHORTS:
        groups['nominal_'+c]=nom[nom.cohort.eq(c)]
        groups['hibrido_'+c]=hib[hib.cohort.eq(c)]
    vinelist=['both','vine_only']
    ids=hib.loc[hib.cohort.isin(vinelist),'entity'].unique()
    groups['nominal_vine_objetivo']=nom[nom.entity.isin(ids)]
    groups['hibrido_vine_objetivo']=hib[hib.entity.isin(ids)]
    ids_actual=hib.loc[hib.actuacion,'entity'].unique()
    groups['nominal_vehiculos_comandados']=nom[nom.entity.isin(ids_actual)]
    groups['hibrido_vehiculos_comandados']=hib[hib.entity.isin(ids_actual)]
    groups['hibrido_muestras_comandadas']=hib[hib.actuacion]
    return groups


def summary_bands(ref,groups):
    summary=[];dist=[]
    datasets={'PoliDriving_desarrollo':ref,**groups}
    for name,df in datasets.items():
        for bl in BIN_LABELS:
            for metric in ('a','jerk'):
                sel=df.speed_bin.eq(bl) & (df.moving_a if metric=='a' else df.moving_j)
                summary.append(dict(grupo=name,banda_kmh=bl,variable=metric,
                                    **column_statistics(df,metric,sel)))
    for name,df in groups.items():
        for bl in BIN_LABELS:
            for metric in ('a','jerk'):
                dist.append(dict(grupo=name,banda_kmh=bl,variable=metric,
                                 **compare_bin(ref,df,metric,bl)))
    return pd.DataFrame(summary),pd.DataFrame(dist)


def per_vehicle_paired(nom,hib):
    """Promedios de diferencias individuales; no es experimento causal.

    En cada banda, individuo válido >=10 muestras en los DOS brazos. Cada métrica
    (a o jerk) usa su propio denominador. No cruza segmentos ni relojes.
    """
    rows=[]
    for metric in ('a','jerk'):
        for bl in BIN_LABELS:
            m=lambda x: x.speed_bin.eq(bl) & (x.moving_a if metric=='a' else x.moving_j)
            nn=nom.loc[m(nom),['entity','cohort',metric]]
            hh=hib.loc[m(hib),['entity','cohort',metric]]
            def ag(x):
                return x.groupby(['entity','cohort'],sort=False,dropna=False)[metric].agg(
                    n='count',mean_abs=lambda v:float(np.mean(np.abs(v.dropna()))) if v.notna().any() else math.nan)
            na=ag(nn).reset_index().rename(columns={'n':'n_nom','mean_abs':'mean_abs_nom'})
            ha=ag(hh).reset_index().rename(columns={'n':'n_hib','mean_abs':'mean_abs_hib'})
            paired=na.merge(ha,on=['entity','cohort'],how='inner')
            paired=paired[(paired.n_nom>=MIN_PAIRED_SAMPLES)&(paired.n_hib>=MIN_PAIRED_SAMPLES)].copy()
            paired['delta_mean_abs']=paired.mean_abs_hib-paired.mean_abs_nom
            for c in ('todos',)+GROUP_COHORTS:
                sub=paired if c=='todos' else paired[paired.cohort.eq(c)]
                rows.append(dict(banda_kmh=bl,variable=metric,cohorte=c,
                                 n_vehiculos=int(len(sub)),
                                 media_delta_abs=None if sub.empty else float(sub.delta_mean_abs.mean()),
                                 mediana_delta_abs=None if sub.empty else float(sub.delta_mean_abs.median()),
                                 n_muestras_nominal=int(sub.n_nom.sum()),n_muestras_hibrido=int(sub.n_hib.sum()),
                                 minimo_muestras_por_brazo=MIN_PAIRED_SAMPLES,
                                 status='SIN_PARES_ELEGIBLES' if sub.empty else 'DESCRIPTIVO_NO_CAUSAL'))
    return pd.DataFrame(rows)


def command_and_leader(actions_path,traj_path):
    cols=('vehicle_id','time_s','target_time_s','guarded_a','observed_a_next',
          'matched_t_plus_dt','command_issued','proposed_a','guard_intervened')
    actions=pd.read_csv(actions_path,usecols=list(cols),dtype={'vehicle_id':str})
    active=actions[actions.command_issued.astype(str).str.lower().eq('true')].copy()
    if active.empty:raise ValueError('No hay comandos directos')
    tele=pd.read_csv(Path(traj_path)/'trayectorias_h11.csv',usecols=[
        'vehicle_id','time_s','speed_m_s','leader_id','gap_m','accel_m_s2'],
        dtype={'vehicle_id':str,'leader_id':str})
    tele['time_tick']=(tele.time_s.astype(float)*1000).round().astype('int64')
    if tele.duplicated(['vehicle_id','time_tick']).any():
        raise ValueError('Telemetría duplicada por vehículo y tiempo')
    lookup=tele.set_index(['vehicle_id','time_tick'])
    records=[]
    for a in active.itertuples(index=False):
        if str(a.matched_t_plus_dt).lower()!='true':
            raise ValueError('Comando sin observación temporal coincidente')
        key=(str(a.vehicle_id),int(round(float(a.time_s)*1000)))
        if key not in lookup.index:raise ValueError(f'Falta paso origen: {key}')
        vehicle=lookup.loc[key]
        t_next=(str(a.vehicle_id),int(round(float(a.target_time_s)*1000)))
        if t_next not in lookup.index:raise ValueError(f'Falta siguiente paso: {t_next}')
        next_acc=float(lookup.loc[t_next]['accel_m_s2'])
        if not math.isclose(next_acc,float(a.observed_a_next),abs_tol=1e-6,rel_tol=0):
            raise ValueError(f'Los dos observadores no coinciden: {t_next}')
        lid=str(vehicle['leader_id']) if pd.notna(vehicle['leader_id']) else ''
        lk=(lid,int(round(float(a.time_s)*1000)))
        v=float(vehicle['speed_m_s']);lspeed=None;closing=None;ttc=None;decel=None
        gap=float(vehicle['gap_m']) if pd.notna(vehicle['gap_m']) else None
        if lid and lk in lookup.index and gap is not None and gap>=0:
            lspeed=float(lookup.loc[lk]['speed_m_s'])
            closing=v-lspeed
            if closing>0 and gap>0:
                ttc=gap/closing;decel=closing**2/(2*gap)
        error=abs(float(a.guarded_a)-next_acc)
        records.append(dict(vehicle_id=str(a.vehicle_id),time_s=float(a.time_s),
                            target_time_s=float(a.target_time_s),speed_kmh=3.6*v,
                            leader_id=lid,leader_speed_kmh=None if lspeed is None else 3.6*lspeed,
                            gap_m=gap,closing_speed_m_s=closing,ttc_cv_s=ttc,
                            decel_relative_m_s2=decel,
                            proposed_a=float(a.proposed_a),commanded_a=float(a.guarded_a),
                            observed_a_next=next_acc,abs_error_m_s2=error,
                            error_gt_0_1=error>.1,ttc_lt3=(ttc is not None and ttc<3),
                            command_positive=float(a.guarded_a)>0,
                            guard_intervened=str(a.guard_intervened).lower()=='true'))
    return pd.DataFrame(records)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--h01',type=Path)
    p.add_argument('--nom',type=Path,required=True)
    p.add_argument('--hib',type=Path,required=True)
    p.add_argument('--vine-actions',type=Path,required=True)
    p.add_argument('--guardar',action='store_true')
    p.add_argument('--out',type=Path)
    args=p.parse_args(argv)
    root=args.root.resolve()
    parent,orig_script=import_parent(root)
    h01=parent.guarded_path(args.h01,root) if args.h01 else next((z for z in (
        root/'resultados'/'ntvc_vine_r_01_cohortes_movimiento_regenerado',
        root/'resultados'/'ntvc_vine_r_01_cohortes_movimiento') if (z/'manifest.json').is_file()),None)
    if h01 is None:raise FileNotFoundError('H01 congelado ausente')
    nom=parent.guarded_path(args.nom,root);hib=parent.guarded_path(args.hib,root)
    act=parent.guarded_path(args.vine_actions,root)
    if act!=(hib.parent/'hibrido_contextual'/'acciones_hito08.csv').resolve():
        raise ValueError('Las acciones deben pertenecer al mismo brazo híbrido que H11.2')
    if args.out and not args.guardar:p.error('--out requiere --guardar')
    provenance,_,_=parent.summarize(root,h01,nom,hib,act,verify_only=True)
    print('H11.3a Bandas v1.0 / procedencia:',
          provenance['nominal']['pareado']['status'],'/',
          provenance['hibrido']['pareado']['status'])
    print('H01 SHA verificado, 5 sesiones autorizadas, test reservado excluido; fuentes de solo lectura')
    if not args.guardar:
        print('PREFLIGHT OK. Añadir --guardar para comparar bandas y comandos; sin SUMO ni entrenamiento.')
        return
    real=assign_speed_bins(parent.load_h01(Path(h01)/'cohortes_muestras_verificadas.csv'))
    nom_x=parent.load_h11(nom,'nominal')
    hib_x=parent.label_actuation(parent.load_h11(hib,'hibrido_contextual'),parent.get_command_times(act))
    nom_x=enrich_nominal_cohorts(nom_x,hib_x)
    nom_x=assign_speed_bins(nom_x);hib_x=assign_speed_bins(hib_x)
    groups=cohorts_for_contrast(nom_x,hib_x)
    stats,dist=summary_bands(real,groups)
    paired=per_vehicle_paired(nom_x,hib_x)
    command=command_and_leader(act,hib)
    if len(command)!=100:raise ValueError(f'Se esperaban 100 comandos para el H11.2 congelado; se encontraron {len(command)}')
    print('Órdenes:',len(command),'errores >0,1:',int(command.error_gt_0_1.sum()),
          'TTC<3:',int(command.ttc_lt3.sum()),'órdenes positivas con TTC<3:',
          int((command.command_positive & command.ttc_lt3).sum()))
    print('\nCOMPARACION ACELERACION / JERK POR VELOCIDAD:')
    view=dist[dist.grupo.isin(['nominal_todos','hibrido_todos','nominal_vine_objetivo',
                              'hibrido_vine_objetivo','hibrido_muestras_comandadas'])]
    print(view[['grupo','banda_kmh','variable','n_ref','n_sim','wasserstein','ks','status']].to_string(index=False))
    out=args.out.resolve() if args.out else root/'resultados'/('h11_3a_bandas_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if not out.is_relative_to(root/'resultados') or out.exists():
        raise ValueError('Salida debe ser NUEVA bajo resultados/')
    out.mkdir(parents=True)
    generated={
        'estadisticos_bandas_h11_3a.csv':stats,
        'distancias_bandas_h11_3a.csv':dist,
        'comparacion_pareada_bandas_h11_3a.csv':paired,
        'auditoria_comandos_lider_h11_3a.csv':command}
    for fname,df in generated.items():df.to_csv(out/fname,index=False,float_format='%.12g')
    manifest=dict(version=VERSION,source_0='H11.3a original v100 verificado',
                  original_script_sha256=sha(orig_script),
                  own_script_sha256=sha(Path(__file__)),
                  integrity=provenance,source_h01=str(h01),source_nom=str(nom),source_hib=str(hib),
                  sources_sha={'h01_samples':sha(Path(h01)/'cohortes_muestras_verificadas.csv'),
                               'nom_trajectory':sha(nom/'trayectorias_h11.csv'),
                               'hib_trajectory':sha(hib/'trayectorias_h11.csv'),
                               'vine_actions':sha(act)},
                  thresholds={'speed_bins_kmh':list(BIN_LABELS),'minimum_samples_per_population':MIN_DIST_SAMPLES,
                              'paired_min_samples_per_arm_vehicle_bin':MIN_PAIRED_SAMPLES,
                              'zero_tolerances_m_s2':[0.05,0.10],
                              'ttc_threshold_s':3},
                  rows={'polidriving':len(real),'nominal':len(nom_x),'hibrido':len(hib_x),
                        'commands':len(command)},
                  warnings=['SÓLO DESCRIPTIVO; SIN REPRESENTATIVIDAD QUITO',
                            'Selección por velocidad observada a posteriori, no identificación causal',
                            'Wasserstein y KS marginales no validan las dependencias temporales ni el contexto',
                            'Distribución de dt POLIDriving irregular; jerk sensible al dt',
                            'Muestras dentro de vehículo/sesión no independientes',
                            'Referencias PoliDriving de solo cinco sesiones de desarrollo',
                            'Los ceros exactos dependen de precisión de sensor/adquisición',
                            'Sin reentrenamiento ni lectura de Richard ni actualización de scripts congelados'],
                  hashes_outputs={fname:sha(out/fname) for fname in generated})
    (out/'manifiesto_h11_3a_bandas.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    report=f'''# H11.3a — Contraste cinemático condicionado por velocidad

**Estado:** diagnóstico descriptivo. **NO** certifica conducción de Quito.

- PoliDriving: {len(real)} filas de cinco sesiones de desarrollo; Richard y Alonso reservado excluidos.
- SUMO nominal: {len(nom_x)} filas; híbrido: {len(hib_x)} filas.
- Comandos: {len(command)}; desviaciones mayores a 0,1 m/s²: {int(command.error_gt_0_1.sum())}.
- TTC constante <3s: {int(command.ttc_lt3.sum())}; órdenes positivas en ese contexto: {int((command.ttc_lt3 & command.command_positive).sum())}.

## Diseño

Velocidad posterior >5 km/h, estratos (5,20], (20,40], (40,60] y (60,∞).
Jerk requiere continuidad entre observaciones en marcha. Para cada banda se ofrecen
número de muestras y unidades, cuantiles, masas alrededor de cero (+/-0.05 y +/-0.10),
Wasserstein y KS cuando ambos dominios tienen al menos {MIN_DIST_SAMPLES} muestras.

Comparación pareada: los mismos vehículos nominal/híbrido dentro de una banda,
exigiendo por métrica >= {MIN_PAIRED_SAMPLES} muestras en ambos brazos. El delta
es media (híbrido–nominal) de la media por vehículo de |a| o |jerk|.
No presume emparejamiento causal de observaciones ni homogeneidad de tráfico.

La cohorte nominal es etiqueta contrafactual basada en asignación del híbrido;
NO implica H09/Vine activos nominalmente. En la submuestra de instantes comandados
hay selección por elegibilidad y presupuesto: distancia menor no acredita naturalismo.

### Interpretación obligatoria

Los cortes por velocidad igualan parcialmente el soporte pero no equilibran líderes,
semáforos, tráfico, vía, sensor ni muestreo temporal. Para jerk comparar además
medianas de dt por banda. Ceros de aceleración en PoliDriving pueden reflejar la
instrumentación y no una parada física. Las muestras vehículo-paso no son réplicas independientes.

No abrir Richard, reentrenar Vine ni modificar SUMO a partir de un solo piloto.
'''
    (out/'informe_h11_3a_bandas.md').write_text(report,encoding='utf-8')
    print('\nINFORME:',out)


if __name__=='__main__':main()
