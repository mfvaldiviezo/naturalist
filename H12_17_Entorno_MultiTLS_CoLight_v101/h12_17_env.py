"""Entorno Gymnasium multi-TLS H12.17 para 12 semáforos Hangzhou.

Sin PPO, CoLight ni Vine/H09. H12.17 prueba solo instrumentación de red.
El estado por intersección conserva fórmula H12.12: obs34 H12.12 importada
SIN cambiar su módulo original; B1 se comprueba contra contrato previo.
"""
from __future__ import annotations
import math
import shutil
from pathlib import Path
from uuid import uuid4
import xml.etree.ElementTree as ET

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from h12_17_contract import (ContractError, PhaseScheduler, parse_network,
                            require,sha256_file)
from h12_12_contract import observation_34, reward_components

class MultiTLSHomologado(gym.Env):
    metadata={'render_modes':[]}
    def __init__(self, *, net_file,route_file,output_dir,sumocfg_file,
                 seed=101,step_length=0.5,delta_t=5.0,min_green_s=10.0,
                 max_rl_steps=12,binary='sumo',expected_net_sha=None,
                 expected_route_sha=None):
        super().__init__()
        self.net_file=Path(net_file).resolve(strict=True)
        self.route_file=Path(route_file).resolve(strict=True)
        self.output_dir=Path(output_dir).resolve()
        self.sumocfg_file=Path(sumocfg_file).resolve()
        self.contract=parse_network(self.net_file,require_hangzhou=True)
        from h12_17_contract import validate_route
        self.route_sha=validate_route(self.route_file)
        if expected_net_sha:require(sha256_file(self.net_file)==expected_net_sha,'SHA red diferente')
        if expected_route_sha:require(self.route_sha==expected_route_sha,'SHA rutas diferente')
        self.seed=int(seed)
        self.step_length=float(step_length)
        self.delta_t=float(delta_t)
        self.min_green_s=float(min_green_s)
        self.max_rl_steps=int(max_rl_steps)
        require(self.seed>=0 and self.max_rl_steps>=1 and self.max_rl_steps<=720,
                'Seed o RL steps incorrectos')
        require(self.step_length==0.5 and self.delta_t==5.0 and self.min_green_s>=5.,
                'Contrato fijo 0.5/5 s, min verde >=5')
        self.n_microticks=10
        self.binary=binary
        self.tls_ids=self.contract.node_ids
        self.geometries={g.tls_id:g for g in self.contract.geometries}
        require(all(len(g.green_indices)==2 for g in self.contract.geometries),
                'H12.17 requiere dos verdes por intersección')
        self.action_space=spaces.MultiDiscrete(np.array([2]*len(self.tls_ids),dtype=np.int64))
        self.observation_space=spaces.Box(0,1,shape=(len(self.tls_ids),34),dtype=np.float32)
        self.conn=None
        self.label=None
        self.schedulers={}
        self.events=[]
        self._cfg_sha=None
        self._steps=0
        self._ticks=0
        self._episode=0
        self._last_counts={}
        self._last_halts={}
        self._last_waits={}
        self._last_local_rewards={}

    def _write_sumocfg(self):
        require(self.sumocfg_file.parent==self.output_dir,
                'sumocfg debe residir en carpeta aislada')
        if self._cfg_sha:
            require(self.sumocfg_file.is_file() and sha256_file(self.sumocfg_file)==self._cfg_sha,
                    'sumocfg alterado entre episodios')
            return
        require(not self.sumocfg_file.exists(),'No sobrescribir sumocfg')
        self.output_dir.mkdir(parents=True,exist_ok=True)
        cfg=ET.Element('configuration')
        inp=ET.SubElement(cfg,'input')
        ET.SubElement(inp,'net-file',value=str(self.net_file))
        ET.SubElement(inp,'route-files',value=str(self.route_file))
        tim=ET.SubElement(cfg,'time')
        ET.SubElement(tim,'begin',value='0')
        ET.SubElement(tim,'end',value=str(self.max_rl_steps*self.delta_t+30.))
        processing=ET.SubElement(cfg,'processing')
        ET.SubElement(processing,'time-to-teleport',value='-1')
        ET.ElementTree(cfg).write(self.sumocfg_file,encoding='utf8',xml_declaration=True)
        self._cfg_sha=sha256_file(self.sumocfg_file)

    def _start(self):
        import traci
        binary=shutil.which(self.binary)
        require(binary is not None,f'SUMO no localizado: {self.binary}')
        require(sha256_file(self.net_file)==self.contract.net_sha256 and sha256_file(self.route_file)==self.route_sha,
                'Fuentes cambiaron antes de iniciar SUMO')
        self._write_sumocfg()
        self.label='h1217_'+uuid4().hex
        cmd=[binary,'-c',str(self.sumocfg_file),'--step-length',str(self.step_length),
             '--seed',str(self.seed),'--no-step-log','--collision.action','warn']
        traci.start(cmd,label=self.label)
        self.conn=traci.getConnection(self.label)
        tl=self.conn.trafficlight
        require(set(tl.getIDList())==set(self.tls_ids),
                f'TLS reales no coinciden: {sorted(tl.getIDList())}')
        for tls in self.tls_ids:
            geo=self.geometries[tls]
            require(set(tl.getControlledLanes(tls))==set(geo.lanes_in),
                    f'{tls}: carriles no coinciden con red')
            require(tl.getProgram(tls)==geo.program_id,f'{tls}: programa diferente')
            programs=[p for p in tl.getAllProgramLogics(tls) if p.programID==geo.program_id]
            require(len(programs)==1,f'{tls}: lógica ambigua')
            require(tuple(p.state for p in programs[0].phases)==tuple(p.state for p in geo.phases),
                    f'{tls}: estados programa TraCI alterados')
            idx=int(tl.getPhase(tls))
            require(idx in geo.green_indices,f'{tls}: inicio en amarillo; fail-closed')
            require(tl.getRedYellowGreenState(tls)==geo.phases[idx].state,
                    f'{tls}: luces iniciales no coinciden')
            self.schedulers[tls]=PhaseScheduler(geo,self.min_green_s,idx)
        for tls in self.tls_ids:
            tl.setRedYellowGreenState(tls,self.schedulers[tls].state)
            require(tl.getRedYellowGreenState(tls)==self.schedulers[tls].state,
                    f'{tls}: falló tomar control online')
            self.events.append(dict(t_s=0.,tls=tls,stage=self.schedulers[tls].stage,
                                    kind='green',event='online_initialization'))

    def _sample(self):
        require(self.conn is not None,'SUMO no conectado')
        input_lanes=set()
        all_lanes=set()
        for geo in self.contract.geometries:
            input_lanes.update(geo.lanes_in)
            all_lanes.update(geo.lanes_in)
            for _,out in geo.lane_out_by_in:all_lanes.update(out)
        lane=self.conn.lane
        counts={l:float(lane.getLastStepVehicleNumber(l)) for l in sorted(all_lanes)}
        halts={l:float(lane.getLastStepHaltingNumber(l)) for l in sorted(input_lanes)}
        waits={l:float(lane.getWaitingTime(l)) for l in sorted(input_lanes)}
        for label,src in [('counts',counts),('halts',halts),('waits',waits)]:
            require(all(math.isfinite(x) and x>=0 for x in src.values()),
                    'Sensor no válido '+label)
        observations=[]
        rewards={}
        for tls in self.tls_ids:
            g=self.geometries[tls]
            s=self.schedulers[tls]
            obs=observation_34(g.lanes_in,counts,halts,waits,dict(g.lane_out_by_in),
                               s.stage,s.stage_elapsed,g.green_indices,self.min_green_s)
            require(len(obs)==34,f'{tls}: obs incorrecto')
            observations.append(obs)
            rewards[tls]=reward_components([waits[l] for l in g.lanes_in])
        a=np.asarray(observations,dtype=np.float32)
        require(self.observation_space.contains(a),'Observaciones fuera de Box')
        self._last_counts=counts;self._last_halts=halts;self._last_waits=waits
        self._last_local_rewards=rewards
        return a

    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if self.conn is not None:self.close()
        self.events=[]
        self.schedulers={}
        self._episode+=1
        if seed is not None:self.seed=int(seed)
        self._ticks=self._steps=0
        try:
            self._start()
            obs=self._sample()
            return obs,dict(node_order=list(self.tls_ids),
                            edge_index=self.contract.as_json()['graph_directed_edge_index'],
                            num_tls=len(self.tls_ids),actions_per_tls=[2]*len(self.tls_ids),
                            episode=self._episode,control_mode='online_12_tls')
        except Exception:
            self.close()
            raise

    def step(self,actions):
        require(self.conn is not None and self.schedulers,'reset antes de step')
        require(self._steps<self.max_rl_steps,'Episodio ya truncado')
        a=np.asarray(actions)
        require(a.shape==(len(self.tls_ids),) and a.dtype.kind in ('i','u') and
                all(v in (0,1) for v in a.tolist()),'Acciones deben ser enteros binarios, orden canónico 12 TLS')
        requested=[int(x) for x in a]
        hits=0
        start_transitions={tls:len(self.schedulers[tls].transitions) for tls in self.tls_ids}
        for _ in range(self.n_microticks):
            newstates={tls:self.schedulers[tls].advance(self.step_length,requested[i])
                       for i,tls in enumerate(self.tls_ids)}
            for tls in self.tls_ids:
                tl=self.conn.trafficlight
                if tl.getRedYellowGreenState(tls)!=newstates[tls]:
                    tl.setRedYellowGreenState(tls,newstates[tls])
                    self.events.append(dict(t_s=round(self._ticks*self.step_length,6),
                                            tls=tls,stage=self.schedulers[tls].stage,
                                            kind=self.schedulers[tls].kind,
                                            event='enter_stage',state=newstates[tls]))
            self.conn.simulationStep()
            self._ticks+=1
            require(abs(float(self.conn.simulation.getTime())-self._ticks*self.step_length)<1e-5,
                    'Tiempo SUMO fuera de microtick 0.5s')
            for tls in self.tls_ids:
                require(self.conn.trafficlight.getRedYellowGreenState(tls)==newstates[tls],
                        f'{tls}: SUMO cambió luces durante online control')
            hits+=int(self.conn.simulation.getCollidingVehiclesNumber())
        self._steps+=1
        obs=self._sample()
        reward=sum(v['reward'] for v in self._last_local_rewards.values())/len(self.tls_ids)
        per={}
        for i,tls in enumerate(self.tls_ids):
            g=self.geometries[tls];s=self.schedulers[tls]
            per[tls]=dict(action=requested[i],requested_green_phase=g.green_indices[requested[i]],
                          effective_stage=s.stage,kind=s.kind,
                          queue=sum(self._last_halts[l] for l in g.lanes_in),
                          wait_s=sum(self._last_waits[l] for l in g.lanes_in),
                          inbound_vehicles=sum(self._last_counts[l] for l in g.lanes_in),
                          reward=self._last_local_rewards[tls]['reward'],
                          new_transition_entries=len(s.transitions)-start_transitions[tls])
        info=dict(step=self._steps,sim_time_s=self.conn.simulation.getTime(),
                  n_microticks=self._ticks,local=per,collisions=hits,
                  graph_nodes=list(self.tls_ids),global_reward=reward)
        return obs,float(reward),False,self._steps>=self.max_rl_steps,info

    def close(self):
        if self.conn is not None:
            try:self.conn.close()
            finally:self.conn=None
    def render(self):return None
