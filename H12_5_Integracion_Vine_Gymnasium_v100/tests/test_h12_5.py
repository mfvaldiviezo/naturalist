import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('h125_testmod',HERE/'h12_5_integrar.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)

class Domain:
    def __init__(self, **kwargs): self.__dict__.update(kwargs)

class FakeVehicle:
    def __init__(self): self.values={'a':(4.,.3),'b':(0.,0.)};self.calls=[]
    def getIDList(self):return list(self.values)
    def getSpeed(self,id):return self.values[id][0]
    def getAcceleration(self,id):return self.values[id][1]
    def getTypeID(self,id):return 'H09_EXPLORATORIO_V12' if id=='a' else 'DEFAULT'

class FakeSim:
    def getTime(self): return .5
    def getArrivedNumber(self): return 1
    def getDepartedNumber(self): return 2
    def getCollidingVehiclesNumber(self): return 0
    def getStartingTeleportNumber(self): return 0

class FakeTraCI:
    def __init__(self): self.vehicle=FakeVehicle();self.simulation=FakeSim()
    def simulationStep(self):raise AssertionError('NEVER advance in H10Hook')

class Tests(unittest.TestCase):
    def test_pin_manifest_fail_closed_for_missing_source(self):
        self.assertEqual(len(M.REL_SHA),8)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                M.validate_source(Path(td))
    def test_trace_determinism_and_no_double_step(self):
        t=FakeTraCI();hook=M.H10Hook('nominal');hook.on_step(t,0)
        self.assertEqual(hook.rows[0]['time_s'],.5)
        self.assertEqual(hook.rows[0]['n_active'],2)
        same=M.H10Hook('nominal');same.on_step(t,0)
        self.assertEqual(hook.trace_hash(),same.trace_hash())
    def test_injector_hook_receives_original_index(self):
        class Inj:
            def __init__(self):self.calls=[]
            def on_step(self,traci,index):self.calls.append(index)
        inj=Inj();h=M.H10Hook('probe',inj)
        h.on_step(FakeTraCI(),41)
        self.assertEqual(inj.calls,[41])
    def test_h09_verification_good(self):
        h=M.H10Hook('h09',h09_ids={'a'})
        h.on_step(FakeTraCI(),0)
        self.assertEqual(h.h09_seen,{'a'})
        self.assertEqual(h.h09_verified,{'a'})
    def test_h09_verification_mismatch(self):
        h=M.H10Hook('h09',h09_ids={'b'})
        with self.assertRaisesRegex(RuntimeError,'RUNTIME TYPE MISMATCH'):
            h.on_step(FakeTraCI(),0)
    def test_invariance_ok(self):
        x={'result':'SMOKE_OK','n_decisions':4,'n_microticks':40,'trace_sha256':'abc','commands':0}
        self.assertEqual(M.assert_probe_pair(x,x)['status'],'PAREADO_NOMINAL_PROBE_OK')
    def test_invariance_rejects_diff(self):
        x={'result':'SMOKE_OK','n_decisions':4,'n_microticks':40,'trace_sha256':'abc','commands':0}
        y={**x,'trace_sha256':'changed'}
        with self.assertRaisesRegex(RuntimeError,'INVARIANCIA FALLIDA'):
            M.assert_probe_pair(x,y)
    def test_invariance_rejects_commands(self):
        x={'result':'SMOKE_OK','n_decisions':4,'n_microticks':40,'trace_sha256':'abc','commands':0}
        with self.assertRaisesRegex(RuntimeError,'contienen comandos'):
            M.assert_probe_pair(x,{**x,'commands':1})
    def test_h09_demands_exact_match(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a.xml';b=Path(td)/'b.xml'
            a.write_text('<routes><vehicle id="a" depart="0"><route edges="a b"/></vehicle><vehicle id="b" depart="1"><route edges="c d"/></vehicle></routes>')
            b.write_text('<routes><vType id="H09_EXPLORATORIO_V12"/><vehicle id="a" depart="0" type="H09_EXPLORATORIO_V12"><route edges="a b"/></vehicle><vehicle id="b" depart="1"><route edges="c d"/></vehicle></routes>')
            self.assertEqual(M.verify_vehicle_demand(a,b,{'a'})['vehicles_unchanged'],2)
    def test_h09_rejects_missing_vehicle(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a.xml';b=Path(td)/'b.xml'
            a.write_text('<routes><vehicle id="a" depart="0"><route edges="a b"/></vehicle></routes>')
            b.write_text('<routes/>')
            with self.assertRaisesRegex(RuntimeError,'CAMBIO DEMANDA'):
                M.verify_vehicle_demand(a,b,set())
    def test_h09_rejects_unselected_type_change(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a.xml';b=Path(td)/'b.xml'
            a.write_text('<routes><vehicle id="a" depart="0"><route edges="a b"/></vehicle></routes>')
            b.write_text('<routes><vehicle id="a" depart="0" type="OTHER"><route edges="a b"/></vehicle></routes>')
            with self.assertRaisesRegex(RuntimeError,'no seleccionado'):
                M.verify_vehicle_demand(a,b,set())
    def test_h09_rejects_departure_change(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a.xml';b=Path(td)/'b.xml'
            a.write_text('<routes><vehicle id="a" depart="0"><route edges="a b"/></vehicle></routes>')
            b.write_text('<routes><vehicle id="a" depart="1"><route edges="a b"/></vehicle></routes>')
            with self.assertRaisesRegex(RuntimeError,'CAMBIO DEMANDA'):
                M.verify_vehicle_demand(a,b,set())
    def test_copied_sumo_cfg_no_output_and_absolute(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);net=root/'a.net.xml';net.write_text('net')
            route=root/'route.xml';route.write_text('routes')
            cfg=root/'old.sumocfg';cfg.write_text('<configuration><input><net-file value="a.net.xml"/><route-files value="route.xml"/></input><output><tripinfo-output value="x.xml"/></output></configuration>')
            new=root/'new.sumocfg';details=M.create_overlay_config(cfg,net,route,new)
            tree=ET.parse(new).getroot()
            self.assertIsNone(tree.find('output'))
            self.assertEqual(tree.find('input/net-file').get('value'),str(net.resolve()))
            self.assertTrue(details['outputs_xml_removed'])
    def test_reject_additional(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);net=root/'a.net.xml';net.write_text('net')
            route=root/'r.xml';route.write_text('routes')
            cfg=root/'old.sumocfg';cfg.write_text('<configuration><input><net-file value="a"/><route-files value="b"/><additional-files value="c"/></input></configuration>')
            with self.assertRaisesRegex(RuntimeError,'additional-files'):
                M.create_overlay_config(cfg,net,route,root/'new.sumocfg')
    def test_fail_closed_invalid_seed(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):M.parse(['--repo-root','.','--seed','2026'])
    def test_active_explicit_two_acks(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):M.parse(['--repo-root','.','--mode','active'])
        args=M.parse(['--repo-root','.','--mode','active','--ack-active','EXPERIMENTAL_ONLY',
                     '--ack-time-scale','NOT_CALIBRATED'])
        self.assertEqual(args.mode,'active')
    def test_explicit_limit_horizon(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):M.parse(['--repo-root','.','--rl-steps','100'])
    def test_smoke_code_has_no_modified_original_write(self):
        src=(HERE/'h12_5_integrar.py').read_text(encoding='utf-8')
        self.assertNotIn('PPO.learn(',src)
        self.assertNotIn('traci.simulationStep()',src)
        self.assertNotIn('setSpeed(',src)
        self.assertNotIn('setAcceleration(',src)

if __name__=='__main__':unittest.main()
