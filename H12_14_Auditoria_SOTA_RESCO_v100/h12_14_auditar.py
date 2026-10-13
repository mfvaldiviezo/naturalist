"""H12.14: auditoría de interfaz y procedencia RESCO vs H12.12 (SOLO LECTURA).

No importa/carga algoritmos RESCO, PyTorch, SB3, SUMO, TraCI ni checkpoints.
No presenta código de repositorio como agente entrenado. La acreditación SOTA requiere
adaptadores, capacitación/auditoría de checkpoints y evaluaciones posteriores.
"""
from __future__ import annotations
import argparse
import ast
import csv
from datetime import datetime, timezone
import hashlib
import json
import pathlib
import sys
import uuid

ROOT=pathlib.Path(__file__).resolve().parent
SCHEMA='H12_14_RESCO_CONTRACT_AUDIT_V100'
EXPECTED_NET='2590ca460dafb57a4c608f4fe1ad9de072068a5b2ef0ea487f617296d8c627f6'
EXPECTED_ROUTES='a78363c99e1a6eab33028c3a36c82dcb66129adf8e73141612b9e7b2358f1369'
CHECKS={
 'FIXED':('agents/static/fixed.py','FIXED','static.fixed','wave','wait','local_baseline'),
 'MAXPRESSURE':('agents/static/maxpressure.py','MAXPRESSURE','static.maxpressure','mplight','wait','local_baseline'),
 'IPPO':('agents/policy/pfrl_ppo.py','IPPO','policy.pfrl_ppo','drq','wait','local_rl'),
 'MPLight':('agents/action_value/mplight.py','MPLight','action_value.mplight','mplight','pressure','shared_rl'),
 'CoSLight':('agents/policy/CoSLight/coslight.py','CoSLight','policy.CoSLight.coslight','coslight','coslight','multiagent_rl'),
}
EXTRA={
 'MAXPRESSURE':['agents/static/maxwave.py'],
 'IPPO':['agents/action_value/pfrl_dqn.py'],
 'MPLight':['agents/action_value/pfrl_dqn.py'],
 'CoSLight':['agents/policy/CoSLight/rMAPPOPolicy.py','agents/policy/CoSLight/r_mappo.py'],
}

class AuditError(RuntimeError):pass

def require(ok,msg):
    if not ok:raise AuditError(msg)

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def jsonload(p):
    with pathlib.Path(p).open(encoding='utf-8') as f:return json.load(f)

def validate_doc(path):
    p=pathlib.Path(path)
    require(p.is_file(), 'Falta código fuente: '+str(p))
    try:t=ast.parse(p.read_text(encoding='utf-8'))
    except (SyntaxError,UnicodeDecodeError) as e:raise AuditError('Python inválido: '+str(p)) from e
    return t

def classes(tree):return {node.name:node for node in tree.body if isinstance(node,ast.ClassDef)}

def get_yaml(p):
    require(p.is_file(),'Falta configuración RESCO agent.yaml')
    try:import yaml
    except ImportError as e:raise AuditError('Falta PyYAML. Instalar pyyaml en tsc-env') from e
    try:
        with p.open(encoding='utf8') as f:doc=yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise AuditError('agent.yaml no se puede interpretar') from exc
    require(isinstance(doc,dict),'agent.yaml no contiene un diccionario')
    return doc

