#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H11.2b — auditoría offline de aproximaciones semafóricas H11.2 (solo lectura).

Analiza todas las oportunidades por episodio, no solo los cruces. Nunca modifica
SUMO/H10 ni infiere infracciones legales, intención o calibración respecto a Quito.
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

VERSION = 'H11.2b-auditoria-semaforica-v1.0.0'
REQUIRED_EVENTS = {'time_s','vehicle_id','cohort','event_kind','tls_id','link_index','episode_id',
                   'lane_before','color_label','distance_previous_m','speed_previous_m_s','quality'}
REQUIRED_TRAJ = {'time_s','vehicle_id','cohort','lane_id','speed_m_s','accel_m_s2','tls_id',
                 'tls_link_index','tls_state','tls_distance_m'}
COHORTS = ('both','h09_only','vine_only','neither','unclassified')
EP_COLS = ['escenario','vehicle_id','cohort_actual','cohorte_contrafactual','tls_id','link_index',
    'lane_aproximacion','visita_movimiento','episode_id','t_inicio_s','t_primera_amarilla_s',
    'distancia_primera_amarilla_m','velocidad_primera_amarilla_m_s',
    'frenado_requerido_sin_reaccion_m_s2','distancia_necesaria_reaccion_05_m',
    'distancia_necesaria_reaccion_10_m','factible_reaccion_05','factible_reaccion_10',
    'oportunidad_verde','oportunidad_amarilla','oportunidad_roja','oportunidad_unknown',
    'n_muestras_aproximacion','t_primer_frenado_s','aceleracion_min_amarillo_m_s2',
    't_cruce_s','color_cruce','calidad_cruce','carril_entrada','carril_interno',
    'resultado','censura_sin_cruce','vine_comandos_ventana','vine_propuestas_ventana',
    'vine_comandos_previos_total','nota_metodologica']
PAIR_COLS = ['vehicle_id','cohorte_objetivo','tls_id','link_index','lane_aproximacion',
    'visita_movimiento','emparejamiento','t_nominal_s','t_hibrido_s','desfase_cruce_s',
    'color_nominal','color_hibrido','calidad_nominal','calidad_hibrido','resultado_nominal',
    'resultado_hibrido','amarillo_nominal','amarillo_hibrido',
    'frenado_factible_05_nominal','frenado_factible_05_hibrido',
    'vine_comandos_hibrido_ventana','advertencia']
GROUP_COLS = ['escenario','cohorte_actual','episodios_con_oportunidad','vehiculos_unicos',
    'episodios_con_amarillo','amarillo_factible_reaccion_05','amarillo_factible_reaccion_10',
    'amarillo_factibilidad_desconocida','episodios_con_rojo_oportunidad',
    'cruces_verde_proxy','cruces_amarillo_proxy','cruces_rojo_proxy','cruces_unknown_proxy',
    'sin_cruce_observado','cruces_rojos_con_amarillo','cruces_rojos_con_amarillo_factible_05',
    'tasa_cruces_rojos_sobre_episodios','tasa_rojo_entre_amarillos_factibles_05',
    'nota_denominadores']


def num(x):
    if x is None or str(x).strip() == '': return None
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None


def color(x):
    c=str(x or '').strip().lower()
    return {'g':'green','green':'green','y':'yellow','yellow':'yellow','r':'red','red':'red'}.get(c,'unknown')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''):h.update(b)
    return h.hexdigest()


def read_csv(path, required=()):
    if not path.is_file():raise FileNotFoundError(path)
    with path.open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        headers=set(reader.fieldnames or [])
        if not required.issubset(headers):
            raise ValueError(f'{path}: columnas obligatorias ausentes: {sorted(required-headers)}')
        return list(reader)


def verify_source(folder, condition, *, expected_steps=600):
    folder=Path(folder).resolve()
    if not folder.is_dir():raise FileNotFoundError(folder)
    mf=folder/'manifest_h11_2.json'
    if not mf.is_file():raise FileNotFoundError(f'Sin manifiesto H11.2: {mf}')
    data=json.loads(mf.read_text(encoding='utf-8'))
    if data.get('condition')!=condition:
        raise ValueError(f'Condición errónea en {mf}: {data.get("condition")!r} vs {condition!r}')
    if int(data.get('observed_steps',-1))!=expected_steps:
        raise ValueError(f'Pasos H11.2 distintos de {expected_steps}: {mf}')
    if data.get('empirically_calibrated_quito') is not False:
        raise ValueError('Manifiesto no declara explícitamente NO calibrado para Quito')
    hashes=data.get('outputs_sha256') or {}
    expected={'trayectorias_h11.csv','eventos_semaforicos_h11.csv',
              'eventos_interseccion_h11.csv','seguridad_h11.csv'}
    if not expected.issubset(hashes):raise ValueError('Faltan hashes de salidas H11.2')
    for name,digest in hashes.items():
        if not re.fullmatch(r'[a-fA-F0-9]{64}',str(digest)):
            raise ValueError(f'Hash inválido en manifiesto: {name}')
        path=(folder/name).resolve()
        if folder not in path.parents:raise ValueError('Ruta insegura en manifiesto H11.2')
        if sha(path)!=digest.lower():raise ValueError(f'INTEGRIDAD FALLIDA: {path}')
    return {'folder':str(folder),'condition':condition,'steps':expected_steps,
            'verified_files':len(hashes),'manifest_sha256':sha(mf),
            'manifest_error_counts':data.get('telemetry_failures_or_missing',{}),
            'input_files_sha256':hashes}



