#!/usr/bin/env python3
"""Run a Python H10 runner through a same-process read-only post-TraCI hook.

MUST point to NEW H10 result paths; never reuse v111/v112 pilot output directories.
Pass original H10 CLI arguments after '--'. Original H10 sources are NOT modified.
"""
import argparse
import datetime
import json
import runpy
import sys
from pathlib import Path
from h11_2_observador_pasivo import load_ids
from h11_2_bootstrap import install

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--runner',type=Path,required=True)
    p.add_argument('--condition',default='unspecified')
    p.add_argument('--seed',default='')
    p.add_argument('--vine-ids',type=Path)
    p.add_argument('--h09-ids',type=Path)
    p.add_argument('rest',nargs=argparse.REMAINDER)
    a=p.parse_args()
    root=a.root.resolve()
    runner=(a.runner if a.runner.is_absolute() else root/a.runner).resolve()
    if not runner.is_file(): raise FileNotFoundError(runner)
    if runner.suffix.lower()!='.py': raise ValueError('El runner H10 debe ser Python; no pasar .ps1')
    if not runner.is_relative_to(root):raise ValueError('El ejecutor debe estar bajo --root')
    if 'h11_2' in runner.name: raise ValueError('No instrumentar el propio H11.2')
    args=a.rest[1:] if a.rest and a.rest[0]=='--' else a.rest
    # We can't know H10 flags: require explicit args; fail closed if user forgets.
    if not args: raise ValueError('Faltan argumentos originales H10 después de --. No ejecutar con defaults desconocidos.')
    vine=load_ids(a.vine_ids)
    h09=load_ids(a.h09_ids)
    folder=root/'resultados'/('h11_2_ejecutado_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'launcher.json').write_text(json.dumps({'runner':str(runner),'condition':a.condition,
        'seed':a.seed,'runner_args':args,'roster_vine_size':len(vine),'roster_h09_size':len(h09),
        'warning':'Los argumentos H10 deben crear sus resultados en una carpeta NUEVA, sin sobrescribir históricos.'},indent=2),encoding='utf-8')
    print('H11.2: observación en sesión H10 existente (nuevo experimento)',flush=True)
    print('H11.2 telemetría:',folder/'telemetria',flush=True)
    old_argv=sys.argv[:]
    old_syspath=sys.path[:]
    old_cwd=Path.cwd()
    hook=None
    try:
        import os
        import traci
        hook=install(traci,folder/'telemetria',condition=a.condition,seed=a.seed,vine_ids=vine,h09_ids=h09)
        sys.path.insert(0,str(runner.parent))
        sys.argv=[str(runner),*args]
        os.chdir(root)
        runpy.run_path(str(runner),run_name='__main__')
    finally:
        if hook: hook.close()
        sys.argv=old_argv
        sys.path[:]=old_syspath
        import os
        os.chdir(old_cwd)
    if not (folder/'telemetria'/'manifest_h11_2.json').is_file():
        raise RuntimeError('H10 terminó sin ejecutar pasos TraCI detectados; revisar llamadas y flags.')
    print('H11.2 integrado OK:',folder,flush=True)

if __name__=='__main__':main()
