import csv
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

RUNNER = Path(__file__).resolve().parents[1]/'scripts'/'piloto_hibrido_h10.py'
spec=importlib.util.spec_from_file_location('h10_runner_tests',RUNNER)
h10=importlib.util.module_from_spec(spec)
spec.loader.exec_module(h10)

class FakeVehicle:
    def __init__(self):self.types={'5':'H09_EXPLORATORIO_V12','1':'DEFAULT_VEHTYPE'}
    def getIDList(self):return ['5','1']
    def getTypeID(self,vid):return self.types[vid]
    def getLaneID(self,vid):return 'A1B1_0'
    def getSpeed(self,vid):return 8.0
    def getLeader(self,vid,dist):return None
    def getNextTLS(self,vid):return []

class FakeSimulation:
    def __init__(self,traci):self.traci=traci
    def getTime(self):return self.traci.n*.5
    def getArrivedNumber(self):return 1
    def getDepartedNumber(self):return 2
    def getCollidingVehiclesNumber(self):return 0
    def getStartingTeleportNumber(self):return 0
    def getMinExpectedNumber(self):return 12

class FakeTraci:
    def __init__(self):self.n=0;self.trace=[];self.vehicle=FakeVehicle();self.simulation=FakeSimulation(self)
    def simulationStep(self):self.n+=1;self.trace.append('simulationStep')

class FakeObs:
    def observe(self,traci):traci.trace.append('observe')

class FakeInjector:
    def on_step(self,traci,step):traci.trace.append('vine_on_step')

