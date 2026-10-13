#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H09 v1.2, perfiles persistentes SUMO bajo hipotesis EXPLORATORIAS.

No escribe ni modifica los archivos del benchmark ni los hitos anteriores.
En ACTIVE crea una COPIA de la ruta dentro de la carpeta de salida, con vType
explicitos para una cohorte exacta planificada y anidada. Mantiene speedMode
predeterminado (no llama setSpeed/setSpeedMode ni modifica TLS). La politica
contextual REAL es el modelo nativo de SUMO, cuyos parametros de interseccion
se aplican condicionados a la fase y a las condiciones del trafico.

NO es una calibracion a Quito, NO conecta todavia Vine, NO garantiza infracciones.
CLI --preparar-solo permite inspeccionar asignaciones antes de iniciar SUMO.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PROFILES=ROOT/'config'/'escenarios_exploratorios.json'
VALID_ATTR={
    'tau':(.5,3.0), 'minGap':(0.5,5.0), 'speedFactor':(.8,1.5),
    'jmDriveAfterYellowTime':(-1.0,3.0), 'jmDriveAfterRedTime':(-1.0,2.0),
    'jmIgnoreKeepClearTime':(-1.0,8.0),
}
ACK='ESCENARIO_EXPLORATORIO_NO_CALIBRADO'


def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def json_dump(path,obj):
    path=Path(path)
    if path.exists():raise FileExistsError('No se sobrescribe '+str(path))
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def stable_uniform(seed,vid):
    d=json.dumps([int(seed),'h09_cohort',str(vid)],separators=(',',':'))
    return int.from_bytes(hashlib.sha256(d.encode()).digest()[:8],'big')/2**64


def exact_selection(roster,pct,seed):
    ids=list(roster)
    if len(set(ids))!=len(ids) or not ids:raise ValueError('Cohorte vacía o con duplicados')
    if pct not in (0,15,30,50):raise ValueError('Porcentajes H09 permitidos: 0,15,30,50')
    ordered=sorted(ids,key=lambda v:(stable_uniform(seed,v),v))
    return set(ordered[:int(math.floor(len(ids)*pct/100+.5))])


def original_inputs(cfg):
    cfg=Path(cfg).resolve()
    if not cfg.is_file():raise FileNotFoundError(cfg)
    root=ET.parse(cfg).getroot()
    input_el=root.find('input')
    if input_el is None:raise ValueError('SUMOCFG no contiene <input>')
    def f(tag):
        el=input_el.find(tag)
        return '' if el is None else el.get('value','').strip()
    if f('additional-files'):raise ValueError('Piloto H09 v1.2 exige sumocfg sin adicionales; no remover automáticamente los originales')
    if not f('route-files') or not f('net-file'):
        raise ValueError('Se exigen net-file y route-files en el sumocfg')
    if ',' in f('route-files') or ',' in f('net-file'):
        raise ValueError('Solo una red y un archivo de rutas explícito para este piloto')
    def resolve(value):
        p=Path(value)
        return (p if p.is_absolute() else cfg.parent/p).resolve()
    routes=resolve(f('route-files'));net=resolve(f('net-file'))
    if not routes.is_file() or not net.is_file():raise FileNotFoundError('Archivos SUMO faltantes: '+str((net,routes)))
    return cfg,net,routes


def read_roster(routes,horizon_s):
    if not horizon_s>0:raise ValueError('horizon_s > 0')
    root=ET.parse(routes).getroot()
    if root.tag!='routes':raise ValueError('El archivo de rutas debe tener raíz <routes>')
    explicit=[];ids=set();unsupported=[]
    for child in root:
        if child.tag=='vehicle':
            vid=child.get('id','')
            if not vid or vid in ids:raise ValueError('ID de vehículo vacío o duplicado')
            ids.add(vid)
            depart=child.get('depart','')
            try:t=float(depart)
            except ValueError:
                unsupported.append(f'vehicle[{vid}].depart={depart}')
                continue
            if not math.isfinite(t) or t<0:raise ValueError('depart inválido: '+vid)
            explicit.append((vid,t,child))
        elif child.tag in ('flow','personFlow','trip','person','container','vTypeDistribution'):
            unsupported.append(child.tag)
    if unsupported:
        raise ValueError('Piloto de demanda explícita solamente. No expandir silenciosamente: '+str(unsupported[:8]))
    if not explicit:raise ValueError('No hay vehículos explícitos')
    roster=[vid for vid,t,_ in explicit if t<horizon_s]
    if not roster:raise ValueError('No hay vehículos previstos en horizonte')
    return root,roster,explicit


