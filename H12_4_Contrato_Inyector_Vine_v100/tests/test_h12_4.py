import importlib.util
from pathlib import Path
import tempfile
import unittest

M=Path(__file__).resolve().parents[1]/'h12_4_inspeccionar.py'
spec=importlib.util.spec_from_file_location('h124',M)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

SOURCE=b'''import json\nfrom h08_kernel import VineKernel\nDEFAULT_DATA = 'unused'\nclass FixedRosterInjector:\n  def __init__(self, kernel, seed=101, *, mode='probe', max_commands=30):\n    self.kernel=kernel\n  def on_step(self, traci, step):\n    t=traci.simulation.getTime()\n    traci.vehicle.setAcceleration('0',1.0,0.5)\n    return t\n'''
class Tests(unittest.TestCase):
    def test_digest(self): self.assertEqual(len(a.digest(SOURCE)),64)
    def test_extract_class(self): self.assertEqual(a.parse_h08b(SOURCE,'a.py')['class'],'FixedRosterInjector')
    def test_signature(self): self.assertIn('on_step(self, traci, step)',[x['signature'] for x in a.parse_h08b(SOURCE,'a.py')['methods']])
    def test_defaults(self):
        m=a.parse_h08b(SOURCE,'a.py')['methods'][0]
        self.assertEqual(next(x['default'] for x in m['arguments'] if x['name']=='seed'),'101')
    def test_find_calls(self): self.assertTrue(any('setAcceleration' in x['target'] for x in a.parse_h08b(SOURCE,'a.py')['all_class_calls']))
    def test_catch_double_step(self):
        r=a.parse_h08b(SOURCE.replace(b'    return t',b'    traci.simulationStep()\n    return t'),'a.py')
        self.assertTrue(any('DOUBLE_STEP_RISK' in x for x in r['warnings']))
    def test_missing_class(self):
        with self.assertRaises(ValueError): a.parse_h08b(b'pass','a.py')
    def test_syntax_error(self):
        with self.assertRaises(SyntaxError):a.parse_h08b(b'class FixedRosterInjector:\n def','a.py')
    def test_no_import_execution(self):
        source=b'import definitely_nonexistent_package\n'+SOURCE
        r=a.parse_h08b(source,'a.py')
        self.assertIn('definitely_nonexistent_package',r['imports'])
    def test_no_output_without_save(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/'scripts'/a.NAME;src.parent.mkdir();src.write_bytes(SOURCE)
            r=a.inspect(root)
            self.assertFalse((root/'resultados').exists());self.assertEqual(r['status'],'LOCATED_STATIC_CONTRACT_ONLY')
    def test_report_only_results(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/'scripts'/a.NAME;src.parent.mkdir();src.write_bytes(SOURCE)
            out=a.write_report(root,a.inspect(root));self.assertTrue((out/'interfaz_h08b.json').is_file())
            self.assertEqual(out.parent,root/'resultados')
    def test_runner_site(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/'scripts'/a.NAME;src.parent.mkdir();src.write_bytes(SOURCE)
            (root/'scripts'/'run_h10.py').write_text('from ntvc_vine_r_08b_cuota_auditada import FixedRosterInjector\ni=FixedRosterInjector(kernel,seed=1)\n',encoding='utf-8')
            sites=a.runner_sites(root,src)
            self.assertEqual(len(sites),1);self.assertEqual(len(sites[0]['related']),2)

if __name__=='__main__':unittest.main()
