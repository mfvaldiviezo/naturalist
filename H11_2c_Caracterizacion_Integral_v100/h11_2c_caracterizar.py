#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H11.2c: análisis OFFLINE, solo lectura, H11.2/H10 nominal vs híbrido.

No ejecuta SUMO, no altera modelos, no infiere causalidad ni calibración de Quito.
Las métricas son proxies, y las muestras vehículo-paso NO son independientes.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION='H11.2c-caracterizacion-v1.0.0'
FILES=('trayectorias_h11.csv','eventos_semaforicos_h11.csv','eventos_interseccion_h11.csv','seguridad_h11.csv')
TRAJ_REQUIRED={'time_s','dt_s','vehicle_id','cohort','lane_id','internal_lane','speed_m_s',
               'posted_lane_limit_m_s','accel_m_s2','jerk_observed_m_s3','leader_id',
               'gap_m','headway_s','ttc_s'}
INTER_REQUIRED={'vehicle_id','cohort','start_s','end_s','duration_s','event_kind','gridlock_confirmed','censored_end'}
SAFE_REQUIRED={'time_s','colliding_vehicles_count','teleport_start_count','emergency_stop_count'}
COHORTS=('both','h09_only','vine_only','neither','unclassified')
METRICS=('exceso_limite_bruto','exceso_limite_margen','exceso_10pct',
         'headway_lt_1s','ttc_lt_2s','frenada_fuerte','frenada_extrema','jerk_alto')
METRIC_HEADERS=('velocidad','headway','ttc','aceleracion','jerk')
EP_FIELDS=['escenario','vehicle_id','cohorte_actual','cohorte_objetivo','indicador','inicio_s','fin_ultima_muestra_s',
    'duracion_observada_s','muestras','censura_izquierda','censura_derecha','valor_extremo',
    'comandos_vine_en_ventana','nota']
VEH_FIELDS=['escenario','vehicle_id','cohorte_actual','cohorte_objetivo','muestras','segundos_vehiculo',
    'velocidad_media_kmh','velocidad_p95_kmh','aceleracion_min_m_s2','jerk_abs_p95_m_s3','comandos_vine_total']
for _m in METRICS:
    VEH_FIELDS += [f'{_m}_validos',f'{_m}_muestras',f'{_m}_tasa',f'{_m}_episodios',f'{_m}_segundos',f'{_m}_duracion_max_s']
GROUP_FIELDS=['escenario','tipo_agrupacion','cohorte','vehiculos','muestras','segundos_vehiculo',
    'velocidad_media_kmh_muestral','velocidad_p95_kmh_muestral','velocidad_media_por_vehiculo_kmh',
    'aceleracion_min_m_s2','jerk_abs_p95_m_s3']
for _m in METRICS:
    GROUP_FIELDS += [f'{_m}_validos',f'{_m}_muestras',f'{_m}_tasa',
                     f'{_m}_vehiculos_afectados',f'{_m}_episodios',f'{_m}_segundos',f'{_m}_duracion_p95_s']
PAIR_FIELDS=['vehicle_id','cohorte_objetivo','nominal_presente','hibrido_presente',
    'muestras_nominal','muestras_hibrido','segundos_nominal','segundos_hibrido',
    'velocidad_media_kmh_nominal','velocidad_media_kmh_hibrido','delta_velocidad_media_kmh']
for _m in METRICS:
    PAIR_FIELDS += [f'{_m}_tasa_nominal',f'{_m}_tasa_hibrido',f'{_m}_delta_tasa',
                    f'{_m}_episodios_nominal',f'{_m}_episodios_hibrido']
INTER_FIELDS=['escenario','vehicle_id','cohorte_actual','cohorte_objetivo',
    'inicio_s','fin_s','duracion_s','censurado','event_kind','gridlock_confirmado','calidad_evidencia','nota']


def number(v):
    if v is None or str(v).strip()=='':return None
    try:
        f=float(v)
        return f if math.isfinite(f) else None
    except (TypeError,ValueError):return None


def quantile(values, q):
    v=sorted(x for x in values if x is not None and math.isfinite(x))
    if not v:return None
    a=(len(v)-1)*q;l=math.floor(a);h=math.ceil(a)
    return v[l]*(h-a)+v[h]*(a-l) if l!=h else v[l]


def mean(values):
    v=[x for x in values if x is not None]
    return sum(v)/len(v) if v else None


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def read_csv(path, required=()):
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        cols=set(reader.fieldnames or [])
        if not set(required).issubset(cols):
            raise ValueError(f'{path}: faltan columnas: {sorted(set(required)-cols)}')
        return list(reader)


