import contextlib
import io
import json
import sys
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
H1212=ROOT.parent/'H12_12_Entorno_Homologado_B1_v100'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(H1212))
from h12_12_contract import read_geometry
import h12_15_baselines as cli
from h12_15_politicas import (build_projection,PhysicalAdapterError,score_directions,
                               maxpressure_action,fixed_action)


def geometry_xml():
    return '''<net><tlLogic id="B1" type="actuated" programID="0">
    <phase duration="42" state="GrGr"/><phase duration="3" state="yryr"/>
    <phase duration="42" state="rGrG"/><phase duration="3" state="ryry"/>
    </tlLogic>
    <connection tl="B1" from="B2B1" fromLane="0" to="B1B0" toLane="0" linkIndex="0"/>
    <connection tl="B1" from="C1B1" fromLane="0" to="B1A1" toLane="0" linkIndex="1"/>
    <connection tl="B1" from="B0B1" fromLane="0" to="B1B2" toLane="0" linkIndex="2"/>
    <connection tl="B1" from="A1B1" fromLane="0" to="B1C1" toLane="0" linkIndex="3"/>
    </net>'''


def fake_signal():
    return {'hangzhou':{
        'phase_pairs':[['S-S','N-N'],['S-E','N-W'],['S-S','S-E'],['N-N','N-W'],
                       ['W-W','E-E'],['W-S','E-N'],['E-E','E-N'],['W-W','W-S']],
        'B1':{'lane_sets':{'S-S':['B2B1_0'],'N-N':['B0B1_0'],
                           'W-W':['C1B1_0'],'E-E':['A1B1_0']},
              'downstream':{'S':'B0','N':'B2','W':'A1','E':'C1'},
              'fixed_timings':[4,2,4,2,4,2,4,2]},
        'B0':{'lane_sets':{'S-S':['B1B0_0']}},
        'B2':{'lane_sets':{'N-N':['B1B2_0']}},
        'A1':{'lane_sets':{'W-W':['B1A1_0']}},
        'C1':{'lane_sets':{'E-E':['B1C1_0']}},
    }}


