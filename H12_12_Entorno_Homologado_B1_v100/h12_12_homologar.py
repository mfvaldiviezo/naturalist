"""H12.12 CLI: inspección, congelación y smoke SUMO del nuevo contrato B1.

python h12_12_homologar.py --revision-root . --repo-root ... --mode plan
python h12_12_homologar.py --revision-root . --repo-root ... --mode freeze
python h12_12_homologar.py --revision-root . --repo-root ... --mode smoke --ack-new-contract NEW_MODEL_REQUIRED --ack-online-control TLS_OVERRIDE
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback
import uuid

from h12_12_contract import ContractError, read_geometry, require, sha256_file

CONTRACT_ID = 'H12_12_B1_GREEN2_OBS34_V100'
ROOT = Path(__file__).resolve().parent


def parser():
    p=argparse.ArgumentParser(description='H12.12: contrato B1 homologado, totalmente separado de checkpoints heredados')
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--revision-root',type=Path,required=True)
    p.add_argument('--mode',choices=['plan','freeze','smoke'],default='plan')
    p.add_argument('--net-file',default='tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml')
    p.add_argument('--route-file',default='tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml')
    p.add_argument('--tls-id',default='B1')
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--rl-steps',type=int,default=12)
    p.add_argument('--min-green',type=float,default=10.0)
    p.add_argument('--binary',default='sumo')
    p.add_argument('--ack-new-contract',default='')
    p.add_argument('--ack-online-control',default='')
    return p


def resolve_input(repo:Path, value:str):
    file=Path(value)
    return (file if file.is_absolute() else repo/file).resolve(strict=True)


def plan(args):
    repo=args.repo_root.resolve(strict=True)
    revision=args.revision_root.resolve(strict=True)
    require(args.tls_id=='B1', 'H12.12 v100 es estrictamente B1')
    require(args.rl_steps>=1 and args.rl_steps<=720,'--rl-steps debe ser 1..720')
    require(5.0<=args.min_green<=120.0,'--min-green debe ser 5..120s')
    require(args.seed>=0, 'Semilla debe ser >=0')
    net=resolve_input(repo,args.net_file)
    route=resolve_input(repo,args.route_file)
    require(net != route,'Red y rutas deben ser distintos archivos')
    require(route.name.endswith('.rou.xml'),'Se requiere archivo .rou.xml')
    # Asegurar que el XML de rutas es bien formado. No se infiere validación de trayectorias.
    import xml.etree.ElementTree as ET
    with open(route,'rb') as f:
        header=f.read(2048).upper()
    require(b'<!DOCTYPE' not in header and b'<!ENTITY' not in header,
            'DTD/ENTITY no admitidas en demanda')
    require(ET.parse(route).getroot().tag=='routes','Archivo rutas no tiene raíz <routes>')
    geo=read_geometry(net,args.tls_id)
    require(geo.green_indices == (0,2),
            f'B1 de Hangzhou esperado verdes (0,2), detectado {geo.green_indices}')
    require(len(geo.lanes_in)==4,
            f'B1 Hangzhou exige 4 carriles reales, detectado {len(geo.lanes_in)}')
    codepaths = [ROOT/'h12_12_contract.py',ROOT/'h12_12_env.py',ROOT/'h12_12_homologar.py']
    origpaths = [repo/'tsc_framework/src/core/tsc_env.py',
                 repo/'tsc_framework/scripts/train.py',
                 repo/'tsc_framework/config/default_config.yaml']
    require(all(p.exists() for p in codepaths+origpaths),'Faltan archivos de contrato o fuentes de referencia')
    checksums = {str(p):sha256_file(p) for p in [net,route,*codepaths,*origpaths]}
    planned = {
        'hito':'H12.12', 'schema':CONTRACT_ID,
        'scope':'NEW_MODEL_REQUIRED; no cargar PPO heredados con action_space=Discrete(4)',
        'tls_id':'B1', 'seed':args.seed, 'network':str(net), 'routes':str(route),
        'sources_sha256':checksums,
        'network_contract':geo.as_json(),
        'simulation':{'microtick_seconds':0.5,'decision_seconds':5.0,
                      'rl_steps':args.rl_steps,'min_green_seconds':args.min_green,
                      'start_seconds':0,'horizon_seconds':args.rl_steps*5.0,
                      'sumo_mode':'online via setRedYellowGreenState; remaining TLS original actuated',
                      'yellow_min_seconds':3.0,
                      'all_red':'Solo si existe en el programa; Hangzhou B1 actual no contiene rojo total explícito',
                      'traffic_demand_xml':'fixed explicit route file; --seed fixed',
                      'original_tls_program_type':geo.original_program_type},
        'observation':{
            'shape':[34], 'dtype':'float32', 'range':[0,1],
            'queue_12':'real incoming lanes in sorted stable order; zero-pad to 12; per-lane halted/MAX_QUEUE50',
            'wait_12':'real incoming lanes in sorted stable order; zero-pad to 12; per-lane waiting/MAX_WAIT300',
            'pressure_4':'for each inbound lane count_in - mean(unique connected downstream lane counts); transform 0.5+pressure/100 and clip to 0..1; inactive pad=0.5',
            'phase_4':'green onehot physical action (n=2); yellow gives all zeros',
            'age_2':'clipped stage_elapsed/120 and clipped stage_elapsed/min_green',
            'lane_order':list(geo.lanes_in),'downstream':dict(geo.lane_out_by_in)},
        'actions':{'type':'Discrete(2)', 'map':dict((str(i),idx) for i,idx in enumerate(geo.green_indices)),
                   'phase_switch':'original net.xml green -> yellow 3 s -> green; min green enforced',
                   'online_control':'explicit states (never direct setPhase green jump)',
                   'conflict_geometry':'NO CERTIFICADA fuera de estados del programa de red'},
        'reward':{'componentes':['delay_norm','gini','cvar95_norm'],
                  'weights':[0.4,0.3,0.3], 'units':'normalized on REAL input lanes only',
                  'gini_on_no_wait':0.0,'cvar95':'top ceil(5% of actual lanes) mean'},
        'evaluation_gates':{'seed_pairing':'required in H12.13',
                            'training_budget_equal':'required in H12.13',
                            'multi_tls':'NOT implemented H12.12',
                            'vine_h09_hook':'NOT implemented H12.12',
                            'cross_city':'NOT validated',
                            'new_checkpoints':'NOT produced'},
        'provenance':{'source':'repositorio local; XML y fuentes SHA verificados al correr',
                      'training_historical':'NOT CERTIFIED'},
        'platform':{'python':sys.version.split()[0],'os':platform.platform()},
    }
    return planned


def unique_dir(revision:Path):
    root=revision/'resultados'
    root.mkdir(exist_ok=True)
    out=root/('h12_12_homologado_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(exist_ok=False)
    return out


def write_json_unique(path,obj):
    require(not Path(path).exists(),'Sin sobrescribir artefactos')
    with open(path,'x',encoding='utf8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')


def main():
    p=parser()
    a=p.parse_args()
    try:
        manifest=plan(a)
        g=manifest['network_contract']
        print(f"H12.12 CONTRATO VALIDADO | tls=B1 | carriles reales {len(g['lanes_in'])} | verdes {g['green_indices']} | acciones=2 | fases={len(g['phases'])}")
        print('RUTAS_SHA256',manifest['sources_sha256'][manifest['routes']])
        print('RED_SHA256',manifest['sources_sha256'][manifest['network']])
        if a.mode=='plan':
            print('H12_12_PLAN_OK: sin SUMO, sin resultados nuevos, checkpoints intactos.')
            return 0
        if a.mode=='smoke':
            require(a.ack_new_contract=='NEW_MODEL_REQUIRED',
                    'Smoke requiere --ack-new-contract NEW_MODEL_REQUIRED')
            require(a.ack_online_control=='TLS_OVERRIDE',
                    'Smoke requiere --ack-online-control TLS_OVERRIDE')
        out=unique_dir(a.revision_root.resolve())
        write_json_unique(out/'manifiesto_h12_12.json',manifest)
        if a.mode=='freeze':
            print('H12_12_FREEZE_OK',out)
            return 0
        from h12_12_env import TSCEnvHomologado
        import numpy as np
        require(shutil.which(a.binary) is not None,'No se encontró SUMO en PATH')
        import gymnasium
        import traci
        import numpy
        manifest['runtime']={'sumo_version':subprocess.run([a.binary,'--version'],capture_output=True,text=True,timeout=10).stdout.splitlines()[:2],
                             'gymnasium':gymnasium.__version__,
                             'numpy':numpy.__version__,
                             'traci_module':str(Path(traci.__file__).resolve())}
        write_json_unique(out/'runtime_h12_12.json',manifest['runtime'])
        env=TSCEnvHomologado(net_file=manifest['network'],route_file=manifest['routes'],
                             sumocfg_file=out/'sumo_h12_12.sumocfg',output_dir=out,
                             tls_id='B1',seed=a.seed,max_rl_steps=a.rl_steps,
                             min_green_s=a.min_green,binary=a.binary)
        try:
            obs,info=env.reset()
            rows=[]
            for k in range(a.rl_steps):
                # Patrón sintético controlado: green0 durante 20 s, green1 20 s, green0...
                # NO representa PPO ni pretende optimizar tráfico.
                action=(k//4)%env.action_space.n
                obs,reward,terminated,truncated,info=env.step(action)
                require(env.observation_space.contains(obs),'Salió un estado inválido')
                rows.append({**info,'observation_34':obs.tolist(),'reward':reward})
            require(len(rows)==a.rl_steps,'Horizonte no ejecutado')
            # Postflight: fallar si la red, demanda o fuente cambiaron durante SUMO.
            for source, before in manifest['sources_sha256'].items():
                require(sha256_file(source)==before, 'Fuente modificada durante smoke: '+source)
            require(env.action_space.n==2,'Acciones físicas inconsistentes')
            # Si horizonte >=45 s, debe haber registrado al menos un ámbar de 3 s.
            if a.rl_steps>=9:
                require(any(e['kind']=='yellow' for e in env.events),'Ámbar no observado en smoke')
            report={'result':'H12_12_SUMO_SMOKE_OK','steps':len(rows),
                    'microticks':env._tick_idx,'tls_events':env.events,
                    'info_reset':{'tls':'B1','actions':2,'obs_shape':[34]},
                    'data':rows,'manifest_sha256':sha256_file(out/'manifiesto_h12_12.json')}
            write_json_unique(out/'smoke_h12_12.json',report)
            print('H12_12_SUMO_SMOKE_OK',f'decisiones={len(rows)}',
                  f'microticks={env._tick_idx}',f'intercambios_tls={len(env.events)-1}',out)
            return 0
        finally:
            env.close()
    except Exception as exc:
        print('H12_12_FAIL_CLOSED:',type(exc).__name__,str(exc),file=sys.stderr)
        if 'out' in locals():
            try:
                write_json_unique(out/'ERROR_h12_12.json',
                    {'error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc()})
                print('DIAGNOSTICO:',out/'ERROR_h12_12.json',file=sys.stderr)
            except Exception:
                pass
        return 2


if __name__=='__main__':
    raise SystemExit(main())
