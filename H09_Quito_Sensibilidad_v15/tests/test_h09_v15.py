from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

def mod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj
O=mod('h09_v15_obs',ROOT/'instrumentacion'/'observador_traci_h09_v11.py')
R=mod('h09_v15_report',ROOT/'scripts'/'reportar_h09_v15.py')
X=mod('h09_v15_runner',ROOT/'scripts'/'ejecutar_h09_v15.py')

class Simulation:
    def __init__(self,tr):self.tr=tr
    def getTime(self):return self.tr.time
    def getDeltaT(self):return .5
    def getCollidingVehiclesNumber(self):return 0
    def getStartingTeleportNumber(self):return 0
class Vehicle:
    def __init__(self,tr):self.tr=tr
    def getIDList(self):return ['x'] if self.tr.present else []
    def getLaneID(self,v):return self.tr.lane_name
    def getLanePosition(self,v):return self.tr.pos
    def getSpeed(self,v):return self.tr.speed
    def getNextTLS(self,v):return [('B1',0,self.tr.dist,self.tr.phase)] if self.tr.lane_name=='a' else []
    def setSpeed(self,*a):raise AssertionError('No mutar SUMO')
    def setSpeedMode(self,*a):raise AssertionError('No mutar SUMO')
class TLS:
    def __init__(self,tr):self.tr=tr
    def getRedYellowGreenState(self,site):return self.tr.phase
    def getNextSwitch(self,site):return 300
    def setRedYellowGreenState(self,*a):raise AssertionError('No mutar SUMO')
class TraCI:
    def __init__(self,phase='r',speed=10,dist=20):
        self.time=.5;self.phase=phase;self.speed=speed;self.dist=dist
        self.lane_name='a';self.pos=80;self.present=True
        self.vehicle=Vehicle(self);self.trafficlight=TLS(self)
        self.simulation=Simulation(self)
    def advance(self,phase=None,speed=None,dist=None,lane=None,present=None):
        self.time+=.5
        if phase is not None:self.phase=phase
        if speed is not None:self.speed=speed
        if dist is not None:self.dist=dist
        if lane is not None:self.lane_name=lane
        if present is not None:self.present=present

