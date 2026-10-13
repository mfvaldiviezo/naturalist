import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from h11_2_observador_pasivo import PassiveObserver, load_ids


class FakeTraCI:
    class Vehicle:
        def __init__(self, p): self.p=p
        def getIDList(self): return ['veh1']
        def getLaneID(self, vid): return 'A_0' if self.p.t <= 2 else ':B_0'
        def getRoadID(self, vid): return 'A' if self.p.t <= 2 else ':B'
        def getSpeed(self, vid):
            if vid=='veh1': return 5. if self.p.t<=2 else 0.
            return 4.
        def getAcceleration(self,vid): return 0.5 if self.p.t<=2 else -0.5
        def getLanePosition(self,vid): return 100.
        def getPosition(self,vid): return (1.,2.)
        def getAllowedSpeed(self,vid): return 12.
        def getTypeID(self,vid): return 'imprudent'
        def getLeader(self,vid,d): return ('leader',10.) if self.p.t<=2 else None
        def getNextTLS(self,vid):
            return [('B1',0,13. if self.p.t==1 else 5.,'r')] if self.p.t<=2 else []
        def getNextLinks(self,vid): return [('B_0','','',False,False,'r','s',10.)]
        def setSpeed(self,*args): raise AssertionError('MUST NOT SET SPEED')
        def setAcceleration(self,*args): raise AssertionError('MUST NOT ALTER ACCELERATION')
        def setTau(self,*args): raise AssertionError('MUST NOT ALTER TAU')
    class Lane:
        def getMaxSpeed(self,lane): return 15.
        def getLastStepHaltingNumber(self,lane): return 2
        def getLastStepVehicleNumber(self,lane): return 3
    class Sim:
        def __init__(self,p): self.p=p
        def getTime(self): return self.p.t * .5
        def getDeltaT(self): return .5
        def getCollidingVehiclesNumber(self): return 0
        def getCollidingVehiclesIDList(self): return ()
        def getStartingTeleportNumber(self): return 0
        def getStartingTeleportIDList(self): return ()
        def getEmergencyStoppingVehiclesNumber(self): return 1 if self.p.t==3 else 0
        def getEmergencyStoppingVehiclesIDList(self): return ('veh1',) if self.p.t==3 else ()
    class TL:
        def getRedYellowGreenState(self,tid): return 'r'
    def __init__(self):
        self.t=0
        self.vehicle=self.Vehicle(self)
        self.lane=self.Lane()
        self.simulation=self.Sim(self)
        self.trafficlight=self.TL()
    def advance(self): self.t+=1
    def simulationStep(self): raise AssertionError('OBS must never advance simulation')


class TestObserver(unittest.TestCase):
    def test_observation_and_proxy_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            traci=FakeTraCI()
            with PassiveObserver(Path(tmp)/'run',vine_ids={'veh1'},h09_ids={'veh1'},stop_min_duration_s=1.0) as o:
                for s in range(10):
                    traci.advance()
                    o.on_step(traci,s)
                with self.assertRaises(RuntimeError): o.on_step(traci,10)  # no duplicate time
            root=Path(tmp)/'run'
            with (root/'trayectorias_h11.csv').open(encoding='utf-8') as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),10)
            self.assertEqual(rows[0]['cohort'],'both')
            self.assertEqual(rows[0]['headway_s'],'2.0')
            self.assertEqual(rows[0]['ttc_s'],'10.0')
            with (root/'eventos_semaforicos_h11.csv').open(encoding='utf-8') as f:
                events=list(csv.DictReader(f))
            self.assertTrue(any(r['event_kind']=='crossing_proxy' and r['color_label']=='red' for r in events))
            self.assertFalse(any(r['quality']=='CONFIRMED_VIOLATION' for r in events))
            with (root/'eventos_interseccion_h11.csv').open(encoding='utf-8') as f:
                candidates=list(csv.DictReader(f))
            self.assertEqual(len(candidates),1)
            self.assertEqual(candidates[0]['gridlock_confirmed'],'false')
            manifest=json.loads((root/'manifest_h11_2.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['observed_steps'],10)
            self.assertEqual(manifest['counts']['internal_stop_candidates'],1)
            self.assertFalse(manifest['empirically_calibrated_quito'])
            self.assertGreater(len(manifest['outputs_sha256']),0)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            with PassiveObserver(Path(t)/'run'):
                pass
            with self.assertRaises(FileExistsError): PassiveObserver(Path(t)/'run')

    def test_ids(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'cohorte.csv'
            path.write_text('vehicle_id\nA\nB\n',encoding='utf-8')
            self.assertEqual(load_ids(path),{'A','B'})
            (Path(t)/'ids.txt').write_text('A\nB\n',encoding='utf-8')
            self.assertEqual(load_ids(Path(t)/'ids.txt'),{'A','B'})

    def test_stop_not_gridlock(self):
        with tempfile.TemporaryDirectory() as t:
            x=FakeTraCI()
            with PassiveObserver(Path(t)/'run',stop_min_duration_s=0.5) as o:
                for j in range(6): x.advance();o.on_step(x)
            with (Path(t)/'run'/'eventos_interseccion_h11.csv').open(encoding='utf-8') as f:
                rows=list(csv.DictReader(f))
            self.assertTrue(rows)
            self.assertTrue(all(z['gridlock_confirmed']=='false' for z in rows))

    def test_source_has_no_traci_setters(self):
        source=(Path(__file__).resolve().parents[1]/'h11_2_observador_pasivo.py').read_text(encoding='utf-8')
        import ast
        tree=ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute):
                self.assertNotIn(node.attr, {'simulationStep','setSpeed','setAcceleration','setTau','setSpeedMode','setPhase','setRoute','setImperfection','setSpeedFactor','setStop','start','close'}) if node.attr != 'close' else None
        # The only close() calls operate on local CSV files.

if __name__=='__main__': unittest.main()
