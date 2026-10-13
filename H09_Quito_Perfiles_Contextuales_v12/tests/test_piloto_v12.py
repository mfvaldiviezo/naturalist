from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

MOD=Path(__file__).resolve().parents[1]/'scripts'/'piloto_perfiles_h09_v12.py'
sp=importlib.util.spec_from_file_location('piloto_h09',MOD)
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)

CONFIG=Path(__file__).resolve().parents[1]/'config'/'escenarios_exploratorios.json'

class TestH09V12(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.net=self.root/'net.xml';self.net.write_text('<net/>',encoding='utf8')
        self.routes=self.root/'routes.rou.xml'
        self.routes.write_text('<routes>'+''.join(f'<vehicle id="{i}" depart="{i}"><route edges="a b"/></vehicle>' for i in range(300))+'</routes>',encoding='utf8')
        self.cfg=self.root/'config.sumocfg'
        self.cfg.write_text('<configuration><input><net-file value="net.xml"/><route-files value="routes.rou.xml"/></input></configuration>',encoding='utf8')

    def test_cohort_exact_and_nested(self):
        _,r,_=m.read_roster(self.routes,300)
        a=m.exact_selection(r,15,101);b=m.exact_selection(r,30,101);c=m.exact_selection(r,50,101)
        self.assertEqual([len(a),len(b),len(c)],[45,90,150]);self.assertTrue(a<b<c)

    def test_cohort_invariant_order(self):
        _,r,_=m.read_roster(self.routes,300)
        self.assertEqual(m.exact_selection(r,30,101),m.exact_selection(reversed(r),30,101))

    def test_no_sumo_config_edits_and_300_s(self):
        cfg,net,routes=m.original_inputs(self.cfg)
        self.assertEqual(net,self.net);self.assertEqual(routes,self.routes)
        _,r,e=m.read_roster(routes,300)
        self.assertEqual(len(e),300);self.assertEqual(len(r),300)
        self.assertEqual(m.hash_file(cfg),m.hash_file(self.cfg))

    def test_route_copy_only_selected(self):
        root,roster,explicit=m.read_roster(self.routes,300)
        selected=m.exact_selection(roster,30,101)
        original_sha=m.hash_file(self.routes)
        output=self.root/'new.rou.xml'
        profile=json.loads(CONFIG.read_text())['families']['combinado']
        m.clone_route(root,explicit,selected,profile,output)
        self.assertEqual(original_sha,m.hash_file(self.routes))
        n=ET.parse(output).getroot()
        self.assertEqual(len(n.findall('vehicle')),300)
        changed={v.get('id') for v in n.findall('vehicle') if v.get('type')=='H09_EXPLORATORIO_V12'}
        self.assertEqual(selected,changed)
        for v in n.findall('vehicle'):
            self.assertEqual(v.find('route').get('edges'),'a b')
            self.assertEqual(v.get('depart'),v.get('id'))
        typ=n.find('vType')
        self.assertEqual(typ.get('jmDriveAfterRedTime'),'0.5')
        self.assertEqual(typ.get('jmIgnoreKeepClearTime'),'0.0')

    def test_no_missing_tag_or_extra_additional(self):
        self.cfg.write_text('<configuration><input><net-file value="net.xml"/><route-files value="routes.rou.xml"/><additional-files value="extra.xml"/></input></configuration>',encoding='utf8')
        with self.assertRaises(ValueError):m.original_inputs(self.cfg)

    def test_unsupported_flow_fail_closed(self):
        self.routes.write_text('<routes><flow id="a" begin="0" end="10" number="3" from="a" to="b"/></routes>',encoding='utf8')
        with self.assertRaises(ValueError):m.read_roster(self.routes,10)

    def test_no_nondefault_vtype_overwrite(self):
        self.routes.write_text('<routes><vType id="bus" vClass="bus"/><vehicle id="v" type="bus" depart="0"><route edges="a b"/></vehicle></routes>',encoding='utf8')
        root,roster,vehicles=m.read_roster(self.routes,300)
        with self.assertRaises(ValueError):m.clone_route(root,vehicles,{'v'},{'tau':.9},self.root/'bad.rou.xml')

    def test_parameters_reject_arbitrary(self):
        for wrong in ({'jmIgnoreFoeProb':.75},{'jmDriveAfterRedTime':55.0},{'tau':.1},{}):
            with self.assertRaises(ValueError):m.validate_profile(wrong)

    def test_source_cannot_claim_quito_calibration(self):
        config=json.loads(CONFIG.read_text(encoding='utf8'))
        self.assertEqual(config['evidence_status'],'EXPLORATORY_HYPOTHESES_NOT_CALIBRATED_QUITO')
        self.assertNotIn('probabilidad_cruce_rojo_quito',config)

    def test_event_observed_vs_type_exposure(self):
        selected={'a','b'}; seen={'a','b'};verified={'a'}
        rows=[{'vehicle_id':'a','event_type':'stopline','signal_state':'red','classification_quality':'confirmed'},
              {'vehicle_id':'b','event_type':'stopline','signal_state':'red','classification_quality':'uncertain'},
              {'vehicle_id':'a','event_type':'speed','speed_mps':'14','limit_mps':'13'}]
        summary,pr=m.summarize_profiles(selected,seen,verified,rows,{},[],10)
        self.assertEqual(summary['n_assigned'],2)
        self.assertEqual(summary['n_selected_verified_vtype'],1)
        self.assertEqual(summary['candidate_events_observed']['cross_red'],1)
        self.assertEqual(summary['candidate_events_observed']['speeding_sample'],1)
        self.assertEqual(summary['n_selected_with_observed_red_cross'],1)

    def test_guard_no_overwrite_original_route(self):
        root,roster,vehicles=m.read_roster(self.routes,300)
        destination=self.root/'exists';destination.write_text('preserve')
        with self.assertRaises(FileExistsError):m.clone_route(root,vehicles,{'0'},{'tau':.9},destination)
        self.assertEqual(destination.read_text(),'preserve')

if __name__=='__main__':unittest.main()