def verify_paired_provenance(telemetry, expected_mode, *, strict=False):
    """Verify both original H10 result branches using the H11.2 paired audit.

    The SHA-256 comparison manifest is not sufficient on its own: validate that
    the files still physically match the hashes recorded for BOTH branches.
    """
    folder=Path(telemetry).resolve()
    if folder.name!='telemetria' or folder.parent.name!='observado':
        if strict:raise ValueError('No es una carpeta observado/telemetria pareada')
        return {'status':'NO_LOCALIZADO','note':'estructura no pareada'}
    pairbase=folder.parent.parent
    manifest=pairbase/'comparacion_h11_2.json'
    if not manifest.is_file():
        if strict:raise FileNotFoundError('Sin comparacion_h11_2.json: '+str(manifest))
        return {'status':'NO_LOCALIZADO','note':'sin manifiesto de invariancia'}
    data=json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('mode')!=expected_mode or data.get('status')!='INVARIANZA_BYTE_A_BYTE_VERIFICADA':
        raise ValueError(f'Comparación pareada no aceptable: {manifest}')
    cmp=data.get('comparison') or {}
    if not cmp or 'trafico_h09.csv' not in cmp:
        raise ValueError('Comparación pareada incompleta')
    for filename,meta in cmp.items():
        if '/' in filename or '\\' in filename or filename.startswith('.'):
            raise ValueError('Nombre inseguro en la comparación pareada')
        if not meta.get('identical') or meta.get('sha_control')!=meta.get('sha_observado'):
            raise ValueError(f'Comparación reporta diferencia: {filename}')
        for arm,key in [('control','sha_control'),('observado','sha_observado')]:
            candidate=pairbase/arm/expected_mode/filename
            if not candidate.is_file() or sha(candidate)!=meta[key]:
                raise ValueError('Archivo histórico pareado alterado: '+str(candidate))
    return {'status':'INVARIANZA_PAREADA_REVERIFICADA','mode':expected_mode,
            'source':str(manifest),'audit_sha256':sha(manifest),
            'reverified_original_files':len(cmp)*2}

def load_events(folder):
    data=read_csv(Path(folder)/'eventos_semaforicos_h11.csv',REQUIRED_EVENTS)
    episodes={}
    counters=Counter()
    for row in data:
        eid=row['episode_id'].strip()
        if not eid: raise ValueError('Evento sin episode_id')
        vid=row['vehicle_id'].strip()
        tls=row['tls_id'].strip()
        lk=row['link_index'].strip()
        if not vid or not tls or not lk:raise ValueError('Evento sin vehículo, TLS o link')
        key=(vid,tls,lk,eid)
        entry=episodes.setdefault(key,dict(vehicle_id=vid,tls_id=tls,link_index=lk,
                                            episode_id=eid,opportunities=[],crossings=[]))
        kind=row['event_kind']
        if kind=='approach_opportunity_proxy':entry['opportunities'].append(row)
        elif kind=='crossing_proxy':entry['crossings'].append(row)
        else:counters['unknown_event_kind']+=1
    for key,e in episodes.items():
        if len(e['crossings'])>1:raise ValueError(f'Doble crossing proxy en un episodio: {key}')
        if not e['opportunities']:
            counters['crossing_without_opportunity']+=len(e['crossings'])
    return episodes,counters


def load_trajectories(folder):
    rows=read_csv(Path(folder)/'trayectorias_h11.csv',REQUIRED_TRAJ)
    bykey=defaultdict(list)
    membership=defaultdict(set)
    max_t=-1
    for row in rows:
        t=num(row['time_s'])
        if t is None:raise ValueError('Tiempo inválido en trayectorias')
        max_t=max(max_t,t)
        membership[row['vehicle_id']].add(row['cohort'])
        if row.get('tls_id') and row.get('tls_link_index') not in (None,''):
            bykey[(row['vehicle_id'],row['tls_id'],row['tls_link_index'])].append(row)
    for key in bykey:bykey[key].sort(key=lambda r:num(r['time_s']))
    for v,groups in membership.items():
        if len(groups)!=1:raise ValueError(f'Cohortes discordantes para {v}: {groups}')
    return bykey,{v:next(iter(c)) for v,c in membership.items()},max_t,len(rows)


