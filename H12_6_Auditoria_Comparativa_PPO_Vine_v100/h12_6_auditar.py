#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.6 — auditoría offline de 60s nominal/probe vs Vine activo de H12.5.

No importa módulos de simulación, no abre SUMO ni modifica datos históricos.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import csv
import json
import math
from pathlib import Path
import statistics
import uuid


class AuditFailure(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditFailure(message)


def load(path):
    p = Path(path)
    require(p.is_file(), 'Archivo inexistente: '+str(p))
    with p.open('r', encoding='utf-8-sig') as f:
        return json.load(f)


def sha_check(pair_dir, nom, probe):
    pairfile=Path(pair_dir)/'pareado_h12_5.json'
    pair=load(pairfile)
    require(pair.get('status')=='PAREADO_NOMINAL_PROBE_OK', 'PAIR no certificado')
    require(nom['trace_sha256']==probe['trace_sha256']==pair['traffic_sha256'],
            'SHA nominal/probe/pareado distinto')
    require(nom['commands']==0 and probe['commands']==0,'Nominal/probe emitió comandos')
    require(nom['mode']=='nominal' and probe['mode']=='probe','Modos nominal/probe incorrectos')
    require(pair['decisions']==nom['n_decisions']==probe['n_decisions'], 'Decisiones de pair discrepantes')
    require(pair['microticks']==nom['n_microticks']==probe['n_microticks'], 'Microticks pair discrepantes')
    return pair


def stable_sources(r):
    return r.get('h10_source_sha256')


def fixed_identity(nom, probe, active, active_dir=None):
    for name,r in [('nominal',nom),('probe',probe),('active',active)]:
        require(r.get('result')=='SMOKE_OK',f'{name}: estado distinto de SMOKE_OK')
        require(r.get('model')=='ppo_ideal',f'{name}: modelo no es ppo_ideal')
        require(r.get('n_decisions')==12,f'{name}: no son 12 decisiones')
        require(r.get('n_microticks')==120,f'{name}: no son 120 microticks')
        require(len(r.get('microticks',[]))==120,f'{name}: telemetría incompleta')
        require(len(r.get('decisions',[]))==12,f'{name}: decisiones incompletas')
        require(abs(float(r.get('start_time_s',-1)))<1e-8, f'{name}: inicio distinto de 0s')
        require(abs(float(r.get('end_time_s',-1))-60.)<1e-8,f'{name}: final distinto de 60s')
        require(r['h10_reference_n']==300,f'{name}: cohorte de referencia no es 300')
        require(r['h10_reference_path']==nom['h10_reference_path'],f'{name}: referencia H08 distinta')
        require(r['checkpoint_sha256']==nom['checkpoint_sha256'],f'{name}: checkpoint distinto')
        require(stable_sources(r)==stable_sources(nom),f'{name}: fuentes H10 diferentes')
        inputs=r.get('inputs',{})
        base=nom['inputs']
        for key in ('cfg_original_sha256','net_sha256','routes_sha256'):
            require(inputs.get(key)==base.get(key),f'{name}: {key} distinto')
        # El sumocfg overlay puede variar por ruta absoluta de salida; no se exige su SHA.
        for i,row in enumerate(r['microticks']):
            require(int(row['tick'])==i,f'{name}: tick discontinuo en índice {i}')
            require(abs(float(row['time_s'])-.5*(i+1))<1e-6,
                    f'{name}: tiempo inesperado en tick {i}')
            require(int(row['collisions'])==0 and int(row['teleports_start'])==0,
                    f'{name}: colisiones o teleports detectados, tick {i}')
            require(int(row['n_active'])>=0 and int(row['n_halted'])>=0,
                    f'{name}: valores negativos')
        for i,row in enumerate(r['decisions']):
            require(int(row['i'])==i,f'{name}: decisión desordenada')
            require(abs(float(row['sim_time_s'])-5*(i+1))<1e-6,
                    f'{name}: tiempo decisión inválido')
            require(0<=int(row['action'])<4,f'{name}: acción fuera de rango')
        require(int(r.get('commands',-1))==(0 if name!='active' else 20),
                f'{name}: recuento de comandos no coincide con este piloto')
    require(active.get('mode')=='active','El escenario intervenido no es active')
    require(active.get('vine_assigned_n')==45,'La cohorte Vine activa no es 45')
    require(active.get('trace_sha256')!=nom.get('trace_sha256'),
            'No se puede acreditar diferencia cinemática entre activo y nominal')
    require(active.get('h09_selected_n')==0 and nom.get('h09_selected_n')==0,
            'Comparación no debe mezclar H09')
    require(nom.get('trace_sha256')==probe.get('trace_sha256'),
            'La invariancia nominal/probe falló')


def validate_vine(active, csv_path):
    info=active.get('extra',{}).get('vine')
    require(isinstance(info,dict),'Faltan metadatos Vine del activo')
    require(int(info.get('n_commands',-1))==20,'Contador Vine distinto de 20')
    require(int(info.get('n_commands_confirmed',-1))==20,'Comandos Vine no confirmados')
    require(int(info.get('remaining_pending',-1))==0,'Hay comandos pendientes')
    require(int(info.get('n_vehicles_commanded',-1))==6,'Vehículos con comando distintos de 6')
    require(not bool(info.get('safety_halt',True)),'Se activó safety halt')
    windows=info.get('commands_by_window',{})
    require(int(windows.get('0',0))==20,'Cuota ventana 0 no coincide con 20')
    require(len(active.get('command_records',[]))==20,'Puente no registra 20 comandos')
    require(Path(csv_path).is_file(),'Falta CSV acciones H08b')
    with Path(csv_path).open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        require(reader.fieldnames is not None,'Acciones CSV vacío')
        cols=('command_issued','matched_t_plus_dt','guarded_a','observed_a_next','vehicle_id')
        require(all(c in reader.fieldnames for c in cols),'Faltan columnas de acciones H08b')
        issued=[r for r in reader if str(r.get('command_issued','')).lower() in ('true','1')]
    require(len(issued)==20,'CSV no contiene exactamente 20 comandos')
    require(all(str(r['matched_t_plus_dt']).lower() in ('true','1') for r in issued),
            'CSV tiene comando sin observación t+dt')
    differences=[]
    for r in issued:
        g=float(r['guarded_a']);a=float(r['observed_a_next'])
        require(math.isfinite(g) and math.isfinite(a),'Aceleraciones no finitas')
        differences.append(abs(g-a))
    return {'commands':20,'confirmed':20,'vehicles':6,
            'max_abs_acceleration_error_m_s2':max(differences),
            'mean_abs_acceleration_error_m_s2':statistics.mean(differences),
            'eligible_observations':int(info.get('n_safety_eligible',0)),
            'viable_observations':int(info.get('n_action_viable',0)),
            'window_0_commands':int(windows['0'])}


def safe_mean(values):
    if not values: return None
    values=[float(v) for v in values]
    require(all(math.isfinite(v) for v in values),'Métrica RL no finita')
    return statistics.mean(values)


def metrics(r):
    rows=r['microticks'];decisions=r['decisions'];dt=.5
    speeds=[float(row['mean_speed_kmh']) for row in rows]
    active_counts=[int(row['n_active']) for row in rows]
    require(all(math.isfinite(v) for v in speeds),'Velocidad no finita')
    vs=sum(v*n for v,n in zip(speeds,active_counts))
    n_total=sum(active_counts)
    return {
        'mean_speed_time_kmh':statistics.mean(speeds),
        'mean_speed_vehicle_weighted_kmh':vs/n_total if n_total else None,
        'mean_active_vehicles':statistics.mean(active_counts),
        'halted_vehicle_seconds':sum(int(row['n_halted'])*dt for row in rows),
        'mean_halted_vehicles':statistics.mean(int(row['n_halted']) for row in rows),
        'departures_total':sum(int(row['departures']) for row in rows),
        'arrivals_total':sum(int(row['arrivals']) for row in rows),
        'collisions_total':sum(int(row['collisions']) for row in rows),
        'teleports_start_total':sum(int(row['teleports_start']) for row in rows),
        'mean_queue_decisions':safe_mean([row['queue'] for row in decisions]),
        'mean_delay_proxy_decisions':safe_mean([row['delay_proxy'] for row in decisions]),
        'mean_gini_decisions':safe_mean([row['gini'] for row in decisions]),
        'reward_sum':sum(float(row['reward']) for row in decisions),
        'actions':[int(row['action']) for row in decisions],
    }


def compare(nom,probe,active,pair_dir,active_dir):
    sha_check(pair_dir,nom,probe)
    fixed_identity(nom,probe,active)
    evidence=validate_vine(active,Path(active_dir)/'acciones_h08b.csv')
    m={name:metrics(r) for name,r in [('nominal',nom),('probe',probe),('active',active)]}
    require(m['nominal']==m['probe'],'Métricas nominal/probe diferentes, pese al mismo SHA de tráfico')
    diffs={}
    for key,value in m['nominal'].items():
        if key=='actions':continue
        a=m['active'][key]
        diffs[key]=a-value if a is not None and value is not None else None
    first_diff=next((int(a['tick']) for a,b in zip(nom['microticks'],active['microticks'])
        if a['vehicle_kinematics_sha256']!=b['vehicle_kinematics_sha256']),None)
    action_diffs=[i for i,(a,b) in enumerate(zip(m['nominal']['actions'],m['active']['actions'])) if a!=b]
    return {'status':'H12_6_AUDITORIA_OK','comparison_type':'single_seed_paired_pilot_not_resilience',
            'model':'ppo_ideal','seed':101,'horizon_seconds':60,'n_microticks':120,
            'n_decisions':12,'baseline_trace_sha256':nom['trace_sha256'],
            'active_trace_sha256':active['trace_sha256'],
            'checkpoint_sha256':nom['checkpoint_sha256'],
            'first_kinematics_difference_tick':first_diff,
            'first_kinematics_difference_time_s':float(nom['microticks'][first_diff]['time_s']) if first_diff is not None else None,
            'n_different_signal_actions':len(action_diffs),
            'different_signal_action_indices':action_diffs,
            'vine_evidence':evidence,'metrics':m,'active_minus_nominal':diffs,
            'limitations':[
                'Una semilla/episodio corto, sin inferencia estadística ni evidencia de resiliencia',
                'Métricas SUMO agregadas globales; PPO controla B1 solamente',
                'Queue/delay son indicadores internos TSCEnv, no demora individual medida por tripinfo',
                'Promedios de velocidad representan medias temporales o ponderación por vehículos presentes, no viajes completados',
                'Los comandos Vine usan un límite de 20 por ventana de 60 s',
                'Comparación válida solo con idénticos checkpoint, red, rutas, fuentes y horizonte',
                'No se han homologado tiempos amarillos/interverdes ni protocolos multiagente SOTA',
                'No se ha calibrado estadísticamente el traslado temporal POLIDriving-SUMO',
            ]}


def fmt(x):
    if x is None: return 'N/D'
    if isinstance(x,float):return f'{x:.6f}'
    return str(x)


def markdown(report):
    metrics_names={
       'mean_speed_time_kmh':'Velocidad media temporal (km/h)',
       'mean_speed_vehicle_weighted_kmh':'Velocidad ponderada por vehículos activos (km/h)',
       'mean_active_vehicles':'Vehículos activos promedio',
       'halted_vehicle_seconds':'Vehículo-segundos detenidos',
       'mean_halted_vehicles':'Detenidos promedio',
       'departures_total':'Salidas durante el piloto',
       'arrivals_total':'Llegadas durante el piloto',
       'collisions_total':'Colisiones reportadas',
       'teleports_start_total':'Inicios de teleport',
       'mean_queue_decisions':'Cola proxy TSCEnv (media por decisión)',
       'mean_delay_proxy_decisions':'Demora proxy TSCEnv (media por decisión)',
       'mean_gini_decisions':'Gini TSCEnv (media por decisión)',
       'reward_sum':'Recompensa acumulada PPO',
    }
    lines=['# H12.6 — Auditoría offline PPO ideal, nominal/probe/Vine activo',
       '',f"**Estado:** {report['status']}. **Seed:** 101. **Horizonte:** 60 s, 120 microticks y 12 decisiones PPO.",
       '',f"**Vine:** {report['vine_evidence']['commands']} comandos, {report['vine_evidence']['confirmed']} confirmados, "
       f"{report['vine_evidence']['vehicles']} vehículos intervenidos.",
       f"**Error máximo de aceleración:** {report['vine_evidence']['max_abs_acceleration_error_m_s2']:.3e} m/s².",
       f"**Primera diferencia cinemática:** microtick {report['first_kinematics_difference_tick']}, "
       f"t={report['first_kinematics_difference_time_s']} s.",
       f"**Diferencias de decisiones semafóricas:** {report['n_different_signal_actions']} de 12, "
       f"índices {report['different_signal_action_indices']}.",
       '', '| Indicador | Nominal | Probe | Vine activo | Activo − nominal |',
       '|---|---:|---:|---:|---:|']
    for key,label in metrics_names.items():
        lines.append('| '+label+' | '+' | '.join(fmt(report['metrics'][scenario][key])
            for scenario in ('nominal','probe','active'))+' | '+fmt(report['active_minus_nominal'][key])+' |')
    lines += ['', '## Advertencias metodológicas']
    lines += ['- '+s for s in report['limitations']]
    lines += ['', 'El informe NO permite afirmar que PPO mejoró o empeoró causalmente, ni que las perturbaciones sean representativas del tráfico de Quito.']
    return '\n'.join(lines)+'\n'


def parse(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair-dir',type=Path,required=True)
    p.add_argument('--active-dir',type=Path,required=True)
    p.add_argument('--results-root',type=Path,default=Path('resultados'))
    return p.parse_args(argv)


def main(argv=None):
    args=parse(argv)
    nom=load(args.pair_dir/'nominal/piloto_h12_5.json')
    probe=load(args.pair_dir/'probe/piloto_h12_5.json')
    active=load(args.active_dir/'active/piloto_h12_5.json')
    report=compare(nom,probe,active,args.pair_dir,args.active_dir/'active')
    root=args.results_root.resolve()
    root.mkdir(parents=True,exist_ok=True)
    out=root/('h12_6_auditoria_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(exist_ok=False)
    (out/'auditoria_h12_6.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (out/'dictamen_h12_6.md').write_text(markdown(report),encoding='utf-8')
    print('H12_6_AUDITORIA_OK',flush=True)
    print('COMANDOS',report['vine_evidence']['commands'],'CONFIRMADOS',report['vine_evidence']['confirmed'],
          'ERROR_MAX_A',f"{report['vine_evidence']['max_abs_acceleration_error_m_s2']:.3e}")
    print('DIF_CINEMATICA_T',report['first_kinematics_difference_time_s'],'DIF_ACCIONES_TLS',report['n_different_signal_actions'])
    print('INFORME',out)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
