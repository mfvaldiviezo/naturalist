#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.11: auditoria offline de contratos y metadatos PPO, SIN ejecutar fuentes.

Sin SUMO, sin importacion de modulos de tesis, sin cargar pesos, sin pickle.
Los metadatos SB3 ZIP NO demuestran por si solos procedencia historica.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import uuid
import zipfile

MODELS=('ppo_ideal','ppo_chaos','ppo_coop_ideal','ppo_coop_chaos')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for buf in iter(lambda:f.read(1048576),b''): h.update(buf)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def as_int(value):
    if isinstance(value,bool):return None
    try:
        v=int(value)
        return v if (isinstance(value,int) or str(value).strip()==str(v)) and v>=0 else None
    except (ValueError,TypeError):return None


def sb3_metadata(path):
    """Only inspect JSON 'data'; NEVER unpickle or import checkpoint content."""
    path=Path(path)
    if not path.is_file():return {'available':False,'relative_file':path.name}
    info={'available':True,'file':str(path),'sha256':digest(path),'size_bytes':path.stat().st_size}
    with zipfile.ZipFile(path,'r') as z:
        members=z.namelist()
        if len(set(members))!=len(members):raise ValueError('ZIP entradas duplicadas: '+str(path))
        if 'data' not in members:raise ValueError('ZIP SB3 sin data JSON: '+str(path))
        if z.getinfo('data').file_size>4_000_000:raise ValueError('data ZIP excesivamente grande')
        meta=json.loads(z.read('data').decode('utf-8'))
        if not isinstance(meta,dict):raise ValueError('data SB3 invalido')
        for key in ('num_timesteps','_total_timesteps','n_envs','n_steps','batch_size','n_epochs','ent_coef','gamma','gae_lambda','seed','policy_kwargs'):
            value=meta.get(key)
            if isinstance(value,(str,float,int,bool,type(None))):
                info[key]=value if not isinstance(value,str) or len(value)<=300 else value[:300]+'...'
            elif isinstance(value,dict):
                info[key]='JSON object present (contents omitted)'
            else:
                info[key]=None
        info['member_count']=len(members)
        info['data_sha256']=hashlib.sha256(z.read('data')).hexdigest()
        info['num_timesteps']=as_int(meta.get('num_timesteps'))
    return info


def locate_features(source):
    """Read-only AST survey: descriptive flags, not proof of executed training path."""
    tree=ast.parse(source)
    methods={}
    for node in ast.walk(tree):
        if isinstance(node,ast.FunctionDef):
            methods[node.name]=ast.get_source_segment(source,node) or ''
    getstate=methods.get('_get_state','')
    loadtls=methods.get('_load_tls_metadata','')
    step=methods.get('step','')
    launcher=methods.get('_launch_sumo','')
    return {
        'state_shape_34_present':'self._obs_dim = 34' in source,
        'state_age_first_unclipped':'phase_age_s / self.cfg.MAX_PHASE_AGE' in getstate and 'tau_norm' in getstate,
        'outgoing_empty_placeholder':'self._outgoing_lanes = []' in loadtls,
        'controlled_lane_padding_last':'unique_lanes[-1]' in loadtls,
        'action_maps_modulo_phases':'action % len(self._green_phases)' in step,
        'direct_traci_setPhase':'traci.trafficlight.setPhase' in step,
        'sumo_train_step_length_1s':'"--step-length", "1.0"' in launcher,
        'age_box_normalization_warning':'high=1.0' in source and 'phase_age_s / self.cfg.MAX_PHASE_AGE' in getstate,
    }


