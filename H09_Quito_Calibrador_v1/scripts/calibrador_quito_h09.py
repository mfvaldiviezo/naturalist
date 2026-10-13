#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H09 Quito | Auditor y comparador empírico agregado, SOLO LECTURA.

No estima tasas condicionales de infracción, ni ajusta por magia parámetros
SUMO. Evalúa EVENTOS REGISTRADOS con denominador explícito y trazabilidad.

Uso:
 python scripts/calibrador_quito_h09.py auditar-fuentes
 python scripts/calibrador_quito_h09.py comparar --eventos RUN/eventos_h09.csv \
  --protocolo config/protocolo_hangzhou_ejemplo.json --salida-dir OUT
 python scripts/calibrador_quito_h09.py comparar-candidatos --manifiesto candidatos.csv \
  --protocolo config/protocolo_hangzhou_ejemplo.json --salida-dir OUT
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parent.parent
REF=ROOT/'datos_referencia'/'objetivos_quito_h09.json'
SITES=ROOT/'datos_referencia'/'cruces_quito_publicados.csv'
INDICATORS=ROOT/'datos_referencia'/'velocidad_quito_publicada.csv'
VERSION='H09-QUITO-VALIDADOR-AGREGADO-v1.0'
CROSSING_STATES={'green','yellow','red','unknown'}
REQUIRED=('run_id','seed','vehicle_id','site_id','passage_id','event_type','signal_state','classification_quality','speed_mps','limit_mps','measurement_id')
EVENT_TYPES={'stopline','speed'}
SITE_IDS={'QUI-1','QUI-2','QUI-3'}

class AuditError(ValueError): pass

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()

def load_json(p):
    with Path(p).open('r',encoding='utf-8-sig') as f:return json.load(f)

def load_csv(p):
    with Path(p).open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames is None: raise AuditError(f'CSV sin cabecera: {p}')
        return list(reader),tuple(reader.fieldnames)

def ensure_rate(name, val):
    if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val) or not 0<=val<=1:
        raise AuditError(f'{name}: probabilidad inválida {val!r}')


def validate_sources(ref_path=REF,sites_path=SITES,indicators_path=INDICATORS):
    target=load_json(ref_path)
    if target.get('city')!='Quito':raise AuditError('Fuente no es Quito')
    entries,fields=load_csv(sites_path)
    if len(entries)!=4:raise AuditError('Fuente: se esperan tres sitios y un total descriptivo')
    total={'n':0,'yellow':0,'red':0}
    for row in entries[:3]:
        sid=row['id_sitio']
        if sid not in SITE_IDS:raise AuditError(f'Sitio inesperado: {sid}')
        t=target['numerical_targets']['signal_stopline_events'][sid]
        n=int(row['vehiculos_observados']); y=int(row['eventos_amarillo']); r=int(row['eventos_rojo'])
        if any(int(t[k])!=v for k,v in [('n_observed_vehicles',n),('n_yellow_cross_events',y),('n_red_cross_events',r)]):
            raise AuditError('Inconsistencia entre objetivo y CSV para '+sid)
        if n <= 0 or y<0 or r<0 or y+r>n:raise AuditError('Conteos inválidos '+sid)
        if row['aprobado_como_parametro_decision'].strip().lower()!='false':
            raise AuditError('No permitir probabilidad individual a partir de tasas agregadas')
        total['n']+=n;total['yellow']+=y;total['red']+=r
    summ=entries[3]
    if [int(summ[k]) for k in ('vehiculos_observados','eventos_amarillo','eventos_rojo')]!=[total['n'],total['yellow'],total['red']]:
        raise AuditError('Suma descriptiva diferente')
    if any(v is not None for v in target.get('individual_decision_probabilities',{}).values()):
        raise AuditError('No permitir probabilidades individuales no identificadas')
    speed=target['numerical_targets']['speeding_prevalence']
    ensure_rate('speed target', speed['report_value_rounded'])
    if speed['sample_n_for_value'] is not None or speed['event_count_for_value'] is not None:
        raise AuditError('No inventar denominador ni eventos del informe de velocidad')
    return target


