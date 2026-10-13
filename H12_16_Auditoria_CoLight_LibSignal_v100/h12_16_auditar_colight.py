"""H12.16 — auditoría offline de CoLight original vs LibSignal.

No clona repositorios, instala dependencias, importa módulos de RL, ejecuta SUMO
ni carga checkpoints. Requiere COPIAS LOCALES de commits fijados por SHA;
compara blobs de git y evidencia H12.14 antes de emitir dictamen de fuentes.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
PIN_FILE = ROOT / 'upstream_pins.json'
SCHEMA = 'H12_16_COLIGHT_SOURCE_AUDIT_V100'

class AuditError(RuntimeError):
    pass


def require(condition, msg):
    if not condition:
        raise AuditError(msg)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def git_blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def load_pins():
    p = json.loads(PIN_FILE.read_text(encoding='utf-8'))
    require(p.get('schema') == 'H12_16_PINNED_SOURCES_V100', 'Schema de pins inválido')
    for key in ('original','libsignal'):
        entry=p[key]
        require(bool(re.fullmatch(r'[a-f0-9]{40}', entry['commit'])), 'Commit malformado: '+key)
        require(all(re.fullmatch(r'[a-f0-9]{40}', s) for s in entry['files'].values()), 'Blobs inválidos')
    return p


def run_git(path, *args, binary=False):
    cmd = ['git','-C',str(Path(path)),'--no-pager',*args]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=35, check=False)
    except (OSError,subprocess.TimeoutExpired) as e:
        raise AuditError(f'No se pudo ejecutar git en {path}: {type(e).__name__}') from e
    if p.returncode:
        desc = p.stderr.decode('utf-8','replace').strip()[:280]
        raise AuditError(f'Git {" ".join(args[:2])} falló: {desc}')
    return p.stdout if binary else p.stdout.decode('utf-8','replace').strip()


def verify_git_repo(path, pin, *, require_clean=True):
    path = Path(path).resolve()
    require(path.is_dir(), 'Clon local no encontrado: '+str(path))
    realroot = Path(run_git(path, 'rev-parse', '--show-toplevel')).resolve()
    require(realroot==path, 'La ruta debe ser la RAÍZ del repositorio git: '+str(path))
    head = run_git(path, 'rev-parse', 'HEAD')
    require(head == pin['commit'], 'Commit equivocado en '+str(path)+'; requerido '+pin['commit']+'; actual '+head)
    if require_clean:
        changes=run_git(path,'status','--porcelain','--untracked-files=no')
        require(not changes, 'Hay modificaciones en archivos tracked; no auditar sin conservar fuentes: '+changes[:200])
    origin=run_git(path,'remote','get-url','origin')
    normalized=origin.lower().replace('.git','').rstrip('/')
    require(pin['repository'].lower() in normalized, 'Remote origin no corresponde a '+pin['repository']+': '+origin)
    source_bytes={}; ledger=[]
    for rel,blob_sha in sorted(pin['files'].items()):
        require(not (rel.startswith('/') or '..' in Path(rel).parts), 'Ruta insegura en pin')
        data=run_git(path, 'show',f'{head}:{rel}',binary=True)
        calc=git_blob_sha(data)
        require(calc==blob_sha, 'Blob SHA no coincide: '+rel+' esperado '+blob_sha+' real '+calc)
        require((path/rel).is_file(), 'Checkout incompleto: '+str(path/rel))
        # Respect committed bytes on Windows; checkout may use CRLF. Dirty check above catches manual edits.
        source_bytes[rel]=data
        ledger.append({'repository':pin['repository'], 'commit':head,
                       'path':rel, 'blob_sha1':calc,'sha256_git_blob':sha256_bytes(data),'size_bytes':len(data)})
    return {'repository':pin['repository'],'local_path':str(path),'commit':head,'origin':origin,'files':ledger},source_bytes


def decoding(data, label):
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError as e:
        raise AuditError('Fuente sin UTF-8: '+label) from e


def assert_python_ast(text, label):
    try:
        return ast.parse(text, filename=label)
    except SyntaxError as e:
        raise AuditError(f'Sintaxis inválida en {label}: {e.msg} línea {e.lineno}') from e


def top_classes(tree):
    return {n.name for n in tree.body if isinstance(n,ast.ClassDef)}


def unused_sorted_calls(tree):
    # AST: sorted(sequence, ...) escrito como statement no tiene efecto sobre el orden original.
    return [n.lineno for n in ast.walk(tree) if isinstance(n,ast.Expr)
            and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name)
            and n.value.func.id=='sorted']


def source_checks(original,libsignal):
    orig=decoding(original['CoLight_agent.py'],'CoLight_agent.py')
    oreq=decoding(original['requirements.txt'],'requirements.txt original')
    otree=assert_python_ast(orig,'CoLight_agent.py')
    require('CoLightAgent' in top_classes(otree),'Falta CoLightAgent en fuente original')
    require('MultiHeadsAttModel' in orig and 'self.num_agents' in orig,
            'No se verificó atención multiagente original')
    require('tensorflow==1.11' in oreq and 'keras==2.1' in oreq,
            'Dependencias originales distintas de TensorFlow 1.11 y Keras 2.1')

    new=decoding(libsignal['agent/colight.py'],'LibSignal agent/colight.py')
    pyalt=decoding(libsignal['agent/colight_pytorch_agent.py'],'agent/colight_pytorch_agent.py')
    init=decoding(libsignal['agent/__init__.py'],'agent/__init__.py')
    yml=decoding(libsignal['configs/tsc/colight.yml'],'colight.yml')
    sumocfg=decoding(libsignal['configs/sim/sumo1x1_colight.cfg'],'sumo1x1_colight.cfg')
    world=decoding(libsignal['world/world_sumo.py'],'world/world_sumo.py')
    newtree=assert_python_ast(new,'LibSignal/agent/colight.py')
    alttree=assert_python_ast(pyalt,'LibSignal/agent/colight_pytorch_agent.py')
    require({'CoLightAgent','ColightNet','MultiHeadAttModel'}.issubset(top_classes(newtree)),
            'Implementación LibSignal no conserva clases del agente y red de atención')
    require('MessagePassing' in new and 'torch_scatter' in new and 'torch_geometric' in new,
            'No se verificó atención de grafo PyTorch Geometric')
    require("@Registry.register_model('colight')" in new,
            'La implementación CoLight no está registrada como modelo colight')
    require('from .colight import CoLightAgent' in init,
            'El agente CoLight PyTorch no aparece importado desde agent/__init__.py')
    require('self.graph' in new and "self.graph['sparse_adj']" in new and
            'len(self.world.intersections)' in new and 'phase_lengths' in new,
            'No se verificó enlace entre red de intersecciones, fases y CoLight')
    require(re.search(r'(?m)^\s*name:\s*colight\s*$',yml),
            'Configuración de CoLight carece de model.name colight')
    require('N_LAYERS:' in yml and 'NUM_HEADS:' in yml and 'NEIGHBOR_NUM:' in yml,
            'Falta configuración explícita de atención vecinal')
    require('def create_yellows' in world,'LibSignal no tiene la rutina SUMO create_yellows esperada')
    require('CoLightAgent' in top_classes(alttree), 'Falta variante alternativa de CoLight')
    require('from .colight_pytorch_agent import' not in init,
            'La variante colight_pytorch_agent.py ahora parece importada: revisar selección')
    config = json.loads(sumocfg)
    require(isinstance(config,dict) and config.get('network')=='cologne1',
            'El ejemplo SUMO ya no corresponde a Cologne1: revisar protocolo')
    return {
       'original_framework':'TensorFlow 1.11 / Keras 2.1 (fuente histórica, no ejecutada)',
       'libsignal_framework':'PyTorch / torch_geometric / torch_scatter (fuente auditada, no importada)',
       'actual_registered_agent':'agent/colight.py::CoLightAgent',
       'alternative_file':'agent/colight_pytorch_agent.py no registrado en agent/__init__.py',
       'network_attention_verified_in_source':True,
       'graph_edge_source':"graph['sparse_adj'] (requiere verificar orden de nodos en runtime)",
       'heterogeneous_phases':'El código usa phase_lengths, máscara de acciones y grafo global',
       'inert_sorted_lines':unused_sorted_calls(newtree),
       'unassigned_sorted_warning':bool(unused_sorted_calls(newtree)),
       'example_sumo_network':config.get('network'),
       'example_sumo_is_hangzhou':config.get('network')=='hangzhou',
       'SUMO_yellow_helper_present':True,
       'incompatible_libraries_for_direct_legacy_execution': ['tensorflow==1.11','keras==2.1'],
    }


def inspect_network(path):
    path=Path(path)
    raw=path.read_bytes()
    require(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),
            'No se permite DTD en red SUMO')
    try:root=ET.fromstring(raw)
    except ET.ParseError as e:raise AuditError('XML Hangzhou inválido') from e
    signals=[]
    for logic in root.findall('tlLogic'):
        ph=logic.findall('phase')
        states=[p.get('state','') for p in ph]
        green=[i for i,s in enumerate(states) if any(c in 'Gg' for c in s)]
        amber=[i for i,s in enumerate(states) if 'y' in s.lower() and not any(c in 'Gg' for c in s)]
        signals.append({'tls':logic.get('id'),'n_phases':len(states),'green_indices':green,
                        'yellow_indices':amber,'program_type':logic.get('type')})
    require(len(signals)>=2,'La red no es multi-TLS')
    b1=[s for s in signals if s['tls']=='B1']
    require(len(b1)==1 and b1[0]['green_indices']==[0,2] and b1[0]['yellow_indices']==[1,3],
            'Contrato B1 contradice H12.12')
    ids=[x['tls'] for x in signals]
    require(len(set(ids))==len(ids),'IDs TLS duplicados')
    connections=[c for c in root.findall('connection') if c.get('tl') in set(ids)]
    count={name:0 for name in ids}
    for c in connections:count[c.get('tl')]+=1
    require(all(n>0 for n in count.values()),'Semáforo sin conexiones de entrada controladas')
    return {'n_tls':len(signals),'n_tls_with_connections':len(count),
            'b1_phases':b1[0], 'signals':signals,
            'all_two_green':all(len(s['green_indices'])==2 for s in signals)}


def local_h1214_check(repo,pins,h1214_dir=None,h1215_dir=None):
    repo=Path(repo).resolve()
    network=repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
    routes=repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
    require(network.is_file() and routes.is_file(),'No existen red/rutas Hangzhou locales')
    net_sha=sha256_file(network); route_sha=sha256_file(routes)
    require(net_sha==pins['local_hangzhou_net_sha256'], 'SHA-256 de red H12.12 no coincide')
    require(route_sha==pins['local_hangzhou_routes_sha256'], 'SHA-256 de rutas H12.12 no coincide')
    result={'repo_root':str(repo),'network_sha256':net_sha,'route_sha256':route_sha,
            'network':inspect_network(network),'H1214':'NOT_SUPPLIED','H1215':'NOT_SUPPLIED'}
    if h1214_dir:
        p=Path(h1214_dir)/'dictamen_h12_14.json'
        require(p.is_file(),'Falta dictamen_h12_14.json')
        a=json.loads(p.read_text(encoding='utf8'))
        require(a.get('result')=='H12_14_SOTA_AUDIT_OK','H12.14 no acreditado')
        identity=a.get('resco_reference_inputs',{})
        require(identity.get('net_byte_identical_to_H1212') is True and identity.get('route_byte_identical_to_H1212') is True,
                'H12.14 sin equivalencia byte red/rutas')
        require(identity.get('net_sha256')==net_sha and identity.get('route_sha256')==route_sha,
                'Los SHA de H12.14 no coinciden con fuentes actuales')
        result['H1214']={'status':a['result'],'report_sha256':sha256_file(p)}
    if h1215_dir:
        p=Path(h1215_dir)/'resultado_h12_15.json'
        require(p.is_file(),'Falta resultado_h12_15.json')
        a=json.loads(p.read_text(encoding='utf8'))
        require(a.get('result')=='H12_15_PHYSICAL_SMOKE_OK', 'H12.15 no acreditado')
        result['H1215']={'status':a['result'],'report_sha256':sha256_file(p)}
    return result


def dep_inventory():
    out={}
    for name in ['torch','torch_scatter','torch_geometric','gym','gymnasium','traci','libsumo','tensorflow','keras']:
        try:spec=importlib.util.find_spec(name)
        except (ModuleNotFoundError,ValueError):spec=None
        out[name]='present_not_imported' if spec is not None else 'not_found'
    return out


def audit(args,pins):
    original,obytes=verify_git_repo(args.original_dir,pins['original'])
    library,lbytes=verify_git_repo(args.libsignal_dir,pins['libsignal'])
    features=source_checks(obytes,lbytes)
    contract=local_h1214_check(args.repo_root,pins,args.h1214_dir,args.h1215_dir)
    docs={
        'result':'H12_16_COLIGHT_SOURCE_AUDIT_OK','schema':SCHEMA,
        'meaning':'FUENTES/CONTRATO auditados; SIN ejecución de CoLight, SUMO o entrenamiento',
        'original':original,'libsignal':library,'feature_audit':features,
        'local_contract':contract,'dependencies_environment':dep_inventory(),
        'gates':{
            'upstream_orig_authenticity':'PASSED_PINNED_COMMIT_AND_BLOBS',
            'upstream_libsignal_authenticity':'PASSED_PINNED_COMMIT_AND_BLOBS',
            'colight_network_attention':'PRESENT_STATICALLY',
            'registered_colight_pytorch':'PRESENT_STATICALLY',
            'libsignal_sumo_support':'PRESENT_STATICALLY',
            'h1212_hangzhou_network_and_demand':'PASSED_IDENTITY',
            'node_order_graph_runtime':'NOT_VERIFIED',
            'yellow_transition_equivalence':'NOT_VERIFIED',
            'phase_action_masking_network':'NOT_VERIFIED',
            'libs_binary_compatibility':'NOT_VERIFIED',
            'multi_tls_h1212_adapter':'NOT_IMPLEMENTED',
            'colight_training_checkpoint':'NOT_ACCREDITED',
            'training_equal_budget':'NOT_ACCREDITED',
            'Vine_H09_injection_multi_TLS':'NOT_IMPLEMENTED',
            'sota_resilience':'BLOCKED'
        },
        'next_stage':'H12.17 multi-TLS and verified CoLight interface; avoid relabeling different model as CoLight',
        'time_utc':datetime.now(timezone.utc).isoformat(),
    }
    return docs


def report_markdown(x):
    f=x['feature_audit'];c=x['local_contract'];g=x['gates'];n=c['network']
    rows='\n'.join(f'| `{k}` | **{v}** |' for k,v in g.items())
    sig='; '.join(f"{s['tls']}:{s['green_indices']}" for s in n['signals'][:12])
    return f'''# H12.16 — CoLight auténtico: código original versus LibSignal

**Estado:** `{x['result']}` — Auditoría **estática de código y trazabilidad**, NO ejecución del algoritmo ni certificación SOTA.

## Fuentes congeladas

| Código | Commit fijado | Uso previsto |
|---|---|---|
| CoLight original (wingsweihua/colight) | `{x['original']['commit']}` | Referencia de arquitectura TensorFlow/Keras |
| LibSignal (DaRL-LibSignal/LibSignal) | `{x['libsignal']['commit']}` | Candidato de integración PyTorch + SUMO |

Los archivos de ambos repositorios fueron cotejados mediante SHA-1 de blobs Git y SHA-256 del contenido comprometido; no se ejecutaron.

## Hallazgos de implementación

- Agente original: {f['original_framework']}.
- Agente LibSignal registrado: `{f['actual_registered_agent']}`; {f['libsignal_framework']}.
- Variante alternativa no registrada: `{f['alternative_file']}`.
- Atención entre intersecciones y adyacencia dispersa: **presentes en fuente**; identidad del orden de nodos **sin validar en runtime**.
- **Advertencia de orden:** llamadas `sorted(...)` cuyo resultado no se usa (líneas del agente LibSignal: `{f['inert_sorted_lines']}`). Debe evaluarse el riesgo de desalineación índice-grafo, sin modificar el algoritmo original a ciegas.
- Configuración SUMO de ejemplo LibSignal: `{f['example_sumo_network']}`; **NO es Hangzhou**.
- Dependencias PyTorch Geometric y `torch_scatter`: declaradas/importadas por la fuente; compatibilidad de ruedas Windows no certificada.

## Condiciones físicas Hangzhou

- La red local (SHA-256 validado) posee **{n['n_tls']} semáforos** con conexiones; B1 verdes `{n['b1_phases']['green_indices']}`, amarillos `{n['b1_phases']['yellow_indices']}`.
- Primeros semáforos: {sig}.
- H12.14: `{c['H1214'] if isinstance(c['H1214'],str) else c['H1214']['status']}`. H12.15: `{c['H1215'] if isinstance(c['H1215'],str) else c['H1215']['status']}`.
- Red y rutas iguales a H12.12. Eso NO acredita el grafo de vecindad ni igualdad de semántica de acciones/amarillos.

## Puertas de homologación

| Gate | Estado |
|---|---|
{rows}

## Decisión

**CoLight queda incorporado formalmente como comparador multiagente**, preferentemente a través de LibSignal. El siguiente paso NO es iniciar entrenamiento comparativo: primero construir adaptador multi-TLS que conserve la atención basada en adyacencia y ejecutar pilotos de control real SUMO con observaciones, fases y transiciones trazables. CoSLight sigue siendo un SOTA distinto.

## Limitaciones

- No se importó CoLight ni se ejecutaron SUMO, PyTorch, CityFlow o entrenamientos.
- `torch_scatter`/`torch_geometric` detectados o ausentes por `find_spec` no implican compatibilidad binaria.
- El agente PyTorch no es identidad de parámetros frente al CoLight TensorFlow de los autores.
- No hay checkpoint de CoLight verificado, ni robustez, transferencia o representatividad de Quito.
- H12.16 no altera H12.12–H12.15 ni los PPO históricos.
'''


def save_result(root,doc):
    outroot=Path(root).resolve();outroot.mkdir(parents=True,exist_ok=True)
    path=outroot/('h12_16_colight_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid4().hex[:6])
    path.mkdir(exist_ok=False)
    try:
        (path/'dictamen_h12_16.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        (path/'dictamen_h12_16.md').write_text(report_markdown(doc),encoding='utf8')
        with (path/'fuentes_git_h12_16.csv').open('w',newline='',encoding='utf-8-sig') as fp:
            writer=csv.DictWriter(fp,fieldnames=['repository','commit','path','blob_sha1','sha256_git_blob','size_bytes']);writer.writeheader()
            writer.writerows(doc['original']['files']+doc['libsignal']['files'])
        (path/'pins_sha256.txt').write_text(sha256_file(PIN_FILE)+'  upstream_pins.json\n',encoding='utf8')
    except Exception:
        # Preserve diagnosis rather than silently claiming success; files remain available.
        raise
    return path


def parse_args(argv=None):
    p=argparse.ArgumentParser(description='H12.16 auditoría CoLight vs LibSignal: no corre modelos ni SUMO')
    p.add_argument('--mode',choices=['inventory','plan','analyze'],default='inventory')
    p.add_argument('--repo-root',type=Path)
    p.add_argument('--original-dir',type=Path)
    p.add_argument('--libsignal-dir',type=Path)
    p.add_argument('--h1214-dir',type=Path)
    p.add_argument('--h1215-dir',type=Path)
    p.add_argument('--results-root',type=Path,default=Path('resultados'))
    return p.parse_args(argv)


def main(argv=None):
    try:
        a=parse_args(argv);pins=load_pins()
        if a.mode=='inventory':
            print('H12.16 | Fuentes remotas fijadas en upstream_pins.json; ninguna clonación ni ejecución')
            for key in ('original','libsignal'):
                e=pins[key]
                print(key, e['url'],e['commit'],'archivos fijados:',len(e['files']))
            print('H12_16_INVENTORY_OK | para PLAN/ANALYZE se requieren clones locales en los commits indicados')
            return 0
        require(a.repo_root and a.original_dir and a.libsignal_dir and a.h1214_dir,
                'Se requieren --repo-root, --original-dir, --libsignal-dir, --h1214-dir (auditoria H12.14 acreditada)')
        x=audit(a,pins)
        print('H12.16 | CoLight original verificado:',x['original']['commit'][:16],
              '| LibSignal verificado:',x['libsignal']['commit'][:16])
        print('H12.16 | TLS Hangzhou:',x['local_contract']['network']['n_tls'],
              '| sorted sin asignación:',len(x['feature_audit']['inert_sorted_lines']))
        if a.mode=='plan':
            print('H12_16_PLAN_OK | sin salidas nuevas, sin SUMO, sin cargar CoLight')
            return 0
        path=save_result(a.results_root,x)
        print('H12_16_COLIGHT_SOURCE_AUDIT_OK',path)
        return 0
    except (AuditError,KeyError,ValueError,OSError,TypeError,json.JSONDecodeError) as e:
        print('H12.16 FAIL-CLOSED:',type(e).__name__,str(e),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
