"""Mock funcional de TraCI+Gymnasium sin SUMO: valida integración de alto nivel.
No equivale a pilotaje real con SUMO.
"""
import importlib
import math
from pathlib import Path
import sys
import tempfile
import types
from unittest import TestCase, mock

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_h12_12 import network_fixture, STATES

class FakeBox:
    def __init__(self,low,high,shape,dtype):self.low,self.high,self.shape,self.dtype=low,high,shape,dtype
    def contains(self,v):return v.shape==self.shape and v.dtype==np.dtype(self.dtype) and bool(np.all(np.isfinite(v)) and np.all(v>=self.low) and np.all(v<=self.high))
class FakeDiscrete:
    def __init__(self,n):self.n=n

class Trafficlight:
    def __init__(self):self.current=STATES[0];self.changed=[]
    def getIDList(self):return ['B1']
    def getControlledLanes(self,tls):return [x+'_0' for x in ['B2B1','C1B1','B0B1','A1B1'] for _ in range(4)]
    def getProgram(self,tls):return '0'
    def getAllProgramLogics(self,tls):
        return [types.SimpleNamespace(programID='0',phases=[types.SimpleNamespace(state=x) for x in STATES])]
    def getPhase(self,tls):return 0
    def getRedYellowGreenState(self,tls):return self.current
    def setRedYellowGreenState(self,tls,state):
        self.current=state;self.changed.append(state)

class Lane:
    def getLastStepVehicleNumber(self,l):return 3
    def getLastStepHaltingNumber(self,l):return 0
    def getWaitingTime(self,l):return 0
class Simulation:
    def __init__(self):self.time=0
    def getTime(self):return self.time
    def getCollidingVehiclesNumber(self):return 0
class Connection:
    def __init__(self):self.trafficlight=Trafficlight();self.lane=Lane();self.simulation=Simulation();self.closed=False;self.spoil=False
    def simulationStep(self):
        self.simulation.time+=0.5
        if self.spoil:self.trafficlight.current='rrrrrrrrrrrrrrrr'
    def close(self):self.closed=True

class RuntimeTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.net=root/'n.net.xml';self.routes=root/'d.rou.xml';self.out=root/'result'
        network_fixture(self.net)
        self.routes.write_text('<routes/>')
        self.conn=Connection()
        fake_gym=types.ModuleType('gymnasium');fake_gym.Env=type('Env',(),{'reset':lambda self,seed=None:None})
        fake_spaces=types.ModuleType('gymnasium.spaces')
        fake_spaces.Box=FakeBox;fake_spaces.Discrete=FakeDiscrete
        fake_gym.spaces=fake_spaces
        fake_traci=types.ModuleType('traci')
        fake_traci.start=lambda cmd,label=None:None
        fake_traci.getConnection=lambda label=None:self.conn
        self.modules=mock.patch.dict(sys.modules,{'gymnasium':fake_gym,'gymnasium.spaces':fake_spaces,'traci':fake_traci})
        self.modules.start();self.addCleanup(self.modules.stop)
        # reload because the faked imports must bind to env in this test
        sys.modules.pop('h12_12_env',None)
        self.module=importlib.import_module('h12_12_env')
        self.addCleanup(lambda:sys.modules.pop('h12_12_env',None))
        self.which=mock.patch('h12_12_env.shutil.which',return_value='sumo_fake');self.which.start();self.addCleanup(self.which.stop)

    def env(self):
        return self.module.TSCEnvHomologado(net_file=self.net,route_file=self.routes,
                    sumocfg_file=self.out/'sumo.sumocfg',output_dir=self.out,max_rl_steps=12)

    def test_runtime_shape_and_time(self):
        env=self.env()
        try:
            obs,meta=env.reset()
            self.assertEqual(obs.shape,(34,));self.assertEqual(env.action_space.n,2)
            obs,r,term,trunc,info=env.step(0)
            self.assertEqual(info['sim_time_s'],5)
            self.assertEqual(env._tick_idx,10)
            self.assertEqual(r,0);self.assertFalse(term);self.assertFalse(trunc)
            self.assertTrue(env.observation_space.contains(obs))
        finally:env.close()

    def test_intergreen_3seconds_in_real_step_loop(self):
        env=self.env()
        try:
            env.reset()
            for k in range(12):
                _,r,_,truncated,info=env.step((k//4)%2)
            self.assertTrue(truncated)
            states=[x['state'] for x in env.events]
            self.assertIn(STATES[1],states);self.assertIn(STATES[3],states)
            # transitions may be open control, but must never write a state outside original program
            self.assertTrue(set(self.conn.trafficlight.changed)<=set(STATES))
            self.assertEqual(info['sim_time_s'],60)
        finally:env.close()

    def test_reject_invalid_action(self):
        env=self.env()
        try:
            env.reset()
            with self.assertRaises(ValueError):env.step(3)
        finally:env.close()

    def test_fail_closed_if_sumo_overrides_stage(self):
        env=self.env()
        try:
            env.reset();self.conn.spoil=True
            with self.assertRaisesRegex(ValueError,'alteró estado TLS'):env.step(0)
        finally:env.close()


    def test_repeated_gymnasium_reset(self):
        env=self.env()
        try:
            o,m=env.reset(seed=101)
            env.step(0)
            o2,m2=env.reset(seed=102)
            self.assertEqual(m['episode'],1)
            self.assertEqual(m2['episode'],2)
            self.assertEqual(env._tick_idx,0)
            self.assertTrue(env.observation_space.contains(o2))
            self.assertEqual(env._sumocfg_sha,__import__('h12_12_contract').sha256_file(env.sumocfg_file))
        finally:env.close()

    def test_reject_sumocfg_modified_between_episodes(self):
        env=self.env()
        try:
            env.reset()
            env.sumocfg_file.write_text('changed')
            with self.assertRaisesRegex(ValueError,'alterado entre episodios'):env.reset()
        finally:env.close()
    def test_reject_file_overwrite(self):
        env=self.env();self.out.mkdir();(self.out/'sumo.sumocfg').write_text('existing')
        with self.assertRaisesRegex(ValueError,'sobrescribir'):env._write_sumocfg()

if __name__=='__main__':
    import unittest;unittest.main()
