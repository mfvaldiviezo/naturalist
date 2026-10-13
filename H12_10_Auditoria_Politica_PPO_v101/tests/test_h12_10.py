import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]/'h12_10_politica.py'
spec=importlib.util.spec_from_file_location('h12_10',SRC)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fake_doc(mode='nominal',a=0.0):
    def state(i):
        x=[0.0]*34;x[28]=1.;x[32]=min(i/100,1.);x[33]=x[32]
        if mode=='active' and i in range(21,60): x[0]=0.1
        return x
    acts=[dict(i=i,sim_time_s=(i+1)*5.,action=0, state_before_34d=state(i),state_after_34d=state(i+1)) for i in range(60)]
    return {'result':'SMOKE_OK','mode':mode,'model':'ppo_ideal',
        'checkpoint_sha256':'a'*64,'h10_reference_path':'frozen','h10_reference_n':300,'h10_source_sha256':{'h1':'a'},
        'n_decisions':60,'n_microticks':600,'end_time_s':300.,
        'decisions':acts,'microticks':[{'collisions':0,'teleports_start':0} for _ in range(600)],
        'h12_7_diagnostic':{'b1_microticks':[{} for _ in range(600)],
            'green_phases':[0,2],'controlled_lanes_used_12':['a']*12,'outgoing_lanes':[]},
        'inputs':{'net_sha256':'a','routes_sha256':'b','cfg_original_sha256':'c'},
        'trace_sha256':'active' if mode=='active' else 'nominal',
        'commands':100 if mode=='active' else 0,
        'extra':{'vine':{'n_commands':100,'n_commands_confirmed':100,'remaining_pending':0}}}


def outputs(docs):
    ans={}
    for mode,doc in docs.items():
        arr=[]
        for i in range(60):
            p=[.65,.1,.15,.1]
            if mode=='active' and i>=21:p=[.64,.11,.15,.1]
            arr.append({'p':p,'action':0})
        ans[mode]=arr
    return ans