def read_protocol(path):
    p=load_json(path)
    for key in ('protocol_version','network_role','denominator_definition','source_population_compatibility',
                'signal_classification_method','crossing_observation_window','speed_sampling_method','sites'):
        if key not in p:raise AuditError(f'Protocolo sin {key}')
    if p['source_population_compatibility'] not in ('not_comparable','proxy_only','documented_harmonized'):
        raise AuditError('Compatibilidad invalida')
    if not isinstance(p['sites'],dict) or not p['sites']:
        raise AuditError('Protocolo debe mapear sitios de SUMO a fuentes Quito')
    for sim,qui in p['sites'].items():
        if not sim or qui not in SITE_IDS:raise AuditError('Mapeo inválido '+repr((sim,qui)))
    if len(set(p['sites'].values()))!=len(p['sites']):
        raise AuditError('No mapear varias intersecciones SUMO al mismo sitio observado')
    if p['source_population_compatibility']=='documented_harmonized':
        for key in ('harmonization_evidence_url','vehicle_observation_rule','yellow_event_definition',
                    'red_event_definition','reference_observation_scope'):
            if not p.get(key):raise AuditError(f'Falta evidencia obligatoria de armonización: {key}')
        if not str(p['harmonization_evidence_url']).startswith('https://'):
            raise AuditError('La armonización requiere URL https de evidencia publicada/documentada')
    return p


def finite_optional(txt,label):
    if txt is None or str(txt).strip()=='':return None
    try:x=float(txt)
    except (ValueError,TypeError):raise AuditError(label+' no numérico')
    if not math.isfinite(x):raise AuditError(label+' no finito')
    return x


def read_events(file):
    rows,fields=load_csv(file)
    missing=set(REQUIRED)-set(fields)
    if missing:raise AuditError('Faltan columnas: '+', '.join(sorted(missing)))
    if not rows:raise AuditError('No hay eventos registrados; no se puede afirmar tasa cero')
    identities=set(); runs=set(); out=[]
    for line,row in enumerate(rows,2):
        for field in ('run_id','seed','vehicle_id','site_id','passage_id','event_type'):
            if not str(row[field]).strip():raise AuditError(f'Línea {line}: {field} vacío')
        event_type=row['event_type'].strip().lower()
        if event_type not in EVENT_TYPES:raise AuditError(f'Línea {line}: event_type inválido')
        color=row['signal_state'].strip().lower()
        if event_type=='stopline' and color not in CROSSING_STATES:
            raise AuditError(f'Línea {line}: semáforo {color!r}')
        if event_type=='speed' and not row['measurement_id'].strip():
            raise AuditError(f'Línea {line}: medición de velocidad sin estación')
        # Una oportunidad registrada en una estación por vehículo y pasada.
        identity=tuple(row[k] for k in ('run_id','seed','event_type','site_id','passage_id'))
        if identity in identities:raise AuditError(f'Línea {line}: oportunidad duplicada {identity}')
        identities.add(identity)
        runs.add((row['run_id'],row['seed']))
        quality=row['classification_quality'].strip().lower()
        if quality not in ('confirmed','uncertain'):
            raise AuditError(f'Línea {line}: quality confirmed/uncertain obligatoria')
        v=finite_optional(row['speed_mps'],f'línea {line}: speed_mps')
        limit=finite_optional(row['limit_mps'],f'línea {line}: limit_mps')
        if event_type=='speed' and ((v is None or limit is None) or v<0 or limit<=0):
            raise AuditError(f'Línea {line}: speed event requiere velocidad y limite positivos')
        out.append({**row,'event_type':event_type,'signal_state':color,
                    'classification_quality':quality,'speed_mps':v,'limit_mps':limit})
    if len(runs)!=1:raise AuditError('Cada CSV representa un único run_id + seed; usar comparar-candidatos para varios')
    return out