def read_phase_xml(source):
    # Contrato probado con la propia red: no confiar solo en nombres de fase.
    import xml.etree.ElementTree as ET
    with source.open('rb') as fh:
        header=fh.read(4096).upper()
    require(b'<!DOCTYPE' not in header and b'<!ENTITY' not in header,'DTD no admitida en red')
    try:
        tree=ET.parse(source).getroot()
    except ET.ParseError as exc:
        raise AuditError('XML de red B1 inválido') from exc
    programs=[x for x in tree.findall('tlLogic') if x.get('id')=='B1']
    require(len(programs)==1,'Se espera un único programa B1')
    phases=[(i,p.get('state',''),float(p.get('duration',0))) for i,p in enumerate(programs[0].findall('phase'))]
    greens=[i for i,s,d in phases if 'G' in s or 'g' in s]
    yellows=[(i,d) for i,s,d in phases if ('y' in s.lower()) and not ('G' in s or 'g' in s)]
    require(greens==[0,2],'Verdes físicos B1 distintos de [0,2]')
    require(yellows==[(1,3.0),(3,3.0)],'Amarillos B1 distintos de 3 segundos en 1 y 3')
    conns=[c for c in tree.findall('connection') if c.get('tl')=='B1']
    inputs=sorted({c.get('from')+'_'+c.get('fromLane') for c in conns})
    require(len(inputs)==4,'B1 no tiene exactamente 4 entradas reales')
    return {'green_indices':greens,'yellow_phases':[x[0] for x in yellows],
            'action_space_n':len(greens),'inbound_lanes':inputs,'phase_states':[x[1] for x in phases]}

def inspected_resco(repo):
    base=repo/'baselines/RESCO/resco_benchmark'
    root=repo/'baselines/RESCO'
    yamlpath=base/'config/agent.yaml'
    mapping=get_yaml(yamlpath)
    rows=[]; codefiles=[yamlpath]
    for name,(part,cl,mod,state,reward,scope) in CHECKS.items():
        path=base/part
        tree=validate_doc(path)
        cls=classes(tree)
        require(cl in cls,f'{name}: Clase {cl} ausente en {path}')
        entry=mapping.get(name)
        require(isinstance(entry,dict),f'Agente {name} no definido en agent.yaml')
        require(entry.get('module')==mod,f'{name}: module YAML incompatible: {entry.get("module")}')
        require(entry.get('state')==state,f'{name}: state YAML inesperado: {entry.get("state")}')
        require(entry.get('reward')==reward,f'{name}: reward YAML inesperado: {entry.get("reward")}')
        for rel in EXTRA.get(name,[]):codefiles.append(base/rel);validate_doc(base/rel)
        codefiles.append(path)
        rows.append({'controller':name,'module':mod,'source':str(path.resolve()),'source_sha256':sha(path),
                     'yaml_state':state,'yaml_reward':reward,'scope':scope,
                     'source_class_verified':True,'yaml_registered':True,
                     'can_execute_directly_on_H1212':False,
                     'checkpoint_verified':False,
                     'training_certified':False,
                     'integration_stage':{
                        'FIXED':'requiere adaptador de ciclo/temporización (sin pesos)',
                        'MAXPRESSURE':'requiere adaptador de sensores/pares por fase; RESCO delega a WaveAgent',
                        'IPPO':'requiere adaptador drq 34D→estado RESCO y acciones 2D; entrenamiento PFRL nuevo',
                        'MPLight':'requiere adaptador de FRAP (pares competitivos/direcciones); DQN nuevo',
                        'CoSLight':'requiere control multi-TLS y estados compartidos; NO homologable como B1 aislado'
                     }[name]})
    cfg=root/'resco_benchmark/config/config.yaml'
    require(cfg.exists(),'Falta RESCO config/config.yaml')
    codefiles.append(cfg)
    rel=root/'README.rst'
    require(rel.exists(),'Falta README RESCO')
    codefiles.append(rel)
    return rows,sorted(set(codefiles))

