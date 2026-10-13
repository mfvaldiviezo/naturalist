# -*- coding: utf-8 -*-
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fact',ROOT/'scripts'/'comparar_factorial_h09_v13.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
spec2=importlib.util.spec_from_file_location('prep',ROOT/'scripts'/'preparar_factorial_h09_v13.py')
prep=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(prep)


def write_csv(path,columns,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)

class H09Factorial(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.mk_runs()

    def tearDown(self):self.temp.cleanup()

    def mk_runs(self):
        self.cohort={str(x) for x in range(45)}
        traffic_rows=[{'step':i,'mean_speed_kmh':40,'n_halted':8,'arrivals_step':1 if i<10 else 0,
                       'collisions_step':0,'teleports_start_step':0} for i in range(12)]
        event_rows=[{'event_type':'stopline','signal_state':'green','classification_quality':'confirmed','vehicle_id':'0',
                    'speed_mps':'','limit_mps':''},
                    {'event_type':'stopline','signal_state':'unknown','classification_quality':'uncertain','vehicle_id':'1',
                    'speed_mps':'','limit_mps':''},
                    {'event_type':'speed','signal_state':'','classification_quality':'','vehicle_id':'2',
                    'speed_mps':12,'limit_mps':10}]
        for label,folder in mod.RUNS.items():
            dest=self.root/folder;dest.mkdir()
            write_csv(dest/'trafico_h09.csv',list(traffic_rows[0]),traffic_rows)
            write_csv(dest/'eventos_h09.csv',list(event_rows[0]),event_rows)
            write_csv(dest/'cohorte_h09.csv',['vehicle_id','assigned'],
                      [{'vehicle_id':str(i),'assigned':'1' if label not in ('baseline','probe') and str(i) in self.cohort else '0'} for i in range(300)])
            original={'C:/same/scenario.sumocfg':'a'*64,'C:/same/net.net.xml':'b'*64,
                      'C:/same/routes.rou.xml':'c'*64,
                      'C:/vary/'+label+'.json':label}
            output={str(dest/name):mod.sha_file(dest/name) for name in ('trafico_h09.csv','eventos_h09.csv','cohorte_h09.csv')}
            manifest={
                'status':'SUMO_EXECUTED_EXPLORATORY',
                'mode':'baseline' if label=='baseline' else 'probe' if label=='probe' else 'active',
                'seed':101,'porcentaje_solicitado':0 if label in ('baseline','probe') else 15,
                'profile_parameters':mod.EXPECTED_PARAMS.get(label),
                'original_hashes_sha256':original,
                'generated_hashes_sha256':output,
                'exposure_summary':{'n_assigned':0 if label in ('baseline','probe') else 45,
                                    'n_roster':300,'n_selected_verified_vtype':0 if label in ('baseline','probe') else 45,
                                    'n_selected_seen':0 if label in ('baseline','probe') else 45},
                'traffic_sha256':mod.sha_file(dest/'trafico_h09.csv')
            }
            (dest/'manifest_H09.json').write_text(json.dumps(manifest),encoding='utf-8')

    def manifest(self,label):
        p=self.root/mod.RUNS[label]/'manifest_H09.json'
        return p,json.loads(p.read_text())

    def test_01_control_hashes_sondeo_y_placebo_identicos(self):
        result=mod.compare(self.root)
        self.assertEqual(result['status'],'PLACEBO_BITWISE_IDENTICAL')
        self.assertEqual(result['cohort_n'],45)
        self.assertEqual(len(result['rows']),7)

    def test_02_perfiles_generan_json_no_empiricos(self):
        folder=self.root/'config';folder.mkdir()
        paths=prep.configs(folder)
        self.assertEqual(set(paths),set(prep.PARAMS))
        for n,p in paths.items():
            cfg=json.loads(p.read_text())
            self.assertEqual(cfg['evidence_status'],prep.ACK)
            self.assertEqual(cfg['families']['combinado'],prep.PARAMS[n])
        with self.assertRaises(FileExistsError):prep.configs(folder)

    def test_03_cambia_solamente_config_perfiles_no_bloquea(self):
        self.assertEqual(len({tuple(sorted(mod.read_run(self.root,n)['core_hashes'].items())) for n in mod.RUNS}),1)

    def test_04_rechazar_red_unknown_confirmada(self):
        events=[{'event_type':'stopline','signal_state':'unknown','classification_quality':'confirmed'}]
        with self.assertRaises(ValueError):mod.metrics([{'mean_speed_kmh':40,'n_halted':0,'arrivals_step':0,'collisions_step':0,'teleports_start_step':0}],events)

    def test_05_detectar_sha_entrada_diferente(self):
        p,m=self.manifest('SV')
        m['original_hashes_sha256']['C:/same/net.net.xml']='different'
        p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'Entradas originales'):mod.compare(self.root)

    def test_06_rechazar_cohorte_distinta(self):
        path=self.root/mod.RUNS['V']/'cohorte_h09.csv'
        rows=mod.rows_from(path)
        rows[0]['assigned']='0';rows[46]['assigned']='1'
        write_csv(path,list(rows[0]),rows)
        p,m=self.manifest('V');m['generated_hashes_sha256'][str(path)]=mod.sha_file(path)
        p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'Cohortes'):mod.compare(self.root)

    def test_07_bloquea_probe_no_identico(self):
        p,m=self.manifest('probe');m['traffic_sha256']='wrong';p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'Hash traffic manifest'):mod.compare(self.root)

    def test_08_rechaza_archivo_modificado(self):
        path=self.root/mod.RUNS['S']/'eventos_h09.csv'
        path.write_text('alterado')
        with self.assertRaisesRegex(ValueError,'Archivo generado modificado'):mod.compare(self.root)

    def test_09_placebo_diferente_advierte_pero_no_inventa_calibracion(self):
        path=self.root/mod.RUNS['placebo']/'trafico_h09.csv'
        rows=mod.rows_from(path);rows[0]['n_halted']='12'
        write_csv(path,list(rows[0]),rows)
        p,m=self.manifest('placebo');newhash=mod.sha_file(path)
        m['generated_hashes_sha256'][str(path)]=newhash;m['traffic_sha256']=newhash
        p.write_text(json.dumps(m))
        r=mod.compare(self.root)
        self.assertEqual(r['status'],'PLACEBO_DIFFERS_FROM_BASELINE_IN_TRAFFIC_SHA256')

    def test_10_red_inferior_superior_ambiguedad(self):
        t=[{'mean_speed_kmh':40,'n_halted':0,'arrivals_step':0,'collisions_step':0,'teleports_start_step':0}]
        events=[{'event_type':'stopline','signal_state':'red','classification_quality':'confirmed'},
                {'event_type':'stopline','signal_state':'unknown','classification_quality':'uncertain'},
                {'event_type':'stopline','signal_state':'green','classification_quality':'confirmed'}]
        m=mod.metrics(t,events)
        self.assertAlmostEqual(m['red_rate_proxy_lower_pct'],33.333333,places=5)
        self.assertAlmostEqual(m['red_rate_proxy_upper_pct'],66.666667,places=5)

    def test_11_interaccion_placebo_cero_cuando_identicos(self):
        r=mod.compare(self.root)
        self.assertEqual(r['exploratory_factorial_interaction']['arrivals'],0)
        self.assertEqual(r['exploratory_factorial_interaction']['red_confirmed'],0)

if __name__=='__main__':unittest.main()
