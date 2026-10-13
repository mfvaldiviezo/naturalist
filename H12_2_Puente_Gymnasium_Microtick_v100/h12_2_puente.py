#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.2 v1.0 — bridge reproducible 5 s RL / 0.5 s SUMO.

NO modifica los archivos del repositorio, ni los checkpoints ni H08/H09/H10/H11.
Construye una copia instrumentada con controles SHA en resultados/h12_2_*.
--pilot nominal: ejecuta un smoke test PPO/Gymnasium/SUMO corto.
--pilot probe|active: solo con hook externo explicito de la integracion H10,
                    no se activa automaticamente; H09 se introduce solo mediante
                    una configuracion SUMO preconstruida y verificada.

Un episodio de este paquete NO demuestra equivalencia cinemática POLIDriving,
resiliencia, ni fidelidad SOTA.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from typing import Any

VERSION = 'H12.2 Microtick Bridge v1.0.0'
REPO_TSC_REL = Path('tsc_framework/src/core/tsc_env.py')
EXPECTED_BLOB_SHA = '06095fe94125dcd8e2a7fdd9015740579a9da3ed'
FIXED_MICROTICK_S = 0.5
FIXED_RL_PERIOD_S = 5.0
RL_SUBSTEPS = 10

# Parche muy acotado, sujeto al hash de contenido original auditable.
P_STEP = '"--step-length", "1.0",  # El tick interno de SUMO DEBE ser 1s.'
Q_STEP = '"--step-length", "0.5",  # H12.2: microtick 0.5s; RL period permanece 5s.'
P_LOOP = 'for _ in range(self.delta_t):\n                traci.simulationStep()'
Q_LOOP = ('for _ in range(self.delta_t * 2):\n'
          '                traci.simulationStep()\n'
          '                self._h12_after_microtick(traci, self._step_count * self.delta_t * 2 + _)')
P_LOG = "self._sumo_log_path = self.sumocfg_path.with_suffix('.sumo.log')"
Q_LOG = 'self._sumo_log_path = Path(self._h12_log_path)  # H12.2, log aislado fuera del repo'


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def git_blob_sha(p: Path) -> str:
    # Git calcula el hash sobre LF cuando el archivo es texto y core.autocrlf lo normaliza.
    b = p.read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()


def exact_patch(source: str, git_sha: str) -> str:
    if git_sha.lower() != EXPECTED_BLOB_SHA:
        raise RuntimeError('FAIL-CLOSED: tsc_env.py difiere del commit auditado. No se parchea un codigo desconocido.')
    for old, new in ((P_STEP,Q_STEP),(P_LOOP,Q_LOOP),(P_LOG,Q_LOG)):
        if source.count(old) != 1:
            raise RuntimeError(f'FAIL-CLOSED: patron de parche ambiguo o ausente: {old[:100]!r}')
        source = source.replace(old, new, 1)
    ast.parse(source)
    return source


def audited_source_path(repo: Path) -> Path:
    p = (repo / REPO_TSC_REL).resolve()
    if not p.is_file():
        raise FileNotFoundError(f'No existe {p}')
    return p


def discover_local_h10(revision: Path) -> list[dict]:
    """Solo metadatos AST de scripts autorizados; NO lee POLIDriving RAW."""
    dirs = sorted([p for p in revision.iterdir() if p.is_dir() and
                   (p.name.startswith('H10_') or p.name.startswith('H08') or p.name.startswith('H09_'))])
    out = []
    for d in dirs[:15]:
        for py in sorted(d.glob('*.py'))[:45]:
            try:
                data = py.read_text(encoding='utf-8-sig')
                tree = ast.parse(data)
            except (UnicodeError, SyntaxError, OSError) as ex:
                out.append({'archivo': str(py.relative_to(revision)), 'parse':type(ex).__name__})
                continue
            defs = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    defs.append(node.name)
                    if isinstance(node, ast.ClassDef):
                        defs.extend(node.name + '.' + a.name + '(' + ','.join(arg.arg for arg in a.args.args) + ')'
                                    for a in node.body if isinstance(a, ast.FunctionDef)
                                    and a.name in ('__init__','on_step','step','on_microtick'))
            out.append({'archivo': str(py.relative_to(revision)), 'sha256': sha256(py),
                        'simbolos':defs[:80], 'parse':'OK'})
    return out