def verify_source(folder, condition, expected_steps=600):
    folder=Path(folder).resolve()
    manifest=folder/'manifest_h11_2.json'
    data=json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('condition')!=condition:raise ValueError(f'Condición diferente: {data.get("condition")}')
    if data.get('empirically_calibrated_quito') is not False:raise ValueError('Falta no-calibración Quito explícita')
    if int(data.get('observed_steps',-1))!=expected_steps:raise ValueError('Número de pasos incorrecto')
    digests=data.get('outputs_sha256') or {}
    if not set(FILES).issubset(digests):raise ValueError('Manifiesto incompleto')
    for name,digest in digests.items():
        if not re.fullmatch(r'[a-fA-F0-9]{64}',str(digest)):raise ValueError('SHA inválido')
        p=(folder/name).resolve()
        if folder not in p.parents or sha(p)!=digest.lower():raise ValueError('INTEGRIDAD FALLIDA: '+str(p))
    return {'folder':str(folder),'condition':condition,'observed_steps':expected_steps,
            'sha_manifest':sha(manifest),'sha_outputs':digests,'seed':data.get('seed'),
            'time_step_source':data.get('version'),'errors':data.get('telemetry_failures_or_missing',{})}


def verify_paired(folder, mode):
    folder=Path(folder).resolve()
    if folder.name!='telemetria' or folder.parent.name!='observado':
        raise ValueError('Se exige la ruta observado/telemetria')
    base=folder.parent.parent
    mf=base/'comparacion_h11_2.json'
    data=json.loads(mf.read_text(encoding='utf-8'))
    if data.get('mode')!=mode or data.get('status')!='INVARIANZA_BYTE_A_BYTE_VERIFICADA':
        raise ValueError('Invariancia pareada no acreditada: '+str(mf))
    files=data.get('comparison',{})
    if not files or 'trafico_h09.csv' not in files:raise ValueError('Comparación original vacía/incompleta')
    for filename,meta in files.items():
        if '/' in filename or '\\' in filename or filename.startswith('.'):
            raise ValueError('Nombre no seguro en manifiesto pareado')
        if not meta.get('identical') or meta.get('sha_control')!=meta.get('sha_observado'):
            raise ValueError('Comparación original no idéntica: '+filename)
        for side,key in (('control','sha_control'),('observado','sha_observado')):
            p=base/side/mode/filename
            if sha(p)!=meta[key]:raise ValueError('Archivo pareado alterado: '+str(p))
    return {'status':'INVARIANZA_PAREADA_REVERIFICADA','sha_comparacion':sha(mf),
            'archivos_revalidados':len(files)*2}


def indicator_flags(r, *, tolerance_kmh=3.6, extreme_brake=-7, strong_brake=-4.5, jerk_limit=8):
    v=number(r.get('speed_m_s'))
    limit=number(r.get('posted_lane_limit_m_s'))
    a=number(r.get('accel_m_s2'))
    j=number(r.get('jerk_observed_m_s3'))
    gap=number(r.get('gap_m'))
    h=number(r.get('headway_s'))
    ttc=number(r.get('ttc_s'))
    have_leader=bool(str(r.get('leader_id') or '').strip())
    posted=v is not None and limit is not None and limit>0 and v>=0
    valid_head=have_leader and v is not None and v>0 and gap is not None and gap>=0 and h is not None and h>=0
    valid_ttc=have_leader and v is not None and v>0 and gap is not None and gap>=0 and ttc is not None and ttc>=0
    return {
        'exceso_limite_bruto': (v>limit+1e-6 if posted else None),
        'exceso_limite_margen': (v>limit+tolerance_kmh/3.6 if posted else None),
        'exceso_10pct': (v>limit*1.10 if posted else None),
        'headway_lt_1s': (h<1 if valid_head else None),
        'ttc_lt_2s': (ttc<2 if valid_ttc else None),
        'frenada_fuerte': (a<=strong_brake if a is not None else None),
        'frenada_extrema': (a<=extreme_brake if a is not None else None),
        'jerk_alto': (abs(j)>=jerk_limit if j is not None else None)
    }


def build_contiguous_episodes(vehicle_rows, metric, actions_times=()):
    """Un episodio = muestras positivas consecutivas sin salto > paso esperado.
    Cuenta cada muestra válida como intervalo observado dt; no infiere duración entre huecos.
    """
    result=[]; open_run=[]
    def flush(next_is_end=False):
        nonlocal open_run
        if not open_run:return
        first=open_run[0];last=open_run[-1]
        values=[]
        for rec in open_run:
            if metric.startswith('frenada'):
                v=rec['a']
            elif metric=='jerk_alto':
                v=abs(rec['j']) if rec['j'] is not None else None
            elif metric=='headway_lt_1s':
                v=rec.get('headway')
            elif metric=='ttc_lt_2s':
                v=rec.get('ttc')
            elif metric=='exceso_10pct':
                v=rec.get('v')/rec['limit'] if rec.get('v') is not None and rec.get('limit') and rec['limit']>0 else None
            else:
                v=rec.get('v')-rec['limit'] if rec.get('v') is not None and rec.get('limit') is not None else None
            if v is not None:values.append(v)
        low=metric.startswith('frenada') or metric.startswith(('headway','ttc'))
        extreme=(min(values) if low else max(values)) if values else None
        end=last['t']+last['dt']
        result.append({'indicador':metric,'inicio_s':first['t'],'fin_ultima_muestra_s':last['t'],
            'duracion_observada_s':sum(x['dt'] for x in open_run),'muestras':len(open_run),
            'censura_izquierda':first['_idx']==0,'censura_derecha':next_is_end,
            'valor_extremo':extreme,
            'comandos_vine_en_ventana':sum(first['t']<=t<end for t in actions_times),
            'nota':'indicador proxy; duracion=numero de muestras x dt, no causa probada'})
        open_run=[]
    for i,r in enumerate(vehicle_rows):
        value=r['flags'][metric]
        continuous=(open_run and abs(r['t']-open_run[-1]['t']-r['dt'])<0.0001)
        if open_run and (not continuous or value is not True):flush(False)
        if value is True:
            open_run.append(dict(r,_idx=i))
    flush(True)
    return result