def load_actions(path):
    if not path:return {}
    rows=read_csv(Path(path),{'vehicle_id','time_s','command_issued','action_decision'})
    grouped=defaultdict(list)
    for r in rows:
        t=num(r['time_s'])
        if t is not None:grouped[r['vehicle_id']].append((t,r['command_issued'].strip().lower()=='true',r['action_decision']))
    for v in grouped:grouped[v].sort()
    return grouped


def classify_episode(e, scenario, lookup, membership, *, actual_cohorts, actions,
                     reference_a, max_t, sample_dt=0.5):
    opp=sorted(e['opportunities'],key=lambda x:num(x['time_s']) if num(x['time_s']) is not None else math.inf)
    cross=e['crossings'][0] if e['crossings'] else None
    if not opp:raise ValueError(f'No existe oportunidad para episodio: {e["episode_id"]}')
    vid=e['vehicle_id']; t0=num(opp[0]['time_s']);tc=num(cross['time_s']) if cross else None
    if t0 is None:raise ValueError('Oportunidad con tiempo inválido')
    cols={color(r['color_label']) for r in opp}
    yellow=next((x for x in opp if color(x['color_label'])=='yellow'),None)
    ty=num(yellow['time_s']) if yellow else None
    dy=num(yellow['distance_previous_m']) if yellow else None
    vy=num(yellow['speed_previous_m_s']) if yellow else None
    dec_req=(vy**2/(2*dy)) if (vy is not None and dy is not None and dy>0) else None
    d05=vy*0.5+vy**2/(2*reference_a) if vy is not None else None
    d10=vy*1.0+vy**2/(2*reference_a) if vy is not None else None
    feasible05=(dy>=d05-1e-9) if dy is not None and d05 is not None else None
    feasible10=(dy>=d10-1e-9) if dy is not None and d10 is not None else None
    key=(vid,e['tls_id'],e['link_index'])
    raw=lookup.get(key,[])
    window=[];prev_t=None
    for r in raw:
        t=num(r['time_s'])
        if t<t0-1e-7:continue
        if tc is not None and t>=tc-1e-7:break
        if prev_t is not None and t-prev_t>1.5*sample_dt+1e-7:break
        if prev_t is None and t>t0+1.5*sample_dt+1e-7:break
        window.append(r);prev_t=t
    # Censura final: si el vehículo no cruza, el observador no distingue entre
    # parada completa, salida del campo de visión, llegada, ruta alternativa y fin de corrida.
    last_t=num(window[-1]['time_s']) if window else t0
    braked=[(num(r['time_s']),num(r['accel_m_s2'])) for r in window
            if ty is not None and num(r['time_s'])>=ty-1e-7 and num(r['accel_m_s2']) is not None]
    first_brake=next((t for t,a in braked if a<=-0.5),None)
    min_a=min((a for _,a in braked),default=None)
    outcome=('cruce_'+color(cross['color_label'])+'_proxy') if cross else 'sin_cruce_observado'
    if cross and cross['quality']!='PROXY_signal_stable' and color(cross['color_label'])!='unknown':
        outcome='cruce_incierto_proxy'
    arows=actions.get(vid,[])
    ncommands=sum(1 for t,issued,_ in arows if issued and t0-1e-7<=t<=(tc if tc is not None else last_t)+1e-7)
    nproposals=sum(1 for t,_,_ in arows if t0-1e-7<=t<=(tc if tc is not None else last_t)+1e-7)
    prev_cmd=sum(1 for t,issued,_ in arows if issued and t<t0-1e-7)
    in_lane=cross['lane_before'] if cross else opp[0]['lane_before']
    actual=membership.get(vid,'unclassified')
    if scenario=='nominal' and actual not in ('unclassified','neither'):
        raise ValueError('Nominal con cohorte activa inesperada')
    desired_cohort=actual_cohorts.get(vid,'sin_dato_en_hibrido') if scenario=='nominal' else actual
    return dict(escenario=scenario,vehicle_id=vid,cohort_actual=actual,cohorte_contrafactual=desired_cohort,
        tls_id=e['tls_id'],link_index=e['link_index'],lane_aproximacion=in_lane,visita_movimiento=0,
        episode_id=e['episode_id'],t_inicio_s=t0,t_primera_amarilla_s=ty,
        distancia_primera_amarilla_m=dy,velocidad_primera_amarilla_m_s=vy,
        frenado_requerido_sin_reaccion_m_s2=dec_req,distancia_necesaria_reaccion_05_m=d05,
        distancia_necesaria_reaccion_10_m=d10,
        factible_reaccion_05=feasible05,factible_reaccion_10=feasible10,
        oportunidad_verde='green' in cols,oportunidad_amarilla=yellow is not None,
        oportunidad_roja='red' in cols,oportunidad_unknown='unknown' in cols,
        n_muestras_aproximacion=len(window),t_primer_frenado_s=first_brake,
        aceleracion_min_amarillo_m_s2=min_a,t_cruce_s=tc,
        color_cruce=color(cross['color_label']) if cross else 'sin_cruce',
        calidad_cruce=cross['quality'] if cross else 'sin_cruce',
        carril_entrada=in_lane,carril_interno=cross['lane_after'] if cross else None,
        resultado=outcome,censura_sin_cruce=(tc is None),
        vine_comandos_ventana=ncommands,vine_propuestas_ventana=nproposals,
        vine_comandos_previos_total=prev_cmd,
        nota_metodologica='proxy; no mide infraccion legal, intencionalidad ni prevalencia de Quito')