def manifest_check(smoke,net,route,h1212):
    root=smoke.resolve(strict=True)
    mpath=root/'manifiesto_h12_12.json';runtime=root/'runtime_h12_12.json';smp=root/'smoke_h12_12.json'
    for p in [mpath,runtime,smp]:require(p.is_file(),'No existe evidencia H12.12: '+str(p))
    m=jsonload(mpath);sm=jsonload(smp);rt=jsonload(runtime)
    require(m.get('schema')=='H12_12_B1_GREEN2_OBS34_V100','Schema H12.12 no acreditado')
    require(sm.get('result')=='H12_12_SUMO_SMOKE_OK','H12.12 smoke sin éxito acreditado')
    require(sm.get('manifest_sha256')==sha(mpath),'manifiesto H12.12 alterado')
    require(sm.get('steps')==12 and sm.get('microticks')==120,'Smoke H12.12 distinto de 12/120')
    require(bool(rt.get('sumo_version')),'H12.12 runtime sin versión SUMO')
    require(str(net.resolve())==m.get('network') and str(route.resolve())==m.get('routes'),
            'Rutas físicas distintas del manifiesto H12.12')
    require(sha(net)==EXPECTED_NET and sha(route)==EXPECTED_ROUTES,'Red/demanda distintas del smoke acreditado')
    old=m.get('sources_sha256',{})
    require(old.get(str(net.resolve()))==sha(net) and old.get(str(route.resolve()))==sha(route),
            'Red/demanda cambiadas respecto de H12.12')
    for n in ['h12_12_contract.py','h12_12_env.py','h12_12_homologar.py']:
        p=h1212/n
        require(p.is_file(),'Fuente H12.12 faltante: '+str(p))
        require(old.get(str(p.resolve()))==sha(p),'Fuente H12.12 alterada: '+n)
    require(m.get('actions',{}).get('type')=='Discrete(2)','Contrato H12.12 no físico 2D')
    require(m.get('simulation',{}).get('microtick_seconds')==0.5 and m.get('simulation',{}).get('decision_seconds')==5.0,
            'H12.12 distinto de 0.5/5s')
    return {'smoke_dir':str(root),'smoke_sha256':sha(smp),'manifest_sha256':sha(mpath),
            'runtime_sha256':sha(runtime),'sumo_version':rt['sumo_version'],
            'H1212_schema':m['schema'],'green_phases':m['network_contract']['green_indices'],
            'controlled_intersection':m['tls_id']}

def optional_train_check(path):
    if path is None:return {'H1213':'NOT_RUN_OR_NOT_SUPPLIED','meaning':'No impide auditar SOTA; falta piloto nuevo de H-SARG-B1/Coop-SARG-B1'}
    p=path.resolve(strict=True)
    f=p/'resultado_h12_13.json';require(f.is_file(),'Se facilitó carpeta H12.13 sin resultado_h12_13.json')
    doc=jsonload(f)
    status=doc.get('result')
    require(status in ('H12_13_PILOT_OK','H12_13_TRAINING_OK'),
            'H12.13: no hay resultado aprobado')
    require(doc.get('n_models',0)>=2 and len(doc.get('reports',[]))==doc.get('n_models'),
            'H12.13: conteo de modelos no acreditado')
    require({r.get('architecture') for r in doc['reports']}=={'hsarg_b1','coop_sarg_b1'},
            'H12.13: arquitecturas no emparejadas')
    return {'H1213':status,'source':str(p),'result_sha256':sha(f),
            'meaning':'Reporta entrenamiento de arquitecturas propias, NO acredita SOTA ni desempeño fuera de muestra'}

def check_resco_same_inputs(repo,net,route):
    n=repo/'baselines/RESCO/resco_benchmark/environments/hangzhou/hangzhou.net.xml'
    r=repo/'baselines/RESCO/resco_benchmark/environments/hangzhou/hangzhou.rou.xml'
    require(n.is_file() and r.is_file(),'Faltan red/rutas RESCO Hangzhou')
    return {'net_original':str(n.resolve()),'route_original':str(r.resolve()),
            'net_sha256':sha(n),'route_sha256':sha(r),
            'net_byte_identical_to_H1212':sha(n)==sha(net),
            'route_byte_identical_to_H1212':sha(r)==sha(route)}