def load_actions(path):
    if path is None:return {}
    data=read_csv(path,{'vehicle_id','time_s','command_issued'})
    actions=defaultdict(list)
    for r in data:
        t=number(r['time_s'])
        if t is not None and r['command_issued'].strip().lower()=='true':actions[r['vehicle_id']].append(t)
    for v in actions:actions[v].sort()
    return actions


def read_trajectories(folder, scenario, target_cohorts, settings, actions):
    data=read_csv(Path(folder)/'trayectorias_h11.csv',TRAJ_REQUIRED)
    byvid=defaultdict(list); check=set(); counts=Counter(); times=set()
    for r in data:
        vid=r['vehicle_id'].strip()
        if not vid:raise ValueError('Fila sin ID de vehículo')
        t=number(r['time_s']);dt=number(r['dt_s'])
        if t is None or dt is None or dt<=0 or abs(dt-settings['dt'])>1e-6:
            raise ValueError(f'Tiempo o dt inválido para {vid}')
        key=(vid,t)
        if key in check:raise ValueError(f'Fila vehículo-tiempo duplicada: {key}')
        check.add(key);times.add(t)
        cohort=r['cohort'].strip()
        if cohort not in COHORTS:raise ValueError(f'Cohorte desconocida: {cohort}')
        if scenario=='nominal' and cohort!='unclassified':raise ValueError('Nominal debe carecer de intervenciones/cohortes activas')
        if scenario=='hibrido_contextual' and cohort=='unclassified':raise ValueError('Híbrido sin cohorte trazable')
        flags=indicator_flags(r, tolerance_kmh=settings['speed_margin_kmh'],
                strong_brake=settings['strong_brake'],extreme_brake=settings['extreme_brake'],
                jerk_limit=settings['jerk_threshold'])
        speed_m_s=number(r['speed_m_s'])
        if speed_m_s is not None and speed_m_s<-1e-6:raise ValueError(f'Velocidad negativa {vid}: {speed_m_s}')
        rec={'t':t,'dt':dt,'v':speed_m_s,'a':number(r['accel_m_s2']),
             'j':number(r['jerk_observed_m_s3']),'headway':number(r['headway_s']),
             'ttc':number(r['ttc_s']),'limit':number(r['posted_lane_limit_m_s']),
             'internal':r['internal_lane'].strip().lower()=='true','cohort':cohort,
             'flags':flags,'lane_id':r['lane_id']}
        byvid[vid].append(rec);counts['rows']+=1
    if len(times)!=settings['steps']:raise ValueError(f'Pasos observados {len(times)} != {settings["steps"]}')
    ordered_times=sorted(times)
    if any(abs((b-a)-settings['dt'])>1e-5 for a,b in zip(ordered_times,ordered_times[1:])):
        raise ValueError('Pasos globales no consecutivos con dt esperado')
    processed=[];episodes=[];profiles={}
    for vid,rows in byvid.items():
        rows.sort(key=lambda x:x['t'])
        if len({r['cohort'] for r in rows})!=1:raise ValueError(f'Cohorte cambiante para {vid}')
        cohort=rows[0]['cohort'];target=target_cohorts.get(vid,'unclassified_target')
        metric_eps={m:build_contiguous_episodes(rows,m,actions.get(vid,())) for m in METRICS}
        event_counts={m:len(metric_eps[m]) for m in METRICS}
        velocity=[r['v']*3.6 for r in rows if r['v'] is not None]
        acc=[r['a'] for r in rows if r['a'] is not None]
        jerk=[abs(r['j']) for r in rows if r['j'] is not None]
        record={'escenario':scenario,'vehicle_id':vid,'cohorte_actual':cohort,
            'cohorte_objetivo':target,'muestras':len(rows),'segundos_vehiculo':sum(r['dt'] for r in rows),
            'velocidad_media_kmh':mean(velocity),'velocidad_p95_kmh':quantile(velocity,.95),
            'aceleracion_min_m_s2':min(acc) if acc else None,'jerk_abs_p95_m_s3':quantile(jerk,.95),
            'comandos_vine_total':len(actions.get(vid,())) if scenario=='hibrido_contextual' else 0}
        for m in METRICS:
            vals=[r['flags'][m] for r in rows]
            n=sum(x is not None for x in vals);hits=sum(x is True for x in vals)
            eps=metric_eps[m]
            record.update({f'{m}_validos':n,f'{m}_muestras':hits,
                f'{m}_tasa':hits/n if n else None,f'{m}_episodios':len(eps),
                f'{m}_segundos':sum(e['duracion_observada_s'] for e in eps),
                f'{m}_duracion_max_s':max((e['duracion_observada_s'] for e in eps),default=0)})
            for ep in eps:
                episodes.append({'escenario':scenario,'vehicle_id':vid,'cohorte_actual':cohort,
                                 'cohorte_objetivo':target,**ep})
        profiles[vid]=record
        processed.extend([{'escenario':scenario,'vid':vid,'cohort':cohort,'target':target,**r} for r in rows])
    if scenario=='hibrido_contextual':
        for vid,rows in byvid.items():
            if target_cohorts.get(vid)!=rows[0]['cohort']:
                raise ValueError(f'Cohorte H11.2 no coincide con cohorte híbrida objetivo: {vid}')
    return processed,profiles,episodes