class TestH1210(unittest.TestCase):
    def setUp(self):
        self.docs={name:fake_doc(name) for name in ('nominal','probe','active')}
    def test_pair_valid(self):self.assertTrue(m.check_pair(self.docs))
    def test_pair_wrong_checkpoint(self):
        self.docs['active']['checkpoint_sha256']='b'*64
        with self.assertRaises(ValueError):m.check_pair(self.docs)
    def test_pair_wrong_demand(self):
        self.docs['active']['inputs']['routes_sha256']='changed'
        with self.assertRaises(ValueError):m.check_pair(self.docs)
    def test_pair_probe_not_identical(self):
        self.docs['probe']['trace_sha256']='changed'
        with self.assertRaises(ValueError):m.check_pair(self.docs)
    def test_pair_invalid_commands(self):
        self.docs['active']['extra']['vine']['remaining_pending']=1
        with self.assertRaises(ValueError):m.check_pair(self.docs)
    def test_pair_different_lanes(self):
        self.docs['active']['h12_7_diagnostic']['controlled_lanes_used_12']=['b']*12
        with self.assertRaises(ValueError):m.check_pair(self.docs)
    def test_pair_probe_observation_different(self):
        self.docs['probe']['decisions'][9]['state_before_34d'][0]=.1
        with self.assertRaises(ValueError):m.check_pair(self.docs)
    def test_unclipped_phase_age_is_kept_exactly(self):
        x=[0.0]*34;x[28]=1.0;x[32]=2.45;x[33]=1.0
        self.assertEqual(m.obs34(x)[32],2.45)
        self.assertEqual(m.obs34(x)[33],1.0)

    def test_box_mismatch_does_not_change_checkpoint_inputs(self):
        for doc in self.docs.values():
            for i,d in enumerate(doc['decisions']):
                age=min(i*5/120,2.5)
                d['state_before_34d'][32]=age
                d['state_before_34d'][33]=min(age,1)
                age_next=min((i+1)*5/120,2.5)
                d['state_after_34d'][32]=age_next
                d['state_after_34d'][33]=min(age_next,1)
        self.assertTrue(m.check_pair(self.docs))
        summary=m.summarize(self.docs,outputs(self.docs),'a'*64)
        self.assertGreater(summary['observation_box_mismatch']['nominal']['n_decisions_with_age_raw_gt_one'],0)
        self.assertIn('Discordancia de rango',m.markdown(summary))

    def test_reject_unclipped_age_beyond_300_seconds(self):
        x=[0.0]*34;x[32]=2.51;x[33]=1.0
        with self.assertRaises(ValueError):m.obs34(x)

    def test_reject_inconsistent_phase_age_copy(self):
        x=[0.0]*34;x[32]=1.4;x[33]=.4
        with self.assertRaises(ValueError):m.obs34(x)

    def test_reject_other_feature_out_of_box(self):
        x=[0.0]*34;x[12]=1.4
        with self.assertRaises(ValueError):m.obs34(x)

    def test_reject_unclipped_age_negative(self):
        x=[0.0]*34;x[32]=-.05
        with self.assertRaises(ValueError):m.obs34(x)

    def test_reject_nonfinite_age(self):
        x=[0.0]*34;x[32]=float('inf')
        with self.assertRaises(ValueError):m.obs34(x)

    def test_probability_valid(self):
        self.assertEqual(m.validate_probs([.25]*4),[.25]*4)
    def test_probability_not_normalized(self):
        with self.assertRaises(ValueError):m.validate_probs([.1]*4)
    def test_probability_nonfinite(self):
        with self.assertRaises(ValueError):m.validate_probs([.1,.1,float('nan'),.8])
    def test_tv_symmetry(self):
        p=[.7,.1,.1,.1];q=[.6,.2,.1,.1]
        self.assertAlmostEqual(m.total_variation(p,q),.1)
        self.assertAlmostEqual(m.total_variation(p,q),m.total_variation(q,p))
    def test_js_zero_identical(self):self.assertAlmostEqual(m.js_divergence([.25]*4,[.25]*4),0.)
    def test_js_positive(self):self.assertGreater(m.js_divergence([.7,.1,.1,.1],[.6,.2,.1,.1]),0)
    def test_phase_alias(self):
        z=m.phase_map([0,2]);self.assertEqual(z,{0:0,1:2,2:0,3:2})
        self.assertEqual(m.phase_probabilities([.6,.1,.2,.1],z),{'0':.8,'2':.2})
    def test_summary_sensitive_with_identical_actions(self):
        report=m.summarize(self.docs,outputs(self.docs),'a'*64)
        self.assertEqual(report['states_different'],39)
        self.assertEqual(report['actions_different'],0)
        self.assertEqual(report['policy_probs_different_among_changed_states'],39)
        self.assertAlmostEqual(report['max_total_variation'],.01)
        self.assertEqual(report['unique_phases'],2)
        self.assertIn('H12_10_POLITICA_OFFLINE_OK',m.markdown(report))
    def test_summary_rejects_mismatch_recorded_actions(self):
        o=outputs(self.docs);o['active'][5]['action']=2
        with self.assertRaises(ValueError):m.summarize(self.docs,o,'a'*64)
    def test_summary_rejects_probe_change(self):
        o=outputs(self.docs);o['probe'][3]['p']=[.6,.15,.15,.1]
        with self.assertRaises(ValueError):m.summarize(self.docs,o,'a'*64)
    def test_plan_does_not_import_model_or_launch_sumo(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runs=root/'previous';runs.mkdir()
            repo=root/'repository';models=repo/'tsc_framework'/'outputs'/'models';models.mkdir(parents=True)
            ck=models/'ppo_ideal.zip';ck.write_bytes(b'fixture only')
            checksum=m.sha256(ck)
            for mode,doc in self.docs.items():
                folder=runs/mode;folder.mkdir()
                doc['checkpoint_sha256']=checksum
                (folder/'piloto_h12_5.json').write_text(json.dumps(doc),encoding='utf-8')
            class Args:
                h129_dir=runs; repo_root=repo; mode='plan'; results_root=root
            self.assertEqual(m.execute(Args()),0)
            self.assertEqual(sorted(x.name for x in root.iterdir()),['previous','repository'])
    def test_distribution_extraction_with_mock_policy(self):
        try:
            import numpy as np
            import torch
        except ImportError:
            self.skipTest('numpy/torch no disponibles para mock')
        class Policy:
            def obs_to_tensor(self,obs):return torch.as_tensor(obs,dtype=torch.float32).reshape(1,34),False
            def get_distribution(self,tensor):
                class Inner:
                    probs=torch.tensor([[.7,.1,.1,.1]])
                class Wrapper:
                    distribution=Inner()
                return Wrapper()
        class Model:
            policy=Policy()
            def predict(self,state,deterministic):return np.array(0),None
        out=m.infer_probabilities(Model(),[[0.0]*34])
        self.assertAlmostEqual(out[0]['p'][0],.7,places=6)
        self.assertEqual(out[0]['action'],0)
    def test_read_run_ok(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'nominal';path.mkdir()
            (path/'piloto_h12_5.json').write_text(json.dumps(self.docs['nominal']),encoding='utf-8')
            self.assertEqual(m.read_run(d,'nominal')['model'],'ppo_ideal')
    def test_read_run_reject_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'nominal';path.mkdir()
            doc=self.docs['nominal'];doc['decisions'].pop()
            (path/'piloto_h12_5.json').write_text(json.dumps(doc),encoding='utf-8')
            with self.assertRaises(ValueError):m.read_run(d,'nominal')
    def test_read_run_reject_crash(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'nominal';path.mkdir()
            doc=self.docs['nominal'];doc['microticks'][40]['collisions']=1
            (path/'piloto_h12_5.json').write_text(json.dumps(doc),encoding='utf-8')
            with self.assertRaises(ValueError):m.read_run(d,'nominal')

if __name__=='__main__':unittest.main()
