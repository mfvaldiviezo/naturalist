#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PRUEBA POSITIVA INSTRUMENTAL en red ARTIFICIAL totalmente aislada.

Crea 1 interseccion y 1 vehiculo por escenario (amarillo/rojo) en una carpeta NUEVA.
SOLO AQUI altera TLS y speedMode (7) para provocar cruces conocidos. Nunca usa
Hangzhou, datos Quito, ruta original, Vine ni cualquier baseline del usuario.
NO es calibracion ni modelo empirico. Requiere SUMO y netconvert en el equipo.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from observador_traci_h09_v11 import EventObserver


def lookup_binary(name):
    binary=shutil.which(name)
    if binary:return binary
    home=os.environ.get('SUMO_HOME')
    if home:
        b=Path(home)/'bin'/(name+'.exe' if os.name=='nt' else name)
        if b.is_file():return str(b)
    raise RuntimeError(f'No se encuentra {name}; revise PATH y SUMO_HOME')

def build_net(out,netconvert):
    out=Path(out)
    (out/'micro.nod.xml').write_text('''<nodes>
<node id="W" x="-120" y="0" type="dead_end"/>
<node id="C" x="0" y="0" type="traffic_light"/>
<node id="E" x="120" y="0" type="dead_end"/>
<node id="S" x="0" y="-120" type="dead_end"/>
<node id="N" x="0" y="120" type="dead_end"/>
</nodes>''',encoding='utf-8')
    (out/'micro.edg.xml').write_text('''<edges>
<edge id="W2C" from="W" to="C" numLanes="1" speed="13.89" priority="2"/>
<edge id="C2E" from="C" to="E" numLanes="1" speed="13.89" priority="2"/>
<edge id="S2C" from="S" to="C" numLanes="1" speed="13.89" priority="2"/>
<edge id="C2N" from="C" to="N" numLanes="1" speed="13.89" priority="2"/>
</edges>''',encoding='utf-8')
    (out/'micro.con.xml').write_text('''<connections>
<connection from="W2C" to="C2E" fromLane="0" toLane="0"/>
<connection from="S2C" to="C2N" fromLane="0" toLane="0"/>
</connections>''',encoding='utf-8')
    cmd=[netconvert,'--node-files',str(out/'micro.nod.xml'),
         '--edge-files',str(out/'micro.edg.xml'),
         '--connection-files',str(out/'micro.con.xml'),
         '--output-file',str(out/'micro.net.xml'),
         '--tls.yellow.time','3']
    ret=subprocess.run(cmd,capture_output=True,text=True)
    if ret.returncode:
        raise RuntimeError(f'netconvert falló: {ret.stderr}\nCOMANDO: {cmd}')
    network=ET.parse(out/'micro.net.xml').getroot()
    tl={x.get('id') for x in network.findall('tlLogic')}
    connections=[c for c in network.findall('connection')
                 if c.get('from')=='W2C' and c.get('to')=='C2E']
    if 'C' not in tl or not connections or connections[0].get('tl')!='C':
        raise RuntimeError('La red artificial no contiene TLS C en movimiento W2C>C2E; revisar netconvert')
    (out/'micro.rou.xml').write_text('''<routes>
<vType id="probe" vClass="passenger" length="4.5" accel="3" decel="4.5" minGap="2" tau="1"/>
<route id="oeste_este" edges="W2C C2E"/>
<vehicle id="probe_0" type="probe" route="oeste_este" depart="0" departSpeed="10"/>
</routes>''',encoding='utf-8')
    return out/'micro.net.xml',out/'micro.rou.xml'

def run_one(traci,sumobin,net,routes,out,phase,dt=0.1,seed=101,max_steps=450):
    directory=out/phase;directory.mkdir(parents=True,exist_ok=False)
    command=[sumobin,'--net-file',str(net),'--route-files',str(routes),
      '--step-length',str(dt),'--seed',str(seed),'--time-to-teleport','-1',
      '--end',str(dt*max_steps),'--output-prefix',str(directory/'sumo_')]
    label=f'h09_isolated_{phase}'
    traci.start(command,label=label)
    conn=traci.getConnection(label)
    observer=EventObserver(f'H09_SOLO_PRUEBA_POSITIVA_{phase}',seed,['C'])
    forced_steps=0
    try:
        raw=conn.trafficlight.getRedYellowGreenState('C')
        if not raw:raise RuntimeError('TLS C no tiene estados')
        target={'red':'r','yellow':'y'}[phase]*len(raw)
        conn.trafficlight.setRedYellowGreenState('C',target)
        for _ in range(max_steps):
            # Esta prueba deliberada fuerza fase y vehiculo en una red que SOLO
            # contiene 1 auto. La simulacion cientifica original queda intacta.
            conn.trafficlight.setRedYellowGreenState('C',target)
            for vid in conn.vehicle.getIDList():
                conn.vehicle.setSpeedMode(vid,7)
                conn.vehicle.setSpeed(vid,10.)
                forced_steps+=1
            conn.simulationStep()
            observer.observe(conn)
            if observer.stats()['stopline_events']>=1:break
            if conn.simulation.getMinExpectedNumber()==0:break
    finally:
        conn.close()
    observer.write_csv(directory/'eventos_h09.csv')
    stats=observer.stats()
    confirmed=sum(r['signal_state']==phase and r['classification_quality']=='confirmed'
                  for r in observer.rows if r['event_type']=='stopline')
    data={'test':f'ISOLATED_POSITIVE_{phase.upper()}','scope':'ARTIFICIAL_NETWORK_NOT_QUITO_OR_HANGZHOU',
          'manual_tls_forced':True,'speedMode_forced_7':True,
          'requested_signal':phase,'forced_vehicle_steps':forced_steps,
          'positive_detected':confirmed>0,'confirmed_positive_count':confirmed,
          'observer_stats':stats,'sumo_command':command}
    (directory/'resultado_prueba.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    return data

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--salida-dir',required=True,type=Path)
    p.add_argument('--permitir-infracciones-aisladas',action='store_true',required=True,
                   help='Confirmar que es SOLO una prueba artificial aislada, nunca usar en benchmark')
    args=p.parse_args()
    if args.salida_dir.exists():raise FileExistsError('No se modifica carpeta existente: '+str(args.salida_dir))
    binary=lookup_binary('sumo');netconvert=lookup_binary('netconvert')
    args.salida_dir.mkdir(parents=True,exist_ok=False)
    net,routes=build_net(args.salida_dir,netconvert)
    try:import traci
    except ImportError:
        home=os.environ.get('SUMO_HOME')
        if home:sys.path.insert(0,str(Path(home)/'tools'))
        import traci
    results=[run_one(traci,binary,net,routes,args.salida_dir,phase) for phase in ('red','yellow')]
    print(json.dumps(results,indent=2,ensure_ascii=False))
    if not all(x['positive_detected'] for x in results):
        raise RuntimeError('Prueba POSITIVA incompleta. Revisar salidas; NO considerar validada la deteccion.')
    print('PRUEBA POSITIVA AISLADA: ambos estados detectados (rojo y amarillo).')
    print('Esto valida funcionamiento instrumental bajo estados FORZADOS; NO tasa de infracciones naturalistas.')
if __name__=='__main__':main()