def target_cohorts_from_hybrid(folder):
    rows=read_csv(Path(folder)/'trayectorias_h11.csv',{'vehicle_id','cohort'})
    mapping={}
    for r in rows:
        vid=r['vehicle_id'];cohort=r['cohort']
        if cohort not in COHORTS or cohort=='unclassified':raise ValueError('Cohorte híbrida no válida')
        if vid in mapping and mapping[vid]!=cohort:raise ValueError(f'Cohorte híbrida inconsistente: {vid}')
        mapping[vid]=cohort
    return mapping


def summarize_group(rows, epis, scenario, group_type, group):
    records=[r for r in rows if r['escenario']==scenario and (group=='todos' or
        r['cohort' if group_type=='actual' else 'target']==group)]
    eprows=[e for e in epis if e['escenario']==scenario and (group=='todos' or
        e['cohorte_actual' if group_type=='actual' else 'cohorte_objetivo']==group)]
    vs=set(r['vid'] for r in records)
    speeds=[r['v']*3.6 for r in records if r['v'] is not None]
    acc=[r['a'] for r in records if r['a'] is not None]
    jerk=[abs(r['j']) for r in records if r['j'] is not None]
    byvid=defaultdict(list)
    for r in records:
        if r['v'] is not None:byvid[r['vid']].append(r['v']*3.6)
    row={'escenario':scenario,'tipo_agrupacion':group_type,'cohorte':group,
         'vehiculos':len(vs),'muestras':len(records),'segundos_vehiculo':sum(r['dt'] for r in records),
         'velocidad_media_kmh_muestral':mean(speeds),'velocidad_p95_kmh_muestral':quantile(speeds,.95),
         'velocidad_media_por_vehiculo_kmh':mean([mean(r) for r in byvid.values()]),
         'aceleracion_min_m_s2':min(acc) if acc else None,'jerk_abs_p95_m_s3':quantile(jerk,.95)}
    for m in METRICS:
        checks=[r['flags'][m] for r in records]
        n=sum(x is not None for x in checks);hits=sum(x is True for x in checks)
        ese=[e for e in eprows if e['indicador']==m]
        row.update({f'{m}_validos':n,f'{m}_muestras':hits,f'{m}_tasa':hits/n if n else None,
            f'{m}_vehiculos_afectados':len({e['vehicle_id'] for e in ese}),
            f'{m}_episodios':len(ese),f'{m}_segundos':sum(e['duracion_observada_s'] for e in ese),
            f'{m}_duracion_p95_s':quantile([e['duracion_observada_s'] for e in ese],.95)})
    return row


def make_groups(data,episodes):
    groups=[]
    for scenario in ('nominal','hibrido_contextual'):
        groups.append(summarize_group(data,episodes,scenario,'actual','todos'))
        if scenario=='hibrido_contextual':
            for cohort in ('both','h09_only','vine_only','neither'):
                groups.append(summarize_group(data,episodes,scenario,'actual',cohort))
        # Cohorte objetivo: nominal hereda la etiqueta de asignación en el híbrido, sin intervención
        for cohort in ('both','h09_only','vine_only','neither','unclassified_target'):
            subset=[r for r in data if r['escenario']==scenario and r['target']==cohort]
            if subset:groups.append(summarize_group(data,episodes,scenario,'objetivo_contrafactual',cohort))
    return groups



