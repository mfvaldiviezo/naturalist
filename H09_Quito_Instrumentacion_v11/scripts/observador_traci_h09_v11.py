#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Observador TraCI H09 v1.1 (SOLO LECTURA de estado, sin control de vehículos/TLS).

Integración:
  obs=EventObserver(run_id='baseline_101',seed=101,sites=['B1'],speed_zones=[])
  traci.simulationStep()
  obs.observe(traci)  # una vez, DESPUES de cada simulationStep
  obs.write_csv('.../eventos_h09.csv')

CLI independiente:
  python scripts/observador_traci_h09.py --sumocfg ... --seed 101 --pasos 600 \
    --step-length 0.5 --sites B1,C1 --salida-dir resultados/h09_nuevo

Detecta PASOS DE LINEA mediante transiciones de estado observables, no la
frontera geométrica exacta; ante transiciones de fase ambiguas conserva
unknown/uncertain. La salida es una PROXY, no se equipara a protocolo Quito.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

FIELDS=('run_id','seed','vehicle_id','site_id','passage_id','event_type',
        'signal_state','classification_quality','speed_mps','limit_mps',
        'measurement_id','time_s','observation_method','distance_prev_m',
        'phase_prev','phase_current','lane_prev','lane_current','reason')

def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for buf in iter(lambda:f.read(1048576),b''):h.update(buf)
    return h.hexdigest()

def fmt_phase(x):
    if not x:return 'unknown'
    s=str(x).lower()
    if s in ('r','y'):return 'red' if s=='r' else 'yellow'
    if s=='g':return 'green'
    # 's' (stop), 'o' (off) y estados no convencionales se marcan inciertos.
    return 'unknown'

