"""H12.17 CLI: grafo homologado y smoke multi-TLS, SIN entrenar CoLight.

plan: sin SUMO, sin artefactos. freeze: manifiesto; smoke: 12 TLS online
con controlador de prueba NO aprendizaje, usando únicamente fases net.xml.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback
import uuid

ROOT=Path(__file__).resolve().parent
# Resolver H12.12 como contrato heredado VERIFICADO; jamás sobreescribirlo.
H1212_DIR_DEFAULT='H12_12_Entorno_Homologado_B1_v100'
from h12_17_contract import (ContractError,SCHEMA,EXPECTED_TLS,EXPECTED_NET_SHA,
                            EXPECTED_ROUTE_SHA,parse_network,require,sha256_file,
                            validate_route)

def arg_parser():
    p=argparse.ArgumentParser(description='H12.17 — piloto físico multi-TLS Hangzhou (NO CoLight entrenado)')
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--revision-root',type=Path,required=True)
    p.add_argument('--h1212-smoke-dir',type=Path,required=True)
    p.add_argument('--h1216-dir',type=Path,required=True)
    p.add_argument('--mode',choices=['plan','freeze','smoke'],default='plan')
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--rl-steps',type=int,default=12)
    p.add_argument('--min-green',type=float,default=10.)
    p.add_argument('--binary',default='sumo')
    p.add_argument('--ack-online-control',default='')
    p.add_argument('--ack-new-contract',default='')
    return p

def load_json(path):
    require(path.is_file(),'Archivo requerido ausente: '+str(path))
    return json.loads(path.read_text(encoding='utf8'))

def verify_against_previous(args,repo,rev,net,route):
    # H12.12 no se confía solo por la cadena OK: SHA del manifest y de las fuentes.
    h1212=args.h1212_smoke_dir.resolve(strict=True)
    manifest_file=h1212/'manifiesto_h12_12.json'
    smoke_file=h1212/'smoke_h12_12.json'
    m=load_json(manifest_file)
    s=load_json(smoke_file)
    require(m.get('schema')=='H12_12_B1_GREEN2_OBS34_V100',
            'H12.12 no tiene esquema esperado')
    require(s.get('result')=='H12_12_SUMO_SMOKE_OK','H12.12 smoke no acreditado')
    require(s.get('manifest_sha256')==sha256_file(manifest_file),
            'Manifest H12.12 alterado respecto al smoke')
    require(Path(m['network']).resolve()==net and Path(m['routes']).resolve()==route,
            'H12.12 referencias net/route distintas')
    sha=m['sources_sha256']
    require(sha.get(str(net))==EXPECTED_NET_SHA and sha.get(str(route))==EXPECTED_ROUTE_SHA,
            'SHA de Hangzhou no coincide con H12.12')
    require(m['network_contract']['green_indices']==[0,2],
            'H12.12 B1 verdes no iguales [0,2]')
    require(m['network_contract']['lanes_in']==['A1B1_0','B0B1_0','B2B1_0','C1B1_0'],
            'H12.12 B1 carriles no coinciden')
    contractfile=rev/H1212_DIR_DEFAULT/'h12_12_contract.py'
    require(contractfile.exists(),'Falta contrato H12.12 extraído de su ZIP')
    require(sha.get(str(contractfile.resolve()))==sha256_file(contractfile),
            'Contrato H12.12 cambiado respecto a su smoke')
    # Asegurar que H12.16 auditó código original y LibSignal, sin inventar ejecución.
    h1216=args.h1216_dir.resolve(strict=True)
    docfile=h1216/'dictamen_h12_16.json'
    doc=load_json(docfile)
    require(doc.get('result')=='H12_16_COLIGHT_SOURCE_AUDIT_OK',
            'H12.16 no fue acreditado')
    require(doc['local_contract']['network_sha256']==EXPECTED_NET_SHA and
            doc['local_contract']['route_sha256']==EXPECTED_ROUTE_SHA,
            'H12.16 corresponde a red/ruta diferentes')
    gates=doc['gates']
    require(gates.get('upstream_orig_authenticity')=='PASSED_PINNED_COMMIT_AND_BLOBS' and
            gates.get('upstream_libsignal_authenticity')=='PASSED_PINNED_COMMIT_AND_BLOBS',
            'H12.16 no acredita ambos upstreams')
    return {'h1212_smoke_report_sha256':sha256_file(smoke_file),
            'h1212_manifest_sha256':sha256_file(manifest_file),
            'h1216_report_sha256':sha256_file(docfile),
            'h1212_smoke_path':str(smoke_file.resolve()),
            'h1212_manifest_path':str(manifest_file.resolve()),
            'h1216_report_path':str(docfile.resolve()),
            'h1212_source':str(contractfile.resolve()),
            'h1216_scope':'STATIC_ONLY_NO_COLIGHT_RUNTIME'}

def make_plan(a):
    repo=a.repo_root.resolve(strict=True)
    rev=a.revision_root.resolve(strict=True)
    require(a.seed>=0 and 1<=a.rl_steps<=720 and 5<=a.min_green<=120,
            'Semilla, decisiones o verde mínimo inválidos')
    net=(repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml').resolve(strict=True)
    route=(repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml').resolve(strict=True)
    require(net!=route,'net/route deben ser distintos')
    require(sha256_file(net)==EXPECTED_NET_SHA and sha256_file(route)==EXPECTED_ROUTE_SHA,
            'Red/demanda modificadas frente a H12.12 antes del preflight')
    contract=parse_network(net,require_hangzhou=True)
    route_sha=validate_route(route)
    require(contract.node_ids==EXPECTED_TLS, 'Orden de 12 TLS inesperado')
    prior=verify_against_previous(a,repo,rev,net,route)
    g=contract.as_json()
    b1=g['geometries']['B1']
    require(b1['green_indices']==[0,2], 'B1 no coincide con H12.12')
    require(b1['lanes_in']==['A1B1_0','B0B1_0','B2B1_0','C1B1_0'],
            'Orden B1 no coincide con H12.12')
    paths=[ROOT/'h12_17_contract.py',ROOT/'h12_17_env.py',ROOT/'h12_17_multi_tls.py',
           Path(prior['h1212_source']),Path(prior['h1212_smoke_path']),
           Path(prior['h1212_manifest_path']),Path(prior['h1216_report_path']),net,route]
    require(all(p.exists() for p in paths),'Falta fuente física')
    shas={str(p.resolve()):sha256_file(p) for p in paths}
    return dict(result='H12_17_PLAN_CONTRACT_OK',schema=SCHEMA,
        network=str(net),routes=str(route),network_sha256=contract.net_sha256,
        route_sha256=route_sha,source_sha256=shas,prior=prior,
        graph=g,simulation={'seed':a.seed,'microtick_s':0.5,'decision_s':5.,
                            'n_decisions':a.rl_steps,'horizon_s':a.rl_steps*5.,
                            'min_green_s':a.min_green,'TLS':['online_all_12'],
                            'controller':'staggered_test_only_not_RL'},
        interface={'observation':'Box(12,34) row-major node_order, H12.12 per-node definition',
                   'action':'MultiDiscrete([2]*12), action 0->green phase 0, 1->2',
                   'yellow':'net.xml states 1 and 3, 3.0 seconds minimum, stage yellow has priority over retained G',
                   'graph':'directed movement edge source_node -> target_node, self-loops excluded',
                   'neighbor_alignment':'node_to_index exact for graph and rows',
                   'colight_adapter':'NOT_IMPLEMENTED; graph is prepared, not consumed by LibSignal',
                   'mask':'2 physical greens each; per-node action masking required for other networks'},
        gates={'H1212_B1_smoke':'VERIFIED','H1216_CoLight_sources':'PINNED_STATIC',
               'H1217_real_Sumo':'NOT_RUN','CoLight_runtime':'NOT_RUN',
               'CoLight_dependencies':'NOT_CERTIFIED','CoSLight':'NOT_RUN',
               'Vine_H09':'NOT_CONNECTED','training':'NOT_RUN',
               'resilience':'BLOCKED'},
        environment={'python':sys.version.split()[0],'system':platform.platform()})

def unique_dir(rev):
    r=rev/'resultados';r.mkdir(exist_ok=True)
    out=r/('h12_17_multi_tls_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(exist_ok=False)
    return out

def write_json_unique(path,obj):
    with Path(path).open('x',encoding='utf8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')

def validate_events(events,node_order,min_green,steps):
    from h12_17_contract import require
    seen={id_:[] for id_ in node_order}
    for e in events:
        seen[e['tls']].append(e)
    for tls,arr in seen.items():
        require(arr and arr[0]['event']=='online_initialization', f'{tls}: falta inicialización')
        stage=arr[0]['stage']; prior_time=0.; entered_green=0.
        for e in arr[1:]:
            expected=(stage+1)%4
            require(e['stage']==expected,f'{tls}: salto ilegal de fase {stage}->{e["stage"]}')
            t=float(e['t_s'])
            require(t>=prior_time,f'{tls}: tiempo no monótono')
            if stage in (0,2):
                require(t+1e-8>=entered_green+min_green,
                        f'{tls}: verde menor a {min_green}s')
            else:
                require(t+1e-8>=prior_time+3.,f'{tls}: amarillo menor a 3s')
            if e['stage'] in (0,2):entered_green=t
            stage=e['stage'];prior_time=t
    require(all(len(seen[tls])>=2 for tls in node_order),'No se probó cambio para todos los TLS')
    return dict(n_tls=len(seen),per_tls_events={k:len(v) for k,v in seen.items()},
                n_yellow_entries=sum(1 for e in events if e.get('kind')=='yellow'))

def run_smoke(a,manifest,out):
    require(a.rl_steps>=12 and a.rl_steps*5>=a.min_green+3.0,
            'Smoke requiere >=12 decisiones y horizonte suficiente para completar ámbar')
    require(a.ack_new_contract=='NEW_MULTIAGENT_MODELS_ONLY',
            'Se exige --ack-new-contract NEW_MULTIAGENT_MODELS_ONLY')
    require(a.ack_online_control=='MULTI_TLS_OVERRIDE',
            'Se exige --ack-online-control MULTI_TLS_OVERRIDE')
    require(shutil.which(a.binary) is not None,'SUMO no encontrado en PATH')
    # No importar Gym/TraCI cuando mode=plan o freeze.
    h1212_src=Path(manifest['prior']['h1212_source']).parent
    sys.path.insert(0,str(h1212_src))
    from h12_17_env import MultiTLSHomologado
    import gymnasium,numpy,traci
    runtime={'sumo_version':subprocess.run([a.binary,'--version'],capture_output=True,text=True,timeout=10).stdout.splitlines()[:2],
             'gymnasium':gymnasium.__version__,'numpy':numpy.__version__,
             'traci_file':str(Path(traci.__file__).resolve())}
    write_json_unique(out/'runtime_h12_17.json',runtime)
    env=MultiTLSHomologado(net_file=manifest['network'],route_file=manifest['routes'],
           output_dir=out,sumocfg_file=out/'sumo_h12_17.sumocfg',seed=a.seed,
           min_green_s=a.min_green,max_rl_steps=a.rl_steps,binary=a.binary)
    try:
        obs,info=env.reset()
        require(info['node_order']==manifest['graph']['node_order'],
                'Graph node_order no corresponde a tensor observaciones')
        require(env.observation_space.contains(obs), 'Estado inicial fuera Box')
        rows=[]
        for k in range(a.rl_steps):
            # Prueba alternante escalonada, sin intervención de CoLight o PPO.
            # Cada nodo experimenta ambos verdes y amarillo al menos en 60s.
            acts=[((k//4)+(i%2))%2 for i in range(len(env.tls_ids))]
            ob,rew,term,trunc,inf=env.step(acts)
            require(env.observation_space.contains(ob),'Obs fuera Box')
            require(not term,'Terminación temprana no esperada')
            require(inf['collisions']==0,'Colisiones en smoke; impedir acreditación')
            rows.append(dict(step=k+1,actions_by_node={tls:acts[i] for i,tls in enumerate(env.tls_ids)},
                             observations_by_node={tls:ob[i].tolist() for i,tls in enumerate(env.tls_ids)},
                             global_reward=rew,per_tls=inf['local'],time_s=inf['sim_time_s']))
        require(len(rows)==a.rl_steps and env._ticks==a.rl_steps*10,
                'No completó horizonte real')
        require(abs(float(env.conn.simulation.getTime())-a.rl_steps*5.)<1e-6,
                'Tiempo final SUMO distinto')
        summary=validate_events(env.events,env.tls_ids,a.min_green,a.rl_steps)
        require(summary['n_yellow_entries']>=len(env.tls_ids),
                'No se observaron amarillos para todos')
        for p,sha in manifest['source_sha256'].items():
            require(sha256_file(p)==sha,'Fuente cambió durante SUMO: '+p)
        # El cierre se documenta como etapa posterior; CoLight sigue no conectado.
        doc={'result':'H12_17_MULTI_TLS_SMOKE_OK','schema':SCHEMA,
             'scope':'physical_multi_TLS_12_TEST_POLICY_NOT_COLIGHT',
             'n_decisions':len(rows),'n_microticks':env._ticks,
             'node_order':list(env.tls_ids),
             'edge_index':env.contract.as_json()['graph_directed_edge_index'],
             'n_tls':len(env.tls_ids),'events_summary':summary,
             'events':env.events,'data':rows,
             'manifest_sha256':sha256_file(out/'manifiesto_h12_17.json'),
             'runtime_sha256':sha256_file(out/'runtime_h12_17.json'),
             'integrity_postflight':'PASS',
             'gates':{'multi_tls_physical':'PASSED_SMOKE',
                      'node_graph_alignment':'PASSED_SCHEMA_NOT_LIBSIGNAL_RUNTIME',
                      'colight_training':'NOT_RUN',
                      'colight_libsignal_inference':'NOT_RUN',
                      'sota_resilience':'BLOCKED'}}
        write_json_unique(out/'smoke_h12_17.json',doc)
        return doc
    finally:
        env.close()

def render_report(manifest,smoke=None):
    g=manifest['graph'];nodes=g['node_order']; E=len(g['graph_directed_edges'])
    if smoke is None:
        status='H12_17_FREEZE_OK'
        rest='No se ejecutó SUMO. Manifiesto físico congelado.'
    else:
        status=smoke['result']
        rest=(f"Ejecución: **{smoke['n_decisions']}** decisiones, "
              f"**{smoke['n_microticks']}** microticks, "
              f"**{smoke['events_summary']['n_yellow_entries']}** entradas en amarillo.")
    geom='\n'.join(f"| {id_} | {len(g['geometries'][id_]['lanes_in'])} | "
                   f"{g['geometries'][id_]['green_indices']} | "
                   f"{[p['index'] for p in g['geometries'][id_]['phases'] if 'y' in p['state'].lower()]} |"
                   for id_ in nodes)
    return f'''# H12.17 — Contrato físico y grafo multi-TLS Hangzhou

**Estado:** `{status}`. {rest}

**Afirmación acotada:** el piloto usa política de prueba escalonada, NO CoLight, NO Coop-SARG ni controlador entrenado.

## Grafo para futuro CoLight

- **12 nodos:** `{', '.join(nodes)}` (orden fijo, compartido por acciones y filas observación).
- **{E} aristas dirigidas:** derivadas de `<edge from=... to=...>` con ambos extremos bajo TLS.
- `edge_index` 2×{E}, sin self-loops; grafo sin pesos y sin inferencia de adyacencia a partir de distancias.
- Nodo→fila: `node_to_index` en `manifiesto_h12_17.json`.
- **LibSignal CoLight NO ha consumido todavía este grafo**; no se declara identidad de su nodo interno.

## Semáforos

| TLS | Carriles de entrada únicos | Verdes físicos | Amarillos (índice XML) |
|---|---:|---|---|
{geom}

El lector H12.17 clasifica como **amarillo cualquier etapa con y/Y**, incluso si otras conexiones conservan G/g. Corrige el riesgo observado al generalizar H12.12 a más intersecciones, sin alterar la fuente H12.12.

## Observación y actuación

- Matriz de observación `(12, 34)`, una fila por TLS, usando exactamente la fórmula de H12.12.
- `MultiDiscrete([2]×12)`, acción 0→fase verde 0, acción 1→fase verde 2.
- Cada transición respeta verde mínimo y ejecuta íntegramente la fase amarilla del `net.xml`.
- Rutas/red y fuentes protegidas por SHA-256; sin renombrar checkpoints anteriores.

## Puertas pendientes

| Área | Resultado |
|---|---|
| Protocolo B1 H12.12 | Anclado al smoke y manifest previos |
| Fuentes originales de CoLight y LibSignal | Auditadas H12.16; no ejecutadas aquí |
| Identidad orden `node_to_index` con LibSignal en runtime | **PENDIENTE** |
| Dependencias `torch_geometric`/`torch_scatter` en Windows | **PENDIENTE** |
| Reproducción y entrenamiento de CoLight | **NO REALIZADOS** |
| Comparación multiagente SOTA | **BLOQUEADA** |
| Conexión Vine/H09 a 12 TLS | **NO IMPLEMENTADA** |

## Alcance científico

Este hito acredita **infraestructura física** si se obtiene `H12_17_MULTI_TLS_SMOKE_OK`; no demuestra robustez, calidad del tráfico, cooperación aprendida o representatividad poblacional de Quito.
'''

def main(argv=None):
    a=arg_parser().parse_args(argv)
    try:
        manifest=make_plan(a)
        print('H12.17 | CONTRATO 12 TLS | nodos',len(manifest['graph']['node_order']),
              '| aristas dirigidas',len(manifest['graph']['graph_directed_edges']),
              '| SHA red/rutas OK')
        if a.mode=='plan':
            print('H12_17_PLAN_OK: sin SUMO, sin archivos nuevos, sin modelos.')
            return 0
        out=unique_dir(a.revision_root.resolve(strict=True))
        write_json_unique(out/'manifiesto_h12_17.json',manifest)
        if a.mode=='freeze':
            (out/'dictamen_h12_17.md').write_text(render_report(manifest),encoding='utf8')
            print('H12_17_FREEZE_OK',out)
            return 0
        smoke=run_smoke(a,manifest,out)
        (out/'dictamen_h12_17.md').write_text(render_report(manifest,smoke),encoding='utf8')
        print('H12_17_MULTI_TLS_SMOKE_OK',
              'nodos='+str(smoke['n_tls']),
              'decisiones='+str(smoke['n_decisions']),
              'microticks='+str(smoke['n_microticks']),out)
        return 0
    except Exception as e:
        print('H12_17_FAIL_CLOSED:',type(e).__name__,str(e),file=sys.stderr)
        if 'out' in locals():
            try:
                write_json_unique(out/'ERROR_h12_17.json',
                    dict(error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc()))
                print('DIAGNOSTICO',out/'ERROR_h12_17.json',file=sys.stderr)
            except Exception:pass
        return 2

if __name__=='__main__':raise SystemExit(main())