def road_context(data):
    result=[]
    for scenario in ('nominal','hibrido_contextual'):
        for internal in (False,True):
            rows=[r for r in data if r['escenario']==scenario and r['internal']==internal]
            row={'escenario':scenario,'tipo_carril':'interno' if internal else 'externo',
                 'muestras':len(rows),'vehiculos':len({r['vid'] for r in rows}),
                 'segundos_vehiculo':sum(r['dt'] for r in rows),
                 'velocidad_media_kmh':mean([r['v']*3.6 for r in rows if r['v'] is not None])}
            for metric in METRICS:
                valid=sum(r['flags'][metric] is not None for r in rows)
                hit=sum(r['flags'][metric] is True for r in rows)
                row[metric+'_validos']=valid;row[metric+'_muestras']=hit
                row[metric+'_tasa']=hit/valid if valid else None
            result.append(row)
    return result

def make_pairs(nom,hyb):
    rows=[]
    for vid in sorted(set(nom)|set(hyb)):
        a=nom.get(vid);b=hyb.get(vid)
        t=(b or a)['cohorte_objetivo']
        row={'vehicle_id':vid,'cohorte_objetivo':t,'nominal_presente':bool(a),'hibrido_presente':bool(b),
             'muestras_nominal':a['muestras'] if a else 0,'muestras_hibrido':b['muestras'] if b else 0,
             'segundos_nominal':a['segundos_vehiculo'] if a else 0,
             'segundos_hibrido':b['segundos_vehiculo'] if b else 0,
             'velocidad_media_kmh_nominal':a.get('velocidad_media_kmh') if a else None,
             'velocidad_media_kmh_hibrido':b.get('velocidad_media_kmh') if b else None}
        z=row['velocidad_media_kmh_nominal'];w=row['velocidad_media_kmh_hibrido']
        row['delta_velocidad_media_kmh']=w-z if z is not None and w is not None else None
        for m in METRICS:
            x=a.get(m+'_tasa') if a else None;y=b.get(m+'_tasa') if b else None
            row.update({m+'_tasa_nominal':x,m+'_tasa_hibrido':y,
                        m+'_delta_tasa':y-x if x is not None and y is not None else None,
                        m+'_episodios_nominal':a[m+'_episodios'] if a else None,
                        m+'_episodios_hibrido':b[m+'_episodios'] if b else None})
        rows.append(row)
    return rows


def make_matched_summary(pairs):
    result=[]
    for cohort in ('todos','both','h09_only','vine_only','neither'):
        g=[r for r in pairs if r['nominal_presente'] and r['hibrido_presente'] and
           (cohort=='todos' or r['cohorte_objetivo']==cohort)]
        out={'cohorte_objetivo':cohort,'vehiculos_pareados':len(g),'nota':'promedio de deltas por vehiculo; no inferencia causal'}
        out['delta_velocidad_media_kmh_promedio_vehiculos']=mean([r['delta_velocidad_media_kmh'] for r in g])
        for m in METRICS:out[f'{m}_delta_tasa_promedio_vehiculos']=mean([r[f'{m}_delta_tasa'] for r in g])
        result.append(out)
    return result


def summarize_intersections(folder,scenario,targets):
    rows=read_csv(Path(folder)/'eventos_interseccion_h11.csv',INTER_REQUIRED)
    result=[]
    for r in rows:
        if str(r['gridlock_confirmed']).strip().lower()=='true':
            raise ValueError('Instrumento H11.2 no puede acreditar gridlock como confirmado')
        duration=number(r['duration_s'])
        if duration is None or duration<0:raise ValueError('Duración de detención inválida')
        result.append({'escenario':scenario,'vehicle_id':r['vehicle_id'],
            'cohorte_actual':r['cohort'],'cohorte_objetivo':targets.get(r['vehicle_id'],'unclassified_target'),
            'inicio_s':r['start_s'],'fin_s':r['end_s'],'duracion_s':duration,
            'censurado':r['censored_end'],'event_kind':r['event_kind'],
            'gridlock_confirmado':False,'calidad_evidencia':r.get('evidence_quality',''),
            'nota':'detención interna candidata; NO demuestra bloqueo de flujos transversales'})
    return result


def summarize_safety(folder,scenario,trajectories):
    rows=read_csv(Path(folder)/'seguridad_h11.csv',SAFE_REQUIRED)
    counts={k:[] for k in ('colliding_vehicles_count','teleport_start_count','emergency_stop_count')}
    for r in rows:
        for k in counts:counts[k].append(number(r[k]))
    result={'escenario':scenario,'filas_seguridad':len(rows),
            'nota':'emergency_stop_count TraCI no equivale a advertencias de emergency braking SUMO'}
    for k,vals in counts.items():
        valid=[v for v in vals if v is not None]
        result[k+'_observaciones_validas']=len(valid)
        result[k+'_suma_registros']=sum(valid) if len(valid)==len(rows) else None
    result['muestras_frenada_extrema_por_aceleracion']=sum(r['flags']['frenada_extrema'] is True for r in trajectories)
    return result


