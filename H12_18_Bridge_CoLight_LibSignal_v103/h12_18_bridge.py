"""H12.18: auditoria de interfaz CoLight LibSignal <-> H12.17.

plan: stdlib, solo lectura. deps: importa modelo upstream en subproceso (sin SUMO).
shadow: controla SUMO solo con politica TEST H12.17; CoLight original ejecuta
forward con pesos aleatorios, sus acciones SOLO SE REGISTRAN; nunca se aplican.
No modifica codigo upstream, no carga checkpoints ni entrena.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import traceback
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
SCHEMA = 'H12_18_LIBSIGNAL_GRAPH_SHADOW_V103_REGISTERED_MODULE'
LIBSIGNAL_COMMIT = '127af9f93902778e556de2eedb2b606c4c9447e6'
LIBSIGNAL_MAIN_BLOB = 'b33858268b51fa008df2ea4ee4bea725a74de476'
NET_SHA = '2590ca460dafb57a4c608f4fe1ad9de072068a5b2ef0ea487f617296d8c627f6'
ROUTE_SHA = 'a78363c99e1a6eab33028c3a36c82dcb66129adf8e73141612b9e7b2358f1369'
NODES = ('A1','A2','B0','B1','B2','B3','C0','C1','C2','C3','D1','D2')

class GateError(RuntimeError): pass

def check(ok, msg):
    if not ok: raise GateError(msg)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def load_json(path):
    p=Path(path)
    check(p.is_file(),'Archivo no encontrado: '+str(p))
    return json.loads(p.read_text(encoding='utf-8'))

def git_cmd(root,*args):
    p=subprocess.run(['git','-C',str(root),'--no-pager',*args],capture_output=True,timeout=30)
    check(p.returncode==0,'git '+str(args)+': '+p.stderr.decode('utf8','replace')[:300])
    return p.stdout

def git_source(lib, prior):
    """Solo archivo ORIGINAL comprometido en H12.16; nada de variantes locales."""
    lib=Path(lib).resolve(strict=True)
    check(Path(git_cmd(lib,'rev-parse','--show-toplevel').decode().strip()).resolve()==lib,
          'LibSignal-dir no es raiz del clon')
    check(git_cmd(lib,'rev-parse','HEAD').decode().strip()==LIBSIGNAL_COMMIT,
          'Commit LibSignal distinto del fijado en H12.16')
    check(not git_cmd(lib,'status','--porcelain','--untracked-files=no').strip(),
          'Archivos seguidos modificados en LibSignal')
    source=lib/'agent'/'colight.py'
    check(source.is_file(), 'Falta agente CoLight registrado')
    blob=git_cmd(lib,'rev-parse','HEAD:agent/colight.py').decode().strip()
    check(blob==LIBSIGNAL_MAIN_BLOB,'Blob SHA-1 del agente distinto de H12.16')
    raw=git_cmd(lib,'show','HEAD:agent/colight.py')
    check(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest()==blob,
          'Contenido comprometido del agente no coincide')
    check(prior['libsignal']['commit']==LIBSIGNAL_COMMIT,'H12.16 no acredita este commit')
    check(Path(prior['libsignal']['local_path']).resolve()==lib,
          'La ruta de LibSignal no corresponde al clon auditado en H12.16')
    led={f['path']:f for f in prior['libsignal']['files']}
    check(led['agent/colight.py']['blob_sha1']==blob,
          'El reporte H12.16 no contiene el blob esperado')
    # El YAML fija hiperparametros de arquitectura usados en el forward.
    yblob=git_cmd(lib,'rev-parse','HEAD:configs/tsc/colight.yml').decode().strip()
    check(led['configs/tsc/colight.yml']['blob_sha1']==yblob,
          'El YAML LibSignal no coincide con H12.16')
    cfgraw=git_cmd(lib,'show','HEAD:configs/tsc/colight.yml')
    check(hashlib.sha1(b'blob '+str(len(cfgraw)).encode()+b'\x00'+cfgraw).hexdigest()==yblob,
          'Blob del YAML upstream incorrecto')
    return dict(commit=LIBSIGNAL_COMMIT,blob_sha1=blob,
                config_blob_sha1=yblob,config_committed_sha256=hashlib.sha256(cfgraw).hexdigest(),
                config_worktree_sha256=sha(lib/'configs/tsc/colight.yml'),
                committed_file_sha256=hashlib.sha256(raw).hexdigest(),
                worktree_sha256=sha(source),local_path=str(lib),source_path=str(source))

def verify_graph(g):
    """Cada elemento de x[i] corresponde exactamente al semaforo node_order[i]."""
    check(g.get('node_order')==list(NODES),'Orden canonical de 12 semaforos cambiado')
    d=g.get('node_to_index')
    check(d=={n:i for i,n in enumerate(NODES)},'node_to_index desalineado')
    edges=g.get('graph_directed_edge_index')
    check(isinstance(edges,list) and len(edges)==2 and len(edges[0])==len(edges[1])==32,
          'edge_index debe ser (2,32)')
    pairs=list(zip(edges[0],edges[1]))
    check(all(type(a) is int and type(b) is int and 0<=a<12 and 0<=b<12 and a!=b for a,b in pairs),
          'Grafo con indice invalido o self-loop')
    check(len(set(pairs))==32,'Hay aristas repetidas')
    check(pairs==sorted(pairs),'Orden de aristas no canonico')
    check(g.get('graph_directed_edges')==[[NODES[a],NODES[b]] for a,b in pairs],
          'graph_directed_edges contradice edge_index')
    geos=g.get('geometries')
    check(isinstance(geos,dict) and set(geos)==set(NODES),'Geometrias incompletas')
    for n in NODES:
        x=geos[n]
        lanes=x.get('lanes_in')
        check(isinstance(lanes,list) and 1<=len(lanes)<=4 and lanes==sorted(set(lanes)),
              'Carriles no unicos/ordenados: '+n)
        check(x.get('green_indices')==[0,2], 'Acciones fisicas distintas de 2 verdes: '+n)
    return dict(node_order=list(NODES),edge_index=edges,
                incoming_lanes={n:geos[n]['lanes_in'] for n in NODES},
                input_dim=4,output_dim=2)

def counts_to_x(lanes,counts):
    """CoLight: lane_count fisico, 4 posiciones por nodo, 0 en padding.
    No reutiliza obs34 ni la rama de colas H12.17 como entrada nativa.
    Orden INDEPENDIENTE del iterador del agente LibSignal, anclado al grafo.
    """
    check(set(lanes)==set(NODES), 'Falta identificador TLS')
    rows=[]
    for n in NODES:
        ls=lanes[n]
        check(1<=len(ls)<=4 and ls==sorted(set(ls)),'Carriles sin orden/duplicados: '+n)
        row=[]
        for l in ls:
            check(l in counts,'Falta conteo de carril '+l)
            v=counts[l]
            check(type(v) in (int,float) and math.isfinite(v) and v>=0,
                  'lane_count invalido '+l)
            row.append(float(v))
        row += [0.0]*(4-len(row))
        rows.append(row)
    check(len(rows)==12 and all(len(a)==4 for a in rows),'Dimensiones de x invalidas')
    return rows

def verify_h1217(run_dir,rev,repo):
    run_dir=Path(run_dir).resolve(strict=True)
    mf=run_dir/'manifiesto_h12_17.json'
    sf=run_dir/'smoke_h12_17.json'
    rt=run_dir/'runtime_h12_17.json'
    manifest=load_json(mf);smoke=load_json(sf)
    check(rt.is_file(),'Falta runtime_h12_17.json')
    check(smoke.get('result')=='H12_17_MULTI_TLS_SMOKE_OK','H12.17 sin smoke SUMO real')
    check(smoke.get('manifest_sha256')==sha(mf),'H12.17 manifiesto cambiado')
    check(smoke.get('runtime_sha256')==sha(rt),'H12.17 runtime cambiado')
    check(smoke.get('n_tls')==12 and smoke.get('n_decisions')>=12,
          'H12.17 smoke incompleto')
    check(smoke.get('n_microticks')==10*smoke['n_decisions'],'Microticks H12.17 inconsistentes')
    check(smoke.get('integrity_postflight')=='PASS','H12.17 postflight sin acreditar')
    check(manifest.get('network_sha256')==NET_SHA and manifest.get('route_sha256')==ROUTE_SHA,
          'SUMO Hangzhou no es la version H12.12')
    gr=verify_graph(manifest['graph'])
    check(smoke.get('node_order')==gr['node_order'] and smoke.get('edge_index')==gr['edge_index'],
          'Orden grafo/filas H12.17 no acreditado')
    net=Path(repo)/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
    route=Path(repo)/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
    check(Path(manifest['network']).resolve()==net.resolve() and
          Path(manifest['routes']).resolve()==route.resolve(),
          'SUMO red/rutas no coinciden con H12.17')
    shas=manifest['source_sha256']
    for p,h in shas.items():
        check(Path(p).is_file() and sha(p)==h, 'Una fuente de H12.17 ha cambiado: '+p)
    check(shas[str(net.resolve())]==NET_SHA and shas[str(route.resolve())]==ROUTE_SHA,
          'El ledger H12.17 contradice el SHA Hangzhou')
    check(isinstance(smoke.get('data'),list) and len(smoke['data'])==smoke['n_decisions'],
          'Reporte H12.17 sin decisiones completas')
    return manifest,smoke,dict(report_sha256=sha(sf),manifest_sha256=sha(mf),
                               runtime_sha256=sha(rt),run_dir=str(run_dir),graph=gr)

def verify_h1216(run_dir, lib):
    run_dir=Path(run_dir).resolve(strict=True)
    report_path=run_dir/'dictamen_h12_16.json'
    r=load_json(report_path)
    check(r.get('result')=='H12_16_COLIGHT_SOURCE_AUDIT_OK','H12.16 no acreditado')
    check(r.get('gates',{}).get('upstream_libsignal_authenticity')=='PASSED_PINNED_COMMIT_AND_BLOBS',
          'H12.16 no anclo fuente LibSignal')
    check(r.get('local_contract',{}).get('network_sha256')==NET_SHA and
          r.get('local_contract',{}).get('route_sha256')==ROUTE_SHA,
          'H12.16 contrato fisico distinto')
    src=git_source(lib,r)
    return r,src,dict(report_sha256=sha(report_path),run_dir=str(run_dir))

def make_plan(a):
    rev=Path(a.revision_root).resolve(strict=True)
    repo=Path(a.repo_root).resolve(strict=True)
    h17m,h17s,h17=verify_h1217(a.h1217_dir,rev,repo)
    h16r,src,h16=verify_h1216(a.h1216_dir,a.libsignal_dir)
    check(Path(h17m['prior']['h1216_report_path']).resolve()==
          (Path(a.h1216_dir).resolve()/'dictamen_h12_16.json').resolve(),
          'H12.17 no deriva de H12.16 suministrado')
    check(h17m['prior']['h1216_report_sha256']==h16['report_sha256'],
          'SHA del antecedente H12.16 cambiado')
    check(h17m['prior']['h1212_smoke_report_sha256']==sha(h17m['prior']['h1212_smoke_path']),
          'Reporte H12.12 original ha cambiado')
    return dict(schema=SCHEMA,result='H12_18_PRECHECK_OK',
                local_h1218_source_sha256={str(ROOT/'h12_18_bridge.py'):sha(ROOT/'h12_18_bridge.py'),
                    str(ROOT/'h12_18_libsignal_probe.py'):sha(ROOT/'h12_18_libsignal_probe.py'),
                    str(ROOT/'h12_18_colight_loader.py'):sha(ROOT/'h12_18_colight_loader.py')},
                provenance=dict(h1217=h17,h1216=h16,libsignal=src),
                graph=h17['graph'],
                topology=dict(n_tls=12,n_directed_edges=32,node_order=list(NODES),
                              green_phases=[0,2],actions_per_tls=2),
                adapter=dict(state_native='lane_count per incoming lane, ordered by net.xml lane id',
                             state_shape=[12,4],state_padding='zero to 4 lanes per TLS',
                             phase_input=False,vehicle_max=1.,
                             policy_import='original agent/colight.py ColightNet class AST (isolated: no CityFlow import)',
                             network_params_source='configs/tsc/colight.yml (selected architecture fields)',
                             graph_source='H12.17 explicit edge_index; PyG adds self-loops',
                             action_semantics='argmax of Q per node; shadow only; never actuates',
                             difference_from_native='ESPECIALIZACION: lista de carriles ordenada por contrato XML, no generadores internos LibSignal; importacion aislada de clases sin CoLightAgent/Trainer',
                             optimizer='NOT_RUN',checkpoint='NONE_RANDOM_INIT'),
                gates=dict(H1217_real_multi_TLS='PASSED',H1216_upstream='VERIFIED',
                           runtime_dependencies='NOT_CHECKED',colight_forward='NOT_EXECUTED',
                           graph_order='CHECKED_INPUT_ADAPTER_NOT_FULL_LIBSIGNAL_WORLD',
                           training='NOT_RUN',resilience='BLOCKED'))

def unique_dir(root):
    r=Path(root)/'resultados';r.mkdir(parents=True,exist_ok=True)
    o=r/('h12_18_colight_shadow_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6]);o.mkdir(exist_ok=False)
    return o

def save_json(p,x):
    with Path(p).open('x',encoding='utf-8') as f:
        json.dump(x,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')

def import_probe_cmd(lib,src,mode='deps'):
    return [sys.executable,str(ROOT/'h12_18_libsignal_probe.py'),
            '--libsignal-dir',str(lib),'--mode',mode,
            '--expected-source-sha256',src['worktree_sha256'],
            '--expected-config-sha256',src['config_worktree_sha256']]

def deps(a,plan):
    p=subprocess.run(import_probe_cmd(a.libsignal_dir,plan['provenance']['libsignal'],'deps'),capture_output=True,
                     text=True,timeout=90)
    if p.stdout:print(p.stdout.strip())
    if p.stderr:print(p.stderr.strip(),file=sys.stderr)
    check(p.returncode==0, 'Dependencias o importacion de CoLight bloqueadas; no ejecutar shadow')
    print('H12_18_DEPENDENCIES_AND_FORWARD_OK | modelo original SIN ENTRENAR, datos sinteticos')

def shadow(a,plan):
    check(a.ack_online_control=='MULTI_TLS_TEST_POLICY' and
          a.ack_shadow_model=='UNTRAINED_SHADOW_NEVER_ACTUATE',
          'Falta consentimiento explicito para politica de PRUEBA SUMO y modelo aleatorio EN SOMBRA')
    check(12<=a.rl_steps<=120 and a.min_green>=5. and a.min_green<=120 and a.seed>=0,
          'Parametros de piloto fuera de limites')
    deps(a,plan)
    # Luego de gate de dependencias, carga SOLO de fuente LibSignal inmutable.
    # Se mantiene en proceso actual para forward por paso mientras SUMO corre.
    # Usar ruta H12.17 exacta del manifiesto, no suposiciones sobre la carpeta.
    h17=Path(plan['provenance']['h1217']['run_dir'])
    manifest=load_json(h17/'manifiesto_h12_17.json')
    h17env=next(Path(p).resolve() for p in manifest['source_sha256'] if Path(p).name=='h12_17_env.py')
    sys.path.insert(0,str(h17env.parent))
    h12env=Path(manifest['prior']['h1212_source']).parent
    sys.path.insert(0,str(h12env))
    from h12_17_env import MultiTLSHomologado
    from h12_17_multi_tls import validate_events
    import numpy as np
    import torch
    lib=Path(a.libsignal_dir).resolve()
    from h12_18_colight_loader import load_original_colight_net
    ColightNet, upstream_provenance=load_original_colight_net(
        lib,plan['provenance']['libsignal']['worktree_sha256'])
    import yaml
    yaml_path=lib/'configs/tsc/colight.yml'
    check(sha(yaml_path)==plan['provenance']['libsignal']['config_worktree_sha256'],
          'YAML CoLight ha cambiado desde el preflight')
    config=yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
    model_params={k:config['model'][k] for k in ('NODE_EMB_DIM','N_LAYERS','INPUT_DIM',
                'OUTPUT_DIM','NUM_HEADS','NODE_LAYER_DIMS_EACH_HEAD','OUTPUT_LAYERS')}
    model_params['batch_size']=1
    torch.manual_seed(a.seed)
    model=ColightNet(4,2,[2]*12,**model_params)
    model.eval()
    edge=torch.tensor(plan['graph']['edge_index'],dtype=torch.long)
    out=unique_dir(a.revision_root)
    save_json(out/'manifiesto_h12_18.json',plan)
    env=MultiTLSHomologado(net_file=manifest['network'],route_file=manifest['routes'],
            output_dir=out,sumocfg_file=out/'sumo_h12_18.sumocfg',seed=a.seed,
            min_green_s=a.min_green,max_rl_steps=a.rl_steps,binary=a.binary,
            expected_net_sha=NET_SHA,expected_route_sha=ROUTE_SHA)
    try:
        ob,info=env.reset()
        check(info['node_order']==list(NODES),'SUMO nodo a fila no corresponde')
        rows=[]
        for k in range(a.rl_steps):
            raw=counts_to_x(plan['graph']['incoming_lanes'],env._last_counts)
            xx=torch.tensor(raw,dtype=torch.float32)
            with torch.no_grad():
                q=model(x=xx,edge_index=edge,train=False)
            check(tuple(q.shape)==(12,2),'Forward ColightNet no retorna 12x2')
            qs=q.detach().cpu().numpy()
            check(np.isfinite(qs).all(),'Q-values no finitos')
            shadow_actions=qs.argmax(axis=1).tolist()
            # Política usada para SUMO = MISMA que H12.17; no usar shadow_actions.
            test_actions=[((k//4)+(i%2))%2 for i in range(12)]
            ob,reward,term,trunc,inf=env.step(test_actions)
            check(not term and inf['collisions']==0,'Fallo fisico/collision en SUMO')
            check(env.observation_space.contains(ob),'Observaciones fisicas fuera de Box')
            rows.append(dict(step=k+1,sim_time_s=inf['sim_time_s'],
                  input_lane_count_12x4=raw,shadow_q_12x2=qs.tolist(),
                  shadow_argmax=shadow_actions,executed_test_policy=test_actions,
                  global_reward=reward,collisions=inf['collisions']))
        check(env._ticks==a.rl_steps*10,'Microticks incompletos')
        validate_events(env.events,env.tls_ids,a.min_green,a.rl_steps)
        # Guardas postflight del antecesor H12.17, upstream y H12.18.
        after=make_plan(a)
        check(after['local_h1218_source_sha256']==plan['local_h1218_source_sha256'],
              'Fuentes del puente H12.18 modificadas durante SUMO')
        result=dict(result='H12_18_COLIGHT_SHADOW_FORWARD_OK',schema=SCHEMA,
            scope='UPSTREAM_ColightNet_RANDOM_WEIGHTS_FORWARD_SHADOW_ONLY',
            n_nodes=12,n_edges=32,n_steps=a.rl_steps,n_microticks=env._ticks,
            model_class='LibSignal:agent/colight.py::ColightNet',
            isolated_load=upstream_provenance,training='NOT_RUN',checkpoint='NONE',
            actions_applied='ONLY_H12.17_STAGGERED_TEST_POLICY',
            libsignal_commit=LIBSIGNAL_COMMIT,source_sha256=plan['provenance']['libsignal']['committed_file_sha256'],
            node_order=list(NODES),diagnostics=rows,
            manifest_sha256=sha(out/'manifiesto_h12_18.json'),
            gates={'upstream_forward':'EXECUTED_RANDOM_WEIGHTS',
                   'graph_inputs':'MATCH_CANONICAL_IDS',
                   'trained_colight':'NOT_CERTIFIED','resilience':'BLOCKED'})
        save_json(out/'resultado_h12_18.json',result)
        (out/'dictamen_h12_18.md').write_text(report(plan,result),encoding='utf-8')
        print('H12_18_COLIGHT_SHADOW_FORWARD_OK nodos=12 decisiones='+str(a.rl_steps),out)
    except Exception as exc:
        try:
            save_json(out/'ERROR_h12_18.json',dict(error_type=type(exc).__name__,
                error=str(exc),scope='H12.18 shadow, SIN certificacion CoLight'))
        except Exception:pass
        raise
    finally:
        env.close()

def report(plan,result=None):
    status='H12_18_COLIGHT_SHADOW_FORWARD_OK' if result else 'H12_18_PRECHECK_OK'
    return f'''# H12.18 — LibSignal CoLight: puente de observación y grafo

**Estado:** `{status}`. Solo evidencia de contrato y, cuando corresponde, forward de un modelo con pesos aleatorios.

- Upstream fijado: `{LIBSIGNAL_COMMIT}`.
- Arquitectura original sin reescribir: clases de `agent/colight.py::ColightNet` cargadas mediante AST aislado para evitar importaciones CityFlow. No se ha importado el agente/entrenador completo.
- Intersecciones: 12. Aristas dirigidas: 32. Orden único: `{', '.join(NODES)}`.
- Entrada del adaptador: lane_count instantáneo `(12,4)` (carriles entrantes únicos ordenados, relleno cero), **NO** el estado 34D.
- Dos acciones correspondientes a fases verdes físicas `[0,2]`; si hay `shadow`, las recomendaciones de CoLight **no se ejecutan**.
- Sin checkpoint; sin entrenamiento; sin Vine/H09; sin comparaciones SOTA, calidad o resiliencia.
- Fuente de carriles: `net.xml` y TraCI directo. Esta adaptación no certifica equivalencia bit a bit con el generador interno de LibSignal.
- La alineación de los tensores de entrada y aristas no certifica aún la semántica total del World/Trainer nativo de LibSignal.

## Gates

- H12.17 SUMO real: validado por manifiesto, reporte y SHA.
- H12.16 código original: validado por commit, blob SHA-1 y reporte.
- Modelo LibSignal PyG/Scatter (solo arquitectura aislada): {'forward ejecutado con pesos aleatorios' if result else 'pendiente de importación real'}.
- Acciones CoLight sobre SUMO: **NO**; aplicado exclusivamente controlador de prueba H12.17.
- Entrenamiento, checkpoint auténtico y evaluación Vine/H09: **BLOQUEADOS**.
'''

def parse_args(argv=None):
    p=argparse.ArgumentParser(description='H12.18 puente real CoLight LibSignal, solo shadow aleatorio')
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--revision-root',type=Path,required=True)
    p.add_argument('--h1216-dir',type=Path,required=True)
    p.add_argument('--h1217-dir',type=Path,required=True)
    p.add_argument('--libsignal-dir',type=Path,required=True)
    p.add_argument('--mode',choices=('plan','deps','shadow'),default='plan')
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--rl-steps',type=int,default=12)
    p.add_argument('--min-green',type=float,default=10.)
    p.add_argument('--binary',default='sumo')
    p.add_argument('--ack-online-control',default='')
    p.add_argument('--ack-shadow-model',default='')
    return p.parse_args(argv)

def main(argv=None):
    try:
        a=parse_args(argv)
        # no imports de RL ni SUMO mientras validamos fuentes.
        plan=make_plan(a)
        print('H12.18 | CoLight original LibSignal | TLS=12 | E=32 | sources OK')
        if a.mode=='plan':
            print('H12_18_PLAN_OK | solo lectura, SIN CoLight, SUMO ni checkpoint')
            return 0
        if a.mode=='deps':
            deps(a,plan);return 0
        shadow(a,plan)
        return 0
    except Exception as exc:
        print('H12_18_FAIL_CLOSED',type(exc).__name__,str(exc),file=sys.stderr)
        # Guardamos stack corto solo en stderr; no crear carpeta resultado en caso de preflight.
        if os.environ.get('H1218_TRACEBACK')=='1':traceback.print_exc()
        return 2

if __name__=='__main__':raise SystemExit(main())
