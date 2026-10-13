import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

RUNNER=Path(__file__).resolve().parents[1]/'scripts'/'piloto_hibrido_h10.py'
spec=importlib.util.spec_from_file_location('h10_v11_runner_tests',RUNNER)
h10=importlib.util.module_from_spec(spec);spec.loader.exec_module(h10)

class FakeConfig:
    def __init__(self,**kwargs): self.__dict__.update(kwargs)
    def validate(self):
        assert 0.1<=self.step_length<=0.6
        assert self.max_commands>0

class FakeH08:StressConfig=FakeConfig

class Policies(unittest.TestCase):
    def setUp(self):self.a=SimpleNamespace(seed=101,dt=.5,steps=600,max_commands=100)
    def test_original_eligibility(self):
        cfg=h10.build_vine_config(FakeH08,self.a,'vine_protegido')
        self.assertEqual((cfg.tls_distance_m,cfg.free_gap_m,cfg.follower_gap_m),(80,60,60))
    def test_contextual_eligibility(self):
        cfg=h10.build_vine_config(FakeH08,self.a,'vine_contextual')
        self.assertEqual((cfg.tls_distance_m,cfg.free_gap_m,cfg.follower_gap_m),(0,2,1))
        self.assertEqual((cfg.distance_to_lane_end_m,cfg.max_speed_kmh),(5,70))
    def test_hybrid_uses_same_context(self):
        a=h10.build_vine_config(FakeH08,self.a,'vine_contextual')
        b=h10.build_vine_config(FakeH08,self.a,'hibrido_contextual')
        self.assertEqual(a.__dict__,b.__dict__)
    def test_same_statistical_variant_budget(self):
        a=h10.build_vine_config(FakeH08,self.a,'vine_protegido')
        b=h10.build_vine_config(FakeH08,self.a,'vine_contextual')
        for name in ('variant','mode','max_commands','max_commands_per_step','max_commands_per_window',
                     'window_seconds','max_commands_per_vehicle','cooldown_steps','seed',
                     'penetration','step_length'):
            self.assertEqual(getattr(a,name),getattr(b,name))
    def test_non_vine_scenario_rejected(self):
        with self.assertRaises(ValueError):h10.build_vine_config(FakeH08,self.a,'h09')
    def test_policy_assignment(self):
        self.assertEqual(h10.policy_for_mode('hibrido_contextual'),'contextual')
        self.assertEqual(h10.policy_for_mode('hibrido_protegido'),'protegido')
    def test_distinct_output_root(self):
        self.assertIn('h10_vine_h09_imprudencia_v11',str(h10.get_paths(Path('/tmp'))['out']))
    def test_factorial_context_vs_protected(self):
        def m(n):return {'instrumental':{'signal_states':{'red':n,'yellow':0}},
           'traffic_metrics':{'arrivals':n,'mean_halted':n,'mean_speed_kmh':n,
                              'collisions':0,'teleports':0}}
        vals=(10,12,15,14,17,22)
        r=h10.build_comparison({k:m(v) for k,v in zip(h10.MODES,vals)})
        self.assertEqual(r['effects']['arrivals']['protegido']['interaction'],1)
        self.assertEqual(r['effects']['arrivals']['contextual']['interaction'],3)
        self.assertEqual(r['effects']['arrivals']['contextual_minus_protegido']['hybrid'],5)

if __name__=='__main__':unittest.main()
