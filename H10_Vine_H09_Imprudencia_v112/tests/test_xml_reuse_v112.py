import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
import xml.etree.ElementTree as ET

RUNNER=Path(__file__).resolve().parents[1]/'scripts'/'piloto_hibrido_h10.py'
spec=importlib.util.spec_from_file_location('h10_v112_regression',RUNNER)
h10=importlib.util.module_from_spec(spec);spec.loader.exec_module(h10)

class FakeH09:
    @staticmethod
    def read_roster(file,horizon):
        root=ET.parse(file).getroot()
        explicit=[(x.attrib['id'],float(x.attrib['depart']),x) for x in root.findall('vehicle')]
        return root,[x[0] for x in explicit],explicit
    @staticmethod
    def clone_route(root,explicit,selected,profile,path):
        root.insert(0,ET.Element('vType',{'id':'H09_EXPLORATORIO_V12','tau':str(profile['tau'])}))
        for vid,t,vehicle in explicit:
            if vid in selected:vehicle.set('type','H09_EXPLORATORIO_V12')
        ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return path

class H10XmlAndLegacy(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.original=self.root/'routes.rou.xml'
        self.original.write_text('<routes><vehicle id="0" depart="0"/><vehicle id="1" depart="1"/><vehicle id="2" depart="2"/></routes>',encoding='utf-8')
    def test_01_reproduces_old_double_parse_failure(self):
        tree=ET.parse(self.original).getroot()
        _,roster,explicit=FakeH09.read_roster(self.original,300)
        f=self.root/'old.rou.xml'
        FakeH09.clone_route(tree,explicit,{'1'},{'tau':0.9},f)
        with self.assertRaisesRegex(RuntimeError,'no asigna H09'):
            h10.verify_route_assignment(f,roster,{'1'})
    def test_02_fixed_one_tree(self):
        tree,roster,explicit=FakeH09.read_roster(self.original,300)
        f=self.root/'new.rou.xml'
        FakeH09.clone_route(tree,explicit,{'1'},{'tau':0.9},f)
        audit=h10.verify_route_assignment(f,roster,{'1'})
        self.assertEqual(audit['assigned_xml'],1)
        self.assertEqual([x.get('type') for x in ET.parse(f).getroot().findall('vehicle')],[None,'H09_EXPLORATORIO_V12',None])
    def test_03_detect_45_expected_0_written(self):
        tree,roster,explicit=FakeH09.read_roster(self.original,300)
        f=self.root/'wrong.rou.xml'
        FakeH09.clone_route(tree,[],{'1'},{'tau':0.9},f)
        with self.assertRaises(RuntimeError):h10.verify_route_assignment(f,roster,{'1'})
    def test_04_reject_injected_extra(self):
        tree,roster,explicit=FakeH09.read_roster(self.original,300)
        f=self.root/'extra.rou.xml'
        FakeH09.clone_route(tree,explicit,{'0','1'},{'tau':0.9},f)
        with self.assertRaises(RuntimeError):h10.verify_route_assignment(f,roster,{'1'})
    def test_05_legacy_manifest_verified_not_rewritten(self):
        loc=self.root/'resultados/h10_vine_h09_imprudencia_v111_piloto_101/nominal'
        loc.mkdir(parents=True)
        csv=loc/'trafico_h09.csv';csv.write_text('sample\n')
        manifest={'mode':'nominal','status':h10.LEGACY_STATUS,'source_sha256':{'test':'test'},
            'seed':101,'steps':600,'dt':.5,'bridge_sha256':h10.LEGACY_BRIDGE_SHA256,
            'vine_guard_policy':None,'historical_traffic_identical':True,
            'output_sha256':{'trafico_h09.csv':h10.sha256(csv)}}
        f=loc/'manifest_h10.json';f.write_text(json.dumps(manifest))
        before=h10.sha256(f)
        complete,origins=h10.inspect_previous(h10.get_paths(self.root),['nominal'],{'test':'test'},101,.5,600)
        self.assertIn('nominal',complete)
        self.assertEqual(origins['nominal']['source'],'v111_verified_readonly')
        self.assertEqual(h10.sha256(f),before)
    def test_06_legacy_wrong_bridge_rejected(self):
        loc=self.root/'resultados/h10_vine_h09_imprudencia_v111_piloto_101/nominal';loc.mkdir(parents=True)
        f=loc/'trafico_h09.csv';f.write_text('x')
        man={'mode':'nominal','status':h10.LEGACY_STATUS,'source_sha256':{},'seed':101,'steps':600,'dt':.5,
             'bridge_sha256':'bad','vine_guard_policy':None,'historical_traffic_identical':True,
             'output_sha256':{'trafico_h09.csv':h10.sha256(f)}}
        (loc/'manifest_h10.json').write_text(json.dumps(man))
        with self.assertRaises(RuntimeError):h10.inspect_previous(h10.get_paths(self.root),['nominal'],{},101,.5,600)
    def test_07_legacy_partial_h09_not_reused(self):
        loc=self.root/'resultados/h10_vine_h09_imprudencia_v111_piloto_101/h09';loc.mkdir(parents=True)
        complete,origins=h10.inspect_previous(h10.get_paths(self.root),['h09'],{},101,.5,600)
        self.assertFalse(complete)
    def test_08_original_route_unchanged(self):
        before=h10.sha256(self.original)
        tree,roster,explicit=FakeH09.read_roster(self.original,300)
        f=self.root/'new2.rou.xml';FakeH09.clone_route(tree,explicit,{'1'},{'tau':0.9},f)
        h10.verify_route_assignment(f,roster,{'1'})
        self.assertEqual(h10.sha256(self.original),before)

if __name__=='__main__':unittest.main()
