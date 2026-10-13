#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H09 v1.5, nuevo experimento con denominadores de oportunidad.

Por defecto PLANIFICA (no ejecuta SUMO). --ejecutar-corridas exige acuse.
Crea 5 seeds * (baseline + combinado 15/30/50) = 20 NUEVAS observaciones
para armonizar el instrumento. REUTILIZA las corridas antiguas como patrón
SHA-256 de invariancia para 0% y 15%; no las sobrescribe.
Reanudable: verifica cada salida antes de omitirla. Fallo cerrado ante parcial.
"""
from __future__ import annotations
import argparse,os,subprocess,sys,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PKG=HERE.parent
sys.path.insert(0,str(HERE))
from reportar_h09_v15 import SEEDS,PCTS,scan_run,oldfolder,readjson,summarize,main as report_main

ACK='ENTIENDO_EXPERIMENTO_EXPLORATORIO_NO_CALIBRADO'

def get_paths(root):
    root=Path(root).resolve()
    return {'root':root,
        'cfg':root/'resultados/ntvc_vine_r_07_hangzhou_piloto/hangzhou_vine_sin_additional.sumocfg',
        'zones':root/'resultados/h09_zonas_velocidad_generadas_v11.json',
        'runner':root/'H09_Quito_Perfiles_Contextuales_v12/scripts/piloto_perfiles_h09_v12.py',
        'profile':root/'H09_Quito_Perfiles_Contextuales_v12/config/escenarios_exploratorios.json',
        'observer':root/'H09_Quito_Sensibilidad_v15/instrumentacion',
        'old101':root/'resultados/h09_v12_piloto_101',
        'oldmulti':root/'resultados/h09_v14_multisemilla',
        'out':root/'resultados/h09_v15_sensibilidad_oportunidades'}

def preflight(p):
    for key in ('cfg','zones','runner','profile'):
        if not p[key].is_file():raise FileNotFoundError(f'Falta {key}: {p[key]}')
    if not (p['observer']/'observador_traci_h09_v11.py').is_file():raise FileNotFoundError('Falta adaptador observador v1.5')
    if not (p['root']/'H09_Quito_Instrumentacion_v11/scripts/observador_traci_h09_v11.py').is_file():
        raise FileNotFoundError('Falta observador heredado v1.1')
    for seed in SEEDS:
        for pct in (0,15):
            old=oldfolder(p['old101'],p['oldmulti'],seed,pct)
            if not (old/'manifest_H09.json').is_file():raise FileNotFoundError('Falta resultado histórico: '+str(old))
    return True

def dirname(pct):return 'baseline' if pct==0 else f'active_{pct}_combinado'

def cmd_for(p,seed,pct):
    dest=p['out']/f'seed_{seed}'/dirname(pct)
    argv=[sys.executable,str(p['runner']),'--sumocfg',str(p['cfg']),
         '--seed',str(seed),'--pasos','600','--step-length','0.5',
         '--sites','B1,B2,C1','--zonas-velocidad',str(p['zones']),
         '--instrument-dir',str(p['observer']),'--modo','baseline' if pct==0 else 'active',
         '--porcentaje',str(pct),'--familia','combinado','--output',str(dest)]
    if pct:argv+=['--ack-active','ESCENARIO_EXPLORATORIO_NO_CALIBRADO']
    return dest,argv

def run(p,execute=False):
    preflight(p)
    plans=[]
    for seed in SEEDS:
        for pct in PCTS:
            dest,argv=cmd_for(p,seed,pct)
            old=oldfolder(p['old101'],p['oldmulti'],seed,pct) if pct in (0,15) else None
            if dest.exists():
                # Si la carpeta EXISTE, no omitir una corrida parcial o corrupta.
                if not (dest/'manifest_H09.json').is_file():
                    raise RuntimeError('Salida parcial existente; no se sobrescribe: '+str(dest))
                scan_run(dest,seed,pct,old)
                print('REUTILIZANDO Y AUDITANDO',seed,pct,str(dest),flush=True)
            else:
                plans.append((seed,pct,dest,argv))
    if not execute:
        print('PLAN H09 v1.5:',len(plans),'corridas nuevas,',len(SEEDS)*len(PCTS)-len(plans),'reutilizables')
        for seed,pct,dest,_ in plans:print('PENDIENTE',seed,pct,str(dest))
        return len(plans)
    for seed,pct,dest,argv in plans:
        print('\nINICIANDO H09 v1.5',seed,pct,flush=True)
        subprocess.run(argv,check=True,cwd=p['root'])
        old=oldfolder(p['old101'],p['oldmulti'],seed,pct) if pct in (0,15) else None
        scan_run(dest,seed,pct,old)
        print('CORRIDA VALIDADA',seed,pct,'; no se reescriben archivos',flush=True)
    prefix=p['out']/'h09_v15_101_105'
    report_args=['--root',str(p['out']),'--old101',str(p['old101']),
                 '--oldmultiseed',str(p['oldmulti']),'--output-prefix',str(prefix)]
    if prefix.with_suffix('.json').exists():
        raise FileExistsError('Reporte ya existe; no se sobrescribe '+str(prefix))
    report_main(report_args)
    return len(plans)

def main(argv=None):
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--root',type=Path,default=Path.cwd())
    a.add_argument('--ejecutar-corridas',action='store_true')
    a.add_argument('--ack',default='')
    args=a.parse_args(argv)
    if args.ejecutar_corridas and args.ack!=ACK:
        a.error('Requiere --ack '+ACK)
    print('H09 v1.5 SOLO OBSERVADOR + PERFILES EXPLORATORIOS; SIN VINE; SIN CALIBRACION QUITO')
    run(get_paths(args.root),execute=args.ejecutar_corridas)

if __name__=='__main__':main()
