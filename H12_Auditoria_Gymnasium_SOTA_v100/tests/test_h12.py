from pathlib import Path
import tempfile
import unittest
import json
import zipfile
import importlib.util

MODULE=Path(__file__).resolve().parents[1]/'h12_auditar.py'
spec=importlib.util.spec_from_file_location('h12_auditar',MODULE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestAudit(unittest.TestCase):
    def test_git_blob_text_sha_normalizes_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.txt';p.write_bytes(b'a\r\nb\r\n')
            actual=m.git_blob_text_sha(p)
            import hashlib
            blob=b'a\nb\n'
            expected=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
            self.assertEqual(actual,expected)
    def test_static_co_light_and_hard_stop(self):
        src={'tsc_framework/scripts/run_evaluation.py':'class FixedAgent: pass\nclass MaxPressureAgent: pass\nclass CoLightAgent:\n q = np.sum(q[0:3]); att=np.exp(q)\n',
             'tsc_framework/src/core/latam_chaos_manager.py':'traci.vehicle.setSpeed(v_id, 0.0)',
             'tsc_framework/src/core/tsc_env.py':'class TSCEnv(gym.Env):\n for _ in range(self.delta_t):\n  traci.simulationStep()\n self.chaos_manager.step()\n return obs, reward, terminated, truncated, info',
             'run_resco.py':'"colight": "CoSLight"',
             'run_all_eval.ps1':'--baselines fixed maxpressure colight\nrun_evaluation.py'}
        data={x['id']:x['encontrado'] for x in m.test_patterns(src)}
        for key in ('SOTA-01','SOTA-02','PERT-01','GYM-01','GYM-02','GYM-03','CTRL-01'):
            self.assertTrue(data[key],key)
    def test_absence_does_not_claim_features(self):
        data={x['id']:x['encontrado'] for x in m.test_patterns({})}
        self.assertFalse(any(data.values()))
    def test_safe_read_checkpoint_metadata_no_pickle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'tsc_framework/outputs/models/ppo_ideal.zip';p.parent.mkdir(parents=True)
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('data',json.dumps({'num_timesteps':123,'policy_class':'PPOPolicy'}))
                z.writestr('policy.pth','NOT_REAL_PICKLE')
            row=m.inspect_checkpoint(p,root)
            self.assertEqual(row['zip_structure'],'ZIP_LEIBLE')
            self.assertEqual(row['data_num_timesteps'],'123')
            self.assertTrue(row['sb3_metadata_presence'])
            self.assertEqual(len(row['sha256']),64)
    def test_missing_h11_does_not_claim_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'resultados').mkdir()
            rows=m.experiment_evidence(Path(tmp))
            self.assertEqual(sum(x['existe'] for x in rows[:3]),0)
    def test_cannot_save_outside_resultados(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);revision=tmp/'revision';repo=tmp/'repo';(revision/'resultados').mkdir(parents=True)
            (repo/'tsc_framework/src/core').mkdir(parents=True)
            (repo/'tsc_framework/src/core/tsc_env.py').write_text('class TSCEnv(gym.Env): pass')
            (repo/'run_all_eval.ps1').write_text('')
            with self.assertRaises(ValueError):
                m.run(['--revision-root',str(revision),'--repo-root',str(repo),
                       '--guardar','--output',str(tmp/'outside')])
    def test_preflight_never_creates_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);revision=tmp/'revision';repo=tmp/'repo';(revision/'resultados').mkdir(parents=True)
            (repo/'tsc_framework/src/core').mkdir(parents=True)
            (repo/'tsc_framework/src/core/tsc_env.py').write_text('class TSCEnv(gym.Env): pass')
            (repo/'run_all_eval.ps1').write_text('')
            self.assertEqual(m.run(['--revision-root',str(revision),'--repo-root',str(repo)]),0)
            self.assertEqual(list((revision/'resultados').iterdir()),[])
    def test_write_only_new_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);revision=tmp/'revision';repo=tmp/'repo';(revision/'resultados').mkdir(parents=True)
            (repo/'tsc_framework/src/core').mkdir(parents=True)
            (repo/'tsc_framework/src/core/tsc_env.py').write_text('class TSCEnv(gym.Env): pass')
            (repo/'run_all_eval.ps1').write_text('')
            dest=revision/'resultados'/'h12_test'
            self.assertEqual(m.run(['--revision-root',str(revision),'--repo-root',str(repo),
                                    '--guardar','--output',str(dest)]),0)
            self.assertTrue((dest/'dictamen_h12.md').is_file())
            self.assertTrue((dest/'manifiesto_h12.json').is_file())
            with self.assertRaises(ValueError):
                m.run(['--revision-root',str(revision),'--repo-root',str(repo),
                       '--guardar','--output',str(dest)])

if __name__=='__main__':unittest.main()
