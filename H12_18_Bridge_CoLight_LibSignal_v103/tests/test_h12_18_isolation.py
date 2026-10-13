"""Aislamiento sin librerias neuronales, red ni simulador."""
import ast
import hashlib
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import h12_18_colight_loader as m
import h12_18_bridge as b

FIXTURE=b'''\n# Side effect prohibido, no debe ejecutarse:\nimport cityflow\nraise RuntimeError("imports de simuladores no deben ejecutarse")\nclass ColightNet:\n    def __init__(self): pass\n    def forward(self): return 1\nclass MaskedOutput:\n    pass\nclass Embedding_MLP:\n    pass\nclass MultiHeadAttModel(MessagePassing):\n    def forward(self): return 1\n    def message(self): return 1\n'''

class TestIsolatedCoLightSource(unittest.TestCase):
    def test_only_original_four_classes_in_original_order(self):
        res=m.extract_original_neural_classes(FIXTURE)
        self.assertEqual([x.name for x in res.body],list(m.CLASSES))
        original=ast.parse(FIXTURE)
        self.assertEqual(ast.dump(res),ast.dump(ast.Module(
            body=[x for x in original.body if isinstance(x,ast.ClassDef)],type_ignores=[])))
    def test_import_side_effect_never_in_compiled_ast(self):
        res=m.extract_original_neural_classes(FIXTURE)
        self.assertTrue(all(isinstance(x,ast.ClassDef) for x in res.body))
        self.assertNotIn('cityflow',ast.unparse(res))
        self.assertNotIn('RuntimeError',ast.unparse(res))
    def test_neither_coLight_agent_nor_simulator_used(self):
        bad=FIXTURE+b'\nclass CoLightAgent: pass\n'
        res=m.extract_original_neural_classes(bad)
        self.assertNotIn('CoLightAgent',[x.name for x in res.body])
    def test_duplicate_class_rejected(self):
        with self.assertRaises(m.IsolatedSourceError):
            m.extract_original_neural_classes(FIXTURE+b'\nclass ColightNet: pass\n')
    def test_missing_attention_class_rejected(self):
        bad=FIXTURE.replace(b'class MultiHeadAttModel(MessagePassing):',b'class Missing(MessagePassing):')
        with self.assertRaises(m.IsolatedSourceError):m.extract_original_neural_classes(bad)
    def test_missing_forward_rejected(self):
        bad=FIXTURE.replace(b'    def forward(self): return 1',b'    def other(self): return 1',1)
        with self.assertRaises(m.IsolatedSourceError):m.extract_original_neural_classes(bad)
    def test_missing_attention_message_rejected(self):
        bad=FIXTURE.replace(b'    def message(self): return 1',b'    def other(self): return 1')
        with self.assertRaises(m.IsolatedSourceError):m.extract_original_neural_classes(bad)
    def test_syntax_error_rejected(self):
        with self.assertRaises(m.IsolatedSourceError):m.extract_original_neural_classes(b'not valid = #')
    def test_class_decorators_rejected(self):
        bad=FIXTURE.replace(b'class ColightNet:',b'@decorate\nclass ColightNet:')
        with self.assertRaises(m.IsolatedSourceError):m.extract_original_neural_classes(bad)
    def _make_pinned_repo(self, root, line_ending=b'\n'):
        """Fixture Git real: core.autocrlf en Windows deja CRLF en worktree.

        Git siempre guarda bytes LF comprometidos; SHA-256 del worktree
        puede ser distinto sin que Git considere sucio el repositorio.
        """
        root=Path(root)
        f=root/'agent/colight.py';f.parent.mkdir(parents=True)
        material=FIXTURE.replace(b'\n',line_ending)
        f.write_bytes(material)
        def g(*args):
            return subprocess.run(['git','-C',str(root),*args],check=True,
                                  capture_output=True).stdout
        g('init','-q')
        g('config','core.autocrlf','true')
        g('config','user.name','Isolated Test')
        g('config','user.email','test@example.invalid')
        g('add','agent/colight.py')
        g('commit','-q','-m','source')
        commit=g('rev-parse','HEAD').decode().strip()
        raw=g('show','HEAD:agent/colight.py')
        blob=m.original_blob_sha(raw)
        self.assertEqual(g('status','--porcelain','--untracked-files=no'),b'')
        return f,raw,blob,commit,hashlib.sha256(material).hexdigest()

    def test_sha_expected_and_git_blob(self):
        with tempfile.TemporaryDirectory() as td:
            f,raw,blob,commit,wtsha=self._make_pinned_repo(td)
            with patch.object(m,'EXPECTED_BLOB',blob),patch.object(m,'EXPECTED_COMMIT',commit):
                self.assertEqual(m.verified_source(td,wtsha)[1],raw)
                self.assertEqual(m.verified_source(td,wtsha)[2],hashlib.sha256(raw).hexdigest())
                with self.assertRaises(m.IsolatedSourceError):
                    m.verified_source(td,'0'*64)
                f.write_bytes(f.read_bytes()+b'\n#tampered')
                with self.assertRaises(m.IsolatedSourceError):
                    m.verified_source(td,wtsha)

    def test_crlf_worktree_genuine_git_blob_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            f,raw,blob,commit,wtsha=self._make_pinned_repo(td,b'\r\n')
            self.assertNotEqual(m.original_blob_sha(f.read_bytes()),blob)
            self.assertNotEqual(hashlib.sha256(raw).hexdigest(),wtsha)
            with patch.object(m,'EXPECTED_BLOB',blob),patch.object(m,'EXPECTED_COMMIT',commit):
                returned_f,committed,returned_sha=m.verified_source(td,wtsha)
                self.assertEqual(returned_f,f)
                self.assertEqual(committed,raw)
                self.assertEqual(returned_sha,hashlib.sha256(raw).hexdigest())

    def test_dirty_git_worktree_with_updated_expectation_still_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f,raw,blob,commit,wtsha=self._make_pinned_repo(td,b'\r\n')
            f.write_bytes(f.read_bytes()+b'#uncommitted-change\n')
            changed_sha=hashlib.sha256(f.read_bytes()).hexdigest()
            with patch.object(m,'EXPECTED_BLOB',blob),patch.object(m,'EXPECTED_COMMIT',commit):
                with self.assertRaisesRegex(m.IsolatedSourceError,'modificaciones'):
                    m.verified_source(td,changed_sha)

    def test_wrong_git_blob_even_with_clean_worktree_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f,raw,blob,commit,wtsha=self._make_pinned_repo(td)
            with patch.object(m,'EXPECTED_COMMIT',commit):
                with self.assertRaisesRegex(m.IsolatedSourceError,'Blob Git CoLight distinto'):
                    m.verified_source(td,wtsha)

    def test_wrong_commit_with_identical_blob_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f,raw,blob,commit,wtsha=self._make_pinned_repo(td)
            with patch.object(m,'EXPECTED_BLOB',blob):
                with self.assertRaisesRegex(m.IsolatedSourceError,'Commit Git LibSignal distinto'):
                    m.verified_source(td,wtsha)

    def test_probe_args_include_sha_pins(self):
        d={'worktree_sha256':'a'*64,'config_worktree_sha256':'b'*64}
        args=b.import_probe_cmd('c:/some/path',d)
        self.assertEqual(args[args.index('--expected-source-sha256')+1],'a'*64)
        self.assertEqual(args[args.index('--expected-config-sha256')+1],'b'*64)
        self.assertIn('h12_18_libsignal_probe.py',' '.join(args))
    def test_source_loader_documented_as_isolation(self):
        p=(ROOT/'h12_18_colight_loader.py').read_text(encoding='utf8')
        self.assertIn('PINNED_LIBSIGNAL_UNMODIFIED_CLASS_AST',p)
        self.assertNotIn('sys.modules[\'cityflow\']',p)
        self.assertIn('gymnasium as gym',p)

if __name__=='__main__':unittest.main()