def aggregate(rows,protocol,targets):
    by_site=defaultdict(list);speed=[]
    for r in rows:
        if r['event_type']=='stopline':by_site[r['site_id']].append(r)
        else:speed.append(r)
    report=[]
    for sim,qui in sorted(protocol['sites'].items()):
        ls=by_site.get(sim,[])
        known=[r for r in ls if r['classification_quality']=='confirmed' and r['signal_state']!='unknown']
        unknown=len(ls)-len(known)
        counts=Counter(r['signal_state'] for r in known)
        n=len(ls)
        quality= len(known)/n if n else None
        target=targets['numerical_targets']['signal_stopline_events'][qui]
        reference_n=target['n_observed_vehicles']
        if n:
            rate_r=counts['red']/n
            rate_y=counts['yellow']/n
            rate_both=(counts['red']+counts['yellow'])/n
            observed={'red':rate_r,'yellow':rate_y,'total':rate_both}
        else:observed={'red':None,'yellow':None,'total':None}
        references={'red':target['red_event_rate_per_all_observed_vehicles'],
                    'yellow':target['yellow_event_rate_per_all_observed_vehicles'],
                    'total':target['all_event_rate_per_all_observed_vehicles']}
        differences={key:(100*(observed[key]-references[key]) if observed[key] is not None else None) for key in references}
        reasons=[]
        if n==0:reasons.append('no_stopline_records')
        if n<protocol.get('minimum_sample_crossings',100):reasons.append('low_simulated_exposure')
        if quality is None or quality<protocol.get('minimum_classified_fraction',0.98):reasons.append('insufficient_classification_coverage')
        if protocol['source_population_compatibility']!='documented_harmonized':reasons.append('observation_protocol_not_harmonized')
        if protocol['network_role']!='Quito_replica':reasons.append('network_not_quito_replica')
        if any(x['observation_method']=='TLS_next_disappeared_with_lane_transition' for x in ls):
            reasons.append('proxy_stopline_detector_not_field_equivalent')
        if target['quality_flag']!='alta':reasons.append('reference_site_quality_caveat')
        valid='VALIDATION_CANDIDATE' if not [x for x in reasons if x!='reference_site_quality_caveat'] else 'DESCRIPTIVE_ONLY'
        report.append({'sim_site_id':sim,'reference_site_id':qui,'reference_n':reference_n,
          'n_simulated_passages':n,'n_simulated_classified':len(known),'n_simulated_uncertain':unknown,
          'classification_fraction':quality,'sim_counts':{k:counts[k] for k in ('green','yellow','red')},
          'simulated_rates':observed,'reference_rates':references,'difference_pp':differences,
          'validation_status':valid,'restrictions':reasons,'ref_quality':target['quality_flag']})
    unique_speed={(r['site_id'],r['measurement_id'],r['vehicle_id']) for r in speed}
    # Cada estación solo una muestra por vehículo. Distintos pasos sobre misma estación se rechazan.
    if len(unique_speed)!=len(speed):raise AuditError('Muestreo de velocidad duplicado para vehículo y estación')
    speed_known=[r for r in speed if r['classification_quality']=='confirmed']
    s_n=len(speed)
    s_k=sum(r['speed_mps']>r['limit_mps'] for r in speed_known)
    s_rate=s_k/s_n if s_n else None
    speeding={'n_samples':s_n,'n_classified':len(speed_known),'n_speeding':s_k,
              'simulated_rate':s_rate,'reference_rounded':targets['numerical_targets']['speeding_prevalence']['report_value_rounded'],
              'difference_pp':(100*(s_rate-targets['numerical_targets']['speeding_prevalence']['report_value_rounded']) if s_rate is not None else None),
              'comparison_status':'DESCRIPTIVE_ONLY',
              'reasons':['no_speed_samples'] if not s_n else ['no_documented_comparable_BIGRS_sampling_frame',
                                                             'published_20_percent_rounded_no_denominator']}
    return report,speeding