def locate_training(source):
    tree=ast.parse(source)
    methods={n.name:ast.get_source_segment(source,n) or '' for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
    make=methods.get('make_env',''); main=methods.get('main','')
    # Distinguish the presence of computed weights from their injection into env_config.
    envconfig=make[make.find('env_config ='):make.find('env = TSCEnv')] if 'env_config =' in make else ''
    return {
        'training_program_constructs_TSCEnv':'env = TSCEnv(**env_config)' in make,
        'training_uses_random_xml_flag':'<random value="true"/>' in make,
        'training_route_selection_sorted':'sorted(route_dir.glob("*.rou.xml"))' in main,
        'training_does_not_pass_reward_weights':'"reward_weights"' not in envconfig and "'reward_weights'" not in envconfig,
        'training_can_enable_legacy_chaos':'enable_traci_chaos=args.chaos' in main,
        'training_cli_supports_extractor':'--extractor' in source,
        'training_script_has_configurable_total_timesteps':'--timesteps' in source,
    }


def load_audits(repo,h129,h1210):
    envpath=repo/'tsc_framework/src/core/tsc_env.py'
    trainpath=repo/'tsc_framework/scripts/train.py'
    if not envpath.is_file() or not trainpath.is_file():raise FileNotFoundError('Faltan fuentes TSCEnv/train.py del repositorio')
    n=read_json(h129/'nominal/piloto_h12_5.json')
    p=read_json(h129/'probe/piloto_h12_5.json')
    a=read_json(h129/'active/piloto_h12_5.json')
    policy=read_json(h1210/'dictamen_h12_10.json')
    if policy.get('status')!='H12_10_POLITICA_OFFLINE_OK':raise ValueError('H12.10 no aprobado')
    if (n.get('model'),p.get('model'),a.get('model'),policy.get('model'))!=('ppo_ideal',)*4:
        raise ValueError('Modelo de H12.9/H12.10 inconsistente')
    if any(x.get('n_decisions')!=60 or x.get('n_microticks')!=600 for x in (n,p,a)):
        raise ValueError('H12.9 incompleto')
    if n.get('trace_sha256')!=p.get('trace_sha256') or n.get('trace_sha256')==a.get('trace_sha256'):
        raise ValueError('Invariancia nominal/probe o perturbacion activa no acreditada')
    if n.get('checkpoint_sha256')!=policy.get('checkpoint_sha256'):
        raise ValueError('Checkpoint distinto entre experimentos y auditoria')
    if policy.get('states_different')!=39 or policy.get('decisions')!=60:
        raise ValueError('Resumen H12.10 inesperado; revisar version antes de afirmar hallazgos')
    return {'model':n['model'],'checkpoint_sha256':n['checkpoint_sha256'],'policy':policy,
            'env':{'path':str(envpath),'sha256':digest(envpath),'flags':locate_features(envpath.read_text(encoding='utf-8-sig'))},
            'training':{'path':str(trainpath),'sha256':digest(trainpath),'flags':locate_training(trainpath.read_text(encoding='utf-8-sig'))}}


def build(repo,h129,h1210):
    d=load_audits(repo,h129,h1210)
    models={name:sb3_metadata(repo/'tsc_framework/outputs/models'/f'{name}.zip') for name in MODELS}
    if not models['ppo_ideal']['available']:raise FileNotFoundError('Falta checkpoint ppo_ideal')
    if models['ppo_ideal']['sha256']!=d['checkpoint_sha256']:
        raise ValueError('SHA256 checkpoint PPO ideal no coincide con H12.9/H12.10')
    ts=[models[m].get('num_timesteps') for m in MODELS]
    ratio=(ts[2]/ts[0] if ts[0] and ts[2] else None)
    p=d['policy']
    if p.get('policy_probs_different_among_changed_states')!=39 or p.get('actions_different')!=0:
        raise ValueError('H12.10 no coincide con hallazgos esperados')
    report={'status':'H12_11_PROVENIENCIA_DIAGNOSTICADA','checkpoint_training_certified':False,
       'experimental_status':'SOLO_DIAGNOSTICO_OFFLINE','version':'H12.11-v1.0.0',
       'model':d['model'],'env':d['env'],'training':d['training'],'checkpoints':models,
       'coop_ideal_to_ideal_timesteps_ratio':ratio,
       'policy_summary':{key:p.get(key) for key in ('decisions','states_different','policy_probs_different_among_changed_states','actions_different','max_total_variation','mean_total_variation_on_changed_states','mean_entropy_nominal_nats','mean_entropy_active_nats','min_argmax_margin_nominal','min_argmax_margin_active','observation_box_mismatch','action_to_physical_phase')},
       'max_entropy_4_actions_nats':math.log(4),
       'entropy_fraction_max_nominal':p['mean_entropy_nominal_nats']/math.log(4),
       'unproven':[
           'ZIP SB3 no contiene obligatoriamente ruta de demanda usada para entrenar ni SHA de archivo .rou.xml',
           'ZIP SB3 no certifica por si solo commit de TSCEnv, semantica de fases o protocolos de interverde',
           'flags de train.py corresponden a CODIGO PRESENTE, no a prueba de ejecucion historica',
           'checkpoint de clases chaos no equivale a entrenado con Vine/H09',
           'cualquier brecha de timesteps observados impide comparacion de entrenamiento igualado',
           'no se acreditan sensibilidad poblacional, robustez ni transferencia Quito'
       ]}
    return report


def markdown(r):
    P=r['policy_summary']; flags=r['env']['flags']; tr=r['training']['flags']
    s=['# H12.11 — Procedencia y compatibilidad del PPO heredado','',
       '**Estado:** '+r['status']+' (**diagnostico, NO certificacion de entrenamiento**).','',
       '## Respuesta de ppo_ideal ante Vine — H12.10',
       f"- Estados 34D modificados: {P['states_different']}/60; distribuciones modificadas: {P['policy_probs_different_among_changed_states']}/39; acciones distintas: {P['actions_different']}/60.",
       f"- TV maxima {P['max_total_variation']:.7g}; TV media en estados modificados {P['mean_total_variation_on_changed_states']:.7g}.",
       f"- Entropia nominal media {P['mean_entropy_nominal_nats']:.6f} nats = {100*r['entropy_fraction_max_nominal']:.2f}% del maximo ln(4). NO equivale a un criterio de calidad.",
       '', '## Metadatos de los ZIP SB3 (solo lectura, sin deserializar)',
       '| Archivo | Disponible | SHA-256 prefijo | num_timesteps archivado | n_envs archivado |',
       '|---|:---:|---|---:|---:|']
    for name, z in r['checkpoints'].items():
        s.append(f"| `{name}` | {'si' if z['available'] else 'no'} | `{z.get('sha256','?')[:16]}` | {z.get('num_timesteps')} | {z.get('n_envs')} |")
    s.extend(['',
       '- El contador `num_timesteps` describe un campo del checkpoint; por si solo no certifica dataset, tiempos ni esquema de entrenamiento.',
       '- Ratio Coop-ideal / ideal de contadores archivados: '+(f"{r['coop_ideal_to_ideal_timesteps_ratio']:.2f}x" if r['coop_ideal_to_ideal_timesteps_ratio'] is not None else 'no disponible')+'.',
       '', '## Contrato ACTUAL del TSCEnv (no probatorio de entrenamiento antiguo)'])
    for k,v in flags.items():s.append(f'- `{k}`: {v}')
    s.extend(['','## Script train.py del repositorio local (indicadores estaticos)'])
    for k,v in tr.items():s.append(f'- `{k}`: {v}')
    s.extend(['','## No acreditado'])
    s.extend('- '+x for x in r['unproven'])
    s.extend(['', '**Decisión metodológica:** preservar checkpoints y resultados originales; reconstruir manifiestos de entrenamiento con red/ruta SHA, semantica 34D, numero de fases, version SUMO, seeds, recompensas y presupuestos antes de una comparacion SOTA definitiva.',''])
    return '\n'.join(s)


def cli(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--h129-dir',type=Path,required=True)
    p.add_argument('--h1210-dir',type=Path,required=True)
    p.add_argument('--mode',choices=('plan','analyze'),default='plan')
    p.add_argument('--results-root',type=Path,default=Path('resultados'))
    return p.parse_args(argv)


def main(argv=None):
    try:
        a=cli(argv);repo=a.repo_root.resolve();h129=a.h129_dir.resolve();h1210=a.h1210_dir.resolve()
        report=build(repo,h129,h1210)
        print('H12.11 | Checkpoints hallados',sum(x['available'] for x in report['checkpoints'].values()),
            '| SHA ppo_ideal OK | Entrenamiento certificado NO',flush=True)
        if a.mode=='plan':print('H12_11_PLAN_OK: no se genero informe ni se abrio SUMO.');return 0
        target=a.results_root.resolve()
        if not target.is_dir():raise NotADirectoryError(str(target))
        dest=target/('h12_11_proveniencia_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
        dest.mkdir(parents=True,exist_ok=False)
        (dest/'dictamen_h12_11.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (dest/'dictamen_h12_11.md').write_text(markdown(report),encoding='utf-8')
        print('H12_11_DIAGNOSTICO_OK (NO CERTIFICA ENTRENAMIENTO)')
        print('INFORME',dest)
        return 0
    except Exception as e:
        print('H12.11 FAIL-CLOSED:',type(e).__name__,str(e),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