class TestH09V15(unittest.TestCase):
    def test_01_unica_exposicion_por_fase_y_episodio(self):
        t=TraCI('r',0);o=O.EventObserver('toy',101,['B1'])
        for _ in range(5):o.observe(t);t.advance()
        self.assertEqual(o.stats()['instrumentation_v15']['phase_exposures']['red'],1)
        self.assertEqual(o.stats()['instrumentation_v15']['moving_opportunities']['red'],0)
    def test_02_detener_y_mover_no_duplica_exposicion(self):
        t=TraCI('r',0);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        t.advance(speed=2);o.observe(t);t.advance();o.observe(t)
        self.assertEqual(o.stats()['instrumentation_v15']['phase_exposures']['red'],1)
        self.assertEqual(o.stats()['instrumentation_v15']['moving_opportunities']['red'],1)
    def test_03_separar_fases_mismo_episodio(self):
        t=TraCI('r',5);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        t.advance(phase='y');o.observe(t)
        self.assertEqual(o.stats()['instrumentation_v15']['moving_opportunities']['red'],1)
        self.assertEqual(o.stats()['instrumentation_v15']['moving_opportunities']['yellow'],1)
    def test_04_rojo_confirmado_y_enlace(self):
        t=TraCI('r',10,3);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        t.advance(lane=':B1_0',dist=0);o.observe(t)
        self.assertEqual(o.stats()['signal_states'],{'red':1})
        self.assertEqual(o.stats()['instrumentation_v15']['crossing_episode_links']['linked'],1)
        l=[r for r in o.rows if r['event_type']=='tls_crossing_link'][0]
        self.assertTrue(l['measurement_id'])
        self.assertEqual(l['signal_state'],'red')
    def test_05_unknown_no_se_vuelve_red(self):
        t=TraCI('r',10,3);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        t.advance(lane=':B1_0',phase='g');o.observe(t)
        self.assertEqual(o.stats()['signal_states'],{'unknown':1})
        l=[r for r in o.rows if r['event_type']=='tls_crossing_link'][0]
        self.assertEqual(l['classification_quality'],'uncertain')
    def test_06_no_inventa_cruce_sin_transicion(self):
        t=TraCI('r',5);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        t.advance();o.observe(t)
        self.assertEqual(o.stats()['stopline_events'],0)
    def test_07_si_fue_lejos_no_inventa_denominador(self):
        t=TraCI('r',25,50);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        t.advance(lane=':B1_0');o.observe(t)
        self.assertEqual(o.stats()['instrumentation_v15']['phase_exposures']['red'],0)
        # Cruce antiguo puede existir; debe quedar sin enlace operacional.
        self.assertEqual(o.stats()['instrumentation_v15']['crossing_episode_links'].get('linked',0),0)
    def test_08_exposicion_fura_radio_excluida(self):
        t=TraCI('r',3,35);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        self.assertEqual(o.stats()['instrumentation_v15']['moving_opportunities']['red'],0)
    def test_09_umbral_movimiento(self):
        t=TraCI('r',.99);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        self.assertEqual(o.stats()['instrumentation_v15']['moving_opportunities']['red'],0)
        t.advance(speed=1.0);o.observe(t)
        self.assertEqual(o.stats()['instrumentation_v15']['moving_opportunities']['red'],1)
    def test_10_visita_repetida_es_otro_episodio(self):
        t=TraCI('r',3);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        t.advance(dist=45);o.observe(t)
        t.advance(dist=20);o.observe(t)
        self.assertEqual(o.stats()['instrumentation_v15']['moving_opportunities']['red'],2)
    def test_11_mismo_paso_rechazado(self):
        t=TraCI('r',5);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        with self.assertRaises(ValueError):o.observe(t)
    def test_12_escribir_csv_compatible_con_v11(self):
        t=TraCI('r',2);o=O.EventObserver('toy',101,['B1']);o.observe(t)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'events.csv'
            o.write_csv(path)
            rows=R.readcsv(path)
            self.assertEqual(len(rows),2)
            self.assertEqual(set(rows[0]),set(O.FIELDS))
            with self.assertRaises(FileExistsError):o.write_csv(path)
    def test_13_cohortes_anidadas_validas(self):
        data=[]
        for seed in R.SEEDS:
            for pct in R.PCTS:
                ids=list(range(pct*3))
                data.append({'seed':seed,'pct':pct,'core_hashes':{'net':'x'},'selected_ids':ids,
                    'arrivals':90+seed%2,'red_crossings':0,'yellow_crossings':0,'unknown_crossings':0,
                    'moving_red_selected':0,'moving_yellow_selected':0,'n_verified':len(ids),'n_assigned':len(ids),
                    'n_selected_seen':len(ids),'n_selected_never_seen':0,'n_crossings':0,'n_roster':300,
                    'moving_red_all':0,'moving_yellow_all':0,'exposure_red_all':0,'exposure_yellow_all':0,
                    'exposure_red_selected':0,'exposure_yellow_selected':0,'linked_red_selected':0,
                    'linked_yellow_selected':0,'red_cross_not_linked_to_moving_candidate':0,
                    'yellow_cross_not_linked_to_moving_candidate':0,'unlinked_crossing_episodes':0,
                    'mean_speed_kmh':40,'mean_halted':8,'traffic_sha256':'abc'})
        result=R.summarize(data)
        self.assertEqual(len(result['summary']),4)
        self.assertEqual(result['status'],'H09_V15_SENSITIVITY_DESCRIPTIVE_NOT_QUITO_CALIBRATED')
    def test_14_cohortes_no_anidadas_rechazadas(self):
        data=[]
        for seed in R.SEEDS:
            for pct in R.PCTS:
                ids=list(range(pct*3))
                if seed==101 and pct==30:ids=list(range(100,190))
                data.append({'seed':seed,'pct':pct,'core_hashes':{'a':1},'selected_ids':ids,
                    'arrivals':1,'mean_speed_kmh':1,'mean_halted':1,'red_crossings':0,
                    'yellow_crossings':0,'unknown_crossings':0,'moving_red_selected':0,
                    'moving_yellow_selected':0,'n_verified':len(ids),'n_assigned':len(ids),
                    'n_selected_seen':0,'n_selected_never_seen':0,'n_crossings':0,'n_roster':300,
                    'moving_red_all':0,'moving_yellow_all':0,'exposure_red_all':0,'exposure_yellow_all':0,
                    'exposure_red_selected':0,'exposure_yellow_selected':0,'linked_red_selected':0,
                    'linked_yellow_selected':0,'red_cross_not_linked_to_moving_candidate':0,
                    'yellow_cross_not_linked_to_moving_candidate':0,'unlinked_crossing_episodes':0,
                    'traffic_sha256':'x'})
        with self.assertRaisesRegex(ValueError,'anidadas'):R.summarize(data)
    def test_15_commandos_correctos_y_rutas_nuevas(self):
        with tempfile.TemporaryDirectory() as d:
            p=X.get_paths(d);path,argv=X.cmd_for(p,101,30)
            self.assertTrue(str(path).endswith('active_30_combinado'))
            self.assertEqual(argv[argv.index('--porcentaje')+1],'30')
            self.assertIn('ESCENARIO_EXPLORATORIO_NO_CALIBRADO',argv)
    def test_16_sin_ack_no_procede_a_ejecutar(self):
        with self.assertRaises(SystemExit):X.main(['--root','/nonexistent','--ejecutar-corridas'])
    def test_17_preflight_bloquea_faltantes(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):X.preflight(X.get_paths(d))
    def test_18_no_rescribe_informe(self):
        with tempfile.TemporaryDirectory() as d:
            prefix=Path(d)/'old.json';prefix.write_text('{}')
            self.assertTrue(prefix.exists())
            # Reportar no debe sobrescribir un archivo preexistente.
            self.assertEqual(prefix.read_text(),'{}')