def write_csv(path,fields,rows):
    with Path(path).open('x',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise');w.writeheader()
        for r in rows:w.writerow({k:r.get(k) for k in fields})


def report(summary,groups,matched,safety,intersections):
    ng=next(g for g in groups if g['escenario']=='nominal' and g['cohorte']=='todos')
    hg=next(g for g in groups if g['escenario']=='hibrido_contextual' and g['cohorte']=='todos')
    fmt=lambda x: 'N/D' if x is None else f'{x:.4f}'
    lines=['# H11.2c — Caracterización integral del comportamiento',
        '', '**Naturaleza: AUDITORÍA DESCRIPTIVA SIN CALIBRACIÓN QUITO Y SIN ATRIBUCIÓN CAUSAL.**','',
        '## Procedencia e integridad',
        f'- Nominal: `{summary["fuentes"]["nominal"]}`',
        f'- Híbrido: `{summary["fuentes"]["hibrido_contextual"]}`',
        '- Se verificaron SHA-256 de manifiestos/archivos y la invariancia pareada original cuando se exige `--require-paired`.',
        f'- Parámetros: margen velocidad {summary["parametros"]["speed_margin_kmh"]} km/h; '
        f'frenada fuerte <= {summary["parametros"]["strong_brake"]} m/s²; '
        f'frenada extrema <= {summary["parametros"]["extreme_brake"]} m/s²; '
        f'|jerk| >= {summary["parametros"]["jerk_threshold"]} m/s³.',
        '', '## Indicadores por muestra válida (NO por conductor único)', '',
        '| Indicador | Nominal | Híbrido | Denominador |','|---|---:|---:|---|']
    names={'exceso_limite_bruto':'Velocidad > límite carril (mínimo numérico)',
        'exceso_limite_margen':'Velocidad > límite + margen',
        'exceso_10pct':'Velocidad > 1,1 × límite',
        'headway_lt_1s':'Headway < 1 s', 'ttc_lt_2s':'TTC finito < 2 s',
        'frenada_fuerte':'Desaceleración fuerte', 'frenada_extrema':'Desaceleración extrema',
        'jerk_alto':'|Jerk| alto'}
    for m in METRICS:
        lines.append(f'| {names[m]} | {ng[m+"_muestras"]}/{ng[m+"_validos"]} ({fmt(ng[m+"_tasa"])}) | '
                     f'{hg[m+"_muestras"]}/{hg[m+"_validos"]} ({fmt(hg[m+"_tasa"])}) | '
                     + ('Oportunidades con líder y condición definida' if m.startswith(('headway','ttc')) else
                        'Velocidad y límite disponibles' if m.startswith('exceso') else
                        'Aceleración disponible' if m.startswith('frenada') else 'Jerk disponible')+' |')
    lines+=['', '## Episodios continuos y conductores únicos', '',
        '| Indicador | Episodios nominal | Episodios híbrido | Vehículos nominal | Vehículos híbrido |',
        '|---|---:|---:|---:|---:|']
    for m in METRICS:lines.append(f'| {names[m]} | {ng[m+"_episodios"]} | {hg[m+"_episodios"]} | '
                                  f'{ng[m+"_vehiculos_afectados"]} | {hg[m+"_vehiculos_afectados"]} |')
    lines+=['','## Emparejamiento por vehículo',
         f'- Vehículos que aparecen en ambos escenarios: **{summary["emparejamiento"]["presentes_en_ambos"]}**.',
         f'- Solo nominal: {summary["emparejamiento"]["solo_nominal"]}; '
         f'solo híbrido: {summary["emparejamiento"]["solo_hibrido"]}.',
         '- Las diferencias individuales no están controladas por la igualdad de duración o condiciones semafóricas.',
         '- La cohorte objetivo en el nominal es exclusivamente una etiqueta contrafactual por ID, SIN tratamiento asignado.',
         '', '## Detenciones internas y seguridad',
         f'- Detenciones internas candidatas nominal/híbrido: '
         f'{sum(r["escenario"]=="nominal" for r in intersections)} / '
         f'{sum(r["escenario"]=="hibrido_contextual" for r in intersections)}.',
         '- Ninguno de estos registros acredita gridlock: falta demostrar obstrucción efectiva de movimientos conflictivos.',
         '- El contador de parada de emergencia TraCI no es equivalente al aviso `emergency braking` de SUMO; '
         'las desaceleraciones fuertes y extremas se analizan mediante aceleración observada.',
         '', '## Limitaciones y decisiones de H11.3',
         '1. Estas muestras y episodios comparten vehículos y semáforos; no tratarlos como observaciones independientes.',
         '2. La duración de episodio es suma de pasos positivos observados, sin interpolación a través de huecos.',
         '3. Las tasas de headway/TTC usan denominadores distintos y dependen de que exista líder y cierre relativo.',
         '4. El exceso respecto al límite de carril SUMO NO es, por sí solo, infracción legal en Quito; consultar `metricas_carril_h11_2c.csv` para separar carriles internos.',
         '5. Headway <1 s, TTC <2 s, frenada extrema y jerk alto son umbrales exploratorios NO calibrados.',
         '6. La comparación de cohortes es descriptiva; la selección y las interacciones impiden atribución causal simple.',
         '7. No se infiere prevalencia de imprudencia en Quito a partir de penetraciones 15/30/50%.',
         '8. Para validar Quito hacen falta distribuciones de referencia por tipo de vía, franja, velocidad y contexto.',
         '', '## Siguientes pasos',
         '- Revisar eventos extremos, cobertura por cohorte y calidad de las series temporales.',
         '- Diseñar una calibración sin usar la eficiencia del tráfico como función objetivo.',
         '- Hacer sensibilidad multisemilla y validación externa antes de evaluar controladores.','']
    return '\n'.join(lines)


def analyze(nom,hib,settings,actions_path=None,require_paired=True):
    if Path(nom).resolve()==Path(hib).resolve():raise ValueError('Fuentes idénticas')
    check_nom=verify_source(nom,'nominal',settings['steps'])
    check_hib=verify_source(hib,'hibrido_contextual',settings['steps'])
    if check_nom['seed']!=check_hib['seed']:raise ValueError('Semillas distintas')
    integrity={'nominal':check_nom,'hibrido_contextual':check_hib}
    if require_paired:
        integrity['pareado_nominal']=verify_paired(nom,'nominal')
        integrity['pareado_hibrido']=verify_paired(hib,'hibrido_contextual')
    targets=target_cohorts_from_hybrid(hib)
    actions=load_actions(actions_path)
    nom_data,nom_vehicles,nom_episodes=read_trajectories(nom,'nominal',targets,settings,{})
    hib_data,hib_vehicles,hib_episodes=read_trajectories(hib,'hibrido_contextual',targets,settings,actions)
    all_data=nom_data+hib_data;all_eps=nom_episodes+hib_episodes
    groups=make_groups(all_data,all_eps)
    pairs=make_pairs(nom_vehicles,hib_vehicles)
    matched=make_matched_summary(pairs)
    ints=summarize_intersections(nom,'nominal',targets)+summarize_intersections(hib,'hibrido_contextual',targets)
    safety=[summarize_safety(nom,'nominal',nom_data),summarize_safety(hib,'hibrido_contextual',hib_data)]
    present_both=sum(r['nominal_presente'] and r['hibrido_presente'] for r in pairs)
    summary={'version':VERSION,'creado_utc':datetime.now(timezone.utc).isoformat(),
        'estado_cientifico':'DESCRIPTIVO_NO_CALIBRADO_QUITO',
        'fuentes':{'nominal':str(Path(nom).resolve()),'hibrido_contextual':str(Path(hib).resolve()),
                   'acciones_vine':str(Path(actions_path).resolve()) if actions_path else None,
                   'sha_acciones_vine':sha(actions_path) if actions_path else None},
        'integridad':integrity,'parametros':settings,
        'emparejamiento':{'presentes_en_ambos':present_both,
           'solo_nominal':len(nom_vehicles)-present_both,'solo_hibrido':len(hib_vehicles)-present_both},
        'registros':{'nominal':len(nom_data),'hibrido_contextual':len(hib_data)},
        'vehiculos':{'nominal':len(nom_vehicles),'hibrido_contextual':len(hib_vehicles)},
        'distribucion_contexto':{f'{r["escenario"]}|{r["tipo_carril"]}':r['muestras'] for r in road_context(all_data)},
        'episodios_por_indicador':dict(Counter(e['escenario']+'|'+e['indicador'] for e in all_eps)),
        'intersecciones_candidatas':dict(Counter(e['escenario'] for e in ints)),
        'seguridad':safety,
        'advertencias':['sin inferencia causal','sin calibración empírica Quito',
          'headway/TTC solo condicional al líder y variables disponibles',
          'internal stop NO es gridlock confirmado','emergency braking NO equivale a emergency stop']}
    return all_data,list(nom_vehicles.values())+list(hib_vehicles.values()),all_eps,groups,pairs,matched,ints,safety,summary


def safe_output(root,out,inputs):
    target=(root/'resultados').resolve();o=out.resolve()
    if not target.is_dir() or target not in o.parents:raise ValueError('Salida nueva debe estar debajo de resultados/')
    if o.exists():raise FileExistsError('No se sobrescriben salidas: '+str(o))
    for inp in inputs:
        p=Path(inp).resolve()
        if o==p or o in p.parents or p in o.parents:raise ValueError('Salida solapa fuente')
    return o


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument('--root',type=Path,default=Path('.'))
    ap.add_argument('--nom',type=Path,required=True,help='Nominal observado/telemetria')
    ap.add_argument('--hib',type=Path,required=True,help='Híbrido observado/telemetria')
    ap.add_argument('--vine-actions',type=Path,help='acciones_hito08.csv del brazo observado híbrido')
    ap.add_argument('--steps',type=int,default=600)
    ap.add_argument('--dt',type=float,default=0.5)
    ap.add_argument('--speed-margin-kmh',type=float,default=3.6)
    ap.add_argument('--strong-brake',type=float,default=-4.5)
    ap.add_argument('--extreme-brake',type=float,default=-7.0)
    ap.add_argument('--jerk-threshold',type=float,default=8.0)
    ap.add_argument('--require-paired',action='store_true')
    ap.add_argument('--guardar',action='store_true',help='Solo con esto crea reportes (siempre carpeta NUEVA)')
    ap.add_argument('--out',type=Path,help='Destino personalizado NUEVO dentro de resultados/')
    a=ap.parse_args(argv)
    settings=dict(steps=a.steps,dt=a.dt,speed_margin_kmh=a.speed_margin_kmh,strong_brake=a.strong_brake,
                  extreme_brake=a.extreme_brake,jerk_threshold=a.jerk_threshold)
    if a.steps<=0 or a.dt<=0 or a.speed_margin_kmh<0 or a.strong_brake>=0 or a.extreme_brake>a.strong_brake or a.jerk_threshold<=0:
        ap.error('Parámetros no válidos')
    root=a.root.resolve();nom=a.nom.resolve();hib=a.hib.resolve()
    for p in (nom,hib):
        if not p.is_dir():raise FileNotFoundError(p)
    if a.vine_actions and not a.vine_actions.is_file():raise FileNotFoundError(a.vine_actions)
    print('=== H11.2c CARACTERIZACIÓN INTEGRAL | SOLO LECTURA ===',flush=True)
    all_data,vehicles,episodes,groups,pairs,matched,ints,safety,summary=analyze(
        nom,hib,settings,a.vine_actions,a.require_paired)
    print('INTEGRIDAD: OK |',summary['integridad'].get('pareado_nominal',{}).get('status','PAREADO_NO_EXIGIDO'), '/',
        summary['integridad'].get('pareado_hibrido',{}).get('status','PAREADO_NO_EXIGIDO'))
    print('TRAYECTORIAS:',summary['registros'],'VEHICULOS:',summary['vehiculos'])
    print('PAREJAS:',summary['emparejamiento'])
    n=next(g for g in groups if g['escenario']=='nominal' and g['cohorte']=='todos')
    h=next(g for g in groups if g['escenario']=='hibrido_contextual' and g['cohorte']=='todos')
    for m in METRICS:
        print(' ',m,':',f'{n[m+"_muestras"]}/{n[m+"_validos"]}', 'vs',
              f'{h[m+"_muestras"]}/{h[m+"_validos"]}', 'episodios:',n[m+'_episodios'],h[m+'_episodios'])
    print('PARADAS INTERNAS CANDIDATAS:',summary['intersecciones_candidatas'])
    if not a.guardar:
        print('PREFLIGHT COMPLETO. Agrega --guardar para escribir reporte nuevo.');return 0
    output=a.out if a.out else root/'resultados'/('h11_2c_caracterizacion_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    output=safe_output(root,output,[nom,hib,a.vine_actions] if a.vine_actions else [nom,hib])
    output.mkdir(parents=False,exist_ok=False)
    try:
        write_csv(output/'vehiculos_h11_2c.csv',VEH_FIELDS,vehicles)
        write_csv(output/'episodios_riesgo_h11_2c.csv',EP_FIELDS,episodes)
        write_csv(output/'metricas_cohortes_h11_2c.csv',GROUP_FIELDS,groups)
        context=road_context(all_data)
        context_fields=['escenario','tipo_carril','muestras','vehiculos','segundos_vehiculo','velocidad_media_kmh']
        for metric in METRICS:context_fields += [metric+'_validos',metric+'_muestras',metric+'_tasa']
        write_csv(output/'metricas_carril_h11_2c.csv',context_fields,context)
        write_csv(output/'comparacion_vehiculos_h11_2c.csv',PAIR_FIELDS,pairs)
        fields=['cohorte_objetivo','vehiculos_pareados','nota','delta_velocidad_media_kmh_promedio_vehiculos']+[f'{m}_delta_tasa_promedio_vehiculos' for m in METRICS]
        write_csv(output/'comparacion_grupos_pareados_h11_2c.csv',fields,matched)
        write_csv(output/'detenciones_internas_h11_2c.csv',INTER_FIELDS,ints)
        write_csv(output/'seguridad_h11_2c.csv',list(safety[0]),safety)
        (output/'informe_h11_2c.md').write_text(report(summary,groups,matched,safety,ints),encoding='utf-8')
        summary['sha256_reportes']={p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()}
        (output/'manifiesto_h11_2c.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    except Exception:
        print('ERROR: reporte incompleto conservado en',output)
        raise
    print('H11.2c INFORME:',output)
    print('AVISO: estadística descriptiva; ninguna tasa acredita prevalencia de Quito')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('ERROR H11.2c:',type(exc).__name__,str(exc))
        raise SystemExit(1)
