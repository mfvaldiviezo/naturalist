import importlib.util
import json
import tempfile
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parent.parent/'h12_2_puente.py'
spec=importlib.util.spec_from_file_location('h122',SCRIPT)
h=importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

class Sim:
    def __init__(self, dt=.5):
        self.t=0;self.dt=dt;self.collisions=0;self.teleports=0
    def getTime(self):return self.t
    def getDeltaT(self):return self.dt
    def getCollidingVehiclesNumber(self):return self.collisions
    def getStartingTeleportNumber(self):return self.teleports

class Veh:
    def __init__(self): self.acc=[]
    def getSpeedMode(self,v):return 31
    def setAcceleration(self,v,a,dur):self.acc.append((v,a,dur))
    def setSpeed(self,*a):raise AssertionError('setSpeed no autorizado')
    def getSpeed(self,vid):return 3.

class TraCI:
    def __init__(self,dt=.5):self.simulation=Sim(dt);self.vehicle=Veh();self.calls=0
    def simulationStep(self):self.calls+=1;self.simulation.t+=self.simulation.dt

class TestH122(unittest.TestCase):
    def test_patch_exact(self):
        src='\n'.join([h.P_STEP,h.P_LOOP,h.P_LOG])
        out=h.exact_patch(src,h.EXPECTED_BLOB_SHA)
        self.assertIn(h.Q_STEP,out)
        self.assertIn(h.Q_LOOP,out)
        self.assertIn(h.Q_LOG,out)
        self.assertNotIn(h.P_LOG,out)
    def test_patch_fails_if_unknown_source(self):
        with self.assertRaises(RuntimeError):h.exact_patch('whatever','bad')
    def test_patch_fails_if_ambiguous(self):
        src='\n'.join([h.P_STEP,h.P_LOOP,h.P_LOG,h.P_LOOP])
        with self.assertRaises(RuntimeError):h.exact_patch(src,h.EXPECTED_BLOB_SHA)
    def test_nominal_ticks_and_timing(self):
        t=TraCI();b=h.MicrotickBridge()
        for i in range(20):t.simulationStep();b.after_microtick(t,i)
        self.assertEqual(t.calls,20)
        self.assertAlmostEqual(b.last_time_s,10)
        self.assertEqual(b.command_count,0)
    def test_double_tick_detected(self):
        t=TraCI();b=h.MicrotickBridge()
        t.simulationStep();b.after_microtick(t,0)
        with self.assertRaises(RuntimeError):b.after_microtick(t,1)
    def test_wrong_delta_detected(self):
        t=TraCI(1.0);b=h.MicrotickBridge()
        t.simulationStep()
        with self.assertRaises(RuntimeError):b.after_microtick(t,0)
    def test_hook_cannot_step(self):
        t=TraCI()
        def bad_hook(view,step):view.simulationStep()
        b=h.MicrotickBridge(mode='probe',hook=bad_hook)
        t.simulationStep()
        with self.assertRaisesRegex(RuntimeError,'DOUBLE-STEP'):b.after_microtick(t,0)
        self.assertEqual(t.calls,1)
    def test_probe_cannot_accelerate(self):
        t=TraCI()
        def bad_hook(view,step):view.vehicle.setAcceleration('a',.1,.5)
        b=h.MicrotickBridge(mode='probe',hook=bad_hook)
        t.simulationStep()
        with self.assertRaisesRegex(RuntimeError,'WRITE-BLOCKED'):b.after_microtick(t,0)
        self.assertFalse(t.vehicle.acc)
    def test_hard_stop_blocked_in_active(self):
        t=TraCI()
        def bad_hook(view,step):view.vehicle.setSpeed('a',0)
        b=h.MicrotickBridge(mode='active',hook=bad_hook)
        t.simulationStep()
        with self.assertRaisesRegex(RuntimeError,'WRITE-BLOCKED'):b.after_microtick(t,0)
    def test_active_one_acceleration(self):
        t=TraCI()
        def hook(view,step):view.vehicle.setAcceleration('a',-.4,.5)
        b=h.MicrotickBridge(mode='active',hook=hook,max_commands=1)
        t.simulationStep();b.after_microtick(t,0)
        self.assertEqual(len(t.vehicle.acc),1)
        t.simulationStep()
        with self.assertRaisesRegex(RuntimeError,'cuota'):b.after_microtick(t,1)
        self.assertEqual(t.calls,2)
    def test_active_duration_rejected(self):
        t=TraCI()
        b=h.MicrotickBridge(mode='active',hook=lambda v,k:v.vehicle.setAcceleration('a',.1,1.))
        t.simulationStep()
        with self.assertRaisesRegex(RuntimeError,'duracion'):b.after_microtick(t,0)
    def test_safety_halt_collision(self):
        t=TraCI();t.simulation.collisions=1
        b=h.MicrotickBridge(mode='active',hook=lambda v,k:None)
        t.simulationStep()
        with self.assertRaisesRegex(RuntimeError,'SAFETY-HALT'):b.after_microtick(t,0)
    def test_input_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'a.net.xml').write_text('<net/>')
            (root/'b.rou.xml').write_text('<routes/>')
            c=root/'c.sumocfg';c.write_text('<configuration><input><net-file value="a.net.xml"/><route-files value="b.rou.xml"/></input></configuration>')
            m=h.input_manifest(c)
            self.assertEqual(len(m['dependencies']),2)
    def test_refuse_sumo_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=root/'c.sumocfg'
            c.write_text('<configuration><input/><output><tripinfo-output value="foo.xml"/></output></configuration>')
            with self.assertRaisesRegex(RuntimeError,'sobrescritura'):h.input_manifest(c)
    def test_unique_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            x=h.make_output(p);y=h.make_output(p)
            self.assertNotEqual(x,y)
            self.assertEqual(x.parent,p/'resultados')
    def test_hook_factory_missing(self):
        with self.assertRaises(FileNotFoundError):h.import_hook_factory(Path('/nonexistent/hook.py'),'create_hook',{})
    def test_csv_safe_no_raw_data_inspection(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);(r/'H10_Test').mkdir()
            (r/'H10_Test'/'sim.py').write_text('class Injector:\n    def on_step(self, traci, step): pass\n')
            (r/'H10_Test'/'private.csv').write_text('not read')
            scans=h.discover_local_h10(r)
            self.assertEqual(len(scans),1)
            self.assertTrue(any(x.startswith('Injector.on_step(') for x in scans[0]['simbolos']))

if __name__=='__main__':unittest.main()