def validate_profile(profile):
    if not profile:raise ValueError('Perfil vacío')
    for k,v in profile.items():
        if k not in VALID_ATTR:raise ValueError('Atributo SUMO no autorizado: '+k)
        if not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('Parámetro no numérico '+k)
        low,high=VALID_ATTR[k]
        if not low<=v<=high:raise ValueError(f'{k}={v} fuera del rango exploratorio')
    return {k:str(v) for k,v in profile.items()}


def clone_route(root,explicit,selected,profile,out):
    """Cambia solo type de seleccionados; nunca la demanda/rutas de los demás."""
    out=Path(out)
    if out.exists():raise FileExistsError(out)
    vtypes={n.get('id') for n in root.findall('vType')}
    newtype='H09_EXPLORATORIO_V12'
    if newtype in vtypes:raise ValueError('Colisión de identificador vType')
    # No sustituimos silenciosamente especificaciones diferentes de vehículo.
    for vid,_,vehicle in explicit:
        if vid not in selected:continue
        if vehicle.get('type','DEFAULT_VEHTYPE')!='DEFAULT_VEHTYPE':
            raise ValueError('Tipo vehículo no predeterminado, requiere clon de atributos exacto: '+vid)
        if vehicle.find('param') is not None:
            raise ValueError('Parámetros individuales no admitidos automáticamente: '+vid)
    # Si DEFAULT_VEHTYPE fue redefinido, un vType nuevo no heredaría sus parámetros.
    # Fallar cerrado antes de introducir diferencias no relacionadas con el estrés.
    default_override=next((x for x in root.findall('vType') if x.get('id')=='DEFAULT_VEHTYPE'),None)
    if default_override is not None:
        raise ValueError('DEFAULT_VEHTYPE redefine atributos; clonado seguro requiere adaptar el escenario')
    # Namespace estándar para que XML sea portable.
    ET.register_namespace('xsi','http://www.w3.org/2001/XMLSchema-instance')
    root.insert(0,ET.Element('vType',{'id':newtype,'vClass':'passenger',**validate_profile(profile)}))
    for vid,_,vehicle in explicit:
        if vid in selected:vehicle.set('type',newtype)
    ET.ElementTree(root).write(out,encoding='utf-8',xml_declaration=True)
    # Asegurar que preservamos cada vehículo y sus rutas.
    chk=ET.parse(out).getroot()
    if len(chk.findall('vehicle'))!=len(explicit):raise AssertionError('Rutas copiadas incompletas')
    return out


def candidate_events(row,profile_ids,prev=None):
    """Clasifica COMPORTAMIENTOS OBSERVADOS, no decisiones internas SUMO."""
    vid=row.get('vehicle_id')
    if vid not in profile_ids:return None
    if row.get('event_type')=='stopline' and row.get('signal_state') in ('red','yellow'):
        if row.get('classification_quality')=='confirmed':return 'cross_'+row['signal_state']
    if row.get('event_type')=='speed':
        try:
            if float(row['speed_mps'])>float(row['limit_mps'])>0:return 'speeding_sample'
        except (TypeError,ValueError,KeyError):pass
    return None


def load_zones(path):
    if not path:return []
    zones=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(zones,list):raise ValueError('zonas deben ser lista')
    for z in zones:
        if not {'measurement_id','lane_id','from_m','to_m'}.issubset(z):raise ValueError('Zona incompleta: '+str(z))
    return zones


def load_observer(path):
    directory=Path(path) if path else ROOT.parent/'H09_Quito_Instrumentacion_v11'/'scripts'
    fp=directory/'observador_traci_h09_v11.py'
    if not fp.is_file():raise FileNotFoundError('Falta observador v1.1 en '+str(fp))
    # ruta solamente de código heredado (lectura), sin importaciones en run hasta uso.
    sys.path.insert(0,str(directory))
    from observador_traci_h09_v11 import EventObserver
    return EventObserver