class H10Unit(unittest.TestCase):
    def test_01_mode_count(self):self.assertEqual(set(h10.MODES),{'nominal','vine_protegido','vine_contextual','h09','hibrido_protegido','hibrido_contextual'})
    def test_02_overlap_disjoint(self):
        self.assertEqual(h10.overlap_counts({'a'},{'b'})['n_ambos'],0)
    def test_03_overlap_partial(self):
        x=h10.overlap_counts({'a','b'},{'b','c'})
        self.assertEqual((x['n_ambos'],x['n_solo_vine'],x['n_solo_h09']),(1,1,1))
    def test_04_overlap_exact(self):
        x=h10.overlap_counts({'1','2'},{'1','2'})
        self.assertEqual(x['selected_ambos'],['1','2'])
    def test_05_source_sha(self):
        meta=json.loads((Path(__file__).resolve().parents[1]/'AUDITORIA_H08B_ADJUNTO.json').read_text())
        self.assertEqual(meta['sha256'],h10.EXPECTED_H08B)
        self.assertEqual(meta['source_file_copied_into_H10'],False)
    def test_06_missing_dependencies_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):h10.discover_vine_dir(Path(d))
    def test_07_wrong_h08b_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in h10.ORIGINAL_MODULES:(root/name).write_text('x=1\n')
            with self.assertRaises(RuntimeError):h10.discover_vine_dir(root,root)
    def test_08_approved_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'resultados').mkdir()
            x=h10.output_safe(root/'resultados'/'nuevo',root)
            self.assertEqual(x.name,'nuevo')
    def test_09_reject_outside(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'resultados').mkdir()
            with self.assertRaises(ValueError):h10.output_safe(root/'otro',root)
    def test_10_reject_existing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'resultados').mkdir();(root/'resultados'/'old').mkdir()
            with self.assertRaises(FileExistsError):h10.output_safe(root/'resultados'/'old',root)
    def test_11_single_step_order_with_vine(self):
        t=FakeTraci();seen=set();verified=set();headways={}
        from collections import defaultdict,Counter
        x,stop=h10.step_once(t,FakeObs(),0,{'5'},seen,verified,defaultdict(Counter),FakeInjector())
        self.assertEqual(t.trace,['simulationStep','observe','vine_on_step'])
        self.assertEqual(t.n,1)
        self.assertEqual((x['step'],x['n_vehicles'],x['arrivals_step']), (0,2,1))
        self.assertEqual(seen,{'1','5'});self.assertEqual(verified,{'5'})
        self.assertFalse(stop)
    def test_12_single_step_no_vine(self):
        t=FakeTraci();from collections import defaultdict,Counter
        h10.step_once(t,FakeObs(),0,set(),set(),set(),defaultdict(Counter),None)
        self.assertEqual(t.trace,['simulationStep','observe'])
    def test_13_moving_links_selected_only(self):
        rows=[{'event_type':'tls_moving_opportunity','measurement_id':'e','vehicle_id':'v','signal_state':'red'},
              {'event_type':'tls_crossing_link','measurement_id':'e','vehicle_id':'v','signal_state':'red','classification_quality':'confirmed'}]
        v=h10.audit_episodes(rows,{'v'})
        self.assertEqual(v['linked_moving_red_selected'],1)
        self.assertEqual(v['selected_cross_red'],1)
    def test_14_no_invented_link(self):
        rows=[{'event_type':'tls_crossing_link','measurement_id':'e','vehicle_id':'v','signal_state':'red','classification_quality':'confirmed'}]
        v=h10.audit_episodes(rows,{'v'})
        self.assertNotIn('linked_moving_red_selected',v)
    def test_15_uncertain_not_red(self):
        v=h10.audit_episodes([{'event_type':'tls_crossing_link','measurement_id':'e','vehicle_id':'v',
                                'signal_state':'unknown','classification_quality':'uncertain'}],{'v'})
        self.assertEqual(v['cross_unknown'],1);self.assertNotIn('cross_red',v)
    def test_16_source_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'a';f.write_text('1');sha=h10.sha256(f);f.write_text('2')
            with self.assertRaises(RuntimeError):h10.verify_sources({str(f):sha})
    def test_17_resumed_manifest_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'resultados/h10_vine_h09_imprudencia_v111_piloto_101/nominal';out.mkdir(parents=True)
            man={'status':h10.STATUS,'source_sha256':{},
                 'seed':101,'steps':600,'dt':.5,'output_sha256':{'test.csv':'xyz'}}
            (out/'manifest_h10.json').write_text(json.dumps(man));(out/'test.csv').write_text('data')
            with self.assertRaises(RuntimeError):h10.inspect_previous(h10.get_paths(root),['nominal'],{},101,.5,600)
    def test_18_factorial_identity(self):
        def m(n):return {'instrumental':{'signal_states':{'red':n,'yellow':n*2}},
                          'traffic_metrics':{'arrivals':n,'mean_halted':n,'mean_speed_kmh':n,
                                           'collisions':0,'teleports':0}}
        x=h10.build_comparison(dict(zip(h10.MODES,(m(10),m(12),m(13),m(14),m(17),m(19)))))
        self.assertEqual(x['effects']['arrivals']['protegido']['interaction'],1)
        self.assertEqual(x['effects']['red']['protegido']['interaction'],1)
    def test_19_factorial_missing_rejected(self):
        with self.assertRaises(ValueError):h10.build_comparison({})
    def test_20_file_export_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'x.csv';h10.write_csv(f,[{'x':1}]);self.assertTrue(f.is_file())
            with self.assertRaises(FileExistsError):h10.write_csv(f,[{'x':2}])
    def test_21_original_onstep_contract_ast(self):
        # Metadatos de AST extraídos de los bytes exactos del adjunto H08b.
        doc=json.loads((Path(__file__).resolve().parents[1]/'AUDITORIA_H08B_ADJUNTO.json').read_text())
        self.assertEqual(doc['class_name'],'FixedRosterInjector')
        self.assertEqual(doc['inherits'],['h08.StressInjector'])
        self.assertFalse(doc['overrides_on_step'])
    def test_22_no_h08b_modification_in_package(self):
        package=Path(__file__).resolve().parents[1]
        self.assertFalse(any((package/n).exists() for n in h10.ORIGINAL_MODULES))

if __name__=='__main__':unittest.main()
