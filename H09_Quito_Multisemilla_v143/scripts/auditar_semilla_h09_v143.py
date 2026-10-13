#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audita corrida H09 v1.4.3 y permite REANUDAR sin sobrescribir.
Audita tanto una corrida específica como el factorial completo por semilla.
"""
from __future__ import annotations
import argparse, importlib.util
from pathlib import Path


def load_comparator(path):
    if not path.is_file():raise FileNotFoundError(path)
    spec=importlib.util.spec_from_file_location('h09_factorial_v142',str(path))
    if spec is None or spec.loader is None:raise ImportError(path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def normalize_label(mod, label):
    """Acepta etiqueta factorial (S, V, SV) O nombre de carpeta del reanudador.

    Nunca usa el nombre solicitado como ruta directa: únicamente etiquetas
    autorizadas en RUNS, evitando alias arbitrarios y lecturas fuera del hito.
    """
    if label in mod.RUNS:
        return label
    reverse = {directory: alias for alias, directory in mod.RUNS.items()}
    if len(reverse) != len(mod.RUNS):
        raise ValueError('Configuración RUNS con carpetas duplicadas')
    if label in reverse:
        return reverse[label]
    raise ValueError(f'Etiqueta de escenario H09 desconocida: {label!r}')


def check_single(comparator,root,seed,label):
    mod=load_comparator(comparator)
    canonical=normalize_label(mod,label)
    run=mod.read_run(root,canonical)
    if int(run['seed'])!=seed:raise ValueError('Semilla interna errónea')
    if canonical not in ('baseline','probe'):
        if run['n_assigned']!=45 or run['n_seen']!=run['n_verified']:
            raise ValueError('Asignación/exposición inválida')
    if label!=canonical:
        print(f'ETIQUETA NORMALIZADA: {label} -> {canonical}',flush=True)
    print(f'CORRIDA CONSERVADA: seed={seed} {label}, '
          f'asignados={run["n_assigned"]}, vistos={run["n_seen"]}, verificados={run["n_verified"]}',flush=True)
    return run


def check_seed(comparator,root,seed):
    mod=load_comparator(comparator)
    result=mod.compare(root)
    if result['status']!='PLACEBO_BITWISE_IDENTICAL':
        raise ValueError(f'Semilla {seed}: placebo difiere de baseline')
    if int(result['seed'])!=seed:raise ValueError('Semilla interna errónea')
    if result['cohort_n']!=45:raise ValueError('No hay 45 asignados')
    print(f'SEMILLA VALIDADA: {seed} | PLACEBO_BITWISE_IDENTICAL | cohorte=45/300',flush=True)
    for x in result['exposure_warnings']:
        print(f'AVISO EXPOSICION: {x["scenario"]}: {x["n_selected_seen"]}/{x["n_assigned"]} '
              f'vistos, {x["n_verified"]} verificados, {x["n_never_seen"]} no vistos',flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparador',required=True,type=Path)
    p.add_argument('--root',required=True,type=Path)
    p.add_argument('--seed',required=True,type=int)
    p.add_argument('--label',default=None)
    a=p.parse_args()
    if a.label:check_single(a.comparador,a.root,a.seed,a.label)
    else:check_seed(a.comparador,a.root,a.seed)

if __name__=='__main__':main()
