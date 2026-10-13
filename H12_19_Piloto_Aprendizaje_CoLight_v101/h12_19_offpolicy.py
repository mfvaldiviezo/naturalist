"""H12.19: piloto limitado de gradientes TD con ColightNet ORIGINAL de LibSignal.

No reproduce el entrenamiento completo de CoLightAgent/Trainer. No permite que
acciones neuronales gobiernen SUMO: recopila transiciones con H12.17 TEST.
"""
from __future__ import annotations
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parent
SCHEMA = 'H12_19_UPSTREAM_COLIGHT_OFFPOLICY_TD_SMOKE_V100'
SHADOW_STATUS = 'H12_18_COLIGHT_SHADOW_FORWARD_OK'
TRAIN_OK = 'H12_19_COLIGHT_UPSTREAM_NETWORK_TD_SMOKE_OK'

class GateError(RuntimeError):pass

def require(condition,msg):
    if not condition:raise GateError(msg)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):
            h.update(chunk)
    return h.hexdigest()

def load_json(p):
    p=Path(p)
    require(p.is_file(),'Falta archivo requerido: '+str(p))
    return json.loads(p.read_text(encoding='utf-8'))

def write_new(p,obj):
    with Path(p).open('x',encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')

def result_path(rev):
    root=Path(rev)/'resultados';root.mkdir(exist_ok=True)
    p=root/('h12_19_colight_td_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    p.mkdir(exist_ok=False)
    return p

def validate_shadow(path, bridge):
    """La evidencia H12.18 debe ser real, completa e internamente coherente."""
    r=Path(path).resolve(strict=True)
    result=load_json(r/'resultado_h12_18.json')
    mfile=r/'manifiesto_h12_18.json'; manifest=load_json(mfile)
    require(result.get('result')==SHADOW_STATUS,'No es H12.18 shadow acreditado')
    require(result.get('training')=='NOT_RUN' and result.get('checkpoint')=='NONE',
            'H12.18 no debe certificar pesos entrenados')
    require(result.get('actions_applied')=='ONLY_H12.17_STAGGERED_TEST_POLICY',
            'H12.18 no mantuvo la politica de test')
    require(result.get('n_nodes')==12 and result.get('n_edges')==32,
            'Dimensiones H12.18 inesperadas')
    require(result.get('n_steps',0)>=12 and result.get('n_microticks')==10*result['n_steps'],
            'H12.18 incompleto')
    require(result.get('manifest_sha256')==sha(mfile),'Manifiesto H12.18 alterado')
    require(result.get('node_order')==list(bridge.NODES),'Orden H12.18 incorrecto')
    require(result.get('libsignal_commit')==bridge.LIBSIGNAL_COMMIT,
            'Commit H12.18 no coincide')
    require(result.get('source_sha256')==manifest['provenance']['libsignal']['committed_file_sha256'],
            'Fuente H12.18 no coincide con su manifiesto')
    require(len(result.get('diagnostics',[]))==result['n_steps'],
            'Faltan decisiones shadow')
    for step,d in enumerate(result['diagnostics'],1):
        require(d.get('step')==step,'Indice step shadow mal ordenado')
        require(len(d.get('input_lane_count_12x4',[]))==12 and
                all(len(v)==4 for v in d['input_lane_count_12x4']),
                'Input lane_count shadow invalido')
        require(len(d.get('shadow_q_12x2',[]))==12 and
                all(len(v)==2 and all(isinstance(x,(float,int)) and math.isfinite(x) for x in v)
                    for v in d['shadow_q_12x2']), 'Forward shadow Q invalido')
        require(len(d.get('executed_test_policy',[]))==12 and
                all(x in (0,1) for x in d['executed_test_policy']),
                'Acciones de politica test H12.18 invalidas')
        require(d.get('collisions')==0,'Colisiones H12.18')
    return {'shadow_dir':str(r),'shadow_result_sha256':sha(r/'resultado_h12_18.json'),
            'shadow_manifest_sha256':sha(mfile),'n_decisions':result['n_steps']}

def prepare_plan(a):
    rev=Path(a.revision_root).resolve(strict=True)
    repo=Path(a.repo_root).resolve(strict=True)
    source_dir=Path(a.h1218_dir).resolve(strict=True)
    require((source_dir/'h12_18_bridge.py').is_file() and
            (source_dir/'h12_18_colight_loader.py').is_file(),
            'Falta H12.18 v103')
    require((source_dir/'h12_18_bridge.py').read_text(encoding='utf-8').find('H12_18_LIBSIGNAL_GRAPH_SHADOW_V103_REGISTERED_MODULE')>=0,
            'Solo se admite H12.18 v103')
    if str(source_dir) not in sys.path:sys.path.insert(0,str(source_dir))
    import h12_18_bridge as bridge
    b=argparse.Namespace(repo_root=repo,revision_root=rev,
         h1216_dir=Path(a.h1216_dir),h1217_dir=Path(a.h1217_dir),
         libsignal_dir=Path(a.libsignal_dir))
    baseline=bridge.make_plan(b)
    sh=validate_shadow(a.h1218_shadow_dir,bridge)
    shmanifest=load_json(Path(sh['shadow_dir'])/'manifiesto_h12_18.json')
    require(shmanifest['schema']==baseline['schema'],
            'Schema H12.18 distinto entre plan y shadow')
    require(shmanifest['provenance']==baseline['provenance'],
            'Proveniencia H12.18 cambió entre sombra y H12.19')
    require(shmanifest['graph']==baseline['graph'],'Grafo H12.18 cambiado')
    require(shmanifest['local_h1218_source_sha256']==baseline['local_h1218_source_sha256'],
            'Codigo H12.18 fuente distinto')
    require(a.seed>=0 and 24<=a.steps<=120 and 1<=a.updates<=16 and
            2<=a.batch_size<=a.steps and a.min_green==10.0,
            'Parametros del piloto fuera de limites homologados')
    require(a.steps*5>=a.min_green+3,'Horizonte insuficiente')
    n={'schema':SCHEMA,'status':'H12_19_PREFLIGHT_OK',
       'h1218_shadow':sh,
       'h1218_manifest_sha256':sh['shadow_manifest_sha256'],
       'libsignal':baseline['provenance']['libsignal'],
       'base_provenance':baseline['provenance'],
       'graph':baseline['graph'],
       'network_sha256':bridge.NET_SHA,'route_sha256':bridge.ROUTE_SHA,
       'settings':{'seed':a.seed,'decision_steps':a.steps,'updates':a.updates,
                   'batch_size':a.batch_size,'min_green_s':a.min_green,
                   'gamma':0.95,'learning_rate':0.001,'gradient_clip':5.,
                   'device':'cpu','target_sync_every_updates':4},
       'strict_label':'UNTRAINED_UPSTREAM_NETWORK_OFF_POLICY_TD_PROBE',
       'gates':{'SUMO_12_TLS':'VERIFIED_PRIOR','upstream_colight_network':'PINNED',
                'native_full_colight_trainer':'NOT_INVOKED',
                'RL_action_applied':'NEVER',
                'resilience':'BLOCKED'},
       'src_sha256':{str((ROOT/x).resolve()):sha(ROOT/x)
                    for x in ('h12_19_offpolicy.py','h12_19_td.py')}}
    return bridge,n,b

def collect_transitions(plan,bridge,a,out):
    """SUMO siempre bajo misma politica de PRUEBA H12.17, nunca Q/argmax."""
    h17=Path(plan['base_provenance']['h1217']['run_dir'])
    h17m=load_json(h17/'manifiesto_h12_17.json')
    h17env=next(Path(p).resolve() for p in h17m['source_sha256']
                if Path(p).name=='h12_17_env.py')
    sys.path.insert(0,str(h17env.parent))
    sys.path.insert(0,str(Path(h17m['prior']['h1212_source']).parent))
    from h12_17_env import MultiTLSHomologado
    from h12_17_multi_tls import validate_events
    import numpy as np
    rows=[]
    env=MultiTLSHomologado(net_file=h17m['network'],route_file=h17m['routes'],
       output_dir=out,sumocfg_file=out/'sumo_h12_19.sumocfg',
       seed=a.seed,min_green_s=a.min_green,max_rl_steps=a.steps,binary=a.binary,
       expected_net_sha=bridge.NET_SHA,expected_route_sha=bridge.ROUTE_SHA)
    try:
        ob,info=env.reset(seed=a.seed)
        require(info.get('node_order')==list(bridge.NODES),'Orden de nodos SUMO cambiado')
        lanes=plan['graph']['incoming_lanes']
        previous=bridge.counts_to_x(lanes,env._last_counts)
        for k in range(a.steps):
            test_actions=[((k//4)+(i%2))%2 for i in range(12)]
            ob,_,term,trunc,inf=env.step(test_actions)
            require(not term and inf.get('collisions')==0,
                    'SUMO termino inesperadamente o detectó colisiones')
            require(env.observation_space.contains(ob),'Fuera de Box H12.17')
            next_obs=bridge.counts_to_x(lanes,env._last_counts)
            # LibSignal CoLight rewards: negative average lane_waiting_count per
            # intersection multiplied by 12. This is NOT H12.17 global reward.
            native_rewards=[-12.*float(inf['local'][n]['queue'])/len(lanes[n])
                            for n in bridge.NODES]
            require(all(math.isfinite(x) for x in native_rewards),'Reward invalido')
            rows.append({'step':k+1,'obs_12x4':previous,
                         'requested_actions':test_actions,
                         'reward_per_node':native_rewards,'next_obs_12x4':next_obs,
                         'done':bool(k==a.steps-1),
                         'effective_phases':{n:inf['local'][n]['effective_stage']
                                             for n in bridge.NODES},
                         'global_reward_h1217':float(inf['global_reward']),
                         'collisions':inf['collisions']})
            previous=next_obs
        require(env._ticks==10*a.steps,'Faltan microticks SUMO')
        stats=validate_events(env.events,env.tls_ids,a.min_green,a.steps)
        return rows,stats,env._ticks
    finally:
        env.close()

def audit_transitions(rows, nodes):
    require(len(rows)>=24,'Replay insuficiente')
    observed_actions=set()
    r_nonzero=0
    for index,r in enumerate(rows):
        require(r['step']==index+1,'Pasos no monótonos')
        for key,shape in [('obs_12x4',4),('next_obs_12x4',4)]:
            val=r[key]
            require(len(val)==12 and all(len(a)==shape for a in val),'Shape incorrecto '+key)
            require(all(type(v) in (int,float) and math.isfinite(v) and v>=0
                        for row in val for v in row),'Lane count invalido')
        acts=r['requested_actions']
        require(len(acts)==12 and all(type(v) is int and v in (0,1) for v in acts),
                'Acciones no binarias')
        observed_actions.update(acts)
        re=r['reward_per_node']
        require(len(re)==12 and all(type(v) in (int,float) and math.isfinite(v) and v<=0 for v in re),
                'Reward CoLight invalido')
        r_nonzero+=sum(x!=0 for x in re)
        require(r['done']==(index==len(rows)-1),'Terminal mal marcado')
        require(r['collisions']==0,'Colisión en replay')
        require(set(r['effective_phases'])==set(nodes),'Fases TLS incompletas')
    require(observed_actions=={0,1},'No se cubrieron ambas acciones')
    return {'decisions':len(rows),'node_transitions':12*len(rows),
            'actions_covered':[0,1],'reward_nonzero_node_transitions':r_nonzero}

def train_td(rows,plan,a,out):
    from h12_19_td import train_offpolicy
    lib=Path(a.libsignal_dir).resolve()
    return train_offpolicy(rows,plan,lib,a,out)

def report(plan,summary=None):
    s='H12_19_COLIGHT_UPSTREAM_NETWORK_TD_SMOKE_OK' if summary else 'H12_19_PREFLIGHT_OK'
    details = ('## Resumen operativo\n\n'+json.dumps(summary,indent=2,ensure_ascii=False)
               if summary else 'Esperando piloto en Windows.')
    return f'''# H12.19 — Piloto TD aislado con red CoLight auténtica

**Estado:** `{s}`.

- Fuente neuronal: LibSignal commit `{plan['libsignal']['commit']}`, blob `{plan['libsignal']['blob_sha1']}`.
- Contrato: Hangzhou 12 TLS, 32 aristas dirigidas, dos verdes físicos por TLS.
- Observación: conteos por carril 12×4 de TraCI, con padding cero y orden de grafo fijado.
- Durante la recolección SUMO ejecuta **exclusivamente la política H12.17 de prueba**; los valores Q de CoLight no actúan.
- Recompensa de entrenamiento: `-12 * promedio lane_waiting_count` por intersección, análoga a la función observada de LibSignal; no es la recompensa H12.17, ni prueba equivalencia completa de World.
- Actualización posterior a la recolección: DQN off-policy de laboratorio (RMSprop/MSE/target network), con la **clase neuronal original** `ColightNet`; sin agente/entrenador LibSignal integral, sin política epsilon-greedy actuando en SUMO.
- No existe entrenamiento SOTA validado, mejora del tráfico, Vine/H09 ni comparación de resiliencia.

{details}
'''

def arg_parser():
    p=argparse.ArgumentParser(description='H12.19 piloto DQN off-policy con red CoLight original; NO CoLight SOTA certificado')
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--revision-root',type=Path,required=True)
    p.add_argument('--h1216-dir',type=Path,required=True)
    p.add_argument('--h1217-dir',type=Path,required=True)
    p.add_argument('--h1218-dir',type=Path,required=True)
    p.add_argument('--h1218-shadow-dir',type=Path,required=True)
    p.add_argument('--libsignal-dir',type=Path,required=True)
    p.add_argument('--mode',choices=('plan','probe','pilot'),default='plan')
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--steps',type=int,default=24)
    p.add_argument('--updates',type=int,default=4)
    p.add_argument('--batch-size',type=int,default=4)
    p.add_argument('--min-green',type=float,default=10.)
    p.add_argument('--binary',default='sumo')
    p.add_argument('--ack-new-checkpoint',default='')
    p.add_argument('--ack-sumo-test-policy',default='')
    return p

def main(argv=None):
    a=arg_parser().parse_args(argv)
    out=None
    try:
        # Los modos sin acciones son de solo lectura.
        bridge,plan,_=prepare_plan(a)
        print('H12.19 | H12.18 shadow acreditado | TLS=12 grafo=32 | fuentes OK')
        if a.mode=='plan':
            print('H12_19_PLAN_OK | solo lectura; sin PyTorch, SUMO ni checkpoint')
            return 0
        if a.mode=='probe':
            # Forward y backward sinteticos con red original, sin SUMO ni archivos.
            from h12_19_td import gradient_probe
            print(json.dumps(gradient_probe(plan,Path(a.libsignal_dir),a.seed),ensure_ascii=False,allow_nan=False))
            print('H12_19_GRADIENT_PROBE_OK | gradientes sinteticos, no entrenamiento en SUMO')
            return 0
        require(a.ack_new_checkpoint=='NEW_EXPLORATORY_WEIGHTS_ONLY',
                'Falta consentimiento nuevo checkpoint experimental')
        require(a.ack_sumo_test_policy=='H1217_TEST_POLICY_NOT_NEURAL',
                'Piloto requiere reconocer explicitamente que CoLight no controla SUMO')
        import numpy as np
        import torch
        random.seed(a.seed);np.random.seed(a.seed);torch.manual_seed(a.seed)
        out=result_path(a.revision_root)
        write_new(out/'manifiesto_h12_19.json',plan)
        print('H12.19 INICIANDO recoleccion SUMO; SOLO politica test H12.17')
        rows,events,ticks=collect_transitions(plan,bridge,a,out)
        consistency=audit_transitions(rows,bridge.NODES)
        replay=out/'telemetria_h12_19.json'
        write_new(replay,rows)
        print('H12.19 SUMO_OK nodos=12 steps='+str(len(rows))+' microticks='+str(ticks))
        print('H12.19 INICIANDO TD off-policy CPU (CoLightNet original, no trainer LibSignal)')
        training=train_td(rows,plan,a,out)
        # Guardas postflight: repetir verificaciones originales y propias.
        _,after,_=prepare_plan(a)
        require(after==plan,'Preflight H12.19 cambió durante piloto')
        require(sha(ROOT/'h12_19_offpolicy.py')==plan['src_sha256'][str((ROOT/'h12_19_offpolicy.py').resolve())],
                'Fuente H12.19 cambio')
        require(sha(ROOT/'h12_19_td.py')==plan['src_sha256'][str((ROOT/'h12_19_td.py').resolve())],
                'Fuente TD cambio')
        summary={'result':TRAIN_OK,'scope':'OFF_POLICY_TD_GRADIENT_SMOKE_ONLY',
                 'steps':len(rows),'microticks':ticks,'node_order':list(bridge.NODES),
                 'graph_edges':32,'sumo_controller':'ONLY_H12.17_TEST_POLICY',
                 'neural_actions_applied':False,'training':training,
                 'replay_audit':consistency,'phase_events':events,
                 'replay_sha256':sha(replay),
                 'manifest_sha256':sha(out/'manifiesto_h12_19.json'),
                 'checkpoints_certified_SOTA':False,'Vine_H09':'NOT_CONNECTED'}
        write_new(out/'resultado_h12_19.json',summary)
        (out/'dictamen_h12_19.md').write_text(report(plan,summary),encoding='utf-8')
        print(TRAIN_OK,str(out))
        return 0
    except Exception as exc:
        if out is not None and out.is_dir():
            try:
                write_new(out/'ERROR_h12_19.json',{'error_type':type(exc).__name__,
                      'error':str(exc),'status':'H12_19_NOT_ACCREDITED',
                      'checkpoint_if_present':'DO_NOT_TREAT_AS_CERTIFIED'})
            except Exception:pass
        print('H12_19_FAIL_CLOSED',type(exc).__name__,str(exc),file=sys.stderr)
        if os.environ.get('H1219_TRACEBACK')=='1':traceback.print_exc()
        # Fallo previo a resultados: no inventar evidencia ni certificar.
        return 2

if __name__=='__main__':raise SystemExit(main())