def summary_object(events_path,protocol_path,source_path=REF):
    targets=validate_sources(source_path,SITES,INDICATORS)
    proto=read_protocol(protocol_path)
    rows=read_events(events_path)
    by_site,speed=aggregate(rows,proto,targets)
    return {'version':VERSION,'mode':'READ_ONLY','input':str(Path(events_path).resolve()),
       'input_sha256':sha256(Path(events_path)),'protocol':str(Path(protocol_path).resolve()),
       'protocol_sha256':sha256(Path(protocol_path)),'reference_sha256':sha256(Path(source_path)),
       'reference_article':targets['sources']['Q01'],'speed_source':targets['sources']['Q02'],
       'run_id':rows[0]['run_id'],'seed':rows[0]['seed'],'network_role':proto['network_role'],
       'reference_population_compatibility':proto['source_population_compatibility'],
       'site_metrics':by_site,'speed_metrics':speed,
       'interpretation':'AGGREGATE_DESCRIPTIVE; null individual rates; no claim of Quito driver prevalence or causal calibration',
       'individual_decision_parameters':targets['individual_decision_probabilities']}


def summarize_console(obj):
    print('\n=== H09 QUITO / VALIDACIÓN AGREGADA ===')
    print('Escenario:',obj['run_id'],'semilla:',obj['seed'],'red:',obj['network_role'])
    print('Protocolo:',obj['reference_population_compatibility'])
    print(f"{'SIM => QUITO':<23}{'N Sim':>7}{'N Qui':>7}{'Rojo sim':>11}{'Rojo Qui':>11}{'Amar sim':>11}{'Amar Qui':>11}{'Estado':>22}")
    for s in obj['site_metrics']:
        vals=[s['simulated_rates']['red'],s['reference_rates']['red'],s['simulated_rates']['yellow'],s['reference_rates']['yellow']]
        fmt=lambda v: f'{100*v:6.2f}%' if v is not None else 'ND'
        print(f"{s['sim_site_id']+' => '+s['reference_site_id']:<23}{s['n_simulated_passages']:>7}{s['reference_n']:>7}"
              f"{fmt(vals[0]):>11}{fmt(vals[1]):>11}{fmt(vals[2]):>11}{fmt(vals[3]):>11}{s['validation_status']:>22}")
        if s['restrictions']:print('  Observaciones:',', '.join(s['restrictions']))
    s=obj['speed_metrics']
    print('Velocidad: n=',s['n_samples'],'excesos=',s['n_speeding'],
          'fracción simulada=',None if s['simulated_rate'] is None else round(s['simulated_rate'],5),
          'referencia Quito≈',s['reference_rounded'])
    print('NOTA: ni los cocientes simulados ni los publicados se convierten en P(decisión|contexto).')