def audit(repo,smoke,h1212,training=None):
    repo=pathlib.Path(repo).resolve(strict=True)
    h1212=pathlib.Path(h1212).resolve(strict=True)
    net=repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
    route=repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
    require(net.is_file() and route.is_file(),'Red/demanda Hangzhou faltante')
    geo=read_phase_xml(net)
    h12=manifest_check(pathlib.Path(smoke),net,route,h1212)
    rows,files=inspected_resco(repo)
    resco_inputs=check_resco_same_inputs(repo,net,route)
    extras=[repo/'baselines/RESCO/resco_benchmark/environments/hangzhou/hangzhou.net.xml',
            repo/'baselines/RESCO/resco_benchmark/environments/hangzhou/hangzhou.rou.xml']
    all_files=[net,route,*files,*extras,ROOT/'h12_14_auditar.py']
    require(len({str(p.resolve()) for p in all_files})==len(all_files),'Fuentes duplicadas inesperadas')
    names={r['controller']:r for r in rows}
    textm=(repo/'baselines/RESCO/resco_benchmark/agents/static/maxpressure.py').read_text(encoding='utf8')
    require('WaveAgent' in textm,'MAXPRESSURE RESCO ya no usa WaveAgent: revisar interfaz')
    cos=(repo/'baselines/RESCO/resco_benchmark/agents/policy/CoSLight/coslight.py').read_text(encoding='utf8')
    require('len(obs_act)' in cos and 'SharedAgent' in cos,'CoSLight: interfaz multiagente cambió')
    mp=(repo/'baselines/RESCO/resco_benchmark/agents/action_value/mplight.py').read_text(encoding='utf8')
    require('phase_pairs' in mp and 'build_comp_mask' in mp and 'FRAP' in mp,
            'MPLight no conserva interfaz fase-par / FRAP conocida')
    ip=(repo/'baselines/RESCO/resco_benchmark/agents/policy/pfrl_ppo.py').read_text(encoding='utf8')
    require('PFRLPPOAgent' in ip and 'PPO(' in ip,'IPPO referencia modificada inesperadamente')
    outcome={
      'result':'H12_14_SOTA_AUDIT_OK','schema':SCHEMA,
      'meaning':'Auditoría estática + validación de identidad de archivos; NINGUN controlador SOTA fue entrenado o ejecutado',
      'scope':'Hangzhou B1, baselines/RESCO original, sin tocar checkpoint ni código',
      'network':geo,'H1212':h12,'H1213':optional_train_check(pathlib.Path(training) if training else None),
      'resco_reference_inputs':resco_inputs,'controllers':rows,
      'source_sha256':{str(p.resolve()):sha(p) for p in all_files},
      'gates':{
        'source_code_and_yaml':'PASSED',
        'h1212_physical_contract':'PASSED',
        'resco_hangzhou_network_identity': 'PASSED' if resco_inputs['net_byte_identical_to_H1212'] else 'NOT_IDENTICAL',
        'resco_hangzhou_routes_identity': 'PASSED' if resco_inputs['route_byte_identical_to_H1212'] else 'NOT_IDENTICAL',
        'B1_SOTA_state_adapter':'NOT_IMPLEMENTED',
        'B1_SOTA_action_adapter':'NOT_IMPLEMENTED',
        'B1_SOTA_transition_adapter':'NOT_IMPLEMENTED',
        'SOTA_model_training':'NOT_ACCREDITED',
        'CoSLight_multi_TLS_environment':'NOT_IMPLEMENTED',
        'Vine_H09_injection_in_new_contract':'NOT_IMPLEMENTED',
        'SOTA_full_comparison':'BLOCKED'},
      'protocol':{
        'stage_A_B1':['Fixed physical homologated baseline','MaxPressure physical homologated baseline',
                      'IPPO adapted + retrained with verified 2 actions','MPLight original FRAP adapted and retrained',
                      'HSARG_B1/CoopSARG_B1 new architectures trained'],
        'stage_B_network':['CoSLight must use multi-agent controlled TLS not just B1',
                           'Match controller scope and opponent TLS policy',
                           'No network claim from single-B1 testing'],
        'fairness':['Freeze exact network and demand SHA','Match 5s decisions, 0.5s SUMO ticks, yellow 3s and min-green 10s',
                    'Match *decision opportunities* and matched SUMO seeds','Document own algorithm observation & reward mapping; do not silently replace SOTA architecture',
                    'Match interaction budgets, use multiple seeds and report compute/time',
                    'Freeze independent evaluation demand and Vine/H09 profiles',
                    'Causal comparison only under paired randomized experiments, not single seed'],
        'do_not_label':['RESCO code as trained checkpoint','RESCO CoSLight as original CoLight',
                        'RESCO MAXPRESSURE WaveAgent as theoretical MaxPressure without examination',
                        'local Coop-SARG-B1 as cooperative multiagent'],
      },
      'limitations':['Los códigos RESCO NO se han importado ni ejecutado','RESCO puede requerir dependencias/API históricas PFRL y cambios de adaptador',
                     'No existe equivalencia automática entre estados RESCO (drq, mplight, coslight) y H12.12 34D',
                     'No se han certificado modelos entrenados ni métricas de resiliencia',
                     'Una red igual byte a byte NO implica igual demand protocol, amarillo, decisiones, reward o entrenamiento'],
    }
    assert_sources(outcome)
    return outcome

