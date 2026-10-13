#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12 v1.0: inventario y puertas de comparabilidad de Gymnasium/SOTA.

LECTURA UNICAMENTE de GitHub checkout local, checkpoints y resultados experimentales.
NO ejecuta SUMO, TraCI, Gymnasium, PyTorch, entrenamientos, ni scripts históricos.
No abre PoliDriving RAW, Richard, ni los CSV H01. No interpreta zip/Pickle.

Primero evalua/prepara en memoria. Solo --guardar permite escribir informes
nuevos en revision_naturalista/resultados/h12_auditoria_... .
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

VERSION='H12.AUDITORIA_GYMNASIUM_SOTA_v1.0.0'
REPO='mfvaldiviezo/framework_RLT'
# SHA de blobs observados en GitHub rama main durante auditoría. NO indican
# que el checkout local esté actualizado. CRLF de Windows se normaliza solo
# para comparación SHA de texto, nunca se modifica el original.
GITHUB_BLOBS={
 'run_all_eval.ps1':'ec4c4fd3e31311e69214e5f0b65dcd4ab3047e93',
 'run_resco.py':'1d6968b6636897d00f9921f3debd8b2d0df15b6a',
 'evaluate_marl.py':'d5c515792797dab7118ff38100e92511415a4827',
 'tsc_framework/scripts/run_evaluation.py':'2732bb7d9a2be0066658c5b347153681ad3eea65',
 'tsc_framework/src/core/tsc_env.py':'06095fe94125dcd8e2a7fdd9015740579a9da3ed',
 'tsc_framework/src/core/latam_chaos_manager.py':'7419d633b807450cccf62000fb83887130fe0809',
 'tsc_framework/src/rl_env/sumo_env.py':'6cb503866661dcbd772cae6ff073d8ded6fe22e9',
 'tsc_framework/environment.yml':'b60c321365153e2bf326c0b96e69759b2973e192',
 'tsc_framework/transfer_eval_n30_robust.py':'98994b421d8e20d620c9979374abb7e2fa267ed9',
 'tsc_framework/src/rl_agent/sarg_policy.py':'1f90af289a9e68855b715fb2a629f9dce950c41f',
 'tsc_framework/scripts/transfer_eval.py':'21af0cf2bbc441e50bf577ea19c04a1d0d508dc4'
}
MODEL_NAMES=('ppo_ideal','ppo_chaos','ppo_coop_ideal','ppo_coop_chaos')
EXPECTED_FILES={
    'nominal':('h11_2_pareado_h10_nominal_20261011_184549_504694',
        'observado/telemetria/trayectorias_h11.csv'),
    'hibrido':('h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351',
        'observado/telemetria/trayectorias_h11.csv'),
    'vine_acciones_hibrido':('h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351',
        'observado/hibrido_contextual/acciones_hito08.csv'),
}


def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def git_blob_text_sha(p):
    data=Path(p).read_bytes().replace(b'\r\n',b'\n')
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def text_file(p, max_bytes=2_000_000):
    if not p.is_file():return ''
    if p.stat().st_size>max_bytes:raise ValueError('Archivo de codigo demasiado grande: '+str(p))
    return p.read_text(encoding='utf-8-sig',errors='replace')