def input_manifest(cfg: Path) -> dict:
    """Verifica que dependencias declaradas existen; rechaza outputs SUMO implicitos."""
    cfg=cfg.resolve()
    if not cfg.is_file():
        raise FileNotFoundError(f'Archivo .sumocfg no encontrado: {cfg}')
    tree=ET.parse(cfg)
    root=tree.getroot()
    output=root.find('output')
    if output is not None and len(list(output)):
        raise RuntimeError('SUMOCFG posee etiquetas <output>: piloto no permite sobrescritura de salidas. Use uno sin outputs.')
    inputs=root.find('input')
    if inputs is None:
        raise RuntimeError('SUMOCFG carece de <input>.')
    res={'sumocfg':str(cfg), 'sha256_sumocfg':sha256(cfg), 'dependencies':{},'unresolved':[]}
    for tag in ('net-file','route-files','additional-files'):
        item=inputs.find(tag)
        if item is None:
            if tag in ('net-file','route-files'):
                raise RuntimeError('Falta entrada SUMO obligatoria: '+tag)
            continue
        for raw in item.get('value','').split(','):
            name=raw.strip().strip('"')
            if not name: continue
            p=Path(name)
            p=p if p.is_absolute() else cfg.parent/p
            p=p.resolve()
            if not p.is_file():
                res['unresolved'].append(str(p))
            else:
                res['dependencies'][str(p)] = sha256(p)
    if res['unresolved']:
        raise FileNotFoundError('Entradas SUMO ausentes: '+repr(res['unresolved']))
    return res


class GuardedVehicle:
    """Proxy mejor esfuerzo; solo setAcceleration en modo active. No sandbox de Python."""
    def __init__(self, vehicle, bridge):
        self._vehicle=vehicle
        self._bridge=bridge

    def setAcceleration(self, vid, value, duration):
        b=self._bridge
        if b.mode!='active':
            raise RuntimeError('WRITE-BLOCKED: setAcceleration requiere modo active.')
        if b.command_count >= b.max_commands:
            raise RuntimeError('FAIL-CLOSED: cuota de comandos H12.2 excedida.')
        if int(self._vehicle.getSpeedMode(vid)) !=31:
            raise RuntimeError('FAIL-CLOSED: vehicle speedMode distinto de 31.')
        val=float(value);dur=float(duration)
        if not math.isfinite(val) or not math.isfinite(dur) or abs(dur-b.microtick_s)>1.e-8:
            raise RuntimeError('FAIL-CLOSED: aceleracion/duracion no admisible.')
        self._vehicle.setAcceleration(vid,val,dur)
        b.command_count+=1
        b.command_records.append({'tick':b.tick,'time_s':b.last_time_s,'id':str(vid),
                                  'a_m_s2':val,'duration_s':dur})

    def __getattr__(self, name):
        if name.startswith(('set','change','add','remove','move','reroute','slowDown','openGap')):
            raise RuntimeError(f'WRITE-BLOCKED vehicle.{name}')
        return getattr(self._vehicle,name)


class ReadOnlyDomain:
    def __init__(self, obj, label):
        self._obj=obj; self._label=label
    def __getattr__(self,name):
        if name.startswith(('set','change','add','remove','move','reroute','slowDown')):
            raise RuntimeError(f'WRITE-BLOCKED {self._label}.{name}')
        return getattr(self._obj,name)


class HookTraCI:
    """Evita doble simulationStep en hooks; limita rutas de escritura conocidas."""
    def __init__(self,traci, bridge):
        self._traci=traci; self._bridge=bridge
        self.vehicle=GuardedVehicle(traci.vehicle,bridge)
    def simulationStep(self,*args,**kwargs):
        raise RuntimeError('DOUBLE-STEP-BLOCKED: solo Gymnasium avanza SUMO.')
    def __getattr__(self,name):
        if name in ('simulation','lane','trafficlight','junction','person','route','edge','inductionloop'):
            return ReadOnlyDomain(getattr(self._traci,name),name)
        if name in ('init','start','close','load','switch','getConnection','setOrder'):
            raise RuntimeError(f'CONNECTION-BLOCKED: traci.{name}')
        return getattr(self._traci,name)