def derive_rows(folder,scenario,actual_cohorts,actions,reference_a,expected_dt=0.5):
    episodes,ev_warnings=load_events(folder)
    trajectories,membership,max_t,rows_n=load_trajectories(folder)
    output=[]
    for e in episodes.values():
        output.append(classify_episode(e,scenario,trajectories,membership,
                       actual_cohorts=actual_cohorts,actions=actions,
                       reference_a=reference_a,max_t=max_t,sample_dt=expected_dt))
    # Per physical movement, derive visit ordinal; no matching based on timestamps.
    movement=defaultdict(list)
    for e in output:
        key=(e['vehicle_id'],e['tls_id'],e['link_index'],e['lane_aproximacion'])
        movement[key].append(e)
    for records in movement.values():
        for order,e in enumerate(sorted(records,key=lambda x:x['t_inicio_s']),start=1):
            e['visita_movimiento']=order
    output.sort(key=lambda r:(r['t_inicio_s'],r['vehicle_id'],r['tls_id'],r['episode_id']))
    return output,dict(trajectory_rows=rows_n,vehicles_seen=len(membership),
                       episodes=len(output),event_warnings=dict(ev_warnings),
                       max_time_s=max_t,observed_cohorts=dict(Counter(membership.values()))),membership


def pairs(nom,hib):
    def index(data):
        result={}
        for x in data:
            key=tuple(str(x[q]) for q in ('vehicle_id','tls_id','link_index','lane_aproximacion','visita_movimiento'))
            if key in result:raise ValueError('Colisión de clave de emparejamiento')
            result[key]=x
        return result
    a=index(nom);b=index(hib);out=[]
    for key in sorted(set(a)|set(b),key=str):
        x=a.get(key);y=b.get(key)
        rn=x['t_cruce_s'] if x else None;rh=y['t_cruce_s'] if y else None
        matched=('ambos' if x and y else 'solo_nominal' if x else 'solo_hibrido')
        note=('Emparejamiento por ID, TLS, enlace, carril y ordinal; NO controla diferencia de tiempo de llegada.'
              if x and y else 'No existe episodio equivalente en ambos brazos; posible censura/visita distinta.')
        out.append(dict(vehicle_id=key[0],cohorte_objetivo=y['cohort_actual'] if y else x['cohorte_contrafactual'],
            tls_id=key[1],link_index=key[2],lane_aproximacion=key[3],visita_movimiento=key[4],
            emparejamiento=matched,t_nominal_s=rn,t_hibrido_s=rh,
            desfase_cruce_s=(rh-rn) if rh is not None and rn is not None else None,
            color_nominal=x['color_cruce'] if x else 'sin_episodio',
            color_hibrido=y['color_cruce'] if y else 'sin_episodio',
            calidad_nominal=x['calidad_cruce'] if x else None,calidad_hibrido=y['calidad_cruce'] if y else None,
            resultado_nominal=x['resultado'] if x else 'sin_episodio',
            resultado_hibrido=y['resultado'] if y else 'sin_episodio',
            amarillo_nominal=x['oportunidad_amarilla'] if x else None,
            amarillo_hibrido=y['oportunidad_amarilla'] if y else None,
            frenado_factible_05_nominal=x['factible_reaccion_05'] if x else None,
            frenado_factible_05_hibrido=y['factible_reaccion_05'] if y else None,
            vine_comandos_hibrido_ventana=y['vine_comandos_ventana'] if y else None,
            advertencia=note))
    return out