def assert_sources(report):
    for file,digest in report['source_sha256'].items():require(sha(file)==digest,'Fuente cambió durante auditoría: '+file)

def md(report):
    lines=['# H12.14 — Auditoría de compatibilidad SOTA RESCO con H12.12','',
           f"**Estado:** `{report['result']}` — Código y metadatos auditados, **NO controladores entrenados ni certificados**.",'',
           '## Evidencia de contrato físico','',
           f"- H12.12 acreditado: `{report['H1212']['H1212_schema']}` · fases verdes {report['network']['green_indices']} · 4 carriles de entrada reales.",
           f"- Red RESCO Hangzhou igual byte a byte: **{report['resco_reference_inputs']['net_byte_identical_to_H1212']}**.",
           f"- Ruta RESCO Hangzhou igual byte a byte: **{report['resco_reference_inputs']['route_byte_identical_to_H1212']}**.",
           f"- Piloto H12.13: **{report['H1213']['H1213']}**.",'',
           '## Matriz de implementaciones y brechas','',
           '| Controlador | Fuente y registro YAML | Estado RESCO | Reward RESCO | Ámbito | Listo H12.12 |','|---|---|---|---|---|---|']
    for r in report['controllers']:
        lines.append(f"| {r['controller']} | Verificados | `{r['yaml_state']}` | `{r['yaml_reward']}` | `{r['scope']}` | **NO** |")
    lines+=['','## Puertas de homologación','']
    for gate,state in report['gates'].items():lines.append(f'- `{gate}`: **{state}**')
    lines+=['','## Por qué no son todavía controladores comparables','',
            '- IPPO RESCO emplea PFRL y entrada `drq`; H12.12 entrega observaciones 34D. Mantener arquitectura/recompensa documentadas o registrar adaptación.',
            '- MPLight RESCO es FRAP/DQN y usa pares de fases/direcciones; no es un PPO ni puede reemplazarse por una MLP y llamarse MPLight.',
            '- El `MAXPRESSURE` de RESCO delega en `WaveAgent` después de descartar el primer dato; su equivalencia con presión física requiere inspección de `state_builder` y la definición de presiones.',
            '- CoSLight usa `SharedAgent`, `num_agents` y políticas multiagente: un B1 aislado no prueba cooperación de red.',
            '- FIXED no necesita aprendizaje, pero debe fijarse explícitamente su calendario físico y transición de amarillos.',
            '- El experimento H12.13 piloto de 64 transiciones es opcional para esta auditoría y **no** certifica aprendizaje.',
            '','## Protocolo propuesto (no ejecutado)','',
            '**Nivel A (B1):** Fixed, MaxPressure, IPPO, MPLight y H-SARG-B1/Coop-SARG-B1 bajo el mismo dominio semafórico. '
            'Se deben registrar las diferencias de arquitectura y entradas de los SOTA: no se presupone igualdad de representación interna.',
            '', '**Nivel B (red multi-TLS):** CoSLight auténtico junto con comparadores multiagente; necesidad de control simultáneo y métrica de red. '
            'No afirmar cooperación de Coop-SARG-B1 hasta desarrollar versión multiagente.',
            '', '**Condición previa a resultados de resiliencia:** adaptación y pruebas integradas reales SUMO, checkpoints nuevos certificados, '
            'presupuestos y semillas emparejadas, verificación de inyección Vine/H09 en el entorno nuevo.',
            '', '## Límites', '']
    lines+=['- '+v for v in report['limitations']]
    lines+=['','**Dictamen final:** H12.14 demuestra disponibilidad de fuentes, describe brechas y define gates. '
            'No acredita que ningún SOTA esté funcionando con H12.12 ni habilita entrenamiento comparativo todavía.','']
    return '\n'.join(lines)

