#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H09 1.4: agregador multisemilla del factorial SxV.

Valida CADA semilla mediante el comparador estricto 1.3; exige placebo
bitwise idéntico al baseline y no sobrescribe archivos.
No usa valores individuales derivados de las observaciones de Quito.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from statistics import mean, stdev

LABELS=('baseline','probe','placebo','S','V','SV','combinado')
METRICS=('arrivals','mean_halted','mean_speed_kmh','speed_exceed_pct',
         'red_confirmed','yellow_confirmed','unknown','collisions','teleports',
         'crossings','speed_n')
FACTOR_METRICS=('arrivals','mean_halted','mean_speed_kmh','speed_exceed_pct',
                'red_confirmed','yellow_confirmed','unknown')

def load_comparator(path):
    path=Path(path).resolve()
    if not path.is_file():raise FileNotFoundError(path)
    spec=importlib.util.spec_from_file_location('h09_factorial_v13_comparator',str(path))
    if spec is None or spec.loader is None:raise ImportError(path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def finite(n):
    if n is None:return None
    v=float(n)
    if not math.isfinite(v):raise ValueError('Indicador no finito')
    return v

def aggregate(records):
    """Las comparaciones por semilla se suministran YA auditadas por v1.3."""
    if len(records)<2:raise ValueError('Mínimo dos semillas para resumir variabilidad')
    seeds=[int(r['seed']) for r in records]
    if len(seeds)!=len(set(seeds)):raise ValueError('Semillas duplicadas')
    if 101 not in seeds:raise ValueError('Falta semilla histórica 101')
    allcores={tuple(sorted(r['core_hashes'].items())) for r in records}
    if len(allcores)!=1:raise ValueError('Red, sumocfg o rutas originales distintos entre semillas')
    per_seed=[];paired=[];interactions=[];exposure_warnings=[]
    for run in sorted(records,key=lambda r:int(r['seed'])):
        seed=int(run['seed'])
        exposure_warnings.extend([{'seed':seed,**x} for x in run.get('exposure_warnings',[])])
        if run['status']!='PLACEBO_BITWISE_IDENTICAL':
            raise ValueError(f'El placebo difiere del baseline en seed {seed}: cancelar agregado')
        if run['cohort_n']!=45:raise ValueError('Cohorte distinta de 45')
        rows={x['label']:x for x in run['rows']}
        if set(rows)!=set(LABELS):raise ValueError('Faltan escenarios factoriales: '+str(set(LABELS)-set(rows)))
        if any(int(x['seed'])!=seed for x in rows.values()):raise ValueError('Semillas mezcladas dentro de corrida')
        if any(int(x['n_steps'])!=int(rows['baseline']['n_steps']) for x in rows.values()):
            raise ValueError('Duración diferente')
        for label in LABELS:
            x=rows[label]
            per_seed.append({'seed':seed,'label':label,'cohort_n':run['cohort_n'],
                **{k:finite(x[k]) for k in METRICS},
                'n_assigned':x['n_assigned'],'n_seen':x['n_seen'],'n_verified':x['n_verified'],
                'n_never_seen':x['n_never_seen'],'n_seen_total':x['n_seen_total'],
                'red_lower_pct':finite(x['red_rate_proxy_lower_pct']),
                'red_upper_pct':finite(x['red_rate_proxy_upper_pct'])})
        # Paired effects always use same-seed placebo, not independent groups.
        for label in ('S','V','SV','combinado'):
            paired.append({'seed':seed,'contrast':label+'_minus_placebo',
                **{k:finite(rows[label][k])-finite(rows['placebo'][k])
                   if finite(rows[label][k]) is not None and finite(rows['placebo'][k]) is not None
                   else None for k in FACTOR_METRICS}})
        inter={'seed':seed}
        for k in FACTOR_METRICS:
            vs=[finite(rows[lab][k]) for lab in ('SV','S','V','placebo')]
            inter[k]=vs[0]-vs[1]-vs[2]+vs[3] if all(v is not None for v in vs) else None
        interactions.append(inter)
    summary=[]
    for kind,rs,key_field in [('paired',paired,'contrast'),('factorial_interaction',interactions,None)]:
        groups=(sorted({r[key_field] for r in rs}) if key_field else ['SV_minus_S_minus_V_plus_placebo'])
        for group in groups:
            group_rows=[r for r in rs if key_field is None or r[key_field]==group]
            for metric in FACTOR_METRICS:
                vals=[float(r[metric]) for r in group_rows if r[metric] is not None]
                n=len(vals)
                if not n:continue
                summary.append({'kind':kind,'contrast':group,'metric':metric,'n_seeds':n,
                                'mean':mean(vals),'sd_across_seeds':stdev(vals) if n>1 else None,
                                'min':min(vals),'max':max(vals),
                                'positive_seeds':sum(v>0 for v in vals),
                                'negative_seeds':sum(v<0 for v in vals),
                                'zero_seeds':sum(v==0 for v in vals)})
    return {'status':'MULTISEED_DESCRIPTIVE_NOT_CALIBRATED',
        'n_seeds':len(seeds),'seeds':sorted(seeds),
        'core_hashes':dict(allcores.pop()),
        'per_seed':per_seed,'paired_differences':paired,'interactions':interactions,'summary':summary,
        'exposure_warnings':exposure_warnings,
        'limitations':[
          'Semillas únicas repetidas para demanda fija; no replicaciones independientes de ciudades.',
          'Factorial aplicado a 15% de cohorte seleccionada según cada seed.',
          'Interacciones son contrastes descriptivos, no significación o causalidad general.',
          'Amarillo no equivale necesariamente a infracción.',
          'Red confirmado y unknown no convierten eventos en oportunidades condicionadas.',
          'Los intervalos lower/upper de rojo son extremos lógicos, NO IC estadísticos.',
          'Porcentaje de exceso corresponde a muestras, no porcentaje de conductores.',
          'Los avisos de frenado de emergencia SUMO NO se cuentan en el CSV actual.',
          'Sin calibración de probabilidades individuales ni equivalencia de protocolos con Quito.',
          'Vine Student no está activado en este experimento.',
          '45 asignados no implica 45 observados: reportar n_seen y n_verified por escenario.']}

def dump_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        cols=list(rows[0].keys())
        wr=csv.DictWriter(f,fieldnames=cols);wr.writeheader();wr.writerows(rows)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed101-root',type=Path,required=True)
    p.add_argument('--multiseed-root',type=Path,required=True)
    p.add_argument('--additional-seeds',default='102,103,104,105')
    p.add_argument('--comparador-v13',type=Path,required=True)
    p.add_argument('--output-prefix',type=Path,required=True)
    args=p.parse_args(argv)
    try:additional=[int(x) for x in args.additional_seeds.split(',')]
    except ValueError as exc:raise ValueError('Semillas inválidas') from exc
    if not additional or len(additional)!=len(set(additional)) or 101 in additional:
        raise ValueError('Semillas adicionales duplicadas/vacías/101 repetido')
    targets=[(101,args.seed101_root)]+[(seed,args.multiseed_root/f'seed_{seed}') for seed in additional]
    validator=load_comparator(args.comparador_v13)
    records=[]
    for seed,root in targets:
        print('AUDITANDO SEMILLA:',seed,'CARPETA:',root,flush=True)
        result=validator.compare(root)
        if int(result['seed'])!=seed:raise ValueError(f'Semilla esperada {seed} no coincide')
        records.append(result)
    result=aggregate(records)
    paths={ext:Path(str(args.output_prefix)+ext) for ext in ('.json','_por_semilla.csv','_contrastes.csv','_interacciones.csv','_resumen.csv')}
    if any(path.exists() for path in paths.values()):
        raise FileExistsError('Salida existente: '+str([str(x) for x in paths.values() if x.exists()]))
    args.output_prefix.parent.mkdir(parents=True,exist_ok=True)
    paths['.json'].write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    for ext,key in [('_por_semilla.csv','per_seed'),('_contrastes.csv','paired_differences'),('_interacciones.csv','interactions'),('_resumen.csv','summary')]:
        dump_csv(paths[ext],result[key])
    print('ESTADO:',result['status'],'SEMILLAS:',result['seeds'])
    for row in result['summary']:
        if row['metric'] in ('arrivals','yellow_confirmed','red_confirmed'):
            print(row['kind'],row['contrast'],row['metric'],'media=',round(row['mean'],5),
                  'rango=',[round(row['min'],5),round(row['max'],5)])
    print('REPORTES:',*[str(x) for x in paths.values()])

if __name__=='__main__':main()