class TestScanRun(unittest.TestCase):
    def _fixture(self,d,pct=15):
        import json,csv
        d=Path(d);src=d/'inputs';src.mkdir();out=d/'newrun';out.mkdir();old=d/'old';old.mkdir()
        core={}
        for filename in ('micro.sumocfg','micro.net.xml','micro.rou.xml','profile.json'):
            f=src/filename;f.write_text(filename,encoding='utf-8');core[str(f)]=R.digest(f)
        assigned=set(str(x) for x in range(pct*3))
        with (out/'cohorte_h09.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=['vehicle_id','expected_depart_s','assigned','profile']);w.writeheader()
            for x in range(300):w.writerow({'vehicle_id':str(x),'expected_depart_s':x,
                'assigned':int(str(x) in assigned),'profile':'combinado' if str(x) in assigned else 'nominal'})
        with (out/'exposicion_h09.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=['vehicle_id','seen','profile_verified']);w.writeheader()
            for v in sorted(assigned):w.writerow({'vehicle_id':v,'seen':1,'profile_verified':1})
        with (out/'trafico_h09.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=['arrivals_step','mean_speed_kmh','n_halted']);w.writeheader()
            for x in range(600):w.writerow({'arrivals_step':int(x==599),'mean_speed_kmh':40,'n_halted':8})
        with (out/'eventos_h09.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(O.FIELDS));w.writeheader()
            ep='h09ep|0|B1|0|1'
            common={'vehicle_id':'0','site_id':'B1','measurement_id':ep,'signal_state':'red','time_s':1,
                    'classification_quality':'observed_snapshot','passage_id':ep+'|tls_phase_exposure|red'}
            w.writerow({**common,'event_type':'tls_phase_exposure'})
            w.writerow({**common,'event_type':'tls_moving_opportunity','passage_id':ep+'|tls_moving_opportunity|red'})
            w.writerow({**common,'event_type':'stopline','passage_id':'B1|0|1','measurement_id':'',
                        'classification_quality':'confirmed'})
            w.writerow({**common,'event_type':'tls_crossing_link','passage_id':'B1|0|1',
                        'classification_quality':'confirmed'})
        gen={str(out/n):R.digest(out/n) for n in ('cohorte_h09.csv','exposicion_h09.csv','trafico_h09.csv','eventos_h09.csv')}
        sha=gen[str(out/'trafico_h09.csv')]
        man={'status':'SUMO_EXECUTED_EXPLORATORY','mode':'baseline' if pct==0 else 'active',
            'seed':101,'porcentaje_solicitado':pct,'pasos_requested':600,'step_length_s':.5,
            'original_hashes_sha256':core,'generated_hashes_sha256':gen,'traffic_sha256':sha,
            'exposure_summary':{'n_selected_seen':len(assigned)},'instrumental_stats':{'stopline_events':1}}
        (out/'manifest_H09.json').write_text(json.dumps(man),encoding='utf-8')
        (old/'manifest_H09.json').write_text(json.dumps({'traffic_sha256':sha}),encoding='utf-8')
        return out,old

    def test_19_scan_registra_denominadores_y_enlace(self):
        with tempfile.TemporaryDirectory() as d:
            out,old=self._fixture(d,15)
            data=R.scan_run(out,101,15,old)
            self.assertEqual(data['n_assigned'],45)
            self.assertEqual(data['moving_red_selected'],1)
            self.assertEqual(data['exposure_red_selected'],1)
            self.assertEqual(data['linked_red_selected'],1)
            self.assertEqual(data['red_crossings'],1)

    def test_20_scan_hash_original_diferente_bloquea(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            out,old=self._fixture(d,15)
            (old/'manifest_H09.json').write_text(json.dumps({'traffic_sha256':'no-coincide'}))
            with self.assertRaisesRegex(ValueError,'modificó el tráfico'):
                R.scan_run(out,101,15,old)

    def test_21_scan_archivo_generado_alterado_bloquea(self):
        with tempfile.TemporaryDirectory() as d:
            out,old=self._fixture(d,15)
            with (out/'eventos_h09.csv').open('a') as f:f.write('CORRUPTED\n')
            with self.assertRaisesRegex(ValueError,'alterado'):
                R.scan_run(out,101,15,old)

    def test_22_baseline_instrumentado_aceptado(self):
        with tempfile.TemporaryDirectory() as d:
            out,old=self._fixture(d,0)
            dat=R.scan_run(out,101,0,old)
            self.assertEqual(dat['n_assigned'],0)
            self.assertEqual(dat['moving_red_selected'],0)
            self.assertEqual(dat['moving_red_all'],1)

if __name__=='__main__':unittest.main()