def safe_write_json(path,object_data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():raise FileExistsError('No se sobrescribe '+str(p))
    with p.open('w',encoding='utf-8') as f:json.dump(object_data,f,indent=2,ensure_ascii=False,allow_nan=False)


def compare_candidates(manifest_path,proto,output,source=REF):
    lines,headers=load_csv(manifest_path)
    required={'eventos','escenario','seed'}
    if not required.issubset(headers):raise AuditError('CSV candidatos requiere eventos,escenario,seed')
    if not lines:raise AuditError('Sin candidatos; no se puede calibrar')
    outputs=[]
    ref_path=Path(manifest_path).resolve().parent
    scenarios=set()
    for r in lines:
        p=Path(r['eventos'])
        if not p.is_absolute():p=ref_path/p
        obj=summary_object(p,proto,source)
        if obj['seed']!=r['seed']:raise AuditError(f'Semilla manifiesto distinta en {p}')
        scenarios.add(r['escenario'])
        sites=obj['site_metrics']
        available=[s for s in sites if s['difference_pp']['total'] is not None and
                   s['n_simulated_passages'] >= read_protocol(proto).get('minimum_sample_crossings',100)]
        # Score descriptivo: error absoluto porcentual en puntos; NO es una verosimilitud
        # ni estimación conductual. Penalización por conteos insuficientes -> sin score.
        score=(statistics.fmean(abs(s['difference_pp']['total']) for s in available)
               if len(available)==len(sites) else None)
        outputs.append({'escenario':r['escenario'],'seed':r['seed'],'events_file':str(p),
                'events_sha256':obj['input_sha256'],'n_sites':len(sites),
                'sites_with_sufficient_sim_exposure':len(available),
                'mean_absolute_difference_total_pp':score,
                'eligible_for_empirical_calibration':all(s['validation_status']=='VALIDATION_CANDIDATE' for s in sites),
                'indicators':sites,'speed':obj['speed_metrics']})
    group=defaultdict(list)
    for r in outputs:group[r['escenario']].append(r)
    aggregate=[]
    for scenario,ls in sorted(group.items()):
        ss=[v['mean_absolute_difference_total_pp'] for v in ls]
        same_n=len(ss)>0 and all(s is not None for s in ss)
        vals=[s for s in ss if s is not None]
        aggregate.append({'escenario':scenario,'n_seeds':len(ls),
            'n_complete_scores':len(vals),'mean_abs_error_pp':statistics.fmean(vals) if same_n else None,
            'min_abs_error_pp':min(vals) if same_n else None,
            'max_abs_error_pp':max(vals) if same_n else None,
            'calibration_eligible':same_n and all(v['eligible_for_empirical_calibration'] for v in ls)})
    status='ONLY_DESCRIPTIVE_CANDIDATE_COMPARISON'
    if aggregate and all(x['calibration_eligible'] for x in aggregate):status='CALIBRATION_SCREENING_ONLY'
    ret={'version':VERSION,'comparison_status':status,'source':str(Path(manifest_path).resolve()),
         'source_sha256':sha256(Path(manifest_path)),'protocol_sha256':sha256(Path(proto)),
         'candidate_rows':outputs,'scenario_summary':aggregate,
         'warning':'Puntaje descriptivo de diferencias agregadas; no identifica probabilidades individuales ni demuestra transferencia a Quito'}
    safe_write_json(output,ret)
    print('COMPARACIÓN:',status)
    for row in aggregate:
        print(row['escenario'],'semillas',row['n_seeds'], 'diferencia media pp:',row['mean_abs_error_pp'],
              'calibración elegible:',row['calibration_eligible'])
    return ret


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('auditar-fuentes')
    a.add_argument('--fuentes',default=str(REF),type=Path)
    c=sub.add_parser('comparar')
    c.add_argument('--eventos',type=Path,required=True)
    c.add_argument('--protocolo',type=Path,required=True)
    c.add_argument('--salida-dir',type=Path,required=True)
    multi=sub.add_parser('comparar-candidatos')
    multi.add_argument('--manifiesto',type=Path,required=True)
    multi.add_argument('--protocolo',type=Path,required=True)
    multi.add_argument('--salida-dir',type=Path,required=True)
    args=p.parse_args(argv)
    if args.cmd=='auditar-fuentes':
        t=validate_sources(args.fuentes,SITES,INDICATORS)
        print('FUENTES OK: Quito 3 sitios (4518+2716+2409=9643), 168 amarillo, 343 rojo;')
        print('velocidad Quito≈20% redondeado; todos los parámetros individuales null.')
        print('Fuente primarias:',t['sources']['Q01'],t['sources']['Q02'])
    elif args.cmd=='comparar':
        obj=summary_object(args.eventos,args.protocolo)
        dest=args.salida_dir
        dest.mkdir(parents=True,exist_ok=True)
        safe_write_json(dest/'reporte_comparacion_h09.json',obj)
        summarize_console(obj)
        print('REPORTE:',dest/'reporte_comparacion_h09.json')
    elif args.cmd=='comparar-candidatos':
        dest=args.salida_dir
        dest.mkdir(parents=True,exist_ok=True)
        compare_candidates(args.manifiesto,args.protocolo,dest/'comparacion_candidatos_h09.json')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (AuditError, FileNotFoundError, FileExistsError) as exc:
        print('AUDITORÍA DETENIDA:',exc,file=sys.stderr);sys.exit(2)
