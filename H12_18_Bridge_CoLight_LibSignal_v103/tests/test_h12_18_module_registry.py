"""Regresiones para introspeccion tipo PyG: los tests no importan PyG."""
import ast
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import h12_18_colight_loader as loader

SOURCE = b'''
class ColightNet:
    def forward(self): return 1
class MaskedOutput:
    pass
class Embedding_MLP:
    pass
class MultiHeadAttModel(MessagePassing):
    def forward(self): return 2
    def message(self): return 3
'''


class FakePyGInspectorBase:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Igual que un Inspector de PyG, falla si no se registro modulo.
        mod = sys.modules[cls.__module__]
        assert mod.__dict__.get(cls.__name__) is cls or cls.__name__ == 'MultiHeadAttModel'
        assert mod.__name__ == loader.ISOLATED_MODULE


class ExplodingInspectorBase:
    def __init_subclass__(cls, **kwargs):
        raise RuntimeError('inspection failed')


class TestModuleRegistry(unittest.TestCase):
    def setUp(self):
        self.assertNotIn(loader.ISOLATED_MODULE, sys.modules)

    def tearDown(self):
        sys.modules.pop(loader.ISOLATED_MODULE, None)

    def _ast(self):
        return loader.extract_original_neural_classes(SOURCE)

    def test_registration_allows_pyg_style_inspector(self):
        cls, mod = loader.execute_verified_neural_classes(self._ast(), 'agent/colight.py',
                                                           {'MessagePassing': FakePyGInspectorBase})
        self.assertIs(sys.modules[loader.ISOLATED_MODULE], mod)
        self.assertIs(cls, mod.ColightNet)
        self.assertEqual(mod.__file__, 'agent/colight.py')
        self.assertIsNone(mod.__package__)
        self.assertEqual(mod.MultiHeadAttModel.__module__, loader.ISOLATED_MODULE)

    def test_reject_existing_module_no_overwrite(self):
        existing = object()
        with patch.dict(sys.modules, {loader.ISOLATED_MODULE: existing}):
            with self.assertRaisesRegex(loader.IsolatedSourceError, 'sobrescribir'):
                loader.execute_verified_neural_classes(self._ast(), '<fixture>',
                                                      {'MessagePassing': FakePyGInspectorBase})
            self.assertIs(sys.modules[loader.ISOLATED_MODULE], existing)

    def test_failed_introspection_removes_only_own_module(self):
        with self.assertRaisesRegex(RuntimeError, 'inspection failed'):
            loader.execute_verified_neural_classes(self._ast(), '<fixture>',
                                                  {'MessagePassing': ExplodingInspectorBase})
        self.assertNotIn(loader.ISOLATED_MODULE, sys.modules)

    def test_reject_incomplete_execution_and_cleanup(self):
        bad = ast.parse('class ColightNet: pass')
        with self.assertRaisesRegex(loader.IsolatedSourceError, 'completamente'):
            loader.execute_verified_neural_classes(bad, '<fixture>', {})
        self.assertNotIn(loader.ISOLATED_MODULE, sys.modules)

    def test_re_registration_after_explicit_cleanup(self):
        for _ in range(2):
            _, mod = loader.execute_verified_neural_classes(self._ast(), '<fixture>',
                                                            {'MessagePassing': FakePyGInspectorBase})
            self.assertIs(sys.modules[loader.ISOLATED_MODULE], mod)
            del sys.modules[loader.ISOLATED_MODULE]

    def test_ast_classes_preserved_not_rewritten(self):
        tree = self._ast()
        self.assertEqual([x.name for x in tree.body], list(loader.CLASSES))
        import inspect
        text = (ROOT / 'h12_18_colight_loader.py').read_text(encoding='utf8')
        self.assertIn('ModuleType(name)', text)
        self.assertIn('sys.modules[name] = module', text)
        self.assertIn('cls, isolated_module = execute_verified_neural_classes', text)
        self.assertNotIn('sys.modules[\'cityflow\']', text)

if __name__ == '__main__':
    unittest.main()