def test_patterns(src):
    eval_code=src.get('tsc_framework/scripts/run_evaluation.py','')
    env_code=src.get('tsc_framework/src/core/tsc_env.py','')
    old_code=src.get('tsc_framework/src/core/latam_chaos_manager.py','')
    trans_code=src.get('tsc_framework/transfer_eval_n30_robust.py','')
    runner=src.get('run_all_eval.ps1','')
    resco=src.get('run_resco.py','')
    # Deliberadamente detecciones estáticas; evidencia, NO validación de equivalencia runtime.
    return [
      dict(id='GYM-01',tema='TSCEnv implementa Gymnasium',encontrado=bool(re.search(r'class\s+TSCEnv\s*\(\s*gym\.Env\s*\)',env_code) and 'return obs, reward, terminated, truncated, info' in env_code),
           severidad='INFORMATIVO',resultado='API Gymnasium observada en código, pendiente verificación operacional'),
      dict(id='GYM-02',tema='API de paso con subpasos SUMO',encontrado='for _ in range(self.delta_t):' in env_code and 'traci.simulationStep()' in env_code,
           severidad='VERIFICAR',resultado='delta_t entero recorre subpasos; con step-length=0.5, 5 iteraciones son 2.5 s físicos'),
      dict(id='GYM-03',tema='Entorno histórico llama gestor de caos',encontrado='self.chaos_manager.step()' in env_code,
           severidad='BLOQUEO',resultado='No usar como equivalente a H10/H11 Vine/H09; se requiere reemplazo/puente controlado'),
      dict(id='SOTA-01',tema='CoLightAgent histórico es heurística',encontrado=bool(re.search(r'class\s+CoLightAgent',eval_code) and 'np.sum(q[' in eval_code and 'np.exp(' in eval_code),
           severidad='BLOQUEO',resultado='Etiquetar como heurística de colas tipo softmax; no original CoLight ni SOTA comprobado'),
      dict(id='SOTA-02',tema='RESCO mapea colight a CoSLight',encontrado=bool(re.search(r'["\']colight["\']\s*:\s*["\']CoSLight["\']',resco)),
           severidad='VERIFICAR',resultado='CoSLight es ruta distinta; no asumir equivalencia a CoLight original sin documentación'),
      dict(id='CTRL-01',tema='FixedTime/MaxPressure disponibles',encontrado=bool('class FixedAgent' in eval_code and 'class MaxPressureAgent' in eval_code),
           severidad='INFORMATIVO',resultado='Implementaciones históricas disponibles; homologar acción/observación/horizonte'),
      dict(id='PERT-01',tema='Bloqueo impuesto en ruta histórica',encontrado=bool(re.search(r'setSpeed\s*\(\s*v_id\s*,\s*0(?:\.0+)?\s*\)',old_code) or re.search(r'setSpeed\s*\(\s*v_id\s*,\s*0(?:\.0+)?\s*\)',trans_code)),
           severidad='BLOQUEO',resultado='setSpeed(v,0) en gestor histórico; excluirlo del brazo Vine/H09 no nominal'),
      dict(id='RUN-01',tema='Suite histórica llama evaluador local, no RESCO puro',encontrado=bool('scripts/run_evaluation.py' in runner and 'maxpressure colight' in runner.lower()),
           severidad='VERIFICAR',resultado='No citar los resultados de esta ruta como benchmarking CoLight original'),
    ]


def safe_header(path):
    if not path.is_file():return []
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        row=next(csv.reader(f),[])
    return row[:120]


def inspect_checkpoint(p,repo_root):
    row={'checkpoint':str(p.relative_to(repo_root)).replace('\\','/'),'size_bytes':p.stat().st_size,
         'sha256':None,'zip_structure':'NO_VALIDADO','sb3_metadata_presence':False,
         'data_num_timesteps':None,'data_policy_class':None,'data_observation_space':None,'data_action_space':None}
    if not zipfile.is_zipfile(p):
        row['zip_structure']='NO_ZIP';return row
    try:
        with zipfile.ZipFile(p) as z:
            names=set(z.namelist())
            row['zip_structure']='ZIP_LEIBLE'
            row['sb3_metadata_presence']='data' in names
            if 'data' in names and z.getinfo('data').file_size<=512000:
                # SB3 almacena JSON + representaciones, NUNCA cargar pickle/pth.
                metadata=json.loads(z.read('data').decode('utf-8'))
                for k,col in (('num_timesteps','data_num_timesteps'),('policy_class','data_policy_class'),
                              ('observation_space','data_observation_space'),('action_space','data_action_space')):
                    val=metadata.get(k)
                    if val is not None:row[col]=str(val)[:180]
    except (OSError,ValueError,RuntimeError,json.JSONDecodeError,UnicodeDecodeError,KeyError) as exc:
        row['zip_structure']='ERROR_'+type(exc).__name__
    if p.name in {x+'.zip' for x in MODEL_NAMES}:
        row['sha256']=sha256(p)
    return row


def inventory_run_dirs(revision):
    root=revision/'resultados'
    if not root.is_dir():return []
    outputs=[]
    for p in sorted(root.iterdir()):
        if not p.is_dir():continue
        if not re.search(r'(h11|h10|h09|vine_r_0|h12_|resiliencia|eval|ablation)',p.name,re.I):continue
        kinds=[]
        for k in ('h11_2_pareado','h11_3a','h11_3b','h11_3c','h10','h09','vine','eval','ablation'):
            if k in p.name.lower():kinds.append(k)
        outputs.append(dict(folder=p.name,tipo=';'.join(kinds) or 'OTRO',
                            manifest_at_root=(p/'manifest.json').is_file(),
                            manifest_span=[]))
    return outputs