class TestPhysicalB1(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.net=Path(self.t.name)/'network.net.xml';self.net.write_text(geometry_xml(),encoding='utf8')
        self.geometry=read_geometry(self.net,'B1');self.cfg=fake_signal()
        self.p=build_projection(self.geometry,self.net,self.cfg)

    def test_two_actions(self):self.assertEqual(len(self.p.physical_green_phases),2)
    def test_actions_original_indices(self):self.assertEqual(self.p.original_resco_pair_indices,(0,4))
    def test_original_eight_pairs(self):self.assertEqual(self.p.original_resco_action_count,8)
    def test_two_inbound_each(self):self.assertEqual([len(x) for x in self.p.grouped_inbound],[2,2])
    def test_original_fixed_eight(self):self.assertEqual(len(self.p.original_resco_fixed_timings),8)
    def test_target_green_42(self):self.assertEqual(self.p.fixed_target_green_s,42.)
    def test_label_not_certified(self):self.assertIn('NOT original',self.p.document()['identity'])
    def test_pair_change_blocked(self):
        self.cfg['hangzhou']['phase_pairs'][0]=['S-S','S-E']
        with self.assertRaises(PhysicalAdapterError):build_projection(self.geometry,self.net,self.cfg)
    def test_green0_without_lane_blocked(self):
        self.cfg['hangzhou']['B1']['lane_sets']['N-N']=[]
        with self.assertRaises(PhysicalAdapterError):build_projection(self.geometry,self.net,self.cfg)
    def test_wrong_outgoing_neighbor(self):
        del self.cfg['hangzhou']['B2']
        with self.assertRaises(PhysicalAdapterError):build_projection(self.geometry,self.net,self.cfg)
    def test_wrong_fixed_timings(self):
        self.cfg['hangzhou']['B1']['fixed_timings']=[4,2]
        with self.assertRaises(PhysicalAdapterError):build_projection(self.geometry,self.net,self.cfg)
    def test_missing_signal_hangzhou(self):
        with self.assertRaises(PhysicalAdapterError):build_projection(self.geometry,self.net,{'grid':{}})
    def test_group_lanes_expected(self):
        self.assertEqual(set(self.p.grouped_inbound[0]),{'B2B1_0','B0B1_0'})
        self.assertEqual(set(self.p.grouped_inbound[1]),{'C1B1_0','A1B1_0'})
    def test_outgoing_expected(self):
        outs={d.name:d.downstream for group in self.p.directions for d in group}
        self.assertEqual(outs['S-S'],('B1B0_0',))
        self.assertEqual(outs['N-N'],('B1B2_0',))
        self.assertEqual(outs['W-W'],('B1A1_0',))
        self.assertEqual(outs['E-E'],('B1C1_0',))
    def halts(self):
        return {'B2B1_0':5,'B0B1_0':3,'C1B1_0':1,'A1B1_0':1,
                'B1B0_0':2,'B1B2_0':1,'B1A1_0':1,'B1C1_0':2}
    def test_tls_sequence_yellow_3s(self):
        ev=[{'event':'online_initialization','stage':0,'state':'GrGr','kind':'green','t_s':0.},
            {'event':'enter_stage','stage':1,'state':'yryr','kind':'yellow','t_s':45.},
            {'event':'enter_stage','stage':2,'state':'rGrG','kind':'green','t_s':48.},
            {'event':'enter_stage','stage':3,'state':'ryry','kind':'yellow','t_s':95.},
            {'event':'enter_stage','stage':0,'state':'GrGr','kind':'green','t_s':98.}]
        self.assertEqual(cli.audit_tls_events(ev,self.geometry,10)['verified_yellow_clearances'],2)
    def test_tls_no_direct_green_skip(self):
        ev=[{'event':'online_initialization','stage':0,'state':'GrGr','kind':'green','t_s':0.},
            {'event':'enter_stage','stage':2,'state':'rGrG','kind':'green','t_s':45.}]
        with self.assertRaises(PhysicalAdapterError):cli.audit_tls_events(ev,self.geometry,10)
    def test_tls_no_short_amber(self):
        ev=[{'event':'online_initialization','stage':0,'state':'GrGr','kind':'green','t_s':0.},
            {'event':'enter_stage','stage':1,'state':'yryr','kind':'yellow','t_s':45.},
            {'event':'enter_stage','stage':2,'state':'rGrG','kind':'green','t_s':46.}]
        with self.assertRaises(PhysicalAdapterError):cli.audit_tls_events(ev,self.geometry,10)
    def test_tls_no_short_green(self):
        ev=[{'event':'online_initialization','stage':0,'state':'GrGr','kind':'green','t_s':0.},
            {'event':'enter_stage','stage':1,'state':'yryr','kind':'yellow','t_s':3.}]
        with self.assertRaises(PhysicalAdapterError):cli.audit_tls_events(ev,self.geometry,10)
    def test_tls_bad_green_state(self):
        ev=[{'event':'online_initialization','stage':0,'state':'rrrr','kind':'green','t_s':0.}]
        with self.assertRaises(PhysicalAdapterError):cli.audit_tls_events(ev,self.geometry,10)
    def test_pressure_numeric(self):self.assertEqual(score_directions(self.p,self.halts()),(5.0,-1.0))
    def test_pressure_choice_0(self):self.assertEqual(maxpressure_action(self.p,self.halts())[0],0)
    def test_pressure_choice_1(self):
        q=self.halts();q['C1B1_0']=12
        self.assertEqual(maxpressure_action(self.p,q)[0],1)
    def test_pressure_tie_first(self):
        q={k:0 for k in self.halts()}
        self.assertEqual(maxpressure_action(self.p,q)[0],0)
    def test_negative_queued_rejected(self):
        q=self.halts();q['B2B1_0']=-1
        with self.assertRaises(PhysicalAdapterError):score_directions(self.p,q)
    def test_missing_queued_rejected(self):
        q=self.halts();del q['B1B0_0']
        with self.assertRaises(PhysicalAdapterError):score_directions(self.p,q)
    def test_nan_queued_rejected(self):
        q=self.halts();q['B1B0_0']=float('nan')
        with self.assertRaises(PhysicalAdapterError):score_directions(self.p,q)
    def scheduler(self,phase=0,age=0,path=None):
        return types.SimpleNamespace(green_phase=phase,green_elapsed=age,path=list(path or []))
    def test_fixed_stay_initial(self):self.assertEqual(fixed_action(self.p,self.scheduler(age=10)),0)
    def test_fixed_switch_at_42(self):self.assertEqual(fixed_action(self.p,self.scheduler(age=42)),1)
    def test_fixed_switch_back(self):self.assertEqual(fixed_action(self.p,self.scheduler(phase=2,age=42)),0)
    def test_fixed_intergreen_continue(self):self.assertEqual(fixed_action(self.p,self.scheduler(phase=0,age=1,path=[2])),1)
    def test_fixed_invalid_scheduler(self):
        with self.assertRaises(PhysicalAdapterError):fixed_action(self.p,None)
    def test_fixed_bad_phase(self):
        with self.assertRaises(PhysicalAdapterError):fixed_action(self.p,self.scheduler(phase=5))
    def test_public_manifest(self):
        b={'geometry':self.geometry,'physical_projection':self.p,'schema':cli.SCHEMA}
        m=cli.public_manifest(b)
        self.assertNotIn('geometry',m)
        self.assertIn('NOT original',m['projection']['identity'])
    def test_sha_bytes_change(self):
        before=cli.sha(self.net);self.net.write_text(self.net.read_text()+'\n')
        self.assertNotEqual(before,cli.sha(self.net))
    def test_json_new_exclusive(self):
        p=Path(self.t.name)/'a.json';cli.jsonnew(p,{'a':1})
        with self.assertRaises(PhysicalAdapterError):cli.jsonnew(p,{'a':2})
    def test_markdown_gated_claims(self):
        m={'projection':self.p.document()}
        stub={'n_decisions':12,'n_microticks':120,'n_intergreen_entries':2,
              'collision_events':0,'sum_rewards':-2.3,'mean_queued':1.2,'mean_wait_total_s':2.0}
        text=cli.markdown(m,[stub,stub]);self.assertIn('NO reproducción integral',text)
    def test_unique_dir_never_overwrite(self):
        rev=Path(self.t.name);a=cli.temp_new_dir(rev);b=cli.temp_new_dir(rev)
        self.assertNotEqual(a,b)
    def test_pressure_snapshot_integration(self):
        q=self.halts()
        lane=types.SimpleNamespace(getIDList=lambda:list(q),getLastStepHaltingNumber=lambda k:q[k])
        conn=types.SimpleNamespace(lane=lane)
        idx,values,reading=cli.snapshot_pressure(conn,self.p)
        self.assertEqual(idx,0);self.assertEqual(values,(5.,-1.))
        self.assertEqual(reading['B2B1_0'],5.)
    def test_pressure_missing_lane_fail_closed(self):
        q=self.halts();del q['B1B0_0']
        lane=types.SimpleNamespace(getIDList=lambda:list(q),getLastStepHaltingNumber=lambda k:q[k])
        conn=types.SimpleNamespace(lane=lane)
        with self.assertRaises(PhysicalAdapterError):cli.snapshot_pressure(conn,self.p)
    def test_run_one_mocked_traCI(self):
        import numpy as np
        s=self.scheduler();s.stage=0
        class FakeEnv:
            def __init__(self,**kw):
                self.steps=kw['max_rl_steps'];self.i=0;self.scheduler=s
                self.events=[{'t_s':0,'kind':'green','stage':0,'state':'GrGr','event':'online_initialization'}]
                self.observation_space=types.SimpleNamespace(contains=lambda obs:len(obs)==34)
                q=self_halts
                self.conn=types.SimpleNamespace(lane=types.SimpleNamespace(getIDList=lambda:list(q),getLastStepHaltingNumber=lambda k:q[k]))
            def reset(self,seed=None):return np.zeros(34,dtype=np.float32),{}
            def step(self,action):
                self.i+=1;self.scheduler.green_elapsed+=5.0
                return np.zeros(34,dtype=np.float32),0.,False,self.i==self.steps,{
                    'sim_time_s':self.i*5.,'stage':0,'stage_kind':'green',
                    'inbound_vehicle_count':1,'total_queue':0,'wait_total_s':0,
                    'colliding_vehicles_tick_sum':0,'transition_entries':0}
            def close(self):pass
        self_halts=self.halts()
        b={'network':str(self.net),'routes':str(self.net),'seed':101,
           'rl_steps':2,'min_green_s':10.,'binary':'sumo','physical_projection':self.p,'geometry':self.geometry}
        with patch.dict(sys.modules,{'h12_12_env':types.SimpleNamespace(TSCEnvHomologado=FakeEnv)}):
            out=Path(self.t.name)/'fake';out.mkdir()
            r=cli.run_one(b,'maxpressure_resco_projected_b1',out)
        self.assertEqual(r['n_decisions'],2)
        self.assertTrue((out/'maxpressure_resco_projected_b1/pilot.json').is_file())


if __name__=='__main__':unittest.main()

class TestH1215Preflight(unittest.TestCase):
    def setUp(self):
        import shutil
        import yaml
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.tmp=Path(self.t.name)
        self.repo=self.tmp/'traffic_project';self.rev=self.tmp/'revision';self.rev.mkdir()
        self.net=self.repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
        self.route=self.repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
        self.net.parent.mkdir(parents=True);self.route.parent.mkdir(parents=True)
        self.net.write_text(geometry_xml(),encoding='utf8');self.route.write_text('<routes/>',encoding='utf8')
        self.h1212=self.rev/'H12_12_Entorno_Homologado_B1_v100';self.h1212.mkdir()
        self.h1212_files=[]
        for n in ('h12_12_contract.py','h12_12_env.py','h12_12_homologar.py'):
            dest=self.h1212/n;shutil.copyfile(H1212/n,dest);self.h1212_files.append(dest)
        self.smoke=self.rev/'resultados/h12_12_mock';self.smoke.mkdir(parents=True)
        srcs={str(p.resolve()):cli.sha(p) for p in [self.net,self.route,*self.h1212_files]}
        manifest={'schema':'H12_12_B1_GREEN2_OBS34_V100',
                  'network':str(self.net.resolve()),'routes':str(self.route.resolve()),
                  'sources_sha256':srcs}
        mp=self.smoke/'manifiesto_h12_12.json';mp.write_text(json.dumps(manifest),encoding='utf8')
        self.smoker=self.smoke/'smoke_h12_12.json'
        self.smoker.write_text(json.dumps({'result':'H12_12_SUMO_SMOKE_OK',
            'manifest_sha256':cli.sha(mp),'steps':12,'microticks':120}),encoding='utf8')
        (self.smoke/'runtime_h12_12.json').write_text(json.dumps({'sumo_version':['SUMO 1.26']}),encoding='utf8')
        self.base=self.repo/'baselines/RESCO/resco_benchmark'
        (self.base/'config').mkdir(parents=True)
        self.signal=self.base/'config/signal.yaml'
        self.signal.write_text(yaml.safe_dump(fake_signal()),encoding='utf8')
        other=[]
        for n in ('agents/static/maxpressure.py','agents/static/maxwave.py','agents/static/fixed.py',
                  'mdp_options/states.py','traffic_signal.py'):
            p=self.base/n;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text('class Placeholder: pass\n',encoding='utf8');other.append(p)
        self.aud=self.rev/'resultados/h12_14_mock';self.aud.mkdir()
        aud_doc={'result':'H12_14_SOTA_AUDIT_OK','gates':{
          'source_code_and_yaml':'PASSED','h1212_physical_contract':'PASSED',
          'resco_hangzhou_network_identity':'PASSED','resco_hangzhou_routes_identity':'PASSED'},
          'H1212':{'smoke_sha256':cli.sha(self.smoker)},
          'resco_reference_inputs':{'net_byte_identical_to_H1212':True,
                                    'route_byte_identical_to_H1212':True},
          'source_sha256':{str(p.resolve()):cli.sha(p) for p in [self.net,self.route,*other]}}
        self.audit_file=self.aud/'dictamen_h12_14.json'
        self.audit_file.write_text(json.dumps(aud_doc),encoding='utf8')
        self.args=types.SimpleNamespace(repo_root=self.repo,revision_root=self.rev,
                  smoke_dir=self.smoke,h1214_dir=self.aud,seed=101,rl_steps=12,
                  min_green=10.,binary='sumo')
        self.nn=patch.object(cli,'EXPECTED_NET',cli.sha(self.net));self.nn.start();self.addCleanup(self.nn.stop)
        self.rr=patch.object(cli,'EXPECTED_ROUTE',cli.sha(self.route));self.rr.start();self.addCleanup(self.rr.stop)

    def test_preflight_valid_manifest(self):
        b=cli.validate(self.args)
        self.assertEqual(b['physical_projection'].original_resco_pair_indices,(0,4))
    def test_preflight_no_results(self):
        argv=['--repo-root',str(self.repo),'--revision-root',str(self.rev),
              '--smoke-dir',str(self.smoke),'--h1214-dir',str(self.aud),'--mode','plan']
        with contextlib.redirect_stdout(io.StringIO()) as buf:res=cli.main(argv)
        self.assertEqual(res,0)
        self.assertIn('H12_15_PLAN_OK',buf.getvalue())
        self.assertFalse(list((self.rev/'resultados').glob('h12_15_baselines_b1_*')))
    def test_preflight_wrong_smoke_sha(self):
        doc=json.loads(self.smoker.read_text());doc['manifest_sha256']='bad'
        self.smoker.write_text(json.dumps(doc),encoding='utf8')
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
    def test_preflight_wrong_h1214_smoke(self):
        doc=json.loads(self.audit_file.read_text());doc['H1212']['smoke_sha256']='bad'
        self.audit_file.write_text(json.dumps(doc),encoding='utf8')
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
    def test_preflight_one_gate_blocked(self):
        doc=json.loads(self.audit_file.read_text());doc['gates']['resco_hangzhou_routes_identity']='NO'
        self.audit_file.write_text(json.dumps(doc),encoding='utf8')
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
    def test_preflight_wrong_source(self):
        p=self.base/'agents/static/maxpressure.py';p.write_text('# changed')
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
    def test_preflight_wrong_h1212_source(self):
        p=self.h1212/'h12_12_env.py';p.write_text('# changed')
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
    def test_preflight_wrong_signal_map(self):
        self.signal.write_text('hangzhou:\n  phase_pairs: []\n')
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
    def test_preflight_wrong_route(self):
        self.route.write_text('<routes><v/></routes>')
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
    def test_preflight_unknown_h1214_result(self):
        doc=json.loads(self.audit_file.read_text());doc['result']='UNAPPROVED'
        self.audit_file.write_text(json.dumps(doc),encoding='utf8')
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
    def test_preflight_no_readonly_override(self):
        self.args.rl_steps=800
        with self.assertRaises(PhysicalAdapterError):cli.validate(self.args)
