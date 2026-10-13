#!/usr/bin/env python3
"""Optional 20-step smoke test in isolated SUMO nominal, NOT integrated H10.
Uses same SUMO .sumocfg, seed and 0.5s; writes only NEW H11 folder.
"""
import argparse
import shutil
from pathlib import Path
from h11_2_observador_pasivo import PassiveObserver

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--cfg',type=Path,default=Path('resultados/ntvc_vine_r_07_hangzhou_piloto/hangzhou_vine_sin_additional.sumocfg'))
    p.add_argument('--steps',type=int,default=20)
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    root=args.root.resolve()
    cfg=(args.cfg if args.cfg.is_absolute() else root/args.cfg).resolve()
    out=(args.out if args.out.is_absolute() else root/args.out).resolve()
    if root not in out.parents or root/'resultados' not in out.parents:
        raise ValueError('--out debe estar dentro de root/resultados en una carpeta nueva')
    if not cfg.is_file(): raise FileNotFoundError(cfg)
    if args.steps<1: raise ValueError('steps>=1')
    sumo=shutil.which('sumo')
    if not sumo: raise RuntimeError('SUMO no encontrado en PATH')
    import traci
    out.mkdir(parents=True,exist_ok=False)
    command=[sumo,'-c',str(cfg),'--seed',str(args.seed),'--step-length','0.5',
             '--output-prefix',str(out/'sumo_'),'--no-step-log']
    traci.start(command)
    try:
        with PassiveObserver(out/'telemetria',condition='nominal-smoke-not-H10',seed=args.seed) as obs:
            for step in range(args.steps):
                traci.simulationStep()
                obs.on_step(traci,step)
    finally:
        traci.close()
    print('H11.2 SMOKE OK:',out)
    print('NOTA: corrida nominal independiente, no evalua H10 ni demuestra invariancia histórica.')

if __name__=='__main__':main()