def write_unique(path,data):
    require(not path.exists(),'No se sobrescribe archivo: '+str(path))
    with path.open('x',encoding='utf-8',newline='') as f:f.write(data)

def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root',type=pathlib.Path,required=True)
    p.add_argument('--revision-root',type=pathlib.Path,default=pathlib.Path('.'))
    p.add_argument('--smoke-dir',type=pathlib.Path,required=True)
    p.add_argument('--h1212-dir',type=pathlib.Path,default=pathlib.Path('H12_12_Entorno_Homologado_B1_v100'))
    p.add_argument('--h1213-run',type=pathlib.Path)
    p.add_argument('--mode',choices=['plan','analyze'],default='plan')
    a=p.parse_args(argv)
    try:
        revision=a.revision_root.resolve(strict=True)
        h1212=a.h1212_dir if a.h1212_dir.is_absolute() else revision/a.h1212_dir
        report=audit(a.repo_root,a.smoke_dir,h1212,a.h1213_run)
        print('H12.14 | RESCO verificados:',', '.join(x['controller'] for x in report['controllers']))
        print('H12.14 | Red RESCO == H12.12:',report['resco_reference_inputs']['net_byte_identical_to_H1212'],
              '| rutas:',report['resco_reference_inputs']['route_byte_identical_to_H1212'])
        if a.mode=='plan':
            print('H12_14_PLAN_OK | solo lectura, sin salida, sin SUMO, sin carga de SOTA')
            return 0
        root=revision/'resultados';root.mkdir(parents=True,exist_ok=True)
        dest=root/('h12_14_sota_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6]);dest.mkdir(exist_ok=False)
        try:
            assert_sources(report)
            write_unique(dest/'dictamen_h12_14.json',json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
            write_unique(dest/'dictamen_h12_14.md',md(report))
            csvpath=dest/'matriz_sota_h12_14.csv'
            with csvpath.open('x',newline='',encoding='utf-8-sig') as f:
                writer=csv.DictWriter(f,fieldnames=list(report['controllers'][0].keys()))
                writer.writeheader();writer.writerows(report['controllers'])
            assert_sources(report)
        except Exception:
            write_unique(dest/'ERROR_h12_14.json',json.dumps({'error':'postflight_failed'},indent=2))
            raise
        print('H12_14_SOTA_AUDIT_OK',dest)
        return 0
    except (AuditError,ValueError,FileNotFoundError,KeyError,OSError,TypeError) as e:
        print('H12_14_FAIL_CLOSED',type(e).__name__,str(e),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(run())
