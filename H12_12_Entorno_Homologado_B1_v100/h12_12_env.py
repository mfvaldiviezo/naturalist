"""TSCEnvHomologado: entorno NUEVO de SUMO para futuro entrenamiento H12.13.

No compatible con checkpoint heredado (acciones 2 vs 4 y features redefinidas).
Se necesita SUMO+TraCI+Gymnasium. Único TLS B1; otros TLS conservan sus programas.
El TLS seleccionado pasa explícitamente a control 'online' de TraCI para evitar
saltos actuados espontáneos; estados de luz vienen solo del net.xml.
"""
from __future__ import annotations
import math
from pathlib import Path
import shutil
import uuid
import xml.etree.ElementTree as ET

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from h12_12_contract import (ContractError, PhaseScheduler, read_geometry,
                            observation_34, reward_components, require, sha256_file)


class TSCEnvHomologado(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, *, net_file, route_file, sumocfg_file, output_dir,
                 tls_id='B1', seed=101, step_length=0.5, delta_t=5.0,
                 min_green_s=10.0, max_rl_steps=12, binary='sumo'):
        super().__init__()
        self.net_file=Path(net_file).resolve(strict=True)
        self.route_file=Path(route_file).resolve(strict=True)
        self.sumocfg_file=Path(sumocfg_file).resolve()
        self.output_dir=Path(output_dir).resolve()
        self.geometry=read_geometry(self.net_file,tls_id)
        self.seed=int(seed)
        self.step_length=float(step_length)
        self.delta_t=float(delta_t)
        self.min_green_s=float(min_green_s)
        self.max_rl_steps=int(max_rl_steps)
        require(self.max_rl_steps>=1 and self.max_rl_steps<=720, 'max_rl_steps fuera 1..720')
        require(self.step_length==0.5 and self.delta_t==5.0,
                'H12.12 fija microtick=0.5 s, macrodecisión=5.0 s')
        require(self.min_green_s>=self.delta_t, 'min_green debe ser >=5s')
        self.n_microticks = int(round(self.delta_t/self.step_length))
        require(self.n_microticks ==10, 'Contrato microtick incorrecto')
        self.binary = binary
        self.observation_space = spaces.Box(low=0.0,high=1.0,shape=(34,),dtype=np.float32)
        self.action_space = spaces.Discrete(len(self.geometry.green_indices))
        self.conn=None
        self.scheduler=None
        self._label=None
        self._sumocfg_sha=None
        self._episode_idx=0
        self._step_idx=0
        self._tick_idx=0
        self.events=[]
        self._counts={}
        self._halts={}
        self._waits={}

    def _write_sumocfg(self):
        require(self.sumocfg_file.parent==self.output_dir, 'sumocfg fuera de carpeta de resultados')
        if self._sumocfg_sha is not None:
            require(self.sumocfg_file.exists() and sha256_file(self.sumocfg_file)==self._sumocfg_sha,
                    'Archivo sumocfg alterado entre episodios')
            return
        require(not self.sumocfg_file.exists(), 'No sobrescribir sumocfg existente')
        self.output_dir.mkdir(parents=True,exist_ok=True)
        cfg = ET.Element('configuration')
        inputs=ET.SubElement(cfg,'input')
        ET.SubElement(inputs,'net-file',{'value':str(self.net_file)})
        ET.SubElement(inputs,'route-files',{'value':str(self.route_file)})
        times=ET.SubElement(cfg,'time')
        ET.SubElement(times,'begin',{'value':'0'})
        ET.SubElement(times,'end',{'value':str(self.max_rl_steps*self.delta_t+30.0)})
        processing=ET.SubElement(cfg,'processing')
        ET.SubElement(processing,'time-to-teleport',{'value':'-1'})
        ET.ElementTree(cfg).write(self.sumocfg_file,encoding='utf-8',xml_declaration=True)
        self._sumocfg_sha=sha256_file(self.sumocfg_file)

    def _start(self):
        import traci
        sumo_bin=shutil.which(self.binary)
        require(bool(sumo_bin),f'Binario SUMO no localizado: {self.binary}')
        self._write_sumocfg()
        self._label = 'h1212_'+uuid.uuid4().hex
        cmd=[sumo_bin,'-c',str(self.sumocfg_file),'--step-length',str(self.step_length),
             '--seed',str(self.seed),'--no-step-log','--collision.action','warn']
        traci.start(cmd,label=self._label)
        self.conn=traci.getConnection(self._label)
        tl=self.conn.trafficlight
        tls_id=self.geometry.tls_id
        require(tls_id in self.conn.trafficlight.getIDList(),'B1 no existe en SUMO')
        raw=list(tl.getControlledLanes(tls_id))
        require(set(raw)==set(self.geometry.lanes_in),
                f'Desacuerdo de entradas net.xml vs TraCI: {set(raw)} != {set(self.geometry.lanes_in)}')
        require(tl.getProgram(tls_id)==self.geometry.program_id,
                'Programa TLS actual no corresponde al net.xml')
        logs=list(tl.getAllProgramLogics(tls_id))
        programs=[p for p in logs if p.programID==self.geometry.program_id]
        require(len(programs)==1, 'Programa de TraCI ambiguo')
        require(tuple(p.state for p in programs[0].phases)==
                tuple(p.state for p in self.geometry.phases),
                'Estados TLS TraCI difieren de net.xml')
        init_index=int(tl.getPhase(tls_id))
        require(init_index in self.geometry.green_indices,'Arranque en interverde: bloquear')
        require(tl.getRedYellowGreenState(tls_id)==self.geometry.phases[init_index].state,
                'Estado de luces inconsistente al arrancar')
        self.scheduler=PhaseScheduler(self.geometry,self.min_green_s,init_index)
        # Estado explícito "online" congelado. No usar setPhase, evita salto de verdes.
        tl.setRedYellowGreenState(tls_id,self.scheduler.state)
        require(tl.getRedYellowGreenState(tls_id)==self.scheduler.state,
                'No se pudo fijar estado online inicial')
        self.events.append({'t_s':0.0,'stage':self.scheduler.stage,'kind':'green',
                            'state':self.scheduler.state,'event':'online_initialization'})

    def _sample(self):
        require(self.conn is not None, 'TraCI no conectado')
        output=dict(self.geometry.lane_out_by_in)
        all_lanes=sorted(set(self.geometry.lanes_in).union(*(set(v) for v in output.values())))
        l=self.conn.lane
        self._counts={lane:float(l.getLastStepVehicleNumber(lane)) for lane in all_lanes}
        self._halts={lane:float(l.getLastStepHaltingNumber(lane)) for lane in self.geometry.lanes_in}
        self._waits={lane:float(l.getWaitingTime(lane)) for lane in self.geometry.lanes_in}
        for name,d in [('count',self._counts),('halt',self._halts),('wait',self._waits)]:
            require(all(math.isfinite(v) and v>=0 for v in d.values()),'Sensor inválido: '+name)
        obs=observation_34(list(self.geometry.lanes_in),self._counts,self._halts,
                            self._waits,output,self.scheduler.stage,
                            self.scheduler.stage_elapsed,self.geometry.green_indices,
                            self.min_green_s)
        arr=np.asarray(obs,dtype=np.float32)
        require(self.observation_space.contains(arr),'Observación fuera de Box')
        return arr

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        # Gymnasium/SB3 repite reset en cada episodio: iniciar nueva conexión SUMO
        # sin alterar las fuentes y reutilizando la copia de .sumocfg verificada.
        if self.conn is not None:
            self.close()
        self.events=[]
        self.scheduler=None
        self._episode_idx += 1
        if seed is not None:
            self.seed=int(seed)
        try:
            self._start()
            self._step_idx=0
            self._tick_idx=0
            obs=self._sample()
            return obs,dict(tls=self.geometry.tls_id,action_phases=list(self.geometry.green_indices),
                            real_inbound_lanes=list(self.geometry.lanes_in),
                            control_mode='traci_online',sumo_microtick_s=self.step_length,
                            episode=self._episode_idx)
        except Exception:
            self.close()
            raise

    def step(self, action):
        require(self.conn is not None and self.scheduler is not None,'reset antes de step')
        require(not isinstance(action,bool) and isinstance(action,(int,np.integer)) and
                0<=int(action)<self.action_space.n,'Acción fuera del espacio')
        require(self._step_idx<self.max_rl_steps,'Episodio ya truncado')
        action=int(action)
        collision_events=0
        initial_event_count=len(self.scheduler.transitions)
        for _ in range(self.n_microticks):
            state=self.scheduler.advance(self.step_length,action)
            actual_state=self.conn.trafficlight.getRedYellowGreenState(self.geometry.tls_id)
            if actual_state != state:
                # Solo fijar el estado enumerado, nunca salto directo de green.
                self.conn.trafficlight.setRedYellowGreenState(self.geometry.tls_id,state)
                self.events.append({'t_s':round(self._tick_idx*self.step_length,6),
                                    'stage':self.scheduler.stage,
                                    'kind':self.scheduler.kind,'state':state,'event':'enter_stage'})
            self.conn.simulationStep()
            self._tick_idx+=1
            require(abs(self.conn.simulation.getTime()-self._tick_idx*self.step_length)<1e-5,
                    'SUMO no mantiene microtick 0.5 s')
            require(self.conn.trafficlight.getRedYellowGreenState(self.geometry.tls_id)==state,
                    'SUMO alteró estado TLS: control no aislado')
            collision_events+=int(self.conn.simulation.getCollidingVehiclesNumber())
        self._step_idx+=1
        obs=self._sample()
        rr=reward_components([self._waits[lane] for lane in self.geometry.lanes_in])
        info={'step':self._step_idx,'sim_time_s':self.conn.simulation.getTime(),
              'action_requested':action,'action_green_phase':self.geometry.green_indices[action],
              'stage':self.scheduler.stage,'stage_kind':self.scheduler.kind,
              'stage_state':self.scheduler.state,
              'transition_entries':len(self.scheduler.transitions)-initial_event_count,
              'total_queue':sum(self._halts.values()),
              'wait_total_s':sum(self._waits.values()),
              'reward_components':rr,
              'colliding_vehicles_tick_sum':collision_events,
              'inbound_vehicle_count':sum(self._counts[l] for l in self.geometry.lanes_in)}
        # truncado por horizonte, no asumir episodio resuelto por tráfico inexistente.
        truncated=(self._step_idx >= self.max_rl_steps)
        return obs,float(rr['reward']),False,truncated,info

    def close(self):
        if self.conn is not None:
            try:self.conn.close()
            finally:self.conn=None

    def render(self):
        return None
