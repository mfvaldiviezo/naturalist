#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.1: verificacion segura de archivos SB3 y contrato temporal Gymnasium/SUMO.
Solo lee codigo y ZIP. No hace unpickle, no carga PPO, no inicia SUMO/TraCI.
"""
from __future__ import annotations
import argparse, base64, csv, hashlib, io, json, math, os, re, sys, zipfile
from datetime import datetime
from pathlib import Path
from itertools import count

MODELS = ('ppo_ideal','ppo_chaos','ppo_coop_ideal','ppo_coop_chaos')
REQUIRED = ('tsc_framework/src/core/tsc_env.py','tsc_framework/scripts/run_evaluation.py',
            'tsc_framework/src/core/latam_chaos_manager.py')

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def _space_summary(val):
    if isinstance(val,dict):
        typ=str(val.get(':type:', '?'))
        enc=val.get(':serialized:')
        if not isinstance(enc,str):return typ,'METADATO_NO_ESTANDAR'
        try:
            raw=base64.b64decode(enc,validate=True)
            if len(raw)>100_000:return typ,'DATOS_SERIALIZADOS_EXCESIVOS'
            # Deliberadamente NO deserializar. SB3 usa pickle/cloudpickle para espacios.
            return typ,'CODIFICACION_LEGIBLE_NO_DESERIALIZADA'
        except Exception:
            return typ,'SERIALIZACION_BASE64_INVALIDA'
    return type(val).__name__,'DESCONOCIDO'

def inspect_zip(path):
    d=dict(checkpoint=path.name,path=str(path),exists=path.is_file(),bytes=None,sha256=None,
           zip_integrity='NO_ENCONTRADO',n_timesteps=None,observation_type=None,observation_status=None,
           action_type=None,action_status=None,contract_34d_4actions='NO_VERIFICADO',message='')
    if not path.is_file():return d
    d['bytes']=path.stat().st_size
    d['sha256']=sha256(path)
    try:
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                d['zip_integrity']='ARCHIVO_DANADO';return d
            d['zip_integrity']='OK'
            if 'data' not in z.namelist():d['message']='Falta SB3 data';return d
            inf=z.getinfo('data')
            if inf.file_size>3_000_000:d['message']='Metadato data demasiado grande';return d
            meta=json.loads(z.read('data').decode('utf-8'))
            t=meta.get('num_timesteps')
            d['n_timesteps']=int(t) if isinstance(t,int) and not isinstance(t,bool) else None
            a,st=_space_summary(meta.get('action_space'))
            o,ost=_space_summary(meta.get('observation_space'))
            d.update(action_type=a,action_status=st,observation_type=o,observation_status=ost)
            d['message']='Para certificar Box(34) y Discrete(4) se requiere una prueba aislada de carga del modelo confiable; aqui NO se hace pickle.'
    except (zipfile.BadZipFile, ValueError,UnicodeDecodeError, OSError,json.JSONDecodeError) as e:
        d['zip_integrity']='ERROR';d['message']=type(e).__name__+': '+str(e)[:200]
    return d

def inspect_temporal(src: str,microtick:float,rl_period:float):
    if not (math.isfinite(microtick) and microtick>0 and math.isfinite(rl_period) and rl_period>0):
        raise ValueError('Tiempos deben ser finitos y positivos')
    # Solo estático: encuentra los subpasos de TSCEnv, NO confirma configuración real del SUMO.
    m=re.search(r'for\s+_\s+in\s+range\s*\(\s*self\.delta_t\s*\)\s*:\s*\n\s*traci\.simulationStep\s*\(',src)
    pattern=bool(m)
    ratio=rl_period/microtick
    integral=math.isclose(ratio,round(ratio),abs_tol=1e-9,rel_tol=0)
    nominal_substeps=round(ratio) if integral else None
    return {'pattern_substeps_detected':pattern,'microtick_s_assumed':microtick,'desired_rl_period_s':rl_period,
            'desired_substeps_if_constant_microtick':nominal_substeps,'step_count_if_delta_t_5':5,
            'physical_time_if_delta_t_5_s':5*microtick,
            'temporal_contract':'REQUIERE_VALIDACION_EN_SUMO' if pattern and integral else 'REVISAR_CONTRATO',
            'warning':'El valor de delta_t en el código se utiliza como número de llamadas simulationStep(), no como segundos físicos. La configuración real debe verificarse en runtime.' if pattern else 'No se reconoce patrón de avance SUMO.'}

def read_repo_text(repo,relative):
    p=repo/relative
    if not p.is_file():raise FileNotFoundError(str(p))
    if p.stat().st_size>2_000_000:raise RuntimeError('Archivo fuente inesperadamente grande: '+str(p))
    return p.read_text(encoding='utf-8',errors='replace')

def gather(repo:Path,microtick:float,rl_period:float):
    for rel in REQUIRED:read_repo_text(repo,rel)
    base=repo/'tsc_framework/outputs/models'
    checkpoints=[inspect_zip(base/(name+'.zip')) for name in MODELS]
    ts=read_repo_text(repo,REQUIRED[0]); ev=read_repo_text(repo,REQUIRED[1]); chaos=read_repo_text(repo,REQUIRED[2])
    temporal=inspect_temporal(ts,microtick,rl_period)
    controls={
      'gymnasium_import':'import gymnasium' in ts,
      'gymnasium_env':'class TSCEnv(gym.Env)' in ts,
      'historical_colight_heuristic':bool(re.search(r'class\s+CoLightAgent\s*:',ev)) and bool(re.search(r'np\.exp\(',ev)),
      'historical_force_stop':'traci.vehicle.setSpeed(v_id, 0.0)' in chaos,
      'historical_env_uses_chaos':'self.chaos_manager.step()' in ts,
      'historical_evaluator_uses_chaos': 'enable_traci_chaos' in ev,
      'historical_coop_extractors_present':(repo/'tsc_framework/src/rl_agent/sarg_policy.py').is_file(),
    }
    count_steps=[(x['checkpoint'],x['n_timesteps']) for x in checkpoints]
    vals=[x['n_timesteps'] for x in checkpoints]
    ratios={'coop_vs_noncoop_steps_ratio':(vals[2]/vals[0] if vals[0] and vals[2] else None),
            'ideal_chaos_budget_paired':(vals[0]==vals[1] and vals[2]==vals[3] if all(x is not None for x in vals) else None)}
    gates={
        'CKP-01_ZIP_SHA':'ENCONTRADO' if all(x['zip_integrity']=='OK' and x['sha256'] for x in checkpoints) else 'INCOMPLETO',
        'CKP-02_ESPACIOS_34D_4ACCIONES':'PENDIENTE_VERIFICACION_DINAMICA',
        'CKP-03_PRESUPUESTO_ENTRENAMIENTO':'DESIGUAL' if len({v for v in vals if v is not None})>1 else 'REVISAR',
        'TIM-01_CONTRATO_MICROTICK':'PENDIENTE_PRUEBA_REAL',
        'SOTA-01_COLIGHT_GENUINO':'NO_ACREDITADO' if controls['historical_colight_heuristic'] else 'REVISAR',
        'PERT-01_SIN_BLOQUEO':'NO_ACREDITADO_EN_RUTA_HISTORICA' if controls['historical_force_stop'] else 'REVISAR'
    }
    return {'checkpoints':checkpoints,'temporal':temporal,'controls':controls,'ratios':ratios,'gates':gates}

def safe_output_dir(revision_root:Path):
    results=revision_root/'resultados'
    if not results.is_dir():raise FileNotFoundError('Debe existir carpeta resultados: '+str(results))
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    for k in range(50):
        out=results/(f'h12_1_verificacion_{stamp}' + (f'_{k}' if k else ''))
        try:out.mkdir(mode=0o700,exist_ok=False);return out
        except FileExistsError:continue
    raise RuntimeError('No se pudo crear carpeta única de resultados')

def save_csv(path,rows):
    if not rows:return
    fields=list(rows[0].keys())
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def export(out,result,repo):
    save_csv(out/'checkpoints_h12_1.csv',result['checkpoints'])
    save_csv(out/'contrato_temporal_h12_1.csv',[result['temporal']])
    save_csv(out/'puertas_h12_1.csv',[dict(id=k,estado=v) for k,v in result['gates'].items()])
    (out/'evidencia_h12_1.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    c=result['checkpoints'];t=result['temporal'];g=result['gates'];ra=result['ratios']
    lines=['# H12.1 — Verificación estática segura de checkpoints y sincronización temporal','','**Alcance:** solo lectura de código y ZIP propios; no ejecuta SUMO, TraCI, PPO.load ni pickle.','',
           '## Checkpoints', '', '|Modelo|Pasos|SHA-256|ZIP|', '|---|---:|---|---|']
    for x in c:lines.append(f"|{x['checkpoint']}|{x['n_timesteps']}|`{x['sha256']}`|{x['zip_integrity']}|")
    lines+=['','**No certificado aún:** `Box(34,)` y `Discrete(4)`. SB3 serializa espacios con pickle/cloudpickle; no se deserializan por seguridad en esta auditoría.',
            '',f"**Razón entrenamiento Coop/no-Coop:** {ra['coop_vs_noncoop_steps_ratio']}",
            '','## Contrato temporal','',f"- Microtick supuesto (según CLI): {t['microtick_s_assumed']} s; periodo RL deseado: {t['desired_rl_period_s']} s.",
            f"- Si `delta_t=5`, el bucle de subpasos produce {t['physical_time_if_delta_t_5_s']} s físicos bajo ese microtick.",
            f"- Para {t['desired_rl_period_s']} s se necesitarían {t['desired_substeps_if_constant_microtick']} microticks si la longitud de paso efectiva es constante.",
            '- No modificar `delta_t` automáticamente: el mismo parámetro puede usarse para lógica de fases y temporizadores; es necesaria una auditoría de efectos colaterales y prueba de reloj en SUMO.','',
            '## Puertas','']
    lines += [f'- **{k}:** {v}' for k,v in g.items()]
    lines += ['','## Decisión científica','',
              'Los cuatro checkpoints están disponibles como políticas históricas, pero no se acredita aún identidad de espacios, seguridad temporal ni igualdad de presupuesto de entrenamiento.',
              'No usar el CoLight heurístico como SOTA neuronal. No mezclar paradas forzadas con perturbaciones Vine/H09.',
              'Este informe NO ejecuta evaluaciones de controladores.']
    (out/'dictamen_h12_1.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    manifest={'repo_root':str(repo),'inputs_sha256':{r:sha256(repo/r) for r in REQUIRED},
              'outputs_sha256':{p.name:sha256(p) for p in out.iterdir() if p.is_file()}}
    (out/'manifiesto_h12_1.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--revision-root',type=Path,required=True)
    p.add_argument('--microtick-s',type=float,default=0.5,help='Hipótesis de microtick para escenarios H11, no configura SUMO')
    p.add_argument('--rl-period-s',type=float,default=5.0,help='Periodo RL que se desea cotejar; no configura SUMO')
    p.add_argument('--guardar',action='store_true')
    a=p.parse_args(argv)
    repo=a.repo_root.resolve(strict=True);revision=a.revision_root.resolve(strict=True)
    r=gather(repo,a.microtick_s,a.rl_period_s)
    print('H12.1 | SIN SUMO | SIN PPO.load | SIN DESERIALIZAR PICKLE')
    for c in r['checkpoints']:
        print(f"{c['checkpoint']:<26} pasos={str(c['n_timesteps']):>9}  zip={c['zip_integrity']}")
    print('Razon Coop/no-Coop:',r['ratios']['coop_vs_noncoop_steps_ratio'])
    print('Contrato temporal si delta_t=5:',r['temporal']['physical_time_if_delta_t_5_s'],'s; objetivo:',a.rl_period_s,'s')
    for key,status in r['gates'].items():print(f'{key}: {status}')
    print('NOTA: espacios 34D/4 acciones NO verificados sin inspección dinámica controlada.')
    if a.guardar:
        out=safe_output_dir(revision);export(out,r,repo);print('INFORME:',out)
    else:
        print('PREFLIGHT OK: sin escritura. Usar --guardar solo para generar carpeta nueva.')
    return 0

if __name__=='__main__':sys.exit(main())
