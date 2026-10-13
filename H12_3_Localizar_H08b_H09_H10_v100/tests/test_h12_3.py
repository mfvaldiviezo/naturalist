import importlib.util
import tempfile
from pathlib import Path
import unittest
import zipfile

script=Path(__file__).resolve().parents[1]/'h12_3_localizador.py'
spec=importlib.util.spec_from_file_location('h12_3_localizador',script)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Tests(unittest.TestCase):
    def test_finds_nested_h08b(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'H10_ZIP_v112'/'nested'
            p.mkdir(parents=True)
            (p/'ntvc_vine_r_08b_cuota_auditada.py').write_text(
                'class FixedRosterInjector:\n    def __init__(self, a): pass\n    def on_step(self,traci,step): pass\n')
            out=m.audit(root)
            self.assertTrue(out['ready_for_integration'])
            self.assertEqual(out['scripts'][0]['definitions'][1]['params'],['self','a'])
    def test_archived_h08b(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with zipfile.ZipFile(root/'H10_Vine_H09_v112.zip','w') as z:
                z.writestr('nested/ntvc_vine_r_08b_cuota_auditada.py',
                           'class FixedRosterInjector:\n    def on_step(self,traci,step):pass\n')
            out=m.audit(root)
            self.assertTrue(out['ready_for_integration'])
            self.assertEqual(out['scripts'][0]['source'],'zip')
    def test_ignores_results_and_raw(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in ['resultados','data','raw']:
                d=root/name;d.mkdir()
                (d/'ntvc_vine_r_08b_cuota_auditada.py').write_text('x=1')
            self.assertEqual(m.audit(root)['scripts'],[])
    def test_not_import_or_execute(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'ntvc_vine_r_08b_cuota_auditada.py').write_text('raise RuntimeError("WRONG")\nclass FixedRosterInjector: pass')
            self.assertEqual(len(m.audit(root)['fixed_roster_classes']),1)
    def test_corrupt_zip_nonfatal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'H10_bad.zip').write_bytes(b'broken')
            self.assertEqual(m.audit(root)['errors'][0]['issue'],'BadZipFile')
    def test_no_save_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            self.assertEqual(m.main(['--revision-root',str(root)]),0)
            self.assertFalse((root/'resultados').exists())
    def test_external_search_root_save_revision_only(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); revision=base/'revision'; revision.mkdir()
            external=base/'external'; external.mkdir()
            (external/'ntvc_vine_r_08b_cuota_auditada.py').write_text(
                'class FixedRosterInjector:\n    def on_step(self,traci,step):pass\n')
            self.assertEqual(m.main(['--revision-root',str(revision),'--search-root',str(external),'--guardar']),0)
            self.assertFalse((external/'resultados').exists())
            self.assertEqual(len(list((revision/'resultados').glob('h12_3_localizador_*'))),1)
    def test_save_only_under_results(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            self.assertEqual(m.main(['--revision-root',str(root),'--guardar']),0)
            self.assertEqual(len(list((root/'resultados').glob('h12_3_localizador_*'))),1)

if __name__=='__main__': unittest.main()