def summarize_profiles(selected,seen,seen_types,eventrows,headways,windows,roster_n):
    behavior=Counter()
    per_id=defaultdict(Counter)
    for r in eventrows:
        c=candidate_events(r,selected)
        if c:
            behavior[c]+=1;per_id[r['vehicle_id']][c]+=1
    for vid in headways:
        per_id[vid]['headway_opportunities']=headways[vid]['headway_observed']
        per_id[vid]['close_headway_snapshots']=headways[vid]['short_headway']
        per_id[vid]['red_snapshots_near_tls']=headways[vid]['red_opportunities']
        per_id[vid]['yellow_snapshots_near_tls']=headways[vid]['yellow_opportunities']
        per_id[vid]['internal_stopped_snapshots']=headways[vid]['internal_stopped_snapshots']
    summary={
        'n_assigned':len(selected),'n_roster':roster_n,'assigned_pct':100*len(selected)/roster_n,
        'n_selected_seen':len(seen&selected),
        'n_selected_verified_vtype':len(seen_types&selected),
        'n_selected_never_seen':len(selected-seen),
        'n_expected_selected_without_verified_profile':len(selected-seen_types),
        'candidate_events_observed':dict(behavior),
        'n_selected_with_observed_red_cross':sum(v['cross_red']>0 for v in per_id.values()),
        'n_selected_with_observed_yellow_cross':sum(v['cross_yellow']>0 for v in per_id.values()),
        'n_selected_with_close_headway':sum(v['close_headway_snapshots']>0 for v in per_id.values()),
        'n_selected_with_internal_lane_stop':sum(v['internal_stopped_snapshots']>0 for v in per_id.values()),
        'protocol': 'PERSISTENT_TYPE_EXPOSURE_NOT_COUNT_OF_OBSERVED_VIOLATIONS'
    }
    return summary,per_id


