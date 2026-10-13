from __future__ import annotations
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

A=load('auditor_h09_v11',ROOT/'scripts'/'auditar_eventos_h09.py')
Z=load('zonas_h09_v11',ROOT/'scripts'/'generar_zonas_velocidad_h09.py')
O=load('obs_h09_v11',ROOT/'scripts'/'observador_traci_h09_v11.py')

class Sim:
    def __init__(self,app):self.a=app
    def getTime(self):return self.a.time
    def getDeltaT(self):return 0.5
    def getCollidingVehiclesNumber(self):return 0
    def getStartingTeleportNumber(self):return 0

class Vehicle:
    def __init__(self,app):self.a=app
    def getIDList(self):return ['x']
    def getLaneID(self,vid):return self.a.lane
    def getLanePosition(self,vid):return self.a.pos
    def getSpeed(self,vid):return 10.
    def getNextTLS(self,vid):
        return [('B1',0,self.a.distance,self.a.phase)] if self.a.lane=='approach' else []
    def setSpeedMode(self,*args):raise AssertionError('No permite modificar SUMO')
    def setSpeed(self,*args):raise AssertionError('No permite modificar SUMO')
    def setAcceleration(self,*args):raise AssertionError('No permite modificar SUMO')

class TLS:
    def __init__(self,app):self.a=app
    def getRedYellowGreenState(self,site):return self.a.phase
    def getNextSwitch(self,site):return self.a.next_switch
    def setRedYellowGreenState(self,*args):raise AssertionError('No permite modificar semaforos')

class Lane:
    def getMaxSpeed(self,lane):return 13.89

class MockTraci:
    def __init__(self,phase='r',switch=300):
        self.time=.5;self.lane='approach';self.pos=90.;self.distance=3.
        self.phase=phase;self.next_switch=switch
        self.simulation=Sim(self);self.vehicle=Vehicle(self)
        self.trafficlight=TLS(self);self.lane_api=Lane()
        self.lane=self.lane  # lane es string por falso, no registrar velocidad aqui
    def crossing(self,phase=None):
        self.time=1.;self.lane=':B1_2_0';self.pos=0
        if phase is not None:self.phase=phase

class TestH09V11(unittest.TestCase):
    def test_red_confirmado_escenario_simulado(self):
        t=MockTraci('r',300)
        o=O.EventObserver('toy',101,['B1']);o.observe(t);t.crossing();o.observe(t)
        self.assertEqual(o.stats()['signal_states'],{'red':1})
        self.assertEqual(o.rows[0]['classification_quality'],'confirmed')

    def test_yellow_confirmado_escenario_simulado(self):
        t=MockTraci('y',300)
        o=O.EventObserver('toy',101,['B1']);o.observe(t);t.crossing();o.observe(t)
        self.assertEqual(o.stats()['signal_states'],{'yellow':1})

    def test_red_green_es_ambiguo(self):
        t=MockTraci('r',.75)
        o=O.EventObserver('toy',101,['B1']);o.observe(t);t.crossing('g');o.observe(t)
        self.assertEqual(o.stats()['signal_states'],{'unknown':1})
        self.assertEqual(o.rows[0]['reason'],'phase_change_between_snapshots')

    def test_yellow_con_cambio_programado_en_ventana(self):
        t=MockTraci('y',.75)
        o=O.EventObserver('toy',101,['B1']);o.observe(t);t.crossing('y');o.observe(t)
        self.assertEqual(o.stats()['signal_states'],{'unknown':1})
        self.assertEqual(o.rows[0]['reason'],'scheduled_switch_inside_interval')

    def test_guardas_no_dos_observaciones_en_mismo_paso(self):
        t=MockTraci();o=O.EventObserver('toy',101,['B1']);o.observe(t)
        with self.assertRaises(ValueError):o.observe(t)

    def test_auditoria_offline_distingue_ambiguedades(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'e.csv'
            with p.open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=O.FIELDS)
                w.writeheader()
                w.writerow({'event_type':'stopline','vehicle_id':'1','site_id':'B1','passage_id':'B1|1|1',
                    'signal_state':'unknown','classification_quality':'uncertain','phase_prev':'red',
                    'phase_current':'green','time_s':1,'lane_prev':'a','lane_current':'b'})
                w.writerow({'event_type':'stopline','vehicle_id':'2','site_id':'B1','passage_id':'B1|2|1',
                    'signal_state':'red','classification_quality':'confirmed','phase_prev':'red',
                    'phase_current':'red','time_s':2,'lane_prev':'a','lane_current':'b'})
            r=A.audit(p)
            self.assertEqual(r['stopline_events'],2)
            self.assertEqual(r['unknown_transitions'],{'red->green':1})
            self.assertEqual(r['classification'],{'unknown':1,'red':1})

    def test_zonas_desde_net_xml_sin_inventar_carriles(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'net.xml'
            p.write_text('''<net>
<edge id="W2C"><lane id="W2C_0" length="120" speed="13.89"/></edge>
<connection from="W2C" fromLane="0" to="C2E" toLane="0" tl="B1" linkIndex="0"/>
</net>''',encoding='utf-8')
            zones,_=Z.generate_zones(p,['B1'])
            self.assertEqual(len(zones),1)
            self.assertEqual(zones[0]['lane_id'],'W2C_0')
            self.assertEqual(zones[0]['from_m'],75)
            self.assertEqual(zones[0]['to_m'],105)

    def test_zonas_tls_ausentes_bloquea(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'net.xml';p.write_text('<net/>',encoding='utf-8')
            with self.assertRaises(ValueError):Z.generate_zones(p,['B1'])

if __name__=='__main__':unittest.main()
