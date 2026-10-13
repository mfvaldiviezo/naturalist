import importlib.util
from pathlib import Path
import unittest

MAIN=Path(__file__).resolve().parents[1]/'h12_7_estado_b1.py'
spec=importlib.util.spec_from_file_location('h127_testmod',MAIN)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestH127(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[2]
        cls.source=(root/'H12_5_Integracion_Vine_Gymnasium_v100/h12_5_integrar.py').read_text(encoding='utf-8')

    def test_original_is_pinned(self):
        root=Path(__file__).resolve().parents[2]
        self.assertEqual(m.sha256(root/m.H125_REL),m.EXPECTED_H125_SHA256)
    def test_patch_syntax(self):
        patched=m.patch_h125(self.source)
        self.assertIn("result['h12_7_diagnostic']=diagnostic",patched)
        self.assertIn('"state_before_34d"',patched.replace("'state_before_34d'",'"state_before_34d"'))
    def test_patch_fails_missing_anchor(self):
        with self.assertRaises(RuntimeError):m.patch_h125(self.source.replace('self.rows.append(row)','self.rows.append(other)'))
    def test_patch_fails_ambiguous_anchor(self):
        with self.assertRaises(RuntimeError):m.patch_h125(self.source+'\n'+m.PATCHES[0][0])
    def test_vector_dimension(self):
        with self.assertRaises(ValueError):m.obs_differences([0]*33,[0]*34)
    def test_nonfinite_vector(self):
        with self.assertRaises(ValueError):m.obs_differences([float('nan')]+[0]*33,[0]*34)
    def test_segments(self):
        a=[0]*34;b=[0]*34
        for i in (1,13,25,29,33):b[i]=1
        d=m.obs_differences(a,b)
        self.assertEqual(d['n_diff'],5)
        self.assertEqual({k:len(v) for k,v in d['segments'].items()},
                         {'cola_12':1,'espera_12':1,'presion_4':1,'fase_4':1,'edad_2':1})
    def test_tolerance(self):
        a=[0]*34;b=[0]*34;b[0]=1e-9
        self.assertEqual(m.obs_differences(a,b)['n_diff'],0)
    def test_analyze_mock(self):
        obs=[0.]*34
        def mock(active):
            return {'model':'ppo_ideal','checkpoint_sha256':'x',
               'n_decisions':1,'n_microticks':1,'inputs':{'net_sha256':'a',
               'routes_sha256':'b','cfg_original_sha256':'c'},
               'h10_source_sha256':{'z':'y'},'commands':20 if active else 0,
               'trace_sha256':'active' if active else 'nom',
               'extra':{'n_commands_confirmed':20},
               'decisions':[{'i':0,'sim_time_s':5.,'action':0,'queue':0,
                             'state_before_34d':obs,'state_after_34d':obs}],
               'h12_7_diagnostic':{'controlled_lanes_unique_raw':['1'],
                'controlled_lanes_used_12':['1']*12,'outgoing_lanes':[],
                'green_phases':[0,2],'b1_microticks':[{'tick':0,'time_s':.5,
                         'n_b1':1,'halted_b1':0}]}}
        a,b=mock(False),mock(True)
        b['decisions'][0]['state_before_34d']=[1.]+[0.]*33
        res=m.analyze(a,b)
        self.assertEqual(res['n_decisions_obs_different'],1)
        self.assertTrue(res['same_actions'])
        self.assertEqual(res['b1_nominal_ticks_with_vehicles'],1)
    def test_analyze_mismatch_demand_rejected(self):
        a={'model':'x','checkpoint_sha256':'z','n_decisions':1,'n_microticks':1,
           'inputs':{'net_sha256':'a','routes_sha256':'b','cfg_original_sha256':'c'},
           'h10_source_sha256':{},'commands':0}
        b={**a,'commands':1,'inputs':{**a['inputs'],'routes_sha256':'different'}}
        with self.assertRaisesRegex(RuntimeError,'NOT_PAIRED_routes_sha256'):m.analyze(a,b)

if __name__=='__main__':unittest.main()
