#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H10 v1.1.2: correction of XML object identity; ablation of H08b original eligibility and contextual eligibility + H09 v1.5.

Reusa el H08b/H08/H06/H03/H04 ORIGINAL en disco, sin copiar ni modificar núcleos.
Una simulación SUMO y una conexión TraCI POR CONDICIÓN. Escenarios:
nominal, vine_protegido, vine_contextual, h09, hibrido_protegido, hibrido_contextual.
Sin controlador RL; sin calibración Quito.
PLAN es solo lectura; RUN requiere dos acuses. No sobrescribe resultados.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

EXPECTED_H08B = 'ee70a04c7f0b698309f7a637a8a0b2b5ddf18434ec3ab6c11dc3346a7a904943'
ORIGINAL_MODULES = (
    'ntvc_vine_r_08b_cuota_auditada.py',
    'ntvc_vine_r_08_inyector_estres_porcentual.py',
    'ntvc_vine_r_06_piloto_integracion_protegida.py',
    'ntvc_vine_r_03_integracion_cinematica_sumo.py',
    'ntvc_vine_r_04_shadow_multivehiculo_rutas_corregidas.py',
)
MODES = ('nominal', 'vine_protegido', 'vine_contextual', 'h09', 'hibrido_protegido', 'hibrido_contextual')

# Solo cambia el dominio de elegibilidad de H06 a través de StressConfig.
# NO se altera speedMode=31, la cópula Vine, el guard cinemático ni el presupuesto.
GUARD_POLICIES = {
    'protegido': dict(free_gap_m=60.0, follower_gap_m=60.0,
        distance_to_lane_end_m=60.0, tls_distance_m=80.0,
        max_speed_kmh=50.0, max_command_delta_a=0.8),
    'contextual': dict(free_gap_m=2.0, follower_gap_m=1.0,
        distance_to_lane_end_m=5.0, tls_distance_m=0.0,
        max_speed_kmh=70.0, max_command_delta_a=0.8),
}
STATUS = 'H10_V112_XML_IDENTITY_FIXED_EXPLORATORY_NOT_QUITO_CALIBRATED'
LEGACY_STATUS = 'H10_V1111_CONTEXTUAL_GUARDS_EXPLORATORY_NOT_QUITO_CALIBRATED'
LEGACY_BRIDGE_SHA256 = '2e5f6693003a435b7f93d93f8e101ab32852882227f8f892dd5b75b7c273efe3'
LEGACY_REUSE_MODES = ('nominal', 'vine_protegido', 'vine_contextual')

ACK1 = 'EXPERIMENTAL_ONLY'
ACK2 = 'NOT_CALIBRATED'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


