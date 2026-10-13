from __future__ import annotations
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'analizar_comparacion_h09_v12.py'
spec=importlib.util.spec_from_file_location('cmp_h09',SCRIPT)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class TestComparadorH09V12(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def make_run(self,mode,sha='same',orig='sources'):
        p=self.root/mode;p.mkdir()
        man={'status':'SUMO_EXECUTED_EXPLORATORY','mode':mode,'porcentaje_solicitado':0,'familia':'combinado',
             'seed':101,'traffic_sha256':sha,'original_hashes_sha256':{'cfg':orig},
             'exposure_summary':{'n_assigned':0,'n_selected_seen':0,'n_selected_verified_vtype':0}}
        (p/'manifest_H09.json').write_text(json.dumps(man))
        with (p/'trafico_h09.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['mean_speed_kmh','n_halted','arrivals_step','collisions_step','teleports_start_step'])
            w.writeheader();w.writerow({'mean_speed_kmh':40,'n_halted':8,'arrivals_step':1,'collisions_step':0,'teleports_start_step':0})
        with (p/'eventos_h09.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=['event_type','signal_state','classification_quality','speed_mps','limit_mps'])
            w.writeheader();w.writerow({'event_type':'stopline','signal_state':'unknown','classification_quality':'uncertain','speed_mps':'','limit_mps':''})
        return p

    def test_baseline_probe_identicos(self):
        b=self.make_run('baseline');p=self.make_run('probe')
        r=mod.compare([b,p]);self.assertEqual(len(r),2)
        self.assertEqual(r[0]['cross_unknown'],1)
        self.assertEqual(r[1]['delta_speed_kmh_vs_baseline'],0)

    def test_probe_diferente_bloquea(self):
        b=self.make_run('baseline');p=self.make_run('probe','other')
        with self.assertRaises(ValueError):mod.compare([b,p])

    def test_original_distinto_bloquea(self):
        b=self.make_run('baseline');p=self.make_run('probe',orig='mutated')
        with self.assertRaises(ValueError):mod.compare([b,p])

if __name__=='__main__':unittest.main()
