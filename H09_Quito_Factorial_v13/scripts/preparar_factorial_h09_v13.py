#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepara tres archivos de configuración para un factorial H09 SxV (no ejecuta SUMO).

S: tolerancia experimental de semáforos; V: distribución de velocidad deseada.
Control placebo: nuevo vType con tau nominal explícito. Debe auditarse su
neutralidad en la salida; NO presuponer tráfico idéntico por tratarse de vType.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

PARAMS={
 'placebo': {'tau':1.0},
 'velocidad':{'speedFactor':1.15},
 'semaforos_velocidad': {'speedFactor':1.15,'jmDriveAfterYellowTime':1.5,'jmDriveAfterRedTime':0.5},
}
SUMO_PREVIOUS={'semaforos':{'jmDriveAfterYellowTime':1.5,'jmDriveAfterRedTime':0.5}}
ACK='EXPLORATORY_HYPOTHESES_NOT_CALIBRATED_QUITO'

def configs(directory):
    dest=Path(directory)
    if not dest.is_dir():raise FileNotFoundError(dest)
    paths={}
    for name,parameters in PARAMS.items():
        fp=dest/('perfil_'+name+'.json')
        if fp.exists():raise FileExistsError('Configuración ya existe: '+str(fp))
        payload={
            'version':'H09_FACTORIAL_SxV_v1.3',
            'evidence_status':ACK,
            'experiment_name':name,
            'note':'Hipótesis de sensibilidad SUMO; no calibrado con Quito. Se conserva demanda, red, semilla y cohorte de H09 v1.2.',
            'families':{'combinado':parameters}
        }
        fp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        paths[name]=fp
    return paths

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config-dir',type=Path,required=True)
    args=p.parse_args()
    paths=configs(args.config_dir)
    for name,fp in paths.items():print(f'{name}: {fp} SHA256={hashlib.sha256(fp.read_bytes()).hexdigest()}')
    print('SOLO CONFIGURACIONES, SUMO NO EJECUTADO')

if __name__=='__main__':main()