class MicrotickBridge:
    def __init__(self, mode='nominal', hook=None, *, max_commands=100,
                 microtick_s=FIXED_MICROTICK_S, max_events=10000):
        if mode not in ('nominal','probe','active'):
            raise ValueError('Modo invalido')
        if mode!='nominal' and hook is None:
            raise ValueError('probe/active requieren hook explicito.')
        self.mode=mode;self.hook=hook;self.max_commands=int(max_commands)
        self.microtick_s=float(microtick_s);self.last_time_s=None
        self.tick=-1;self.command_count=0;self.command_records=[]
        self.microtick_rows=[];self.max_events=int(max_events)
        self.after_calls=0

    def after_microtick(self,traci, tick):
        self.tick=int(tick)
        sim=traci.simulation
        dt=float(sim.getDeltaT());time_s=float(sim.getTime())
        if not math.isfinite(dt) or abs(dt-self.microtick_s)>1.e-7:
            raise RuntimeError(f'TIM-FAIL: SUMO DeltaT real={dt}, esperado {self.microtick_s}')
        if self.last_time_s is not None and abs((time_s-self.last_time_s)-dt)>1.e-6:
            raise RuntimeError(f'TIM-FAIL: tiempo no monotono o doble paso: {self.last_time_s} -> {time_s}')
        self.last_time_s=time_s;self.after_calls+=1
        if len(self.microtick_rows)<self.max_events:
            self.microtick_rows.append({'tick':self.tick, 'time_s':time_s,'dt_s':dt})
        if self.hook is not None:
            if self.mode=='active':
                if int(sim.getCollidingVehiclesNumber()) >0 or int(sim.getStartingTeleportNumber())>0:
                    raise RuntimeError('SAFETY-HALT: colision o teleport antes de inyeccion.')
            view=HookTraCI(traci,self)
            fn=getattr(self.hook,'on_step',None) or getattr(self.hook,'on_microtick',None)
            if fn is None:
                fn=self.hook
            if not callable(fn):
                raise TypeError('Hook no expone on_step(traci,tick) ni es callable.')
            fn(view,self.tick)


def import_hook_factory(path: Path, factory_name: str, settings: dict):
    if not path.is_file():
        raise FileNotFoundError('Hook file inexistente: '+str(path))
    spec=importlib.util.spec_from_file_location('h12_2_external_hook_'+uuid.uuid4().hex,path)
    if spec is None or spec.loader is None:
        raise RuntimeError('No se puede importar la factoria del hook.')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    factory=getattr(mod,factory_name,None)
    if not callable(factory):
        raise TypeError('Factoria ausente/no callable: '+factory_name)
    hook=factory(**settings)
    if not callable(hook) and not callable(getattr(hook,'on_step',None)) and not callable(getattr(hook,'on_microtick',None)):
        raise TypeError('La factoria no devolvio hook compatible.')
    return hook