def load_source(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if not spec or not spec.loader: raise ImportError('No se puede cargar '+str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_vine_dir(root, explicit=None):
    if explicit is not None:
        locations=[Path(explicit).resolve()]
    else:
        locations=[root/'scripts',root/'src',root]
        # Algunos hitos se entregan en una carpeta de scripts dentro de un hito.
        if (root/'scripts').is_dir():locations += [p for p in (root/'scripts').iterdir() if p.is_dir()]
    found=[p for p in locations if all((p/n).is_file() for n in ORIGINAL_MODULES)]
    if len(found)!=1:
        raise FileNotFoundError('Se requiere UNA ubicación con H08b/H08/H06/H03/H04 originales. '
            'Encontradas: '+str(found)+'; use --vine-scripts RUTA si están en otro directorio.')
    folder=found[0]
    digest=sha256(folder/ORIGINAL_MODULES[0])
    if digest!=EXPECTED_H08B:
        raise RuntimeError('H08b original NO coincide con el archivo que acabas de proporcionar. '
            f'SHA esperado={EXPECTED_H08B}; encontrado={digest}. No reconstruir ni sustituir.')
    return folder


def load_originals(folder):
    sys.path.insert(0,str(folder))
    import ntvc_vine_r_08b_cuota_auditada as h08b
    import ntvc_vine_r_08_inyector_estres_porcentual as h08
    import ntvc_vine_r_06_piloto_integracion_protegida as h06
    if sha256(Path(h08b.__file__))!=EXPECTED_H08B:
        raise RuntimeError('Módulo H08b importado NO es la versión auditada.')
    if h08b.FixedRosterInjector.__bases__[0] is not h08.StressInjector:
        raise RuntimeError('H08b ya no hereda el inyector original H08.')
    if h08b.h08 is not h08 or h08b.h06 is not h06:
        raise RuntimeError('Dependencias importadas no son las originales enlazadas.')
    return h08b,h08,h06


def find_reference(root, explicit, h08b, cfg, seed, steps, dt):
    if explicit:
        folders=[Path(explicit).resolve()]
    else:
        base=root/'resultados'
        if not base.is_dir():raise FileNotFoundError(base)
        # Ubicación explícita preferida, búsqueda sólo de baselines de H08.
        folders=sorted({p.parent for p in base.rglob('manifest_hito08.json') if p.is_file()})
    valid=[]; reasons=[]
    for folder in folders:
        try:
            result=h08b.read_reference(folder,cfg,seed,steps,dt)
            valid.append((folder,result))
        except Exception as exc:
            reasons.append(str(folder)+': '+str(exc))
    if len(valid)!=1:
        raise RuntimeError('No se identificó un ÚNICO baseline H08 compatible (seed, pasos, dt, '
            'hashes de entradas). Use --reference-baseline-dir. Coincidencias=' + str(len(valid)) +
            '; diagnósticos='+repr(reasons[:5]))
    return valid[0]


def overlap_counts(vine, h09):
    vine=set(vine);h09=set(h09)
    return dict(n_vine=len(vine),n_h09=len(h09),n_ambos=len(vine&h09),
                n_solo_vine=len(vine-h09),n_solo_h09=len(h09-vine),
                selected_vine=sorted(vine),selected_h09=sorted(h09),
                selected_ambos=sorted(vine&h09))


def get_paths(root):
    root=Path(root).resolve()
    return dict(root=root,cfg=root/'resultados/ntvc_vine_r_07_hangzhou_piloto/hangzhou_vine_sin_additional.sumocfg',
      zones=root/'resultados/h09_zonas_velocidad_generadas_v11.json',
      h09=root/'H09_Quito_Perfiles_Contextuales_v12/scripts/piloto_perfiles_h09_v12.py',
      profiles=root/'H09_Quito_Perfiles_Contextuales_v12/config/escenarios_exploratorios.json',
      observer=root/'H09_Quito_Sensibilidad_v15/instrumentacion/observador_traci_h09_v11.py',
      observer_old=root/'H09_Quito_Instrumentacion_v11/scripts/observador_traci_h09_v11.py',
      historical=root/'resultados/h09_v12_piloto_101',
      out=root/'resultados/h10_vine_h09_imprudencia_v112_piloto_101',
      legacy=root/'resultados/h10_vine_h09_imprudencia_v111_piloto_101')


def check_paths(p):
    for key in ('cfg','zones','h09','profiles','observer','observer_old'):
        if not p[key].is_file():raise FileNotFoundError(f'Falta dependencia {key}: {p[key]}')
    config=json.loads(p['profiles'].read_text(encoding='utf-8'))
    if config.get('evidence_status')!='EXPLORATORY_HYPOTHESES_NOT_CALIBRATED_QUITO':
        raise ValueError('Perfil H09 no está marcado como exploratorio.')
    if 'combinado' not in config.get('families',{}):raise KeyError('H09 combinado no está definido')
    return config['families']['combinado']


def prepare(args):
    p=get_paths(args.root)
    profile=check_paths(p)
    original_dir=discover_vine_dir(p['root'],args.vine_scripts)
    h08b,h08,h06=load_originals(original_dir)
    h09=load_source(p['h09'],'_h10_h09_original_v12')
    cfg,net,routes=h09.original_inputs(p['cfg'])
    original_roster, planned, explicit=h09.read_roster(routes,args.steps*args.dt)
    if len(planned)!=300:raise ValueError('Piloto Hangzhou esperaba 300 IDs programados, obtuvo '+str(len(planned)))
    h09sel=h09.exact_selection(planned,15,args.seed)
    if len(h09sel)!=45:raise ValueError('El 15% H09 no dio 45 IDs')
    (ref_folder,(ranked,ref_hashes,ref_mf,ref_assign,refdoc))=find_reference(
        p['root'],args.reference_baseline_dir,h08b,cfg,args.seed,args.steps,args.dt)
    vinesel=h08b.select_exact(ranked,.15)
    all_inputs=[p['cfg'],net,routes,p['profiles'],p['zones'],p['h09'],p['observer'],p['observer_old'],
                ref_mf,ref_assign,ref_folder/'trafico_hito08.csv']+[original_dir/x for x in ORIGINAL_MODULES]
    # H03.sha256 devuelve digest en MAYÚSCULAS; este módulo usa minúsculas.
    # No fusionar los dicts sin normalizar: el mismo SHA-256 parecía alterado.
    source_hashes=merge_source_hashes(all_inputs, ref_hashes)
    data_manifest=Path(args.data_dir or h06.DEFAULT_DATA)/'manifest.json'
    if not data_manifest.is_file():raise FileNotFoundError('Falta manifiesto congelado H01: '+str(data_manifest))
    source_hashes[str(data_manifest.resolve())]=sha256(data_manifest)
    coh=overlap_counts(vinesel,h09sel)
    if len(vinesel)==0:raise ValueError('Sin IDs Vine seleccionados de la referencia')
    return p,h08b,h08,h06,h09,profile,original_roster,planned,explicit,ref_folder,ranked,coh,source_hashes,original_dir


def profile_telemetry(traci,ids,selected,seen,verified,headways,sites):
    seen.update(ids)
    veh=traci.vehicle
    for vid in sorted(ids&selected):
        if str(veh.getTypeID(vid))=='H09_EXPLORATORIO_V12':verified.add(vid)
        lane=str(veh.getLaneID(vid))
        speed=float(veh.getSpeed(vid))
        if lane.startswith(':') and speed<0.1:headways[vid]['internal_stopped_snapshots']+=1
        leader=veh.getLeader(vid,50.)
        if leader and leader[0] and float(leader[1])>=0 and speed>1.:
            headways[vid]['headway_observed']+=1
            if float(leader[1])/speed<1:headways[vid]['short_headway']+=1
        for tls in veh.getNextTLS(vid):
            if str(tls[0]) not in sites or not 0<=float(tls[2])<=30:continue
            if str(tls[3]).lower()=='r':headways[vid]['red_opportunities']+=1
            if str(tls[3]).lower()=='y':headways[vid]['yellow_opportunities']+=1


def audit_episodes(eventrows,selected):
    """Contar cruces enlazados a oportunidades del mismo episodio, sin tasas Quito."""
    selected=set(selected)
    moving={(r['measurement_id'],r['vehicle_id'],r['signal_state'])
            for r in eventrows if r['event_type']=='tls_moving_opportunity'
            and r['measurement_id']}
    counts=Counter()
    for r in eventrows:
        if r['event_type']!='tls_crossing_link':continue
        if r['signal_state'] not in ('red','yellow','unknown'):continue
        if r['classification_quality']!='confirmed' and r['signal_state']!='unknown':continue
        phase=r['signal_state'];counts[f'cross_{phase}']+=1
        if r['vehicle_id'] in selected:
            counts[f'selected_cross_{phase}']+=1
            if (r['measurement_id'],r['vehicle_id'],phase) in moving:
                counts[f'linked_moving_{phase}_selected']+=1
    counts['moving_red_selected']=sum(1 for _,vid,p in moving if vid in selected and p=='red')
    counts['moving_yellow_selected']=sum(1 for _,vid,p in moving if vid in selected and p=='yellow')
    return dict(counts)


def step_once(traci,obs,step,hsel,seen,verified,headways,injector):
    """Un avance TraCI; el observador lee antes de que Vine programe t+dt."""
    traci.simulationStep()
    obs.observe(traci)
    ids=set(map(str,traci.vehicle.getIDList()))
    speeds=[float(traci.vehicle.getSpeed(v)) for v in ids]
    if not all(math.isfinite(x) for x in speeds):raise RuntimeError('Velocidad no finita')
    sim=traci.simulation
    record=dict(step=step,time_s=format(float(sim.getTime()),'.6g'),
      n_vehicles=len(ids),mean_speed_kmh=format(sum(speeds)/len(speeds)*3.6 if speeds else 0,'.10g'),
      n_halted=sum(s<0.1 for s in speeds),arrivals_step=int(sim.getArrivedNumber()),
      departures_step=int(sim.getDepartedNumber()),collisions_step=int(sim.getCollidingVehiclesNumber()),
      teleports_start_step=int(sim.getStartingTeleportNumber()))
    if hsel:profile_telemetry(traci,ids,hsel,seen,verified,headways,{'B1','B2','C1'})
    if injector is not None:
        injector.on_step(traci,step)  # No simulationStep aquí, contrato H08b.
    return record,sim.getMinExpectedNumber()==0


def normalize_sha256(digest):
    """Sólo normaliza la representación hexadecimal; no modifica el contenido."""
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdefABCDEF' for c in digest):
        raise ValueError('SHA-256 inválido en manifiesto: '+repr(digest))
    return digest.lower()


def merge_source_hashes(all_inputs, reference_hashes):
    """Fusiona manifiestos H03 (SHA uppercase) y H10 (SHA lowercase).

    Comprueba bytes actuales frente a ambos; falla ante verdaderos conflictos.
    """
    snapshots={}
    for item in all_inputs:
        path=Path(item).resolve()
        if not path.is_file():raise FileNotFoundError('Falta fuente H10: '+str(path))
        digest=sha256(path)
        old=snapshots.get(str(path))
        if old is not None and old!=digest:
            raise RuntimeError('Fuente cambió durante preflight: '+str(path))
        snapshots[str(path)]=digest
    for item,ref_digest in reference_hashes.items():
        path=Path(item).resolve()
        if not path.is_file():raise FileNotFoundError('Falta fuente H08: '+str(path))
        expected=normalize_sha256(ref_digest)
        actual=sha256(path)
        if actual!=expected:
            raise RuntimeError('Conflicto verdadero entre manifiesto H08 y archivo actual: '
                +str(path)+' SHA_H08='+expected+' SHA_ACTUAL='+actual)
        if str(path) in snapshots and snapshots[str(path)]!=actual:
            raise RuntimeError('Conflicto verdadero entre H08 y H10: '+str(path))
        snapshots[str(path)]=actual
    verify_sources(snapshots)
    return dict(sorted(snapshots.items()))


def verify_sources(hashes):
    for item,expected in hashes.items():
        path=Path(item)
        if not path.is_file():
            raise RuntimeError('Fuente de entrada desapareció: '+str(path))
        normalized=normalize_sha256(expected)
        actual=sha256(path)
        if actual!=normalized:
            raise RuntimeError('ARCHIVO REALMENTE DIFERENTE, NO CONTINUAR: '+str(path)
                +' SHA_ESPERADO='+normalized+' SHA_ACTUAL='+actual
                +' (normalización mayúsculas/minúsculas ya aplicada)')


def output_safe(path,root):
    path=Path(path).resolve();anchor=(root/'resultados').resolve()
    if anchor not in path.parents:raise ValueError('Salida H10 debe estar dentro de resultados/')
    if path.exists():raise FileExistsError('Salida H10 ya existente; no se sobrescribe: '+str(path))
    return path


def write_csv(path,rows,columns=None):
    with Path(path).open('x',encoding='utf-8',newline='') as f:
        if columns is None:
            if not rows:raise ValueError('Sin filas CSV')
            columns=list(rows[0])
        writer=csv.DictWriter(f,fieldnames=columns)
        writer.writeheader();writer.writerows(rows)


def policy_for_mode(label):
    if label in ('vine_contextual', 'hibrido_contextual'):
        return 'contextual'
    return 'protegido'


def build_vine_config(h08, args, label):
    if label not in MODES or label in ('nominal', 'h09'):
        raise ValueError('Escenario sin Vine: '+str(label))
    policy = policy_for_mode(label)
    params = GUARD_POLICIES[policy]
    cfg = h08.StressConfig(mode='active', variant='vine_student', seed=args.seed,
        penetration=.15, step_length=args.dt, max_commands=args.max_commands,
        max_commands_per_step=2, max_commands_per_window=20,
        window_seconds=60., max_commands_per_vehicle=12,
        cooldown_steps=8, start_time=0., end_time=args.steps*args.dt,
        **params)
    cfg.validate()
    # No cambiamos a otro inyector ni sustituimos funciones H06 en memoria.
    for k,v in params.items():
        if getattr(cfg,k)!=v:
            raise RuntimeError('Política de elegibilidad no aplicada: '+k)
    return cfg


def verify_route_assignment(route_file, planned, selected, type_id='H09_EXPLORATORIO_V12'):
    """Comprobación sobre el XML realmente escrito, no sobre objetos en memoria.

    Exige correspondencia exacta entre IDs elegidos y IDs que reciben el vType.
    No acepta asignaciones a IDs no elegibles ni pérdida de vehículos.
    """
    path=Path(route_file)
    tree=ET.parse(path).getroot()
    if tree.tag!='routes':raise ValueError('Ruta H09 modificada no es XML routes')
    nodes=tree.findall('vehicle')
    ids=[x.get('id') for x in nodes]
    if len(ids)!=len(set(ids)) or any(not x for x in ids):
        raise RuntimeError('IDs duplicados o vacíos en las rutas H09 modificadas')
    planned=set(planned); selected=set(selected)
    if not selected.issubset(planned):
        raise RuntimeError('IDs H09 seleccionados fuera del roster')
    if not selected.issubset(set(ids)):
        raise RuntimeError('IDs seleccionados ausentes en XML generado: '+str(sorted(selected-set(ids))[:8]))
    if not any(x.get('id')==type_id for x in tree.findall('vType')):
        raise RuntimeError('vType H09 no definido en XML generado')
    assigned={x.get('id') for x in nodes if x.get('type','DEFAULT_VEHTYPE')==type_id}
    if assigned!=selected:
        raise RuntimeError('El XML guardado no asigna H09 a la cohorte exacta: '
            +f'esperados={len(selected)}, guardados={len(assigned)}, '
            +f'ausentes={sorted(selected-assigned)[:8]}, '
            +f'extras={sorted(assigned-selected)[:8]}')
    return {'assigned_expected':len(selected),'assigned_xml':len(assigned),
            'vehicles_in_xml':len(ids),'sha256':sha256(path)}


def run_one(label,ctx,args):
    (p,h08b,h08,h06,h09,profile,roster_tree,planned,explicit,
     ref_folder,ranked,coh,sources,original_dir)=ctx
    out=output_safe(p['out']/label,p['root'])
    has_h09=label=='h09' or label.startswith('hibrido_');has_vine=label.startswith('vine_') or label.startswith('hibrido_')
    vsel=set(coh['selected_vine']) if has_vine else set()
    hsel=set(coh['selected_h09']) if has_h09 else set()
    cfg_file,net,routes=h09.original_inputs(p['cfg'])
    verify_sources(sources)
    kernel=groups=tables=ds_manifest=None;n_pairs=None
    injector=None
    if has_vine:
        config=build_vine_config(h08,args,label)
        kernel,groups,tables,n_pairs,ds_manifest=h08.load_frozen_cohorts(
            args.data_dir or h06.DEFAULT_DATA,config)
        injector=h08b.FixedRosterInjector(config,kernel,groups,ranked,vsel)
    EventObserver=load_source(p['observer'],'_h10_observer_v15').EventObserver
    zones=h09.load_zones(p['zones'])
    obs=EventObserver(run_id=label,seed=args.seed,sites=['B1','B2','C1'],speed_zones=zones)
    binary=args.sumo_binary or shutil.which('sumo')
    if not binary:raise RuntimeError('SUMO no disponible en PATH')
    try:
        import traci
    except ImportError:
        import os
        if os.environ.get('SUMO_HOME'):sys.path.insert(0,str(Path(os.environ['SUMO_HOME'])/'tools'))
        import traci
    out.mkdir(parents=True,exist_ok=False)
    if has_h09:
        # CRÍTICO: read_roster devuelve el árbol y los nodos de ESTE MISMO árbol.
        # v1.1.1 hacía ET.parse(...) por separado y clone_route modificaba nodos
        # desconectados, dejando todos los vehicle type predeterminados en XML.
        root_tree,route_planned,ex=h09.read_roster(routes,args.steps*args.dt)
        if set(route_planned)!=set(planned):
            raise RuntimeError('La demanda cambió entre preflight y clonado de rutas H09')
        route_new=h09.clone_route(root_tree,ex,hsel,profile,out/'rutas_modificadas_H09.rou.xml')
        route_assignment_audit=verify_route_assignment(route_new,planned,hsel)
        print('H10 XML H09 VERIFICADO:',json.dumps(route_assignment_audit,ensure_ascii=False),flush=True)
    else:
        route_new=None
        route_assignment_audit=None
    with (out/'cohortes_h10.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['vehicle_id','vine_reference','vine_selected','h09_planned','h09_selected'])
        universe=sorted(set(ranked)|set(planned))
        for vid in universe:
            w.writerow([vid,int(vid in ranked),int(vid in vsel),int(vid in planned),int(vid in hsel)])
    command=[binary,'-c',str(p['cfg']),'--seed',str(args.seed),
             '--step-length',str(args.dt),'--output-prefix',str(out/'sumo_')]
    if route_new:command+=['--route-files',str(route_new)]
    print('H10 INICIO',label,'SUMO:', ' '.join(command),flush=True)
    seen=set();verified=set();headways=defaultdict(Counter);traffic=[]
    traci.start(command)
    try:
        for step in range(args.steps):
            record,finished=step_once(traci,obs,step,hsel,seen,verified,headways,injector)
            traffic.append(record)
            if finished:break
    finally:
        traci.close()
    if len(traffic)!=args.steps or [x['step'] for x in traffic]!=list(range(args.steps)):
        raise RuntimeError('Horizonte incompleto: no declarar éxito')
    verify_sources(sources)
    if has_h09 and (seen & hsel) != verified:
        # No se inventa validación positiva; dejar diagnóstico en carpeta parcial.
        missing=sorted((seen & hsel)-verified)
        diag={'status':'H09_RUNTIME_TYPE_MISMATCH','seen_selected':len(seen&hsel),
              'verified':len(verified),'unverified_vehicle_ids':missing,
              'xml_route_audit':route_assignment_audit}
        (out/'DIAGNOSTICO_H09_NO_VALIDADO.json').write_text(
            json.dumps(diag,ensure_ascii=False,indent=2),encoding='utf-8')
        raise RuntimeError('Perfil H09 incorrecto para vehículos observados: '
            +str(missing[:12])+'; diagnóstico: '+str(out/'DIAGNOSTICO_H09_NO_VALIDADO.json'))
    if has_h09 and sha256(route_new)!=route_assignment_audit['sha256']:
        raise RuntimeError('Archivo H09 generado cambió durante simulación')
    obs.write_csv(out/'eventos_h09.csv')
    write_csv(out/'trafico_h09.csv',traffic)
    h_summary,h_perid=h09.summarize_profiles(hsel,seen,verified,obs.rows,headways,[],len(planned))
    with (out/'cohorte_h09.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(('vehicle_id','expected_depart_s','assigned','profile'))
        for vid,t,_ in explicit:
            if t<args.steps*args.dt:w.writerow((vid,format(t,'.7g'),int(vid in hsel),'combinado' if vid in hsel else 'nominal'))
    expcols=['vehicle_id','seen','profile_verified','headway_opportunities','close_headway_snapshots',
        'red_snapshots_near_tls','yellow_snapshots_near_tls','cross_red','cross_yellow',
        'speeding_sample','internal_stopped_snapshots']
    with (out/'exposicion_h09.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=expcols);w.writeheader()
        for vid in sorted(hsel):
            c=h_perid[vid]
            w.writerow({'vehicle_id':vid,'seen':int(vid in seen),
                        'profile_verified':int(vid in verified),
                        **{k:int(c[k]) for k in expcols[3:]}})
    vine_meta=None
    if injector is not None:
        actions,fleet,assignment,vine_meta=injector.results()
        if len(fleet)!=args.steps or list(fleet['step'])!=list(range(args.steps)):
            raise RuntimeError('H08b incomplete, abortando éxito')
        if vine_meta['n_commands']!=vine_meta['n_commands_confirmed'] or vine_meta['remaining_pending']:
            raise RuntimeError('Comandos Vine no confirmados t+dt, abortando éxito')
        actions.to_csv(out/'acciones_hito08.csv',index=False,float_format='%.12g')
        fleet.to_csv(out/'trafico_hito08.csv',index=False,float_format='%.12g')
        assignment.to_csv(out/'asignacion_hito08.csv',index=False,float_format='%.12g')
    output_files=['cohortes_h10.csv','eventos_h09.csv','trafico_h09.csv','cohorte_h09.csv','exposicion_h09.csv']
    if route_new:output_files+=['rutas_modificadas_H09.rou.xml']
    if injector is not None:output_files+=['acciones_hito08.csv','trafico_hito08.csv','asignacion_hito08.csv']
    actual={'mode':label,'seed':args.seed,'steps':len(traffic),'dt':args.dt,
         'source_sha256':sources,'h09_route_assignment_audit':route_assignment_audit,'h08_reference':str(ref_folder),
         'sumo_command':command,'h09_profile':profile if has_h09 else None,
         'vine_guard_policy':policy_for_mode(label) if has_vine else None,
         'vine_guard_parameters':GUARD_POLICIES[policy_for_mode(label)] if has_vine else None,
         'bridge_sha256':sha256(Path(__file__).resolve()),
         'cohorts':{**coh,'n_vine_assigned_this_mode':len(vsel),'n_h09_assigned_this_mode':len(hsel)},
         'h09_exposure':h_summary,'instrumental':obs.stats(),
         'episode_audit_h09_selected':audit_episodes(obs.rows,hsel),
         'episode_audit_vine_selected':audit_episodes(obs.rows,vsel),
         'vine':vine_meta,'n_training_pairs_h08_original':n_pairs,
         'frozen_data_manifest':str((Path(args.data_dir or h06.DEFAULT_DATA)/'manifest.json').resolve()),
         'traffic_metrics':{'arrivals':sum(x['arrivals_step'] for x in traffic),
             'mean_halted':sum(x['n_halted'] for x in traffic)/len(traffic),
             'mean_speed_kmh':sum(float(x['mean_speed_kmh']) for x in traffic)/len(traffic),
             'collisions':sum(x['collisions_step'] for x in traffic),
             'teleports':sum(x['teleports_start_step'] for x in traffic)},
         'h09_traffic_sha256':sha256(out/'trafico_h09.csv'),
         'output_sha256':{f:sha256(out/f) for f in output_files},
         'status':STATUS,
         'limitations':['No comparacion RL', 'H08b baseline-observed vs H09 planned departures may differ',
                        'Vine statistical model and kinematic limits unchanged; H06 eligibility thresholds changed ONLY for contextual modes; speedMode remains 31','No calibration for temporal transfer','H09 crossing is stopline proxy']}
    # Comparación fuerte de invariancia: archivo H09 histórico misma semilla/modalidad.
    if args.seed==101 and label in ('nominal','h09'):
        old=p['historical']/('baseline' if label=='nominal' else 'active_15_combinado')/'manifest_H09.json'
        if old.is_file():
            target=json.loads(old.read_text(encoding='utf-8'))['traffic_sha256']
            actual['historical_traffic_sha256']=target
            if actual['h09_traffic_sha256']!=target:
                raise RuntimeError('El piloto H10 cambió tráfico respecto a H09 histórico '+label)
            actual['historical_traffic_identical']=True
        else:raise FileNotFoundError('Falta control histórico para comparar: '+str(old))
    with (out/'manifest_h10.json').open('x',encoding='utf-8') as f:
        json.dump(actual,f,ensure_ascii=False,indent=2,allow_nan=False)
    print('H10 OK',label,'H09 rojo:',obs.stats().get('signal_states',{}).get('red',0),
          'Vine comandos:',(vine_meta or {}).get('n_commands',0),flush=True)
    return actual


def validate_existing_manifest(loc, label, sources, seed, dt, steps, legacy=False):
    """Audita origen, versión del puente y todos los hashes antes de reutilizar."""
    file=loc/'manifest_h10.json'
    if not file.is_file():raise RuntimeError('Salida parcial sin manifest, no sobrescribir: '+str(loc))
    man=json.loads(file.read_text(encoding='utf-8'))
    exp_status=LEGACY_STATUS if legacy else STATUS
    exp_bridge=LEGACY_BRIDGE_SHA256 if legacy else sha256(Path(__file__).resolve())
    if man.get('status')!=exp_status or man.get('source_sha256')!=sources or \
       int(man.get('seed',-1))!=seed or int(man.get('steps',-1))!=steps or \
       float(man.get('dt',-1))!=dt or man.get('bridge_sha256')!=exp_bridge or \
       man.get('mode')!=label or \
       man.get('vine_guard_policy')!=(policy_for_mode(label) if label not in ('nominal','h09') else None):
        raise RuntimeError('Manifest existente incompatible: '+str(loc))
    for filename,digest in man.get('output_sha256',{}).items():
        if sha256(loc/filename)!=digest:raise RuntimeError('Resultado H10 alterado: '+str(loc/filename))
    if not man.get('output_sha256'):
        raise RuntimeError('Manifest sin archivos de salida auditables: '+str(loc))
    if label=='nominal' and not man.get('historical_traffic_identical'):
        raise RuntimeError('Control nominal no corroborado contra H09 histórico: '+str(loc))
    if label.startswith('vine_'):
        meta=man.get('vine') or {}
        if (meta.get('n_commands')!=meta.get('n_commands_confirmed') or
            meta.get('remaining_pending') or meta.get('reference_covers_active_observed') is False):
            raise RuntimeError('Validación Vine original inconsistente: '+str(loc))
    return man


def inspect_previous(p,labels,sources,seed,dt,steps):
    complete={}; origins={}
    for label in labels:
        current=p['out']/label
        old=p['legacy']/label
        if current.exists():
            complete[label]=validate_existing_manifest(current,label,sources,seed,dt,steps)
            origins[label]={'location':str(current),'source':'v112'}
        elif label in LEGACY_REUSE_MODES and old.exists():
            complete[label]=validate_existing_manifest(old,label,sources,seed,dt,steps,legacy=True)
            origins[label]={'location':str(old),'source':'v111_verified_readonly'}
    return complete,origins


def build_comparison(manifests):
    """Two 2x2 factorial contrasts: protected and contextual, same seeds/inputs."""
    if set(manifests)!=set(MODES):raise ValueError('H10 v1.1 requiere seis condiciones')
    def get(m,k):
        if k in ('red','yellow','unknown'):
            return int(manifests[m]['instrumental'].get('signal_states',{}).get(k,0))
        return float(manifests[m]['traffic_metrics'][k])
    metrics=['arrivals','mean_halted','mean_speed_kmh','red','yellow','unknown','collisions','teleports']
    effects={}
    for metric in metrics:
        n=get('nominal',metric);h=get('h09',metric)
        variants={}
        for policy in GUARD_POLICIES:
            v=get('vine_'+policy,metric); b=get('hibrido_'+policy,metric)
            variants[policy]=dict(nominal=n,vine=v,h09=h,hibrido=b,
                vine_minus_nominal=v-n,h09_minus_nominal=h-n,
                hybrid_minus_nominal=b-n,interaction=b-v-h+n)
        variants['contextual_minus_protegido']={
            'vine':variants['contextual']['vine']-variants['protegido']['vine'],
            'hybrid':variants['contextual']['hibrido']-variants['protegido']['hibrido']}
        effects[metric]=variants
    return {'status':'H10_V111_SIX_MODE_ABLATION_ONE_SEED_EXPLORATORY',
        'one_traci_session_per_condition':True,
        'different_sampling_frames_for_vine_and_h09':True,
        'speed_mode_preserved':31,
        'guard_policies':GUARD_POLICIES,
        'effects':effects}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path.cwd())
    ap.add_argument('--vine-scripts',type=Path,default=None)
    ap.add_argument('--reference-baseline-dir',type=Path,default=None)
    ap.add_argument('--data-dir',type=Path,default=None)
    ap.add_argument('--sumo-binary',type=str,default=None)
    ap.add_argument('--seed',type=int,default=101)
    ap.add_argument('--steps',type=int,default=600)
    ap.add_argument('--dt',type=float,default=.5)
    ap.add_argument('--max-commands',type=int,default=100)
    ap.add_argument('--ejecutar',action='store_true')
    ap.add_argument('--ack-active',default='')
    ap.add_argument('--ack-time-scale',default='')
    a=ap.parse_args(argv)
    if a.seed!=101 or a.steps!=600 or a.dt!=.5:
        ap.error('H10 primer piloto requiere seed=101, steps=600, dt=0.5; no extrapolar aún')
    if a.max_commands<1 or a.max_commands>500:ap.error('1 <= max-commands <= 500')
    if a.ejecutar and (a.ack_active!=ACK1 or a.ack_time_scale!=ACK2):
        ap.error('Ejecutar requiere --ack-active EXPERIMENTAL_ONLY --ack-time-scale NOT_CALIBRATED')
    ctx=prepare(a);p=ctx[0];coh=ctx[11];sources=ctx[12]
    prev,origins=inspect_previous(p,MODES,sources,a.seed,a.dt,a.steps)
    print('H10 v1.1.2 PREPARADO: H08b ORIGINAL SHA=',EXPECTED_H08B,flush=True)
    print('POLÍTICAS INYECTOR VINE:',json.dumps(GUARD_POLICIES,ensure_ascii=False),flush=True)
    print('BASELINE H08=',str(ctx[9]),flush=True)
    print('INTEGRIDAD SHA-256: OK; H03/H06 (uppercase) y H10 (lowercase) normalizados sin omitir validación',flush=True)
    print('COHORTES:',json.dumps({k:v for k,v in coh.items() if not k.startswith('selected_')},ensure_ascii=False),flush=True)
    for label in MODES:
        if label in prev:
            print('REUTILIZANDO AUDITADO',label,origins[label]['location'],flush=True)
        else:
            print('PENDIENTE',label,str(p['out']/label),flush=True)
    if not a.ejecutar:return 0
    for label in MODES:
        if label not in prev:
            prev[label]=run_one(label,ctx,a)
            origins[label]={'location':str(p['out']/label),'source':'v112'}
    report=p['out']/'resumen_factorial_h10.json'
    report.parent.mkdir(parents=True,exist_ok=True)
    comparison=build_comparison(prev)
    comparison['source_scenarios']=origins
    comparison['version']='H10_v112_XML_identity_fixed'
    comparison['legacy_bridge_sha256']=LEGACY_BRIDGE_SHA256
    if report.exists():
        data=json.loads(report.read_text(encoding='utf-8'))
        if data!=comparison:raise RuntimeError('Reporte H10 existente incompatible')
    else:
        with report.open('x',encoding='utf-8') as f:
            json.dump(comparison,f,ensure_ascii=False,indent=2,allow_nan=False)
    print('H10 v1.1.2 COMPLETADO: seis condiciones (sin RL, sin calibración Quito).',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
