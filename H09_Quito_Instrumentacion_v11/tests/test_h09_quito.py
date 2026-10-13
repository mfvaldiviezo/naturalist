from __future__ import annotations
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

C=module('calibrador_quito_h09',ROOT/'scripts'/'calibrador_quito_h09.py')
O=module('observador_traci_h09',ROOT/'scripts'/'observador_traci_h09.py')
PROTO=ROOT/'config'/'protocolo_hangzhou_ejemplo.json'


def write_rows(path,rows):
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=O.FIELDS)
        w.writeheader()
        w.writerows(rows)


def event(i,color,site='B1', run='test'):
    return {'run_id':run,'seed':'101','vehicle_id':f'car{i}',
        'site_id':site,'passage_id':f'{site}|car{i}|1','event_type':'stopline',
        'signal_state':color,'classification_quality':'confirmed' if color!='unknown' else 'uncertain',
        'speed_mps':8,'limit_mps':'','measurement_id':'','time_s':i,
        'observation_method':'TEST_SYNTHETIC','distance_prev_m':1,
        'phase_prev':color,'phase_current':color,'lane_prev':'a','lane_current':'b','reason':''}

class FakeSim:
    def __init__(self,p):self.p=p
    def getTime(self):return self.p.t
    def getDeltaT(self):return 0.5
    def getCollidingVehiclesNumber(self):return 0
    def getStartingTeleportNumber(self):return 0

class FakeVeh:
    def __init__(self,p):self.p=p
    def getIDList(self):return ['0']
    def getLaneID(self,x):return self.p.lane_id
    def getLanePosition(self,x):return self.p.pos
    def getSpeed(self,x):return 10
    def getNextTLS(self,x):
        return [('B1',0,self.p.dist,'r')] if self.p.t<=0.5 else []
    def setSpeedMode(self,*a):raise AssertionError('prohibido')
    def setSpeed(self,*a):raise AssertionError('prohibido')
    def setAcceleration(self,*a):raise AssertionError('prohibido')

class FakeLights:
    def getRedYellowGreenState(self,x):return 'r'

class FakeLane:
    def getMaxSpeed(self,x):return 13.9

class FakeTraci:
    def __init__(self):
        self.t=0.5;self.lane_id='B0B1_0';self.pos=95;self.dist=4
        self.simulation=FakeSim(self);self.vehicle=FakeVeh(self)
        self.trafficlight=FakeLights();self.lane=FakeLane()