def make_output(revision: Path) -> Path:
    result_root=(revision/'resultados').resolve()
    if revision.resolve() not in result_root.parents:
        raise RuntimeError('Ruta de resultados fuera de revision_root.')
    result_root.mkdir(exist_ok=True)
    dst=result_root/('h12_2_microtick_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    dst.mkdir(exist_ok=False)
    return dst


def build_preflight(args) -> dict:
    repo=Path(args.repo_root).resolve();revision=Path(args.revision_root).resolve()
    source_path=audited_source_path(repo)
    gitsha=git_blob_sha(source_path)
    original=source_path.read_text(encoding='utf-8-sig')
    patched=exact_patch(original, gitsha)
    cfg=Path(args.sumocfg).resolve() if args.sumocfg else repo/'tsc_framework/sumo_configs/hangzhou.sumocfg'
    mi=input_manifest(cfg)
    if args.mode!='nominal' and not args.hook_file:
        raise RuntimeError('probe/active exigen --hook-file y --hook-factory; no se inventa la conexion H10.')
    if args.mode=='active' and args.ack_active!='EXPERIMENTAL_ONLY':
        raise RuntimeError('active exige --ack-active EXPERIMENTAL_ONLY')
    model=repo/'tsc_framework/outputs/models'/f'{args.model}.zip'
    if not model.is_file():
        raise FileNotFoundError('Checkpoint ausente: '+str(model))
    if not revision.is_dir():
        raise NotADirectoryError(str(revision))
    return {'version':VERSION,'repo':str(repo),'source':str(source_path),
            'source_git_blob_sha':gitsha,'patched_sha256':hashlib.sha256(patched.encode('utf-8')).hexdigest(),
            'model':args.model,'model_sha256':sha256(model),'sumo_input_manifest':mi,
            'h10_scripts':discover_local_h10(revision),
            'mode':args.mode,'microtick_s':0.5,'rl_period_s':5.,'macro_substeps':10,
            'planned_rl_steps':args.rl_steps,
            'caveats':['El código original del repo NO se modifica',
                       'Hook Vine/H09 no se conecta automáticamente; exige factoria explícita',
                       'El experimento no mide aun resiliencia de controladores',
                       'Los escenarios H11 no se comparan directamente sin igualar demanda/red/semilla',
                       'Sin calibracion empirica de jerk; no inferir representatividad Quito']}


def run_pilot(args, record: dict, out: Path) -> dict:
    repo=Path(record['repo']); tsc_root=repo/'tsc_framework'
    if str(tsc_root) not in sys.path:
        sys.path.insert(0,str(tsc_root))
    # Se necesita import de extractores antes de PPO.load para restaurar los modelos propios.
    from stable_baselines3 import PPO
    from src.rl_agent.sarg_policy import HSARGExtractor, CoopSARGExtractor  # noqa: F401
    import numpy as np

    source=Path(record['source']).read_text(encoding='utf-8-sig')
    edited=exact_patch(source,record['source_git_blob_sha'])
    overlay=out/'h12_2_tsc_env_overlay.py'
    overlay.write_text(edited,encoding='utf-8')
    spec=importlib.util.spec_from_file_location('h12_2_tsc_env_overlay_'+uuid.uuid4().hex,overlay)
    if spec is None or spec.loader is None:
        raise RuntimeError('No se puede cargar overlay.')
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)

    hook=None
    if args.mode!='nominal':
        settings=json.loads(args.hook_json)
        if not isinstance(settings,dict):
            raise ValueError('--hook-json debe contener un objeto JSON.')
        hook=import_hook_factory(Path(args.hook_file).resolve(), args.hook_factory, settings)

    bridge=MicrotickBridge(args.mode,hook,max_commands=args.max_commands)
    env=None
    model=PPO.load(str(tsc_root/'outputs/models'/f'{args.model}.zip'),device='cpu')
    assert model.observation_space.shape==(34,) and model.action_space.n==4
    outputs=[]; start=None
    try:
        env=module.TSCEnv(sumocfg_path=record['sumo_input_manifest']['sumocfg'],tls_id=args.tls_id,
                          delta_t=5,max_steps=args.rl_steps,seed=args.seed,enable_traci_chaos=False)
        env._h12_log_path=str(out/'sumo_stderr.log')
        env._h12_after_microtick=bridge.after_microtick
        obs,info=env.reset(seed=args.seed)
        start=float(module.traci.simulation.getTime())
        for decision in range(args.rl_steps):
            if tuple(obs.shape)!=(34,) or not np.isfinite(obs).all():
                raise RuntimeError('Observacion distinta de 34D o con NaN/inf.')
            if args.policy=='fixed':
                action=int((decision//5)%4)
            else:
                action,_=model.predict(obs,deterministic=True)
                action=int(np.asarray(action).reshape(-1)[0])
            prev=bridge.last_time_s if bridge.last_time_s is not None else start
            obs,reward,term,trunc,step_info=env.step(action)
            now=bridge.last_time_s
            if now is None or abs((now-prev)-FIXED_RL_PERIOD_S)>1.e-6:
                raise RuntimeError(f'TIM-FAIL: decision {decision} no avanzo 5s: {prev} -> {now}')
            outputs.append({'decision':decision,'action':action,'sim_time_s':now,
                            'reward':float(reward),'delay':float(step_info.get('delay',0)),
                            'gini':float(step_info.get('gini',0)),
                            'queue':float(step_info.get('total_queue',0)),
                            'cvar':float(step_info.get('cvar_alpha',0)),
                            'phase_age_s':float(step_info.get('phase_age',float('nan'))),
                            'terminated':bool(term),'truncated':bool(trunc)})
            if term or trunc:break
    finally:
        if env is not None:
            try:env.close()
            except Exception:pass
    if bridge.after_calls!=len(outputs)*RL_SUBSTEPS:
        raise RuntimeError('TIM-FAIL: conteo microticks distinto a 10 x decisiones.')
    return {'result':'SMOKE_OK','n_decisions':len(outputs),'n_microticks':bridge.after_calls,
            'first_time_s':start, 'last_time_s':bridge.last_time_s,
            'commands_setAcceleration':bridge.command_count,
            'mode':args.mode,'model':args.model,'policy':args.policy,
            'no_legacy_chaos_manager':True,
            'limitations':['Smoke test de integracion, no comparacion cientifica de resiliencia'],
            'decisions':outputs,'microticks':bridge.microtick_rows,
            'command_records':bridge.command_records}


def parser_args(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo-root',required=True,type=Path)
    ap.add_argument('--revision-root',required=True,type=Path)
    ap.add_argument('--sumocfg',type=Path,default=None)
    ap.add_argument('--model',choices=['ppo_ideal','ppo_chaos','ppo_coop_ideal','ppo_coop_chaos'],default='ppo_ideal')
    ap.add_argument('--policy',choices=['ppo','fixed'],default='ppo')
    ap.add_argument('--tls-id',default='B1')
    ap.add_argument('--seed',type=int,default=101)
    ap.add_argument('--rl-steps',type=int,default=4)
    ap.add_argument('--mode',choices=['nominal','probe','active'],default='nominal')
    ap.add_argument('--hook-file',type=Path)
    ap.add_argument('--hook-factory',default='create_hook')
    ap.add_argument('--hook-json',default='{}')
    ap.add_argument('--max-commands',type=int,default=100)
    ap.add_argument('--ack-active',default='')
    ap.add_argument('--pilot',action='store_true',help='Activa Smoke SUMO / Gymnasium en nueva carpeta de resultados.')
    ap.add_argument('--guardar-auditoria',action='store_true',help='Guarda solo preflight y descubrimiento AST H10.')
    args=ap.parse_args(argv)
    if not (1<=args.rl_steps<=20):
        ap.error('--rl-steps debe estar entre 1 y 20 (piloto limitado).')
    if args.max_commands<0:ap.error('--max-commands no negativo.')
    if args.mode=='active' and args.max_commands==0:ap.error('active requiere cuota positiva.')
    return args


def main(argv=None):
    args=parser_args(argv)
    report=build_preflight(args)
    print(f"H12.2 | source SHA: {report['source_git_blob_sha']} | modo={args.mode}")
    print(f"Gymnasium: delta_t=5s; microtick=0.5s; subpasos=10 por decision")
    print(f"H10/H08/H09 scripts descubiertos: {len(report['h10_scripts'])}; smoke={args.pilot}")
    print(f"Modelo: {report['model']} | checkpoint SHA: {report['model_sha256']}")
    if not args.pilot and not args.guardar_auditoria:
        print('PREFLIGHT OK. CERO escrituras. Para archivos: --guardar-auditoria; para piloto: --pilot.')
        return 0
    out=make_output(Path(args.revision_root).resolve())
    (out/'preflight_h12_2.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'h10_simbolos_h12_2.json').write_text(json.dumps(report['h10_scripts'], indent=2, ensure_ascii=False), encoding='utf-8')
    if args.pilot:
        try:
            pilot=run_pilot(args,report,out)
            (out/'smoke_h12_2.json').write_text(json.dumps(pilot,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
            print(f"SMOKE_OK: {pilot['n_decisions']} decisiones, {pilot['n_microticks']} microticks, "
                  f"{pilot['commands_setAcceleration']} comandos. Tiempo: {pilot['first_time_s']} -> {pilot['last_time_s']} s")
        except Exception as e:
            (out/'error_h12_2.json').write_text(json.dumps({'type':type(e).__name__,'message':str(e),
                'traceback':traceback.format_exc()},ensure_ascii=False,indent=2),encoding='utf-8')
            print('SMOKE_FALLO:',type(e).__name__,str(e),file=sys.stderr)
            print('INFORME:',out)
            return 2
    (out/'dictamen_h12_2.md').write_text(
        '# H12.2 — Contrato microtick y prueba de integración\n\n'
        + f"Fuente original Git SHA: `{report['source_git_blob_sha']}`\n\n"
        + 'El puente genera un overlay local auditado de TSCEnv y NO modifica el repositorio. '
          'Microtick: 0.5 s; 10 subpasos por decisión de 5 s.\n\n'
        + f'Modo: `{args.mode}`; smoke ejecutado: `{args.pilot}`. '
          'No demuestra fidelidad de Vine/H09 ni resiliencia de los controladores.\n',
        encoding='utf-8')
    print('INFORME:',out)
    return 0


if __name__=='__main__':
    sys.exit(main())
