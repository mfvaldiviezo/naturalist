import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

P=Path(__file__).resolve().parents[1]/'h12_11_proveniencia.py'
spec=importlib.util.spec_from_file_location('h1211',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestAudit(unittest.TestCase):
    def test_missing_checkpoint(self):
        with tempfile.TemporaryDirectory() as x:self.assertFalse(m.sb3_metadata(Path(x)/'none.zip')['available'])
    def test_checkpoint_metadata(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/'x.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('data',json.dumps({'num_timesteps':20480,'n_envs':4,'seed':101}))
            x=m.sb3_metadata(p)
            self.assertEqual(x['num_timesteps'],20480);self.assertEqual(x['n_envs'],4)
    def test_corrupted_checkpoint(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/'x.zip';p.write_text('bad')
            with self.assertRaises(zipfile.BadZipFile):m.sb3_metadata(p)
    def test_json_duplicate_checkpoint(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/'x.zip'
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with zipfile.ZipFile(p,'w') as z:
                    z.writestr('data','{}');z.writestr('data','{}')
            with self.assertRaisesRegex(ValueError,'duplicadas'):m.sb3_metadata(p)
    def test_no_pickle_execution(self):
        import inspect
        src=inspect.getsource(m.sb3_metadata)
        self.assertNotIn('pickle.loads',src)
        self.assertNotIn('PPO.load',src)
        self.assertIn("z.read('data')",src)
    def test_age_semantics(self):
        source='def _get_state(self):\n  phase_age_s=1\n  tau_norm=2\n  x=phase_age_s / self.cfg.MAX_PHASE_AGE\n'
        self.assertTrue(m.locate_features(source)['state_age_first_unclipped'])
    def test_training_script_detection(self):
        txt='def make_env():\n  env_config = {"seed": 2}\n  env = TSCEnv(**env_config)\n  x = \'<random value="true"/>\'\ndef main():\n  route_files=sorted(route_dir.glob("*.rou.xml"))\n'
        q=m.locate_training(txt)
        self.assertTrue(q['training_does_not_pass_reward_weights'])
        self.assertTrue(q['training_program_constructs_TSCEnv'])
    def test_int(self):
        self.assertIsNone(m.as_int(True));self.assertIsNone(m.as_int('3.4'))
        self.assertEqual(m.as_int('100'),100)
    def test_provenance_false(self):
        d={'status':'H12_11_PROVENIENCIA_DIAGNOSTICADA','checkpoints':{},'policy_summary':{},'env':{'flags':{}},'training':{'flags':{}},'unproven':[],'coop_ideal_to_ideal_timesteps_ratio':None,'entropy_fraction_max_nominal':.9}
        self.assertIn('NO certificacion',m.markdown({**d,'checkpoints':{},'policy_summary':{'states_different':39,'policy_probs_different_among_changed_states':39,'actions_different':0,'max_total_variation':.01,'mean_total_variation_on_changed_states':.001,'mean_entropy_nominal_nats':1.33}}))
    def test_no_side_effect_static(self):
        import inspect
        src=inspect.getsource(m.load_audits)
        self.assertNotIn('subprocess',src)
        self.assertNotIn('importlib',src)
    def test_requires_complete_traces(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            (p/'tsc_framework/src/core').mkdir(parents=True)
            (p/'tsc_framework/scripts').mkdir(parents=True)
            (p/'tsc_framework/src/core/tsc_env.py').write_text('def x(): pass')
            (p/'tsc_framework/scripts/train.py').write_text('def x(): pass')
            with self.assertRaises(FileNotFoundError):m.load_audits(p,p,p)

if __name__=='__main__':unittest.main()

class TestFullFlow(unittest.TestCase):
    def fixture(self, base):
        base=Path(base);repo=base/'repo';h129=base/'h129';h1210=base/'h1210'
        env=repo/'tsc_framework/src/core/tsc_env.py';env.parent.mkdir(parents=True)
        env.write_text('''class TSCEnv:
 def _get_state(self):
  phase_age_s=1
  tau_norm=2
  return phase_age_s / self.cfg.MAX_PHASE_AGE
''',encoding='utf-8')
        train=repo/'tsc_framework/scripts/train.py';train.parent.mkdir(parents=True)
        train.write_text('def make_env():\n  env_config={}\n  env=TSCEnv(**env_config)\n',encoding='utf-8')
        models=repo/'tsc_framework/outputs/models';models.mkdir(parents=True)
        shas={}
        for name,t in zip(m.MODELS,[20480,20480,1007616,1007616]):
            f=models/(name+'.zip')
            with zipfile.ZipFile(f,'w') as z:z.writestr('data',json.dumps({'num_timesteps':t,'n_envs':1}))
            shas[name]=m.digest(f)
        for mode in ('nominal','probe','active'):
            p=h129/mode;p.mkdir(parents=True)
            (p/'piloto_h12_5.json').write_text(json.dumps({'model':'ppo_ideal','n_decisions':60,'n_microticks':600,'trace_sha256':'different' if mode=='active' else 'same','checkpoint_sha256':shas['ppo_ideal']}))
        h1210.mkdir()
        policy={'status':'H12_10_POLITICA_OFFLINE_OK','model':'ppo_ideal','checkpoint_sha256':shas['ppo_ideal'],
                'states_different':39,'decisions':60,'policy_probs_different_among_changed_states':39,'actions_different':0,
                'max_total_variation':.005,'mean_total_variation_on_changed_states':.001,
                'mean_entropy_nominal_nats':1.33,'mean_entropy_active_nats':1.33,
                'min_argmax_margin_nominal':.003,'min_argmax_margin_active':.003,
                'observation_box_mismatch':{},'action_to_physical_phase':{'0':0,'1':2,'2':0,'3':2}}
        (h1210/'dictamen_h12_10.json').write_text(json.dumps(policy))
        return repo,h129,h1210

    def test_full_h1211(self):
        with tempfile.TemporaryDirectory() as t:
            repo,h129,h1210=self.fixture(t)
            r=m.build(repo,h129,h1210)
            self.assertEqual(r['status'],'H12_11_PROVENIENCIA_DIAGNOSTICADA')
            self.assertFalse(r['checkpoint_training_certified'])
            self.assertAlmostEqual(r['coop_ideal_to_ideal_timesteps_ratio'],49.2)
            self.assertIn('NO certificacion',m.markdown(r))

    def test_fail_sha_mismatch(self):
        with tempfile.TemporaryDirectory() as t:
            repo,h129,h1210=self.fixture(t)
            p=h129/'nominal/piloto_h12_5.json';a=json.loads(p.read_text());a['checkpoint_sha256']='0'*64;p.write_text(json.dumps(a))
            with self.assertRaises(ValueError):m.build(repo,h129,h1210)

    def test_plan_does_not_create_report(self):
        with tempfile.TemporaryDirectory() as t:
            repo,h129,h1210=self.fixture(t)
            root=Path(t)/'results';root.mkdir()
            rc=m.main(['--repo-root',str(repo),'--h129-dir',str(h129),'--h1210-dir',str(h1210),'--mode','plan','--results-root',str(root)])
            self.assertEqual(rc,0)
            self.assertEqual(list(root.iterdir()),[])

    def test_analyze_creates_report_only(self):
        with tempfile.TemporaryDirectory() as t:
            repo,h129,h1210=self.fixture(t)
            root=Path(t)/'results';root.mkdir()
            rc=m.main(['--repo-root',str(repo),'--h129-dir',str(h129),'--h1210-dir',str(h1210),'--mode','analyze','--results-root',str(root)])
            self.assertEqual(rc,0)
            out=list(root.iterdir());self.assertEqual(len(out),1)
            self.assertIn('H12_11_PROVENIENCIA_DIAGNOSTICADA',(out[0]/'dictamen_h12_11.json').read_text())
            self.assertIn('NO certificacion',(out[0]/'dictamen_h12_11.md').read_text())
