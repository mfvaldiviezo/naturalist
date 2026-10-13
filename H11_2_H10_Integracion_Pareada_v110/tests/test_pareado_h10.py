"""Unit checks for fail-closed paired comparison. Does not run SUMO."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1]/'h11_2_integrar_y_comparar_h10.py'
spec = importlib.util.spec_from_file_location('pareado', MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class PairAudit(unittest.TestCase):
    def setUp(self):
        self.ctx=tempfile.TemporaryDirectory()
        self.root=Path(self.ctx.name)
        self.mode='hibrido_contextual'
        for arm in ('control','observado'):
            d=self.root/arm/self.mode
            d.mkdir(parents=True)
            for name in ('trafico_h09.csv','acciones_hito08.csv','eventos_h09.csv'):
                (d/name).write_text('step,value\n0,1\n',encoding='utf-8')
            m={k:'same' for k in ('source_sha256','cohorts','vine_guard_policy','vine_guard_parameters','h09_profile','status','bridge_sha256')}
            m.update({'seed':101,'steps':600,'dt':0.5,'mode':self.mode,
                      'output_sha256':{f:mod.sha(d/f) for f in ('trafico_h09.csv','acciones_hito08.csv','eventos_h09.csv')}})
            (d/'manifest_h10.json').write_text(json.dumps(m),encoding='utf-8')

    def tearDown(self):self.ctx.cleanup()

    def test_identical(self):
        got=mod.compare_pair(self.root/'control',self.root/'observado',self.mode)
        self.assertEqual(got['status'],'INVARIANZA_BYTE_A_BYTE_VERIFICADA')
        self.assertEqual(len(got['comparison']),3)

    def test_modified_traffic_fails_even_when_manifest_matches_old_hash(self):
        (self.root/'observado'/self.mode/'trafico_h09.csv').write_text('modified',encoding='utf-8')
        with self.assertRaises(RuntimeError):mod.compare_pair(self.root/'control',self.root/'observado',self.mode)

    def test_physical_difference_detected_when_manifest_honestly_updated(self):
        arm=self.root/'observado'/self.mode
        (arm/'trafico_h09.csv').write_text('different',encoding='utf-8')
        man=json.loads((arm/'manifest_h10.json').read_text(encoding='utf-8'))
        man['output_sha256']['trafico_h09.csv']=mod.sha(arm/'trafico_h09.csv')
        (arm/'manifest_h10.json').write_text(json.dumps(man),encoding='utf-8')
        result=mod.compare_pair(self.root/'control',self.root/'observado',self.mode)
        self.assertEqual(result['status'],'INVARIANZA_NO_DEMOSTRADA')
        self.assertFalse(result['comparison']['trafico_h09.csv']['identical'])

    def test_missing_manifest_fails(self):
        (self.root/'control'/self.mode/'manifest_h10.json').unlink()
        with self.assertRaises(RuntimeError):mod.compare_pair(self.root/'control',self.root/'observado',self.mode)

    def test_original_digest(self):
        # Original H10 v112 is present only in development; no connection to user's PC.
        source=Path('/mnt/data/h10_temp/H10_Vine_H09_Imprudencia_v112/scripts/piloto_hibrido_h10.py')
        if source.exists():self.assertEqual(mod.sha(source),mod.EXPECTED_H10_SHA)

    def test_no_execution_when_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/mod.H10_RELATIVE
            target.parent.mkdir(parents=True)
            target.write_text('wrong',encoding='utf-8')
            with self.assertRaises(RuntimeError):mod.assert_h10(root)

if __name__=='__main__':unittest.main()