class EventObserver:
    def __init__(self,run_id,seed,sites,speed_zones=(),near_dist_m=25.0,
                 tolerance_m=3.0):
        if not run_id:raise ValueError('run_id obligatorio')
        if not sites:raise ValueError('sites no puede estar vacio')
        self.run_id=str(run_id);self.seed=int(seed);self.sites=set(sites)
        self.speed_zones=list(speed_zones)
        self.near_dist_m=float(near_dist_m);self.tolerance_m=float(tolerance_m)
        if self.near_dist_m<=0 or self.tolerance_m<0:raise ValueError('distancias invalidas')
        self.prev={};self.prev_time=None;self.rows=[]
        self.crossings=Counter();self.speed_seen=set();self.exited_unresolved=0
        self.n_steps=0;self.n_teleports=0;self.n_collisions=0
        self._step_switch_times={};self.uncertain_reasons=Counter()

    @staticmethod
    def _tls_info(raw):
        try:
            for x in raw:
                if len(x)>=4:
                    yield str(x[0]),int(x[1]),float(x[2]),str(x[3])
        except (ValueError,TypeError):return

    def _snapshot(self,traci,vid):
        veh=traci.vehicle
        lane=str(veh.getLaneID(vid));pos=float(veh.getLanePosition(vid))
        v=float(veh.getSpeed(vid))
        if not all(math.isfinite(x) for x in (pos,v)) or v<0:
            raise ValueError('Posición o velocidad no válida '+vid)
        tls={a:(idx,dist,state) for a,idx,dist,state in self._tls_info(veh.getNextTLS(vid))
             if a in self.sites and math.isfinite(dist)}
        return {'lane':lane,'pos':pos,'speed':v,'tls':tls,
                'switches':{k:self._step_switch_times.get(k) for k in tls}}

    def observe(self,traci):
        now=float(traci.simulation.getTime());dt=float(traci.simulation.getDeltaT())
        if not math.isfinite(now) or not math.isfinite(dt) or dt<=0:
            raise ValueError('Reloj TraCI invalido')
        if self.prev_time is not None and now <= self.prev_time:
            raise ValueError('El observer solo puede llamarse una vez por simulationStep')
        # Un registro por TLS y paso. getNextSwitch es una prediccion del proximo
        # cambio; si cae en la ventana temporal, abstenerse de clasificar.
        self._step_switch_times={}
        for tls in self.sites:
            try:
                self._step_switch_times[tls]=float(traci.trafficlight.getNextSwitch(tls))
            except (AttributeError,Exception):
                self._step_switch_times[tls]=None
        ids=sorted(traci.vehicle.getIDList());curr={}
        for vid in ids:
            curr[str(vid)]=self._snapshot(traci,str(vid))
        self.n_steps+=1
        sim=traci.simulation
        self.n_collisions+=int(sim.getCollidingVehiclesNumber())
        self.n_teleports+=int(sim.getStartingTeleportNumber())
        # Registro de VELOCIDAD, primera vez que se entra en un punto de muestreo fijo.
        for vid,state in curr.items():
            for zone in self.speed_zones:
                zname=str(zone['measurement_id']);zone_lane=str(zone['lane_id'])
                key=(zname,vid)
                if key in self.speed_seen or state['lane']!=zone_lane:continue
                if not float(zone['from_m'])<=state['pos']<=float(zone['to_m']):continue
                speed_lim=float(traci.lane.getMaxSpeed(state['lane']))
                if speed_lim<=0 or not math.isfinite(speed_lim):continue
                self.speed_seen.add(key)
                self.rows.append(dict(run_id=self.run_id,seed=self.seed,vehicle_id=vid,
                    site_id=state['lane'],passage_id=f'{zname}|{vid}',event_type='speed',
                    signal_state='',classification_quality='confirmed',speed_mps=state['speed'],
                    limit_mps=speed_lim,measurement_id=zname,time_s=now,
                    observation_method='zone_first_snapshot',distance_prev_m='',
                    phase_prev='',phase_current='',lane_prev='',lane_current=state['lane'],
                    reason='speed_at_defined_zone_not_BIGRS_protocol'))
        if self.prev_time is not None:
            for vid,old in self.prev.items():
                current=curr.get(vid)
                if not current:
                    if old['tls']:self.exited_unresolved+=1
                    continue  # no afirmar que cruzo al desaparecer del mundo.
                for tls,(idx,dist,state) in old['tls'].items():
                    if dist < 0 or dist>self.near_dist_m:continue
                    next_tls=current['tls'].get(tls)
                    # Si el mismo tls sigue siendo el siguiente, no hubo cruce confirmado.
                    if next_tls is not None and next_tls[0]==idx:continue
                    if current['lane']==old['lane']:continue
                    # Se requiere aproximación suficiente para alcanzar la línea en dt.
                    close_enough=dist<=max(old['speed'],current['speed'])*dt+self.tolerance_m
                    phase_prev=fmt_phase(state)
                    try:
                        raw_state=str(traci.trafficlight.getRedYellowGreenState(tls))
                        phase_now=fmt_phase(raw_state[idx]) if idx<len(raw_state) else 'unknown'
                    except Exception:phase_now='unknown'
                    prev_switch=old.get('switches',{}).get(tls)
                    # No confundir fase de la observacion con fase exacta del cruce.
                    planned_inside=(prev_switch is not None and
                        self.prev_time+1e-8 < prev_switch <= now+1e-8)
                    certain=(phase_prev!='unknown' and phase_prev==phase_now
                             and close_enough and not planned_inside)
                    label=phase_prev if certain else 'unknown'
                    if not close_enough:reason='outside_reach_proxy'
                    elif phase_prev!=phase_now:reason='phase_change_between_snapshots'
                    elif planned_inside:reason='scheduled_switch_inside_interval'
                    elif phase_prev=='unknown':reason='unsupported_tls_state'
                    else:reason='stable_phase_transition_proxy'
                    if not certain:self.uncertain_reasons[reason]+=1
                    self.crossings[(vid,tls)]+=1
                    nr=self.crossings[(vid,tls)]
                    self.rows.append(dict(run_id=self.run_id,seed=self.seed,vehicle_id=vid,
                        site_id=tls,passage_id=f'{tls}|{vid}|{nr}',event_type='stopline',
                        signal_state=label,classification_quality='confirmed' if certain else 'uncertain',
                        speed_mps=old['speed'],limit_mps='',measurement_id='',
                        time_s=now,observation_method='TLS_next_disappeared_with_lane_transition',
                        distance_prev_m=round(dist,5),phase_prev=phase_prev,phase_current=phase_now,
                        lane_prev=old['lane'],lane_current=current['lane'],
                        reason=reason))
        self.prev=curr;self.prev_time=now

    def write_csv(self,path):
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists():raise FileExistsError(f'Se protege salida previa: {p}')
        with p.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(self.rows)

    def stats(self):
        v=Counter(r['event_type'] for r in self.rows)
        col=Counter(r['signal_state'] for r in self.rows if r['event_type']=='stopline')
        return {'n_steps':self.n_steps,'stopline_events':v['stopline'],
                'speed_samples':v['speed'],'signal_states':dict(col),
                'unresolved_vehicle_departures':self.exited_unresolved,
                'uncertain_reasons':dict(self.uncertain_reasons),
                'collision_reports_sum':self.n_collisions,'teleport_reports_sum':self.n_teleports,
                'limitation':'stopline_event_is_transition_proxy_not_same_as_Quito_field_protocol'}