def identify_sources(repo_root):
    rows=[];src={}
    for rel,expected in GITHUB_BLOBS.items():
        p=repo_root/rel
        if p.is_file():
            actual=git_blob_text_sha(p)
            src[rel]=text_file(p)
            status='IGUAL_A_GITHUB_AUDITADO' if actual==expected else 'DIFIERE_DE_GITHUB_AUDITADO'
        else:actual=None;status='NO_EXISTE_EN_CHECKOUT'
        rows.append(dict(path=rel,presente=p.is_file(),github_git_blob_sha1=expected,
                         local_git_blob_sha1_normalizado=actual,estado=status))
    return rows,src


def experiment_evidence(revision):
    root=revision/'resultados'
    rows=[]
    for label,(folder,rel) in EXPECTED_FILES.items():
        file=root/folder/rel
        rows.append(dict(id=label,fuente=str(file.relative_to(revision)).replace('\\','/'),
                         existe=file.is_file(),tamanio_bytes=file.stat().st_size if file.is_file() else None,
                         columnas=';'.join(safe_header(file)) if file.is_file() else '',
                         comparabilidad='COMPARABILIDAD_H11_PAREADA_SUJETA_A_MANIFIESTOS' if file.is_file() else 'FALTANTE'))
    has_h113b=any(root.glob('h11_3b_evidencia_*')) if root.exists() else False
    has_h113c=any(root.glob('h11_3c_cinematica_*')) if root.exists() else False
    rows.append(dict(id='h11_3b',fuente='resultados/h11_3b_evidencia_*',existe=has_h113b,tamanio_bytes=None,
                     columnas='',comparabilidad='INVENTARIO_CERRADO_NO_CALIBRACION'))
    rows.append(dict(id='h11_3c',fuente='resultados/h11_3c_cinematica_*',existe=has_h113c,tamanio_bytes=None,
                     columnas='',comparabilidad='EPISODIOS_DESCRIPTIVOS_NO_FRECUENCIA_URBANA'))
    return rows


def build_gates(checks,files,experiments,models):
    lookup={x['id']:x for x in checks}
    n_present=sum(x['existe'] for x in experiments[:3])
    model_set={Path(x['checkpoint']).stem for x in models}
    return [
      dict(id='H12-G1',tema='SOTA autenticos',estado='BLOQUEADO' if lookup['SOTA-01']['encontrado'] else 'REVISAR',
           causa='El pseudobaseline CoLight de run_evaluation no es la arquitectura CoLight original',
           cierre='Identificar implementación exacta RESCO/CoSLight, checkpoint, protocolo y métrica; no renombrar como CoLight SOTA'),
      dict(id='H12-G2',tema='Perturbaciones no nominales sin bloqueo',estado='BLOQUEADO' if lookup['PERT-01']['encontrado'] else 'REVISAR',
           causa='Gestor histórico con setSpeed(..., 0)',
           cierre='Desactivar gestor histórico y enlazar H10 Vine/H09 en un único ciclo TraCI sin bloqueo, con tests de no doble step'),
      dict(id='H12-G3',tema='Compatibilidad temporal Gymnasium/SUMO',estado='PENDIENTE',
           causa='delta_t iteraciones pueden no coincidir con segundos físicos si step-length !=1.0 s',
           cierre='Fijar separación microtick .5 s y macrodecisión RL, verificar tiempo real y semillas'),
      dict(id='H12-G4',tema='Checkpoint 4 modelos',estado='INVENTARIADO' if all(x in model_set for x in MODEL_NAMES) else 'INCOMPLETO',
           causa='Localización de checkpoints SB3, sin cargar pesos',
           cierre='Validar espacios observación/acción y extractor en modo lectura antes de usar predict'),
      dict(id='H12-G5',tema='Pareado H11 nominal e híbrido',estado='ENCONTRADO' if n_present==3 else 'INCOMPLETO',
           causa='Tres rutas H11.2: nominal, híbrido y acciones',
           cierre='Mantener la validación SHA existente; NO equivale a una evaluación de controladores'),
      dict(id='H12-G6',tema='Ablación Coop-SARG MAD-Gating',estado='PENDIENTE',
           causa='Comparar modelos diferentes no identifica contribución causal MAD-Gating',
           cierre='Ablación ON/OFF mismos pesos arquitectónicos salvo puerta, semillas y presupuesto de entrenamiento'),
      dict(id='H12-G7',tema='Métricas comunes e independencia',estado='PENDIENTE',
           causa='Definiciones históricas Gini/CVaR/delay/TP/throughput y semilla por episodio requieren homologación',
           cierre='Mismo estimando, unidad, horizonte, warmup, emparejamiento; IC95% por episodio/semilla'),
    ]


