"""H12.15: auditoría y smoke real de DOS proyecciones de baselines B1.

PLAN: solo lectura, no SUMO ni resultados.
SMOKE: usa H12.12 ORIGINAL verificado mediante SHA; SUMO con Fixed B1 net.xml
        y proyección explícita del algoritmo RESCO MaxPressure sobre 2 fases.
NINGÚN controlador neuronal SOTA se declara adaptado/entrenado.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import uuid

from h12_15_politicas import build_projection,check,fixed_action,maxpressure_action,score_directions,PhysicalAdapterError

SCHEMA='H12_15_B1_PHYSICAL_PROJECTIONS_V100'
EXPECTED_NET='2590ca460dafb57a4c608f4fe1ad9de072068a5b2ef0ea487f617296d8c627f6'
EXPECTED_ROUTE='a78363c99e1a6eab33028c3a36c82dcb66129adf8e73141612b9e7b2358f1369'
SELF=Path(__file__).resolve().parent


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):digest.update(block)
    return digest.hexdigest()


def jsonread(path):
    with Path(path).open('r',encoding='utf8') as f:return json.load(f)


def jsonnew(path,data):
    check(not Path(path).exists(),'No sobrescribir artefacto: '+str(path))
    with Path(path).open('x',encoding='utf8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def cli_parser():
    p=argparse.ArgumentParser(description='H12.15: proyecciones físicas Fixed/MaxPressure B1, sin entrenamiento')
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--revision-root',type=Path,required=True)
    p.add_argument('--smoke-dir',type=Path,required=True,help='H12.12 SUMO smoke acreditado')
    p.add_argument('--h1214-dir',type=Path,required=True,help='H12.14 auditoría real')
    p.add_argument('--mode',choices=('plan','smoke'),default='plan')
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--rl-steps',type=int,default=24)
    p.add_argument('--min-green',type=float,default=10.0)
    p.add_argument('--binary',default='sumo')
    p.add_argument('--ack-projection',default='')
    p.add_argument('--ack-online-control',default='')
    return p


def validate(a):
    repo=a.repo_root.resolve(strict=True)
    rev=a.revision_root.resolve(strict=True)
    smoke=a.smoke_dir.resolve(strict=True)
    aud=a.h1214_dir.resolve(strict=True)
    check(a.seed>=0,'Semilla negativa')
    check(1<=a.rl_steps<=720,'--rl-steps debe estar 1..720')
    check(5.0<=a.min_green<=120.0,'--min-green fuera de 5..120')
    h1212=rev/'H12_12_Entorno_Homologado_B1_v100'
    files1212=[h1212/n for n in ('h12_12_contract.py','h12_12_env.py','h12_12_homologar.py')]
    for f in files1212:check(f.is_file(),'Falta fuente H12.12: '+str(f))
    manifest=smoke/'manifiesto_h12_12.json'; result=smoke/'smoke_h12_12.json';rt=smoke/'runtime_h12_12.json'
    for f in (manifest,result,rt):check(f.is_file(),'No existe evidencia H12.12: '+str(f))
    ms=jsonread(manifest);sr=jsonread(result)
    check(ms.get('schema')=='H12_12_B1_GREEN2_OBS34_V100','H12.12 schema incompatible')
    check(sr.get('result')=='H12_12_SUMO_SMOKE_OK','H12.12 smoke no acreditado')
    check(sr.get('manifest_sha256')==sha(manifest),'H12.12 manifesto modificado')
    check(sr.get('steps')==12 and sr.get('microticks')==120,'H12.12 smoke incompleto')
    original=ms.get('sources_sha256',{})
    for f in files1212:check(original.get(str(f.resolve()))==sha(f),'Fuente H12.12 alterada: '+f.name)
    net=repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
    route=repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
    check(net.is_file() and route.is_file(),'Faltan XML de Hangzhou')
    check(ms.get('network')==str(net.resolve()) and ms.get('routes')==str(route.resolve()),
          'H12.12 ejecutado con otros archivos')
    check(sha(net)==EXPECTED_NET and sha(route)==EXPECTED_ROUTE,'Red/rutas no son el contrato congelado')
    check(original.get(str(net.resolve()))==sha(net) and original.get(str(route.resolve()))==sha(route),
          'H12.12 manifest de entradas no corresponde a XML')
    report_path=aud/'dictamen_h12_14.json'
    check(report_path.is_file(),'Falta dictamen H12.14.json')
    report=jsonread(report_path)
    check(report.get('result')=='H12_14_SOTA_AUDIT_OK','H12.14 no aprobado')
    gates=report.get('gates',{})
    for key in ('source_code_and_yaml','h1212_physical_contract','resco_hangzhou_network_identity','resco_hangzhou_routes_identity'):
        check(gates.get(key)=='PASSED','H12.14 puerta incompleta: '+key)
    check(report.get('H1212',{}).get('smoke_sha256')==sha(result),
          'H12.14 auditó otra versión de H12.12')
    refs=report.get('source_sha256',{})
    check(bool(refs),'H12.14 sin hashes de fuentes')
    for f,digest in refs.items():
        check(Path(f).is_file() and sha(f)==digest,'Una fuente auditada por H12.14 cambió: '+f)
    check(report.get('resco_reference_inputs',{}).get('net_byte_identical_to_H1212') is True,
          'Red RESCO distinta de red controlada')
    check(report.get('resco_reference_inputs',{}).get('route_byte_identical_to_H1212') is True,
          'Demanda RESCO distinta')
    # Contrato H12.12 verificado ANTES de importar las clases originales.
    sys.path.insert(0,str(h1212))
    from h12_12_contract import read_geometry
    geo=read_geometry(net,'B1')
    check(tuple(geo.green_indices)==(0,2),'Cambió programa de fases B1')
    try:import yaml
    except ImportError as e:raise PhysicalAdapterError('Requiere PyYAML, disponible en H12.14') from e
    signal_cfg=repo/'baselines/RESCO/resco_benchmark/config/signal.yaml'
    with signal_cfg.open(encoding='utf8') as f:res=yaml.safe_load(f)
    projection=build_projection(geo,net,res)
    sources={str(p.resolve()):sha(p) for p in
             [net,route,*files1212,SELF/'h12_15_politicas.py',SELF/'h12_15_baselines.py',signal_cfg,
              repo/'baselines/RESCO/resco_benchmark/agents/static/maxpressure.py',
              repo/'baselines/RESCO/resco_benchmark/agents/static/maxwave.py',
              repo/'baselines/RESCO/resco_benchmark/agents/static/fixed.py',
              repo/'baselines/RESCO/resco_benchmark/mdp_options/states.py',
              repo/'baselines/RESCO/resco_benchmark/traffic_signal.py']}
    return {'schema':SCHEMA,'repo':str(repo),'revision_root':str(rev),'smoke_dir':str(smoke),
            'audit_h1214_dir':str(aud),'audit_h1214_sha256':sha(report_path),
            'prior_smoke_h1212_sha256':sha(result),'sources_sha256':sources,
            'network':str(net),'routes':str(route),'geometry':geo,
            'physical_projection':projection,'seed':a.seed,'rl_steps':a.rl_steps,
            'min_green_s':a.min_green,'binary':a.binary}


def public_manifest(bundle):
    return {key:value for key,value in bundle.items() if key not in ('geometry','physical_projection')} | {
        'projection':bundle['physical_projection'].document(),
        'experiment':{'rl_decision_s':5.0,'microtick_s':0.5,'SUMO_seeds_pairing':'same seed in both independent runs',
                      'controlled_TLS':'B1 only; other TLSs remain native SUMO',
                      'not_trained':'Both physical baselines require no training',
                      'fixed_policy':'original net.xml desired green 42 s, quantized to 5 s decisions; distinct from RESCO FIXED 8-action plan',
                      'maxpressure_policy':'RESCO 8 phase pairs projected to physically realizable pairs #0/#4; uses instantaneous TraCI halts as queued proxy',
                      'not_a_SOTA_certificate':True,
                      'vine_h09':'NOT_INTEGRATED', 'multi_TLS':'NOT_INTEGRATED'},
    }


def temp_new_dir(rev):
    root=rev/'resultados';root.mkdir(exist_ok=True)
    out=root/('h12_15_baselines_b1_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(exist_ok=False)
    return out


def snapshot_pressure(conn,projection):
    lanes=set()
    for group in projection.directions:
        for d in group:lanes.update(d.inbound);lanes.update(d.downstream)
    lane_api=conn.lane
    ids=set(lane_api.getIDList())
    check(lanes<=ids, 'Carriles de presión RESCO no están todos en SUMO: '+repr(sorted(lanes-ids)))
    readings={lane:float(lane_api.getLastStepHaltingNumber(lane)) for lane in sorted(lanes)}
    action,scores=maxpressure_action(projection,readings)
    return action,scores,readings


def audit_tls_events(events, geometry, minimum_green_s):
    """Audita etapas B1, duración de amarillos y prohibición de saltos verde-verde."""
    check(bool(events) and events[0].get('event')=='online_initialization',
          'Ausente inicialización online TLS')
    ordered=[e for e in events if e.get('event') in ('online_initialization','enter_stage')]
    check(bool(ordered),'Sin etapas TLS')
    phases=geometry.phases
    prev=None
    summary={'yellow_entries':0,'green_entries':0,'verified_yellow_clearances':0,
             'verified_min_green_exits':0}
    for e in ordered:
        idx=e.get('stage')
        check(isinstance(idx,int) and 0<=idx<len(phases),'Etapa TLS no declarada')
        check(e.get('state')==phases[idx].state,'Estado TLS no procede del programa original')
        check(e.get('kind')==phases[idx].kind,'Tipo de etapa TLS incorrecto')
        now=float(e.get('t_s'))
        check(math.isfinite(now) and now>=0,'Tiempo TLS no finito')
        if prev is None:
            check(e.get('kind')=='green' and abs(now)<1e-7,'Inicialización fuera de verde t=0')
        else:
            before=int(prev['stage'])
            check(idx==(before+1)%len(phases),'Salto TLS no secuencial (verde directo prohibido)')
            elapsed=now-float(prev['t_s'])
            check(elapsed>=0,'Eventos TLS fuera de orden')
            if prev['kind']=='green':
                check(e['kind']=='yellow','Verde no seguido de amarillo en B1')
                check(elapsed+1e-7>=minimum_green_s,'Salida de verde antes de mínimo')
                summary['verified_min_green_exits']+=1
            elif prev['kind']=='yellow':
                check(e['kind']=='green','Amarillo no seguido de verde en B1')
                duration=phases[before].duration_s
                check(abs(elapsed-duration)<1e-5,
                      f'Amarillo no duró {duration} s (observado {elapsed})')
                summary['verified_yellow_clearances']+=1
            else:
                check(False,'H12.15 solo espera fases verde/amarillo en B1')
        if e['kind']=='yellow':summary['yellow_entries']+=1
        else:summary['green_entries']+=1
        prev=e
    return summary


def run_one(bundle,method,out):
    from h12_12_env import TSCEnvHomologado
    from h12_12_contract import require
    check(method in ('fixed_b1','maxpressure_resco_projected_b1'),'Método desconocido')
    base=out/method;base.mkdir(exist_ok=False)
    env=TSCEnvHomologado(net_file=bundle['network'],route_file=bundle['routes'],
                         sumocfg_file=base/'run.sumocfg',output_dir=base,tls_id='B1',
                         seed=bundle['seed'],step_length=0.5,delta_t=5.0,
                         min_green_s=bundle['min_green_s'],max_rl_steps=bundle['rl_steps'],
                         binary=bundle['binary'])
    rows=[];obs=None
    try:
        obs,init=env.reset(seed=bundle['seed'])
        for i in range(bundle['rl_steps']):
            check(env.observation_space.contains(obs),'Estado 34D inválido antes de decidir')
            projection=bundle['physical_projection']
            if method=='fixed_b1':
                action=fixed_action(projection,env.scheduler)
                scores=None
            else:
                action,scores,_=snapshot_pressure(env.conn,projection)
            prev_green=env.scheduler.green_phase
            prev_stage=env.scheduler.stage
            prev_age=env.scheduler.green_elapsed
            obs,reward,term,trunc,info=env.step(int(action))
            check(env.observation_space.contains(obs),'Estado 34D inválido después de decidir')
            check(not term,'H12.12 terminó prematuramente')
            check(bool(trunc)==(i==bundle['rl_steps']-1),'Truncamiento inesperado')
            check(math.isfinite(reward),'Recompensa no finita')
            rows.append({'decision':i,'time_end_s':info['sim_time_s'],
                         'action':int(action),'prior_green':prev_green,'prior_stage':prev_stage,
                         'prior_green_age_s':prev_age,'pressure_scores':list(scores) if scores is not None else None,
                         'result_stage':info['stage'],'result_kind':info['stage_kind'],
                         'inbound_vehicles':info['inbound_vehicle_count'],
                         'queued':info['total_queue'],'wait_total_s':info['wait_total_s'],
                         'reward':reward,'collision_events':info['colliding_vehicles_tick_sum'],
                         'transition_entries':info['transition_entries'],
                         'observation_34':obs.tolist()})
        check(len(rows)==bundle['rl_steps'],'Número de decisiones incompleto')
        tls_audit=audit_tls_events(env.events,bundle['geometry'],bundle['min_green_s'])
        if method=='fixed_b1' and bundle['rl_steps']>=12:
            check(tls_audit['verified_yellow_clearances']>=1,
                  'FIXED_B1 no verificó ninguna transición ámbar completa')
        collisions=sum(row['collision_events'] for row in rows)
        # No certificar smoke sin un registro explícito de seguridad; conservar resultados en falla.
        if collisions:
            jsonnew(base/'telemetria_no_acreditada.json',{'method':method,'collision_events':collisions,
                  'decision_rows':rows,'tl_events':list(env.events), 'tls_audit':tls_audit})
        check(collisions==0,f'{method}: {collisions} eventos de colisión; inspección necesaria')
        result={'method':method,'status':'SMOKE_EXECUTED_NOT_SOTA_CERTIFIED',
                'n_decisions':len(rows),'n_microticks':len(rows)*10,
                'seed':bundle['seed'],'final_time_s':rows[-1]['time_end_s'],
                'sum_rewards':sum(r['reward'] for r in rows),
                'mean_queued':sum(r['queued'] for r in rows)/len(rows),
                'mean_wait_total_s':sum(r['wait_total_s'] for r in rows)/len(rows),
                'n_intergreen_entries':tls_audit['yellow_entries'],
                'tls_safety_audit':tls_audit, 'collision_events':collisions,'decision_rows':rows,'tl_events':list(env.events),
                'readings_semantics':'SUMO getLastStepHaltingNumber; original RESCO queued is sticky per vehicle',
                'scope':'B1 only; no proof of SOTA model equivalence/quality'}
        jsonnew(base/'pilot.json',result)
        return result
    finally:
        env.close()


def verify_end(bundle):
    for file,old in bundle['sources_sha256'].items():
        check(sha(file)==old,'Fuente modificada durante simulación: '+file)


def markdown(manifest,results):
    proj=manifest['projection']
    lines=['# H12.15 — Baselines físicos auditados en B1','',
           '**Estado:** `H12_15_PHYSICAL_SMOKE_OK` — smoke técnico, **NO reproducción integral de RESCO ni comparación SOTA certificada**.','',
           '## Brecha estructural RESCO -> B1','',
           f"- RESCO Hangzhou tiene **{proj['resco_original_action_count']} pares de fase** y FIXED registra {len(proj['original_fixed_timings_resco_8'])} duraciones.",
           '- El `net.xml` validado en H12.12 contiene **2 verdes físicos** (0 y 2) y dos amarillos de 3 s.',
           '- Solo proyectamos los pares RESCO 0 (S-S/N-N) y 4 (W-W/E-E), verificados contra los enlaces SUMO de B1.',
           '- Los otros seis pares RESCO no corresponden a seis verdes físicos independientes. No se inventaron fases nuevas.',
           '- Fixed-B1 usa duración objetivo de 42 s según net.xml; no se llama Fixed RESCO 8 fases.',
           '- MaxPressure-B1 conserva la suma de presión por par, pero reemplaza el estado persistente `Lane.queued` RESCO por detenciones instantáneas TraCI.',
           '', '## Ejecución SUMO (misma semilla/red/rutas)','',
           '| Indicador | Fixed-B1 físico | MaxPressure-B1 proyectado |','|---|---:|---:|']
    keys=[('Decisiones','n_decisions'),('Microticks','n_microticks'),('Entrada en amarillos','n_intergreen_entries'),('Colisiones','collision_events'),('Recompensa acumulada','sum_rewards'),('Cola media (B1)','mean_queued'),('Espera total media por decisión (s)','mean_wait_total_s')]
    a,b=results
    for label,key in keys:
        fmt=lambda v: f'{v:.6f}' if isinstance(v,float) else str(v)
        lines.append(f'| {label} | {fmt(a[key])} | {fmt(b[key])} |')
    lines.extend(['','## Limitaciones','',
                  '- No hay evidencia de entrenamientos IPPO/MPLight/CoSLight.',
                  '- No se atribuye la mejora/empeoramiento de tráfico a resiliencia: es un smoke de una semilla.',
                  '- Este H12.15 NO demuestra ejecución directa de clases RESCO Fixed/MaxPressure; son proyecciones documentadas.',
                  '- Los controladores solo actúan en B1; el resto de los semáforos conserva la lógica de SUMO.',
                  '- Vine/H09 siguen fuera del contrato nuevo y requieren puente protegido posterior.',
                  '- H12.13 piloto funcional de PPO puede ejecutarse independientemente; no es una prueba SOTA.',''])
    return '\n'.join(lines)


def main(argv=None):
    a=cli_parser().parse_args(argv)
    try:
        b=validate(a)
        print('H12.15 CONTRATO | RESCO 8 pares -> físicos 2 | originales 0/4 | red/ruta sha OK')
        print('H12.15 | dir B1:',b['physical_projection'].grouped_inbound)
        if a.mode=='plan':
            print('H12_15_PLAN_OK | sin SUMO ni nuevas carpetas de resultados')
            return 0
        check(a.rl_steps>=12,'Smoke exige >=12 decisiones para auditar amarillo Fixed-B1')
        check(a.ack_projection=='PHYSICAL_PROJECTIONS_ONLY',
              'Requiere --ack-projection PHYSICAL_PROJECTIONS_ONLY')
        check(a.ack_online_control=='TLS_OVERRIDE',
              'Requiere --ack-online-control TLS_OVERRIDE')
        check(bool(shutil.which(a.binary)),'No se encontró SUMO en PATH')
        import traci, gymnasium, numpy
        out=temp_new_dir(Path(b['revision_root']))
        public=public_manifest(b)
        public['runtime']={
            'sumo_version':subprocess.run([a.binary,'--version'],capture_output=True,text=True,timeout=12).stdout.splitlines()[:2],
            'traci_file':str(Path(traci.__file__).resolve()),'gymnasium':gymnasium.__version__,'numpy':numpy.__version__}
        jsonnew(out/'manifiesto_h12_15.json',public)
        results=[]
        try:
            for method in ('fixed_b1','maxpressure_resco_projected_b1'):
                print('INICIANDO H12.15',method,flush=True)
                r=run_one(b,method,out);verify_end(b);results.append(r)
            check(all(r['n_microticks']==10*a.rl_steps for r in results),'Microticks distintos de lo esperado')
            report={'result':'H12_15_PHYSICAL_SMOKE_OK','schema':SCHEMA,
                    'not_full_resco_replication':True,'network_sha256':sha(b['network']),
                    'routes_sha256':sha(b['routes']),'seed':a.seed,'n_decisions_per_baseline':a.rl_steps,
                    'sources_sha256':b['sources_sha256'],
                    'baseline_results':[{k:v for k,v in r.items() if k not in ('decision_rows','tl_events')} for r in results],
                    'meaning':'solo dos baselines físicos proyectados; NO SOTA completo ni resiliencia'}
            jsonnew(out/'resultado_h12_15.json',report)
            check(not (out/'dictamen_h12_15.md').exists(),'No sobrescribir dictamen')
            (out/'dictamen_h12_15.md').write_text(markdown(public,results),encoding='utf8')
            print('H12_15_PHYSICAL_SMOKE_OK',out)
            return 0
        except Exception as exc:
            jsonnew(out/'ERROR_h12_15.json',{'type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),
                                            'completed':[r['method'] for r in results]})
            print('H12.15 FALLO | conservar carpeta:',out,flush=True)
            raise
    except Exception as exc:
        print('H12.15 FAIL-CLOSED:',type(exc).__name__,str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
