import importlib.util
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

p=Path(__file__).resolve().parents[1]/'scripts'/'piloto_hibrido_h10.py'
spec=importlib.util.spec_from_file_location('runner_v111',p)
h10=importlib.util.module_from_spec(spec);spec.loader.exec_module(h10)

class DigestRegression(unittest.TestCase):
    def test_uppercase_h03_digest_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'hangzhou_vine_sin_additional.sumocfg';f.write_bytes(b'<configuration/>')
            upper=hashlib.sha256(f.read_bytes()).hexdigest().upper()
            merged=h10.merge_source_hashes([f],{str(f):upper})
            self.assertEqual(merged[str(f.resolve())], upper.lower())
            h10.verify_sources({str(f):upper})
    def test_changed_cfg_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'hangzhou_vine_sin_additional.sumocfg';f.write_text('before')
            old=h10.sha256(f).upper();f.write_text('after')
            with self.assertRaisesRegex(RuntimeError, 'Conflicto verdadero'):
                h10.merge_source_hashes([f],{str(f):old})
    def test_change_after_merge_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'hangzhou_vine_sin_additional.sumocfg';f.write_text('before')
            merged=h10.merge_source_hashes([f],{str(f):h10.sha256(f).upper()})
            f.write_text('after')
            with self.assertRaisesRegex(RuntimeError,'REALMENTE DIFERENTE'):
                h10.verify_sources(merged)
    def test_missing_files_fail(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'missing.sumocfg'
            with self.assertRaises(FileNotFoundError):h10.merge_source_hashes([f],{})
    def test_bad_sha_rejected(self):
        for sha in ['UNRESOLVED','XX'*32, '123', None]:
            with self.assertRaises(ValueError):h10.normalize_sha256(sha)
    def test_original_h08b_is_not_bundled(self):
        self.assertFalse((Path(__file__).resolve().parents[1]/'ntvc_vine_r_08b_cuota_auditada.py').exists())

if __name__=='__main__': unittest.main()