def write_csv(path,rows,fields=None):
    fields=list(rows[0]) if rows else list(fields or ['sin_registros'])
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)


def make_report(data):
    checks={x['id']:x for x in data['detecciones_estaticas']}
    flags=[x['id'] for x in data['puertas'] if x['estado'] in ('BLOQUEADO','PENDIENTE','INCOMPLETO')]
    countmodels=len(data['checkpoints'])
    n_nom=sum(x['existe'] for x in data['evidencia_h11'][:3])
    return '\n'.join([
        '# H12 — Auditoría estática Gymnasium, SOTA y rutas de perturbación',
        '', '**Alcance:** lectura de código, ZIP SB3 como contenedores y metadatos H11. NO se ejecutó SUMO, PPO, Vine ni benchmarks.',
        'Repositorio auditado: `'+REPO+'` rama `main`, árbol observado `'+data['github_tree_sha']+'`.',
        'El checkout local puede no coincidir con GitHub: ver `fuentes_codigo_h12.csv`.',
        '', '## Inventario comprobable',
        '- Gymnasium TSCEnv: '+str(checks['GYM-01']['encontrado'])+' (API, **no test runtime**).',
        '- Potencial desfase de subpasos delta_t frente a step-length=.5 s: '+str(checks['GYM-02']['encontrado'])+'.',
        '- CoLight histórico implementado como heurística: '+str(checks['SOTA-01']['encontrado'])+'.',
        '- RESCO alias colight->CoSLight: '+str(checks['SOTA-02']['encontrado'])+'.',
        '- Bloqueo forzado histórico setSpeed(...,0): '+str(checks['PERT-01']['encontrado'])+'.',
        '- Checkpoints ZIP encontrados: '+str(countmodels)+'. Metadatos leídos sin pickle ni torch.',
        '- Fuentes H11.2 nominal/híbrido/acciones disponibles: '+str(n_nom)+'/3.',
        '', '## Regla de no sobredeclaración',
        '- CoLightAgent del runner histórico NO es evaluación del modelo original CoLight.',
        '- RESCO CoSLight, IPPO y otras políticas NO son intercambiables con los controles locales sin homologar observaciones, acciones, recompensas, fases, red, demanda y duración.',
        '- Experimentos históricos con hard blocking NO representan aisladamente Vine/H09.',
        '- Poseer ZIP no valida su compatibilidad con espacios 34D/4 acciones ni sus presupuestos de entrenamiento.',
        '- Los resultados H11.2 nominal/híbrido son pilotos de perturbación, no pruebas de resiliencia de controladores RL.',
        '', '## Puertas pendientes',
        '\n'.join('- '+x['id']+': **'+x['estado']+'** — '+x['cierre'] for x in data['puertas']),
        '', '## Diseño experimental recomendado después de cerrar las puertas',
        '1. Conservar corridas existentes, versiones/hashes y checkpoints, sin sobrescribir artefactos.',
        '2. Usar controladores fijos/heurísticos/RL/SOTA genuinos con interfaz de observación, acción, horizonte y contabilidad equivalentes.',
        '3. Separar perturbaciones nominal/Vine/H09/híbrido sin bloqueo; disponer de brazos de bloqueo solo si están claramente etiquetados como intervenciones distintas.',
        '4. Cerrar sincronización 0.5s SUMO versus paso de acción RL, invocación una sola vez por microtick, estado/reset de cohortes y semillas.',
        '5. Verificar recompensa y métricas; evaluar multisemilla emparejado después, con CI por unidad experimental (episodio/semilla).',
        '', '**Dictamen:** H12 evidencia estática terminada; ejecución comparativa de SOTA/RL NO autorizada aún por puertas abiertas.',
        ''
    ])


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision-root',type=Path,default=Path('.'))
    p.add_argument('--repo-root',type=Path,required=True,help='raíz del checkout GitHub con tsc_framework/, baselines/, run_all_eval.ps1')
    p.add_argument('--guardar',action='store_true',help='escribe únicamente archivos nuevos bajo revision_root/resultados')
    p.add_argument('--output',type=Path,help='carpeta NUEVA, debe estar dentro de revision_root/resultados')
    a=p.parse_args(argv)
    if a.output and not a.guardar:p.error('--output requiere --guardar')
    rev=a.revision_root.resolve();repo=a.repo_root.resolve()
    if not (rev/'resultados').is_dir():raise FileNotFoundError('No existe directorio de revision/resultados: '+str(rev))
    if not (repo/'tsc_framework/src/core/tsc_env.py').is_file() or not (repo/'run_all_eval.ps1').is_file():
        raise FileNotFoundError('repo-root no parece checkout de mfvaldiviezo/framework_RLT: '+str(repo))
    sources,code=identify_sources(repo)
    detection=test_patterns(code)
    exp=experiment_evidence(rev)
    existing=inventory_run_dirs(rev)
    mods=repo/'tsc_framework/outputs/models'
    checkpoints=[inspect_checkpoint(f,repo) for f in sorted(mods.glob('*.zip'))] if mods.exists() else []
    checkpoints.extend([inspect_checkpoint(f,repo) for f in sorted((mods/'best_model').glob('*.zip'))] if (mods/'best_model').is_dir() else [])
    gates=build_gates(detection,sources,exp,checkpoints)
    data={'version':VERSION,'github_repository':REPO,'github_tree_sha':'fe124c599104f8a4ef8b1fa7b41a92a7da77c646',
          'revision_root':str(rev),'repo_root':str(repo),
          'fuentes_codigo':sources,'detecciones_estaticas':detection,'evidencia_h11':exp,
          'carpetas_resultados':existing,'checkpoints':checkpoints,'puertas':gates,
          'sumo_ejecutado':False,'modelos_cargados':False,'entrenamiento_ejecutado':False,'holdouts_abiertos':False}
    print('=== H12 | AUDITORÍA GYMNASIUM + SOTA | SOLO LECTURA ===')
    print('Repo:',repo,'| Revisión:',rev)
    for row in detection:print(row['id'],'SI' if row['encontrado'] else 'NO',row['tema'])
    print('Checkpoints principales:',', '.join(sorted(Path(x['checkpoint']).stem for x in checkpoints)) or 'NINGUNO')
    print('H11 nominal/híbrido/acciones encontrados:',sum(x['existe'] for x in exp[:3]),'/3')
    print('Carpetas de resultados históricas de interés:',len(existing))
    print('Puertas:',', '.join(x['id']+'='+x['estado'] for x in gates))
    if not a.guardar:
        print('PREFLIGHT OK. --guardar exporta informes en una carpeta NUEVA; no se ejecutan simulaciones.')
        return 0
    base=(rev/'resultados').resolve()
    dest=(a.output or base/('h12_auditoria_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
    if not dest.is_relative_to(base) or dest==base or dest.exists():
        raise ValueError('output debe ser NUEVO dentro de resultados: '+str(dest))
    dest.mkdir(parents=True)
    named={
        'fuentes_codigo_h12.csv':sources,
        'detecciones_estaticas_h12.csv':detection,
        'checkpoints_sota_h12.csv':checkpoints,
        'evidencia_h11_h12.csv':exp,
        'carpetas_resultados_h12.csv':existing,
        'puertas_evaluacion_h12.csv':gates,
    }
    fallback_fields={
        'checkpoints_sota_h12.csv':['checkpoint','size_bytes','sha256','zip_structure','sb3_metadata_presence','data_num_timesteps','data_policy_class','data_observation_space','data_action_space'],
        'carpetas_resultados_h12.csv':['folder','tipo','manifest_at_root','manifest_span'],
    }
    for name,rows in named.items():write_csv(dest/name,rows,fields=fallback_fields.get(name))
    (dest/'dictamen_h12.md').write_text(make_report(data),encoding='utf-8')
    manifest={k:v for k,v in data.items() if k not in ('fuentes_codigo','detecciones_estaticas','checkpoints','evidencia_h11','carpetas_resultados','puertas')}
    manifest['created_utc']=datetime.now(timezone.utc).isoformat()
    manifest['code_sha256']=sha256(Path(__file__))
    manifest['outputs_sha256']={n:sha256(dest/n) for n in [*named,'dictamen_h12.md'] if (dest/n).exists()}
    (dest/'manifiesto_h12.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('INFORME:',dest)
    return 0


if __name__=='__main__':
    try:raise SystemExit(run())
    except (FileNotFoundError,ValueError,PermissionError) as exc:
        print('ERROR H12:',exc,file=sys.stderr)
        raise SystemExit(2)