class TestH09Quito(unittest.TestCase):
    def test_01_fuentes_correctas(self):
        data=C.validate_sources()
        self.assertEqual(sum(s['n_observed_vehicles'] for s in data['numerical_targets']['signal_stopline_events'].values()),9643)
        self.assertEqual(sum(s['n_red_cross_events'] for s in data['numerical_targets']['signal_stopline_events'].values()),343)
        self.assertTrue(all(v is None for v in data['individual_decision_probabilities'].values()))

    def test_02_respetar_fuente_no_traspasar_probabilidades(self):
        p=C.read_protocol(PROTO)
        self.assertEqual(p['network_role'],'Hangzhou_pilot')
        self.assertEqual(p['source_population_compatibility'],'proxy_only')

    def test_03_duplicados_rechazados(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.csv';a=event(1,'red');write_rows(path,[a,a])
            with self.assertRaises(C.AuditError):C.read_events(path)

    def test_04_agregados_y_cautela(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.csv'
            rows=[event(i,'red' if i<10 else ('yellow' if i<20 else 'green')) for i in range(100)]
            write_rows(path,rows)
            report=C.summary_object(path,PROTO)
            qui1=next(x for x in report['site_metrics'] if x['reference_site_id']=='QUI-1')
            self.assertEqual(qui1['n_simulated_passages'],100)
            self.assertAlmostEqual(qui1['simulated_rates']['red'],0.1)
            self.assertEqual(qui1['validation_status'],'DESCRIPTIVE_ONLY')
            self.assertIn('observation_protocol_not_harmonized',qui1['restrictions'])
            self.assertEqual(report['individual_decision_parameters']['run_red_given_red_opportunity'],None)

    def test_05_no_contar_ambiguos_como_verdes(self):
        rows=[event(i,'unknown') for i in range(5)]+[event(i,'red') for i in range(5,100)]
        data=C.aggregate(rows,C.read_protocol(PROTO),C.validate_sources())
        qui1=next(x for x in data[0] if x['reference_site_id']=='QUI-1')
        self.assertEqual(qui1['n_simulated_uncertain'],5)
        self.assertEqual(qui1['simulated_rates']['red'],0.95)
        self.assertIn('insufficient_classification_coverage',qui1['restrictions'])

    def test_06_rechazar_documented_sin_prueba(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=json.loads(PROTO.read_text(encoding='utf-8'))
            p['source_population_compatibility']='documented_harmonized'
            path=Path(tmp)/'proto.json';path.write_text(json.dumps(p),encoding='utf-8')
            with self.assertRaises(C.AuditError):C.read_protocol(path)

    def test_07_observador_registra_cruce_sin_cambiar_Sumo(self):
        traci=FakeTraci()
        obs=O.EventObserver('test',101,['B1'])
        obs.observe(traci)
        traci.t=1.0;traci.lane_id=':B1_0';traci.pos=0;traci.dist=0
        obs.observe(traci)
        self.assertEqual(obs.stats()['stopline_events'],1)
        self.assertEqual(obs.rows[0]['signal_state'],'red')
        self.assertEqual(obs.rows[0]['classification_quality'],'confirmed')
        with self.assertRaises(ValueError):obs.observe(traci)

    def test_08_cambio_fase_ambiguo(self):
        traci=FakeTraci();obs=O.EventObserver('test',101,['B1'])
        obs.observe(traci)
        traci.t=1.0;traci.lane_id=':B1_0';traci.trafficlight.getRedYellowGreenState=lambda x:'y'
        obs.observe(traci)
        self.assertEqual(obs.rows[0]['signal_state'],'unknown')
        self.assertEqual(obs.rows[0]['classification_quality'],'uncertain')

    def test_09_nadie_desaparece_y_se_cuenta_como_cruce(self):
        traci=FakeTraci();obs=O.EventObserver('test',101,['B1'])
        obs.observe(traci)
        traci.t=1.0;traci.vehicle.getIDList=lambda:[]
        obs.observe(traci)
        self.assertEqual(obs.stats()['stopline_events'],0)
        self.assertEqual(obs.stats()['unresolved_vehicle_departures'],1)

    def test_10_score_descriptivo_no_calibracion(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);events=tmp/'events.csv'
            rows=[event(i,'red' if i%10==0 else 'green') for i in range(100)]
            rows+=[event(i,'green','B2') for i in range(100)]
            rows+=[event(i,'green','C1') for i in range(100)]
            write_rows(events,rows)
            manifest=tmp/'candidatos.csv'
            with manifest.open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=['escenario','seed','eventos']);w.writeheader()
                w.writerow({'escenario':'SYNTHETIC_NOT_REAL','seed':101,'eventos':events.name})
            output=tmp/'scores.json'
            obj=C.compare_candidates(manifest,PROTO,output)
            self.assertEqual(obj['comparison_status'],'ONLY_DESCRIPTIVE_CANDIDATE_COMPARISON')
            self.assertFalse(obj['scenario_summary'][0]['calibration_eligible'])

    def test_11_speed_sample_unico(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=[event(1,'green')]
            a=event(2,'green');a.update(event_type='speed',site_id='B0B1_0',
                measurement_id='station_A',speed_mps='16',limit_mps='13')
            a2=a.copy();a2['passage_id']='station_A|car2|repeat'
            path=Path(tmp)/'events.csv';write_rows(path,rows+[a,a2])
            with self.assertRaises(C.AuditError):C.summary_object(path,PROTO)

if __name__=='__main__':unittest.main()
