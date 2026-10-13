import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import h12_19_offpolicy as s
import h12_19_td as td

NAMES=list(('A1','A2','B0','B1','B2','B3','C0','C1','C2','C3','D1','D2'))

class Bridge:
    NODES=tuple(NAMES)
    LIBSIGNAL_COMMIT='127af9f93902778e556de2eedb2b606c4c9447e6'
    NET_SHA='fake-net-sha'
    ROUTE_SHA='fake-route-sha'
    @staticmethod
    def counts_to_x(lanes,counts):
        return [[float(counts[x]) for x in lanes[n]]+[0.]*(4-len(lanes[n])) for n in NAMES]

def fixture_rows(n=24):
    rows=[]
    for k in range(n):
        rows.append(dict(step=k+1,obs_12x4=[[float((k+i)%5)]*4 for i in range(12)],
          next_obs_12x4=[[float((k+i+1)%5)]*4 for i in range(12)],
          requested_actions=[((k//4)+(i%2))%2 for i in range(12)],
          reward_per_node=[-float(i%4) for i in range(12)],
          effective_phases={j:0 if i%2==0 else 2 for i,j in enumerate(NAMES)},
          global_reward_h1217=-1.,done=(k==n-1),collisions=0))
    return rows

def make_shadow(base,n=12):
    base.mkdir(parents=True,exist_ok=True)
    mf={'schema':'shadow-fixture','provenance':{'libsignal':{'committed_file_sha256':'abc'}},'graph':{},'local_h1218_source_sha256':{}}
    s.write_new(base/'manifiesto_h12_18.json',mf)
    d=[]
    for k in range(n):
        d.append({'step':k+1,'input_lane_count_12x4':[[0.]*4 for _ in range(12)],
         'shadow_q_12x2':[[.2,.5] for _ in range(12)],
         'executed_test_policy':[k%2 for _ in range(12)],'collisions':0})
    result={'result':s.SHADOW_STATUS,'training':'NOT_RUN','checkpoint':'NONE',
     'actions_applied':'ONLY_H12.17_STAGGERED_TEST_POLICY',
     'n_nodes':12,'n_edges':32,'n_steps':n,'n_microticks':n*10,
     'manifest_sha256':s.sha(base/'manifiesto_h12_18.json'),
     'node_order':NAMES,'libsignal_commit':Bridge.LIBSIGNAL_COMMIT,
     'source_sha256':'abc','diagnostics':d}
    s.write_new(base/'resultado_h12_18.json',result)
    return mf,result

class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)
        self.m,self.r=make_shadow(self.dir)
    def put(self,x):
        (self.dir/'resultado_h12_18.json').write_text(json.dumps(x),encoding='utf-8')
    def test_good(self):
        z=s.validate_shadow(self.dir,Bridge)
        self.assertEqual(z['n_decisions'],12)
    def test_status(self):
        d=copy.deepcopy(self.r);d['result']='PENDING';self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_neural_control_not_shadow(self):
        d=copy.deepcopy(self.r);d['actions_applied']='COLIGHT';self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_training_forged(self):
        d=copy.deepcopy(self.r);d['training']='YES';self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_checkpoint_forged(self):
        d=copy.deepcopy(self.r);d['checkpoint']='old.zip';self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_network(self):
        d=copy.deepcopy(self.r);d['n_nodes']=13;self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_steps(self):
        d=copy.deepcopy(self.r);d['n_steps']=11;self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_microticks(self):
        d=copy.deepcopy(self.r);d['n_microticks']+=1;self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_manifest_changed(self):
        (self.dir/'manifiesto_h12_18.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_wrong_nodes(self):
        d=copy.deepcopy(self.r);d['node_order'][0]='X';self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_commit(self):
        d=copy.deepcopy(self.r);d['libsignal_commit']='BAD';self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_source(self):
        d=copy.deepcopy(self.r);d['source_sha256']='changed';self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_incomplete_diagnostics(self):
        d=copy.deepcopy(self.r);d['diagnostics'].pop();self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_q_non_finite(self):
        d=copy.deepcopy(self.r);d['diagnostics'][0]['shadow_q_12x2'][0][0]=float('nan');self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_input_shape(self):
        d=copy.deepcopy(self.r);d['diagnostics'][0]['input_lane_count_12x4'][0]=[1,2,3];self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_nonbinary(self):
        d=copy.deepcopy(self.r);d['diagnostics'][0]['executed_test_policy'][0]=2;self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_collision(self):
        d=copy.deepcopy(self.r);d['diagnostics'][0]['collisions']=1;self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_order(self):
        d=copy.deepcopy(self.r);d['diagnostics'][0]['step']=99;self.put(d)
        with self.assertRaises(s.GateError):s.validate_shadow(self.dir,Bridge)
    def test_readonly_validation(self):
        before=sorted(p.name for p in self.dir.iterdir())
        s.validate_shadow(self.dir,Bridge)
        self.assertEqual(before,sorted(p.name for p in self.dir.iterdir()))

class ReplayTests(unittest.TestCase):
    def setUp(self):self.rows=fixture_rows()
    def test_good(self):
        x=s.audit_transitions(self.rows,NAMES)
        self.assertEqual(x['node_transitions'],288)
        self.assertEqual(x['actions_covered'],[0,1])
    def bad(self,path,value):
        rows=copy.deepcopy(self.rows)
        o=rows
        for k in path[:-1]:o=o[k]
        o[path[-1]]=value
        with self.assertRaises(s.GateError):s.audit_transitions(rows,NAMES)
    def test_short_replay(self):
        with self.assertRaises(s.GateError):s.audit_transitions(self.rows[:12],NAMES)
    def test_step_order(self):self.bad([0,'step'],2)
    def test_obs_shape(self):self.bad([0,'obs_12x4',0],[2.,3.])
    def test_next_shape(self):self.bad([0,'next_obs_12x4',0],[2.,3.])
    def test_obs_nan(self):self.bad([0,'obs_12x4',0,0],float('nan'))
    def test_obs_negative(self):self.bad([0,'obs_12x4',0,0],-1.)
    def test_float_actions(self):self.bad([0,'requested_actions',0],.1)
    def test_action_out_of_range(self):self.bad([0,'requested_actions',0],3)
    def test_action_all_one(self):
        rows=copy.deepcopy(self.rows)
        for r in rows:r['requested_actions']=[1]*12
        with self.assertRaises(s.GateError):s.audit_transitions(rows,NAMES)
    def test_reward_positive(self):self.bad([0,'reward_per_node',0],1.)
    def test_reward_nan(self):self.bad([0,'reward_per_node',0],float('nan'))
    def test_early_done(self):self.bad([0,'done'],True)
    def test_no_last_done(self):self.bad([23,'done'],False)
    def test_collisions(self):self.bad([0,'collisions'],1)
    def test_missing_tls(self):self.bad([0,'effective_phases'],{'B1':0})
    def test_missing_action(self):self.bad([0,'requested_actions'],[1])
    def test_wrong_type(self):self.bad([0,'obs_12x4',0,0],'0')

class DriverTests(unittest.TestCase):
    def test_parser_defaults(self):
        p=s.arg_parser();a=p.parse_args(['--repo-root','x','--revision-root','y','--h1216-dir','a','--h1217-dir','b','--h1218-dir','c','--h1218-shadow-dir','d','--libsignal-dir','e'])
        self.assertEqual((a.mode,a.steps,a.updates,a.batch_size),('plan',24,4,4))
    def test_parser_missing_required(self):
        with self.assertRaises(SystemExit):s.arg_parser().parse_args([])
    def test_plan_no_result(self):
        with mock.patch.object(s,'prepare_plan',return_value=(None,{},None)):
            self.assertEqual(s.main(['--repo-root','x','--revision-root','y','--h1216-dir','a','--h1217-dir','b','--h1218-dir','c','--h1218-shadow-dir','d','--libsignal-dir','e','--mode','plan']),0)
    def test_pilot_without_ack(self):
        with mock.patch.object(s,'prepare_plan',return_value=(None,{},None)):
            self.assertEqual(s.main(['--repo-root','x','--revision-root','y','--h1216-dir','a','--h1217-dir','b','--h1218-dir','c','--h1218-shadow-dir','d','--libsignal-dir','e','--mode','pilot']),2)
    def test_probe_requires_actual_gradient_code(self):
        # Las credenciales ACK no son necesarias para un probe SIN SUMO ni checkpoint.
        with mock.patch.object(s,'prepare_plan',return_value=(None,{},None)):
            with mock.patch.dict(sys.modules,{'h12_19_td':types.SimpleNamespace(
                    gradient_probe=lambda *arg,**kw:{'result':'MOCK'})}):
                self.assertEqual(s.main(['--repo-root','x','--revision-root','y','--h1216-dir','a','--h1217-dir','b','--h1218-dir','c','--h1218-shadow-dir','d','--libsignal-dir','e','--mode','probe']),0)
    def test_pilot_needs_sumo_ack(self):
        with mock.patch.object(s,'prepare_plan',return_value=(None,{},None)):
            self.assertEqual(s.main(['--repo-root','x','--revision-root','y','--h1216-dir','a','--h1217-dir','b','--h1218-dir','c','--h1218-shadow-dir','d','--libsignal-dir','e','--mode','pilot','--ack-new-checkpoint','NEW_EXPLORATORY_WEIGHTS_ONLY']),2)
    def test_unique_dirs(self):
        with tempfile.TemporaryDirectory() as t:
            a=s.result_path(t);b=s.result_path(t)
            self.assertTrue(a.exists());self.assertTrue(b.exists());self.assertNotEqual(a,b)
    def test_report_labels(self):
        plan={'libsignal':{'commit':'somecommit','blob_sha1':'abc'}}
        txt=s.report(plan,{})
        self.assertIn('No existe entrenamiento SOTA',txt)
        self.assertIn('No existe entrenamiento SOTA',s.report(plan))

# Offline mocked tensor tests run when torch is available; PyG is NOT required.
try:
    import torch
except ImportError:
    torch=None

@unittest.skipIf(torch is None,'torch not installed')
class TDMathTests(unittest.TestCase):
    def setUp(self):
        self.module=types.ModuleType('torch_geometric')
        self.data=types.ModuleType('torch_geometric.data')
        class Data:
            def __init__(self,**kw):self.__dict__.update(kw)
        class Batch:
            @classmethod
            def from_data_list(cls,examples):
                n=len(examples)
                return Data(x=torch.cat([x.x for x in examples],dim=0),
                     edge_index=torch.cat([x.edge_index+12*k for k,x in enumerate(examples)],dim=1))
        self.data.Data=Data;self.data.Batch=Batch
        self.patches=[mock.patch.dict(sys.modules,{'torch_geometric':self.module,'torch_geometric.data':self.data})]
        for patch in self.patches:patch.start();self.addCleanup(patch.stop)
        class FakeModel(torch.nn.Module):
            def __init__(self):
                super().__init__();self.fc=torch.nn.Linear(4,2)
            def forward(self,x,edge_index,train=True):
                if train:return self.fc(x)
                with torch.no_grad():return self.fc(x)
        self.model=FakeModel()
        self.target=copy.deepcopy(self.model)
        class TinyOptimizer:
            def __init__(self,model):self.model=model
            def zero_grad(self,set_to_none=True):
                for p in self.model.parameters():p.grad=None
            def step(self):
                with torch.no_grad():
                    for p in self.model.parameters():
                        if p.grad is not None:p.add_(p.grad,alpha=-.001)
        self.opt=TinyOptimizer(self.model)
        self.edge=torch.tensor([[0,1,2],[1,2,3]])
    def test_td_updates_gradients(self):
        before=copy.deepcopy(self.model.state_dict())
        stats=td.td_step(self.model,self.target,self.opt,fixture_rows()[:4],self.edge)
        self.assertGreaterEqual(stats['loss'],0)
        self.assertEqual(stats['batch_node_transitions'],48)
        self.assertTrue(any(not torch.equal(v,before[n]) for n,v in self.model.state_dict().items()))
    def test_td_blocks_malformed_tensor(self):
        rows=fixture_rows()[:4];rows[0]['obs_12x4'][0].append(0)
        with self.assertRaises(Exception):td.td_step(self.model,self.target,self.opt,rows,self.edge)
    def test_td_blocks_nan(self):
        rows=fixture_rows()[:4];rows[0]['obs_12x4'][0][0]=float('nan')
        with self.assertRaises(Exception):td.td_step(self.model,self.target,self.opt,rows,self.edge)
    def test_td_terminal_support(self):
        rows=fixture_rows()[:4]
        rows[-1]['done']=True
        result=td.td_step(self.model,self.target,self.opt,rows,self.edge)
        self.assertTrue(math.isfinite(result['loss']))
    def test_requires_parameter_delta(self):
        before={n:p.detach().clone() for n,p in self.model.named_parameters()}
        with self.assertRaises(RuntimeError):td._before_after(before,self.model)
    def test_reject_nan_weights(self):
        before={n:p.detach().clone() for n,p in self.model.named_parameters()}
        with torch.no_grad():next(self.model.parameters()).fill_(float('nan'))
        with self.assertRaises(RuntimeError):td._before_after(before,self.model)

class PlanTests(unittest.TestCase):
    """Self-contained H12.18 fixture; never depends on /mnt/data or Windows drive letters."""
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        for k in ('repo','rev','lib','h16','h17','h18'):(self.root/k).mkdir()
        self.sh=self.root/'shadow';self.m,self.r=make_shadow(self.sh)
        self.h18=self.root/'h18'
        # prepare_plan must validate the *actual* H12.18 v103 marker and loader file.
        (self.h18/'h12_18_bridge.py').write_text(
            "SCHEMA = 'H12_18_LIBSIGNAL_GRAPH_SHADOW_V103_REGISTERED_MODULE'\n",
            encoding='utf-8')
        (self.h18/'h12_18_colight_loader.py').write_text(
            '# Isolated H12.18 synthetic placeholder for mock tests\n',encoding='utf-8')
        self.a=types.SimpleNamespace(repo_root=self.root/'repo',revision_root=self.root/'rev',
                h1216_dir=self.root/'h16',h1217_dir=self.root/'h17',
                h1218_dir=self.h18,
                h1218_shadow_dir=self.sh,libsignal_dir=self.root/'lib',
                seed=101,steps=24,updates=4,batch_size=4,min_green=10.)
        self.baseline={'schema':self.m['schema'],'provenance':self.m['provenance'],
                'graph':self.m['graph'],
                'local_h1218_source_sha256':self.m['local_h1218_source_sha256']}
        self.fake_bridge=types.ModuleType('h12_18_bridge')
        self.fake_bridge.NODES=tuple(NAMES)
        self.fake_bridge.LIBSIGNAL_COMMIT=Bridge.LIBSIGNAL_COMMIT
        self.fake_bridge.NET_SHA='fake-net-sha'
        self.fake_bridge.ROUTE_SHA='fake-route-sha'
        self.fake_bridge.make_plan=lambda _: self.baseline

    def run_mock_plan(self,baseline=None):
        """Mocks only the external make_plan; exercises real H12.19 gates."""
        if baseline is None:baseline=self.baseline
        with mock.patch.dict(sys.modules,{'h12_18_bridge':self.fake_bridge}):
            with mock.patch.object(self.fake_bridge,'make_plan',return_value=baseline):
                return s.prepare_plan(self.a)

    def test_plan_good_with_mocked_anchor(self):
        result=self.run_mock_plan()
        self.assertEqual(result[1]['schema'],s.SCHEMA)
        self.assertEqual(result[1]['settings']['decision_steps'],24)
        self.assertEqual(result[1]['gates']['RL_action_applied'],'NEVER')

    def test_schema_mismatch(self):
        b=copy.deepcopy(self.baseline);b['schema']='mismatch'
        with self.assertRaises(s.GateError):self.run_mock_plan(b)

    def test_graph_mismatch(self):
        b=copy.deepcopy(self.baseline);b['graph']={'fake':True}
        with self.assertRaises(s.GateError):self.run_mock_plan(b)

    def test_steps_too_short(self):
        self.a.steps=12
        with self.assertRaises(s.GateError):self.run_mock_plan()

    def test_min_green_different(self):
        self.a.min_green=5
        with self.assertRaises(s.GateError):self.run_mock_plan()

    def test_updates_too_many(self):
        self.a.updates=300
        with self.assertRaises(s.GateError):self.run_mock_plan()

    def test_h1218_bridge_missing_rejected(self):
        (self.h18/'h12_18_bridge.py').unlink()
        with self.assertRaises(s.GateError):self.run_mock_plan()

    def test_h1218_version_marker_rejected(self):
        (self.h18/'h12_18_bridge.py').write_text('OLD_VERSION = True\n',encoding='utf-8')
        with self.assertRaises(s.GateError):self.run_mock_plan()

class CollectionMockTests(unittest.TestCase):
    def test_no_neural_actions(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as dirname:
            t=Path(dirname);h17=t/'h17';h17.mkdir()
            src=t/'h12_17_env.py';src.write_text('x=1')
            old=t/'h12_12_contract.py';old.write_text('x=2')
            h17manifest={'network':str(t/'net'), 'routes':str(t/'routes'),
                'source_sha256':{str(src):'fake'},
                'prior':{'h1212_source':str(old)}}
            plan={'base_provenance':{'h1217':{'run_dir':str(h17)}},
                  'graph':{'incoming_lanes':{n:[n+'_0'] for n in NAMES}}}
            class FakeEnv:
                latest=None
                def __init__(self,**kw):
                    self.kw=kw;self._last_counts={n+'_0':1. for n in NAMES}
                    self.observation_space=types.SimpleNamespace(contains=lambda x: True)
                    self.tls_ids=NAMES;self.events=[];self._ticks=0
                    FakeEnv.latest=self
                def reset(self,seed):return np.zeros((12,34)),{'node_order':NAMES}
                def step(self,actions):
                    self._ticks+=10
                    self._last_counts={n+'_0':float(self._ticks//10) for n in NAMES}
                    self._last_actions=actions
                    return np.zeros((12,34)),-1.,False,False,{
                        'collisions':0,'global_reward':-1.,
                        'local':{n:{'queue':2.,'effective_stage':0} for n in NAMES}}
                def close(self):self.closed=True
            mod1=types.ModuleType('h12_17_env');mod1.MultiTLSHomologado=FakeEnv
            mod2=types.ModuleType('h12_17_multi_tls')
            mod2.validate_events=lambda *arg,**kw:{'n_yellow_entries':12}
            a=types.SimpleNamespace(seed=101,steps=24,min_green=10.,binary='sumo')
            with mock.patch.dict(sys.modules,{'h12_17_env':mod1,'h12_17_multi_tls':mod2}),mock.patch.object(s,'load_json',return_value=h17manifest):
                data,ev,ticks=s.collect_transitions(plan,Bridge,a,t)
            self.assertEqual(len(data),24)
            self.assertEqual(ticks,240)
            self.assertTrue(FakeEnv.latest.closed)
            self.assertEqual(data[0]['requested_actions'],[(i%2) for i in range(12)])
            self.assertEqual(data[0]['reward_per_node'],[-24.]*12)
            self.assertTrue(data[-1]['done'])
            self.assertEqual(s.audit_transitions(data,NAMES)['node_transitions'],288)

if __name__ == '__main__':
    unittest.main()