def safe_write_json(path,data):
    path=Path(path)
    if path.exists():raise FileExistsError('Se protege salida previa: '+str(path))
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sumocfg',type=Path,required=True)
    p.add_argument('--seed',type=int,default=101)
    p.add_argument('--step-length',type=float,default=0.5)
    p.add_argument('--pasos',type=int,default=600)
    p.add_argument('--sites',required=True,help='IDs reales de semáforo separados por coma, ej. B1,C1')
    p.add_argument('--zonas-velocidad',type=Path,help='JSON lista de {measurement_id,lane_id,from_m,to_m}')
    p.add_argument('--salida-dir',required=True,type=Path)
    p.add_argument('--sumo-bin',default=None)
    p.add_argument('--run-id',default=None)
    args=p.parse_args(argv)
    if not args.sumocfg.is_file():p.error('sumocfg inexistente')
    if not 0.1<=args.step_length<=2 or args.pasos<2:p.error('Reloj o pasos inválidos')
    sites=[t.strip() for t in args.sites.split(',') if t.strip()]
    if not sites:p.error('Se requieren sitios')
    zones=json.loads(args.zonas_velocidad.read_text(encoding='utf8')) if args.zonas_velocidad else []
    if not isinstance(zones,list):p.error('Zonas de velocidad deben ser lista')
    if args.salida_dir.exists():raise FileExistsError('La salida ya existe; elija nueva carpeta')
    try:import traci
    except ImportError:
        import os
        home=os.environ.get('SUMO_HOME')
        if home:sys.path.insert(0,str(Path(home)/'tools'))
        import traci
    binary=args.sumo_bin or shutil.which('sumo')
    if not binary:raise RuntimeError('SUMO no encontrado en PATH')
    out=args.salida_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    observer=EventObserver(run_id=args.run_id or out.name,seed=args.seed,sites=sites,speed_zones=zones)
    cmd=[str(binary),'-c',str(args.sumocfg.resolve()),'--seed',str(args.seed),
         '--step-length',str(args.step_length),'--output-prefix',str(out/'sumo_')]
    print('SOLO OBSERVADOR SUMO:', ' '.join(cmd),flush=True)
    traci.start(cmd)
    try:
        for _ in range(args.pasos):
            traci.simulationStep()
            observer.observe(traci)
            if traci.simulation.getMinExpectedNumber()==0:break
    finally:traci.close()
    observer.write_csv(out/'eventos_h09.csv')
    manifest={'version':'H09-OBSERVADOR-TRACI-v1.1','run_id':observer.run_id,'seed':args.seed,
       'sumocfg':str(args.sumocfg.resolve()),'sumocfg_sha256':hash_file(args.sumocfg),
       'eventos_sha256':hash_file(out/'eventos_h09.csv'),'sumo_command':cmd,
       'observer_only':True,'sites':sites,'speed_zones':zones,'metrics':observer.stats(),
       'no_vehicle_or_signal_command_sent':True,
       'protocol_caveat':'Proxy de cruces; no replica la metodología de Quito. No infiere infracciones dentro de ventanas de cambio de fase.'}
    safe_write_json(out/'manifest_observador_h09.json',manifest)
    print('FINAL:',json.dumps(observer.stats(),ensure_ascii=False))
    print('SALIDA:',out)

if __name__=='__main__':main()