def start_simulation(args,net,routes,original_cfg,selected,roster,original_hashes,profile,plan,mode):
    if args.output.exists():raise FileExistsError('Carpeta de salida existente: '+str(args.output))
    # Previene sobrescribir entradas accidentalmente.
    out=args.output.resolve()
    protected={Path(p).resolve() for p in original_hashes}
    if out in protected or any(out==parent for parent in protected):raise ValueError('Salida coincide con entrada SUMO')
    out.mkdir(parents=True,exist_ok=False)
    copy_route=None
    if mode=='active':
        copy_route=clone_route(plan['root'],plan['vehicles'],selected,profile,out/'rutas_modificadas_H09.rou.xml')
    generated={}
    if copy_route:generated[str(copy_route)]=hash_file(copy_route)
    profile_csv=out/'cohorte_h09.csv'
    with profile_csv.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(('vehicle_id','expected_depart_s','assigned','profile'))
        for vid,t,_ in plan['vehicles']:
            if t<args.pasos*args.step_length:
                w.writerow((vid,format(t,'.7g'),int(vid in selected),args.familia if vid in selected else 'nominal'))
    generated[str(profile_csv)]=hash_file(profile_csv)
    cmd=[args.sumo_bin or shutil.which('sumo') or '', '-c', str(original_cfg), '--seed',str(args.seed),
         '--step-length',str(args.step_length),'--output-prefix',str(out/'sumo_')]
    if copy_route:cmd+=['--route-files',str(copy_route)]
    manifest_base={
      'version':'H09-PERFILES-CONTEXTUALES-v1.2','scope':'HANGZHOU_SIMULATED_NOT_QUITO',
      'mode':mode,'seed':args.seed,'pasos_requested':args.pasos,'step_length_s':args.step_length,
      'porcentaje_solicitado':args.porcentaje,'familia':args.familia,
      'evidence_status':'EXPLORATORY_PROFILE_PARAMETERS_NOT_ESTIMATED_FROM_QUITO',
      'profile_parameters':profile if mode=='active' else None,
      'selection_algorithm':'H09_SHA256_cohort_v1_not_guaranteed_equal_H08b_IDs',
      'roster_rule':'explicit_route_depart_lt_pasos_times_step_length',
      'n_roster':len(roster),'n_selected':len(selected),'sumo_command':cmd,
      'original_hashes_sha256':original_hashes,'generated_hashes_sha256':generated,
      'original_unchanged':True,
      'violations_imposed_by_manual_speedMode_or_tls':False,
      'limitations':[
        'No calibration of conditional Quito infringement probabilities',
        'Crossings are v1.1 observer stopline-transition proxies',
        'Driver population is planned departures, not necessarily observed departures',
        'Assigned exposure is not observed event',
        'No Vine injection integrated in this pilot'
      ]}
    if args.preparar_solo:
        if any(hash_file(path)!=digest for path,digest in original_hashes.items()):
            raise RuntimeError('Un archivo de entrada original cambió durante la preparación')
        manifest_base['status']='ONLY_PREPARED_NO_SUMO_RUN'
        json_dump(out/'manifest_H09.json',manifest_base)
        print('PREPARACIÓN COMPLETADA SIN SUMO:',str(out),'seleccionados:',len(selected),'de',len(roster))
        return
    if not cmd[0]:raise RuntimeError('SUMO no está en PATH (puede ejecutar --preparar-solo)')
    try:
        import traci
    except ImportError:
        home=os.environ.get('SUMO_HOME')
        if home:sys.path.insert(0,str(Path(home)/'tools'))
        import traci
    EventObserver=load_observer(args.instrument_dir)
    zones=load_zones(args.zonas_velocidad)
    sites=[x.strip() for x in args.sites.split(',') if x.strip()]
    obs=EventObserver(run_id=out.name,seed=args.seed,sites=sites,speed_zones=zones)
    seen=set();seen_types=set();headways=defaultdict(Counter);traffic=[]
    print('SUMO H09 MODO:',mode,'PORCENTAJE:',args.porcentaje,'FAMILIA:',args.familia,flush=True)
    print('SUMO COMANDO:', ' '.join(cmd),flush=True)
    traci.start(cmd)
    try:
        for step in range(args.pasos):
            traci.simulationStep()
            obs.observe(traci)
            ids=set(traci.vehicle.getIDList())
            seen.update(ids)
            for vid in (ids&selected):
                typ=str(traci.vehicle.getTypeID(vid))
                if mode=='active' and typ=='H09_EXPLORATORIO_V12':seen_types.add(vid)
                if mode!='active':continue
                try:
                    current_lane=str(traci.vehicle.getLaneID(vid))
                    if current_lane.startswith(':') and float(traci.vehicle.getSpeed(vid))<0.1:
                        headways[vid]['internal_stopped_snapshots']+=1
                    leader=traci.vehicle.getLeader(vid,50.)
                    speed=float(traci.vehicle.getSpeed(vid))
                    if leader is not None and leader[0] and leader[1]>=0 and speed>1.:
                        headways[vid]['headway_observed']+=1
                        gap=float(leader[1]);dtgap=gap/speed
                        if dtgap<1.0:headways[vid]['short_headway']+=1
                    for t in traci.vehicle.getNextTLS(vid):
                        if t[0] not in sites or t[2]>30 or t[2]<0:continue
                        phase=str(t[3]).lower()
                        if phase=='r':headways[vid]['red_opportunities']+=1
                        elif phase=='y':headways[vid]['yellow_opportunities']+=1
                except Exception as exc:
                    raise RuntimeError('Telemetría H09 no disponible para '+vid) from exc
            speeds=[float(traci.vehicle.getSpeed(v)) for v in ids]
            if not all(math.isfinite(s) for s in speeds):raise RuntimeError('Velocidad no finita')
            sim=traci.simulation
            traffic.append({
              'step':step,'time_s':format(float(sim.getTime()),'.6g'),
              'n_vehicles':len(ids),'mean_speed_kmh':format(sum(speeds)/len(speeds)*3.6 if speeds else 0,'.10g'),
              'n_halted':sum(s<0.1 for s in speeds),
              'arrivals_step':int(sim.getArrivedNumber()),'departures_step':int(sim.getDepartedNumber()),
              'collisions_step':int(sim.getCollidingVehiclesNumber()),
              'teleports_start_step':int(sim.getStartingTeleportNumber())
            })
            if sim.getMinExpectedNumber()==0:break
    finally:traci.close()
    if any(hash_file(path)!=digest for path,digest in original_hashes.items()):
        raise RuntimeError('ALERTA: detectada modificación de archivo ORIGINAL después de SUMO')
    # A partir de la salida REAL del observador, nunca de parámetros impuestos.
    obs.write_csv(out/'eventos_h09.csv')
    with (out/'trafico_h09.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=traffic[0].keys());w.writeheader();w.writerows(traffic)
    summary,per_id=summarize_profiles(selected,seen,seen_types,obs.rows,headways,[],len(roster))
    with (out/'exposicion_h09.csv').open('w',newline='',encoding='utf8') as f:
        cols=['vehicle_id','seen','profile_verified','headway_opportunities','close_headway_snapshots','red_snapshots_near_tls','yellow_snapshots_near_tls','cross_red','cross_yellow','speeding_sample','internal_stopped_snapshots']
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        for vid in sorted(selected):
            c=per_id[vid]
            w.writerow({'vehicle_id':vid,'seen':int(vid in seen),'profile_verified':int(vid in seen_types),
                **{k:int(c[k]) for k in cols[3:]}})
    for p in (out/'eventos_h09.csv',out/'trafico_h09.csv',out/'exposicion_h09.csv'):
        generated[str(p)]=hash_file(p)
    manifest_base.update(status='SUMO_EXECUTED_EXPLORATORY',actual_steps=len(traffic),
      n_seen_total=len(seen),instrumental_stats=obs.stats(),exposure_summary=summary,
      traffic_sha256=hash_file(out/'trafico_h09.csv'))
    json_dump(out/'manifest_H09.json',manifest_base)
    print('FINAL:',json.dumps({'mode':mode,'n_steps':len(traffic),'instrumental':obs.stats(),
          'exposure':summary,'traffic_sha256':manifest_base['traffic_sha256']},ensure_ascii=False))
    print('SALIDA:',out)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sumocfg',type=Path,required=True)
    p.add_argument('--modo',choices=('baseline','probe','active'),required=True)
    p.add_argument('--porcentaje',type=int,default=0,choices=(0,15,30,50))
    p.add_argument('--familia',choices=('seguimiento','semaforos','bloqueo','combinado'),default='combinado')
    p.add_argument('--config-perfiles',type=Path,default=PROFILES)
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--pasos',type=int,default=600)
    p.add_argument('--step-length',type=float,default=0.5)
    p.add_argument('--sites',default='B1,B2,C1')
    p.add_argument('--zonas-velocidad',type=Path)
    p.add_argument('--instrument-dir',type=Path,default=None)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sumo-bin',default=None)
    p.add_argument('--ack-active',default='')
    p.add_argument('--preparar-solo',action='store_true')
    args=p.parse_args(argv)
    if args.pasos<=1 or not 0.1<=args.step_length<=1.:p.error('Pasos / dt inválidos')
    if args.modo=='active':
        if args.porcentaje==0:p.error('Active necesita porcentaje > 0')
        if args.ack_active!=ACK:p.error('Active requiere --ack-active '+ACK)
    elif args.porcentaje!=0:p.error('Baseline y probe deben usar --porcentaje 0')
    cfg,net,routes=original_inputs(args.sumocfg)
    root,roster,explicit=read_roster(routes,args.pasos*args.step_length)
    source=json.loads(args.config_perfiles.read_text(encoding='utf8'))
    if source.get('evidence_status')!='EXPLORATORY_HYPOTHESES_NOT_CALIBRATED_QUITO':
        p.error('Configuración no declara explícitamente hipótesis exploratorias')
    prof=source['families'][args.familia]
    validate_profile(prof)
    selected=exact_selection(roster,args.porcentaje,args.seed) if args.modo=='active' else set()
    originals={str(f):hash_file(f) for f in (cfg,net,routes,args.config_perfiles)}
    plan={'root':root,'vehicles':explicit}
    start_simulation(args,net,routes,cfg,selected,roster,originals,prof,plan,args.modo)

if __name__=='__main__':main()