def groups(rows):
    by=defaultdict(list)
    for x in rows:by[(x['escenario'],x['cohort_actual'])].append(x)
    result=[]
    for (scenario,cohort),g in sorted(by.items()):
        n=len(g);yellow=[r for r in g if r['oportunidad_amarilla']]
        feasible05=[r for r in yellow if r['factible_reaccion_05'] is True]
        feasible10=[r for r in yellow if r['factible_reaccion_10'] is True]
        redcross=[r for r in g if r['color_cruce']=='red']
        redyellow=[r for r in redcross if r['oportunidad_amarilla']]
        rf=[r for r in redyellow if r['factible_reaccion_05'] is True]
        result.append(dict(escenario=scenario,cohorte_actual=cohort,
            episodios_con_oportunidad=n,vehiculos_unicos=len({r['vehicle_id'] for r in g}),
            episodios_con_amarillo=len(yellow),amarillo_factible_reaccion_05=len(feasible05),
            amarillo_factible_reaccion_10=len(feasible10),
            amarillo_factibilidad_desconocida=sum(r['factible_reaccion_05'] is None for r in yellow),
            episodios_con_rojo_oportunidad=sum(r['oportunidad_roja'] for r in g),
            cruces_verde_proxy=sum(r['color_cruce']=='green' for r in g),
            cruces_amarillo_proxy=sum(r['color_cruce']=='yellow' for r in g),
            cruces_rojo_proxy=len(redcross),cruces_unknown_proxy=sum(r['color_cruce']=='unknown' for r in g),
            sin_cruce_observado=sum(r['color_cruce']=='sin_cruce' for r in g),
            cruces_rojos_con_amarillo=len(redyellow),
            cruces_rojos_con_amarillo_factible_05=len(rf),
            tasa_cruces_rojos_sobre_episodios=(len(redcross)/n if n else None),
            tasa_rojo_entre_amarillos_factibles_05=(len(rf)/len(feasible05) if feasible05 else None),
            nota_denominadores='episodios de aproximacion; pueden repetirse por conductor; solo descriptivo'))
    return result



def counterfactual_groups(rows):
    """Descriptive target-cohort comparability only.

    The nominal vehicles never actually receive the hybrid rosters. We use the
    hybrid label of the same ID as a stratification tag, not as an intervention.
    """
    renamed=[]
    for row in rows:
        copy=dict(row)
        copy['cohort_actual']=row['cohorte_contrafactual']
        renamed.append(copy)
    result=groups(renamed)
    for g in result:
        g['cohorte_objetivo']=g.pop('cohorte_actual')
        g['tipo_asignacion']=('SOLO_ETIQUETA_CONTRAFACTUAL_SIN_INTERVENCION'
                              if g['escenario']=='nominal' else 'ASIGNACION_REAL_HIBRIDA')
    return result

def h09_reconcile(rows, path, tolerance=0.5):
    if not path:return [],{'status':'NO_SUMINISTRADO'}
    h09=read_csv(Path(path),{'time_s','vehicle_id','site_id','event_type','signal_state','classification_quality'})
    h09reds=[r for r in h09 if r['event_type']=='tls_crossing_link' and
             color(r['signal_state'])=='red' and r['classification_quality'].lower()=='confirmed']
    h11reds=[r for r in rows if r['color_cruce']=='red']
    matched=set();output=[]
    for r in h11reds:
        found=[]
        for i,q in enumerate(h09reds):
            if i in matched:continue
            if (q['vehicle_id']==r['vehicle_id'] and q['site_id']==r['tls_id'] and
                num(q['time_s']) is not None and r['t_cruce_s'] is not None and
                abs(num(q['time_s'])-r['t_cruce_s'])<=tolerance+1e-8):found.append(i)
        if len(found)>1:raise ValueError('Evento H11 con más de una coincidencia H09')
        ok=bool(found)
        if ok:matched.add(found[0])
        output.append(dict(vehicle_id=r['vehicle_id'],tls_id=r['tls_id'],t_h11_s=r['t_cruce_s'],
                           t_h09_s=h09reds[found[0]]['time_s'] if ok else None,
                           estado='VINCULADO_H09_CONFIRMADO' if ok else 'SOLO_H11_PROXY',
                           calidad_h11=r['calidad_cruce'],calidad_h09=h09reds[found[0]]['classification_quality'] if ok else None))
    for i,q in enumerate(h09reds):
        if i not in matched:
            output.append(dict(vehicle_id=q['vehicle_id'],tls_id=q['site_id'],
                               t_h11_s=None,t_h09_s=q['time_s'],estado='SOLO_H09_CONFIRMADO',
                               calidad_h11=None,calidad_h09=q['classification_quality']))
    return output,{'status':'ANALIZADO','h09_rojos_confirmados':len(h09reds),
                   'h11_rojos_proxy':len(h11reds),'coincidencias':len(matched),
                   'h09_no_encontrados':len(h09reds)-len(matched)}


def write_csv(path,fields,rows):
    with path.open('x',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise');w.writeheader()
        for row in rows:w.writerow(row)


def make_report(summary):
    nom=summary['escenarios']['nominal'];hib=summary['escenarios']['hibrido_contextual']
    total=summary['totales'];recon=summary['reconciliacion_h09']
    return f'''# H11.2b — Auditoría offline de aproximaciones semafóricas

**Estado:** DESCRIPTIVO; SIN calibración con Quito, SIN inferencia causal y SIN adjudicación legal de infracciones.

## Procedencia y controles

- Fuente nominal: `{summary['fuentes']['nominal']}`
- Fuente híbrida: `{summary['fuentes']['hibrido_contextual']}`
- Paso SUMO: 0,5 s; simulación: 600 pasos; semilla: 101 según las fuentes H11.2.
- Integridad: SHA-256 de los cuatro CSV de cada brazo cotejados con sus manifiestos.
- Procedencia pareada nominal: {summary['integridad']['pareado_nominal']['status']}.
- Procedencia pareada híbrida: {summary['integridad']['pareado_hibrido']['status']}.
- Referencia hipotética de desaceleración: {summary['parametros']['a_ref_m_s2']} m/s², no calibrada a Quito.

## Cobertura por brazo

| Magnitud | Nominal | Híbrido contextual |
|---|---:|---:|
| Vehículos vistos | {nom['vehicles_seen']} | {hib['vehicles_seen']} |
| Filas trayectoria | {nom['trajectory_rows']} | {hib['trajectory_rows']} |
| Episodios con oportunidad observada | {nom['episodes']} | {hib['episodes']} |
| Episodios sin cruce observado | {total['nominal']['sin_cruce']} | {total['hibrido_contextual']['sin_cruce']} |
| Episodios que incluyen amarillo | {total['nominal']['con_amarillo']} | {total['hibrido_contextual']['con_amarillo']} |
| Episodios amarillo factible, reacción 0,5 s | {total['nominal']['factibles_05']} | {total['hibrido_contextual']['factibles_05']} |
| Cruces rojos proxy | {total['nominal']['cruces_rojo']} | {total['hibrido_contextual']['cruces_rojo']} |
| Cruces con color desconocido | {total['nominal']['cruces_unknown']} | {total['hibrido_contextual']['cruces_unknown']} |

## Emparejamiento por movimiento

- Episodios emparejados: {summary['parejas']['ambos']}.
- Solo nominal: {summary['parejas']['solo_nominal']}.
- Solo híbrido: {summary['parejas']['solo_hibrido']}.
- Pares con cruce en ambos brazos: {summary['parejas']['cruce_ambos']}.
- Transiciones de cruce nominal verde a híbrido rojo (proxy): {summary['parejas']['verde_a_rojo']}.
- Las diferencias temporales pueden cambiar la fase encontrada: **emparejamiento no equivale a causalidad**.

## Reconciliación H09

- Estado: {recon['status']}.
- Cruces H11 rojo proxy: {recon.get('h11_rojos_proxy','N/D')}.
- Cruces H09 rojo confirmado: {recon.get('h09_rojos_confirmados','N/D')}.
- Coincidencias por vehículo, TLS y tiempo: {recon.get('coincidencias','N/D')}.
- Los eventos adicionales de H11 se conservan como *proxy*, no como *confirmed*.

## Límites de validez

1. Una *oportunidad* H11.2 es un episodio de aproximación dentro del horizonte de observación; un mismo vehículo puede generar varios episodios.
2. Un episodio puede ver verde, ámbar y rojo: esas categorías NO son mutuamente excluyentes.
3. La factibilidad bajo reacción de 0,5 o 1 s y desaceleración constante es una **sensibilidad mecánica**; no infiere reacción humana, legalidad ni intención.
4. `sin_cruce_observado` es censura/ausencia de transición reconocida: puede incluir detenciones, fin de trayecto, pérdida del campo de visión y otros motivos.
5. Los índices de enlace y la detección de cruce son *proxies*; falta validación geométrica independiente.
6. Los registros vehículo-paso y los episodios no son observaciones estadísticamente independientes.
7. La cohorte nominal se conserva como `unclassified`; el contrafactual nominal hereda solo la etiqueta de destino del vehículo híbrido, no una intervención real.
8. Que una aceleración Vine haya sido comandada NO prueba su efecto causal sobre una entrada en rojo; se requiere ablación controlada y réplicas multisemilla.
9. Los resultados provienen de Hangzhou 4x4 con conductas hipotéticas; ninguna tasa corresponde a observaciones de Quito.
'''


def summarize_totals(rows):
    return dict(episodios=len(rows),sin_cruce=sum(r['color_cruce']=='sin_cruce' for r in rows),
        con_amarillo=sum(r['oportunidad_amarilla'] for r in rows),
        factibles_05=sum(r['oportunidad_amarilla'] and r['factible_reaccion_05'] is True for r in rows),
        cruces_rojo=sum(r['color_cruce']=='red' for r in rows),
        cruces_unknown=sum(r['color_cruce']=='unknown' for r in rows))


def run(nom,hib,h09_events=None,actions_path=None,a_ref=4.5,expected_steps=600,require_paired=False):
    if a_ref<=0:raise ValueError('a_ref debe ser > 0')
    checknom=verify_source(nom,'nominal',expected_steps=expected_steps)
    checkhib=verify_source(hib,'hibrido_contextual',expected_steps=expected_steps)
    pair_nom=verify_paired_provenance(nom,'nominal',strict=require_paired)
    pair_hib=verify_paired_provenance(hib,'hibrido_contextual',strict=require_paired)
    # first read hybrid to carry its cohort attribution into nominal ONLY as counterfactual label
    _,hybrid_membership,_,_=load_trajectories(hib)
    actions=load_actions(actions_path)
    nominal,nom_info,_=derive_rows(nom,'nominal',hybrid_membership,{},a_ref)
    hybrid,hib_info,_=derive_rows(hib,'hibrido_contextual',hybrid_membership,actions,a_ref)
    combined=nominal+hybrid; paired=pairs(nominal,hybrid)
    rec,rec_info=h09_reconcile(hybrid,h09_events)
    pair_counts=dict(Counter(r['emparejamiento'] for r in paired))
    transitions=Counter((r['color_nominal'],r['color_hibrido']) for r in paired if r['emparejamiento']=='ambos')
    pair_counts.update(cruce_ambos=sum(r['t_nominal_s'] is not None and r['t_hibrido_s'] is not None for r in paired),
                       verde_a_rojo=sum(r['color_nominal']=='green' and r['color_hibrido']=='red' for r in paired))
    for k in ('ambos','solo_nominal','solo_hibrido'):pair_counts.setdefault(k,0)
    summary=dict(version=VERSION,generated_utc=datetime.now(timezone.utc).isoformat(),
        scientific_status='DESCRIPTIVE_ONLY_NOT_CALIBRATED_TO_QUITO',
        fuentes={'nominal':str(Path(nom).resolve()),'hibrido_contextual':str(Path(hib).resolve()),
                 'h09_events':str(Path(h09_events).resolve()) if h09_events else None,
                 'vine_actions':str(Path(actions_path).resolve()) if actions_path else None},
        parametros=dict(a_ref_m_s2=a_ref,reaction_sensitivity_s=[0.5,1.0],
                       expected_steps=expected_steps,dt_s=0.5),
        integridad={'nominal':checknom,'hibrido_contextual':checkhib,
            'pareado_nominal':pair_nom,'pareado_hibrido':pair_hib,
            'h09_events_sha256':sha(h09_events) if h09_events else None,
            'vine_actions_sha256':sha(actions_path) if actions_path else None},
        escenarios={'nominal':nom_info,'hibrido_contextual':hib_info},
        totales={'nominal':summarize_totals(nominal),'hibrido_contextual':summarize_totals(hybrid)},
        parejas=pair_counts,matriz_transiciones_pareadas=[dict(color_nominal=a,color_hibrido=b,episodios=n)
              for (a,b),n in sorted(transitions.items())],reconciliacion_h09=rec_info,
        limites=['Todos los resultados son proxies',
                 'Tasas basadas en episodios, no prevalencia de conductores de Quito',
                 'No atribución causal entre Vine/H09/tiempos de llegada',
                 'Cruces sin color o episodios sin cruce no se imputan como verdes',
                 'Factibilidad de parada mecánica hipotética; sin reacción real'])
    return combined,paired,groups(combined),rec,summary


def safe_destination(root, dest, input_dirs):
    results=(root/'resultados').resolve()
    if not results.is_dir():raise FileNotFoundError(results)
    dest=dest.resolve()
    if results not in dest.parents:raise ValueError('La carpeta de salida debe estar bajo resultados/')
    if dest.exists():raise FileExistsError('No se sobreescriben resultados existentes: '+str(dest))
    for d in input_dirs:
        p=Path(d).resolve()
        if dest==p or dest in p.parents or p in dest.parents:
            raise ValueError('La salida no puede contener ni solaparse con entradas')
    return dest


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--nom',type=Path,required=True,help='Carpeta observado/telemetria nominal')
    p.add_argument('--hib',type=Path,required=True,help='Carpeta observado/telemetria híbrida')
    p.add_argument('--h09-events',type=Path,help='Archivo eventos_h09.csv en híbrido')
    p.add_argument('--vine-actions',type=Path,help='Archivo acciones_hito08.csv en híbrido')
    p.add_argument('--a-ref',type=float,default=4.5)
    p.add_argument('--expected-steps',type=int,default=600)
    p.add_argument('--require-paired',action='store_true',help='Exige y vuelve a verificar invariancia H11.2 en ambos brazos')
    p.add_argument('--output',type=Path)
    p.add_argument('--guardar',action='store_true',help='Solo escribe en una carpeta de salida NUEVA')
    a=p.parse_args(argv)
    root=a.root.resolve();nom=a.nom.resolve();hib=a.hib.resolve()
    print('H11.2b AUDITORIA SEMAFORICA | FUENTES SOLO LECTURA')
    print('Nominal:',nom,'\nHíbrido:',hib)
    if not a.guardar:
        checka=verify_source(nom,'nominal',expected_steps=a.expected_steps)
        checkb=verify_source(hib,'hibrido_contextual',expected_steps=a.expected_steps)
        pnom=verify_paired_provenance(nom,'nominal',strict=a.require_paired)
        phib=verify_paired_provenance(hib,'hibrido_contextual',strict=a.require_paired)
        print('PREFLIGHT OK:',checka['verified_files'],'+',checkb['verified_files'],'archivos con SHA256 validado')
        print('PAREADO:',pnom['status'],'/',phib['status'])
        print('Solo verificación de fuentes. Agrega --guardar para ejecutar el análisis.')
        return 0
    out=a.output if a.output else (root/'resultados'/('h11_2b_auditoria_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    out=safe_destination(root,out,[nom,hib])
    rows,paired,grouped,reconcile,summary=run(nom,hib,a.h09_events,a.vine_actions,a.a_ref,a.expected_steps,a.require_paired)
    # Create output ONLY after all source integrity checks and computation succeed.
    out.mkdir(parents=False,exist_ok=False)
    try:
        write_csv(out/'episodios_h11_2b.csv',EP_COLS,rows)
        write_csv(out/'movimientos_emparejados_h11_2b.csv',PAIR_COLS,paired)
        write_csv(out/'matriz_transiciones_h11_2b.csv',
                  ['color_nominal','color_hibrido','episodios'],summary['matriz_transiciones_pareadas'])
        write_csv(out/'metricas_cohortes_h11_2b.csv',GROUP_COLS,grouped)
        write_csv(out/'metricas_cohortes_objetivo_h11_2b.csv',
                  ['escenario','cohorte_objetivo','tipo_asignacion'] + GROUP_COLS[2:],
                  counterfactual_groups(rows))
        write_csv(out/'reconciliacion_h09_h11.csv',
                  ['vehicle_id','tls_id','t_h11_s','t_h09_s','estado','calidad_h11','calidad_h09'],reconcile)
        (out/'resumen_h11_2b.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'informe_h11_2b.md').write_text(make_report(summary),encoding='utf-8')
        report_hashes={p.name:sha(p) for p in out.iterdir() if p.is_file()}
        (out/'manifest_h11_2b.json').write_text(json.dumps(dict(
            version=VERSION,created_utc=datetime.now(timezone.utc).isoformat(),
            calibrated_quito=False,output_sha256=report_hashes,
            source_manifest_sha256={key:v['manifest_sha256'] for key,v in
                                    summary['integridad'].items() if isinstance(v,dict) and 'manifest_sha256' in v}),
            ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        print('ERROR creando reporte. Salida parcial preservada:',out)
        raise
    print('INTEGRIDAD: OK (manifiestos y CSV H11.2)')
    for scenario in ('nominal','hibrido_contextual'):
        print(' ',scenario,summary['totales'][scenario])
    print('PAREJAS:',summary['parejas'])
    print('H09:',summary['reconciliacion_h09'])
    print('REPORTES H11.2b:',out)
    print('AVISO: SOLO DESCRIPTIVO; SIN INFERENCIA DE REPRESENTATIVIDAD QUITO')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:
        import sys
        print('H11.2b FALLÓ:',type(e).__name__,str(e),file=sys.stderr)
        raise SystemExit(2)
