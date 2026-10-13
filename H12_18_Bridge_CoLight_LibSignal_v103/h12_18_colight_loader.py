"""Cargador *limitado* de clases neuronales originales de LibSignal CoLight.

No importa ``agent``, ``world``, ``generator`` ni CityFlow. Compila únicamente
las cuatro definiciones de clase sin modificarlas, extraídas del archivo
``agent/colight.py`` cotejado por commit + SHA durante el preflight H12.16/18.
Esto acredita la ejecución de la arquitectura neuronal original, NO la
importación ni reproducibilidad íntegra de CoLightAgent/Trainer de LibSignal.
"""
from __future__ import annotations
import ast
import hashlib
import subprocess
import sys
from types import ModuleType
from pathlib import Path

CLASSES = ('ColightNet', 'MaskedOutput', 'Embedding_MLP', 'MultiHeadAttModel')
EXPECTED_COMMIT = '127af9f93902778e556de2eedb2b606c4c9447e6'
EXPECTED_BLOB = 'b33858268b51fa008df2ea4ee4bea725a74de476'

class IsolatedSourceError(RuntimeError):
    pass


def extract_original_neural_classes(source: bytes, filename: str = '<libsignal>/agent/colight.py'):
    """Devuelve AST de las clases intactas; nada se ejecuta en este paso."""
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError) as exc:
        raise IsolatedSourceError('agent/colight.py no es Python valido') from exc
    defs = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in CLASSES]
    names = [n.name for n in defs]
    if len(defs) != 4 or set(names) != set(CLASSES):
        raise IsolatedSourceError('Faltan o se duplican clases originales de CoLight: '+repr(names))
    if any(n.decorator_list for n in defs):
        raise IsolatedSourceError('No se aceptan decoradores no previstos en clases originales')
    model = next(x for x in defs if x.name == 'ColightNet')
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'forward' for n in model.body):
        raise IsolatedSourceError('La clase ColightNet carece de forward')
    att = next(x for x in defs if x.name == 'MultiHeadAttModel')
    if not all(any(isinstance(n, ast.FunctionDef) and n.name == k for n in att.body)
               for k in ('forward', 'message')):
        raise IsolatedSourceError('Falta mensaje o forward de atencion de CoLight')
    result = ast.Module(body=defs, type_ignores=[])
    ast.fix_missing_locations(result)
    return result


def original_blob_sha(source: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(source)).encode('ascii')+b'\x00'+source).hexdigest()


def _git(root, *args) -> bytes:
    """Lee exclusivamente el repositorio local; no accede a la red ni lo modifica."""
    try:
        p = subprocess.run(['git', '-C', str(root), '--no-pager', *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IsolatedSourceError('No se puede verificar Git de LibSignal') from exc
    if p.returncode:
        raise IsolatedSourceError('Git rechazo '+repr(args)+': '+p.stderr.decode('utf-8','replace')[:200])
    return p.stdout


def verified_source(libsignal_dir, sha256_expected: str):
    """Lee el blob *comprometido* original, con worktree controlado por SHA.

    Windows puede materializar ``\r\n`` mediante core.autocrlf aun cuando
    ``HEAD:agent/colight.py`` contenga ``\n``. Un Git worktree limpio NO
    tiene que poseer el mismo SHA-1 de blob que los bytes en disco.
    Se ejecuta solo el blob Git fijado, con hash verificado byte a byte.
    """
    lib = Path(libsignal_dir).resolve(strict=True)
    f = lib / 'agent' / 'colight.py'
    if not f.is_file():
        raise IsolatedSourceError('Falta agent/colight.py del clon LibSignal')
    wt = f.read_bytes()
    worktree_sha = hashlib.sha256(wt).hexdigest()
    if worktree_sha != sha256_expected:
        raise IsolatedSourceError('SHA-256 worktree CoLight distinto del preflight')

    actual_root = Path(_git(lib, 'rev-parse', '--show-toplevel').decode('utf-8').strip()).resolve()
    if actual_root != lib:
        raise IsolatedSourceError('LibSignal-dir no es la raiz exacta del clon auditado')
    commit = _git(lib, 'rev-parse', 'HEAD').decode('ascii').strip()
    if commit != EXPECTED_COMMIT:
        raise IsolatedSourceError('Commit Git LibSignal distinto del fijado')
    if _git(lib, 'status', '--porcelain', '--untracked-files=no').strip():
        raise IsolatedSourceError('LibSignal contiene modificaciones de archivos versionados')
    git_sha = _git(lib, 'rev-parse', 'HEAD:agent/colight.py').decode('ascii').strip()
    if git_sha != EXPECTED_BLOB:
        raise IsolatedSourceError('Blob Git CoLight distinto del fijado')
    committed = _git(lib, 'show', 'HEAD:agent/colight.py')
    if original_blob_sha(committed) != EXPECTED_BLOB:
        raise IsolatedSourceError('Contenido comprometido no corresponde al blob Git fijado')
    if hashlib.sha256(f.read_bytes()).hexdigest() != sha256_expected:
        raise IsolatedSourceError('Archivo de trabajo CoLight cambio durante la lectura')
    return f, committed, hashlib.sha256(committed).hexdigest()


ISOLATED_MODULE = 'h12_18_upstream_architecture_isolated'


def execute_verified_neural_classes(ast_module, filename: str, symbols: dict):
    """Compila clases autenticas en un modulo real registrado en sys.modules.

    PyG/Inspector consulta sys.modules[cls.__module__] incluso al definir
    MessagePassing; ejecutar en un namespace anonimo provoca KeyError.
    No se reemplazan modulos previos y un fallo deja el registro limpio.
    """
    name = ISOLATED_MODULE
    if name in sys.modules:
        raise IsolatedSourceError('Modulo aislado ya registrado; no sobrescribir identidad')
    module = ModuleType(name)
    module.__file__ = str(filename)
    module.__package__ = None
    module.__dict__.update(symbols)
    sys.modules[name] = module
    try:
        code = compile(ast_module, filename=str(filename), mode='exec')
        exec(code, module.__dict__, module.__dict__)
        if not all(isinstance(module.__dict__.get(n), type) for n in CLASSES):
            raise IsolatedSourceError('Clases neuronales no cargadas completamente')
        if any(module.__dict__[n].__module__ != name for n in CLASSES):
            raise IsolatedSourceError('Modulo de clase no corresponde al registro aislado')
        return module.__dict__['ColightNet'], module
    except BaseException:
        if sys.modules.get(name) is module:
            del sys.modules[name]
        raise


def load_original_colight_net(libsignal_dir, sha256_expected: str):
    """Obtiene ColightNet ORIGINAL sin importar módulos de simulador.

    La única sustitución externa es ``gymnasium.spaces.Discrete`` en lugar del
    ``gym.spaces.Discrete`` histórico, por compatibilidad de interfaz.
    Las clases y sus métodos NO se reescriben ni se recrean manualmente.
    """
    f, source, committed_sha = verified_source(libsignal_dir, sha256_expected)
    ast_module = extract_original_neural_classes(source, filename=str(f))

    # Importaciones diferidas: 'plan' y verificaciones SHA siguen siendo stdlib.
    from collections import OrderedDict
    import numpy as np
    import torch
    from torch import nn
    import torch.nn.functional as F
    import gymnasium as gym
    from torch_geometric.nn import MessagePassing
    from torch_geometric.utils import add_self_loops
    import torch_scatter

    # Solo los símbolos utilizados en las cuatro clases seleccionadas.
    symbols = {'np': np, 'torch': torch, 'nn': nn, 'F': F,
               'gym': gym, 'OrderedDict': OrderedDict,
               'MessagePassing': MessagePassing, 'add_self_loops': add_self_loops,
               'torch_scatter': torch_scatter}
    cls, isolated_module = execute_verified_neural_classes(ast_module, str(f), symbols)
    return cls, {
        'loader': 'PINNED_LIBSIGNAL_UNMODIFIED_CLASS_AST',
        'registered_neural_module': isolated_module.__name__,
        'module_registered_in_sys_modules': (sys.modules.get(isolated_module.__name__) is isolated_module),
        'model_origin': 'agent/colight.py::ColightNet',
        'upstream_source': str(f),
        'upstream_commit': EXPECTED_COMMIT,
        'upstream_blob_sha1': EXPECTED_BLOB,
        'upstream_sha256': committed_sha,
        'upstream_committed_sha256': committed_sha,
        'upstream_worktree_sha256': sha256_expected,
        'source_read_mode': 'GIT_SHOW_PINNED_COMMIT_BLOB_WITH_CLEAN_WORKTREE_GUARD',
        'external_interface_adaptation': 'gymnasium.spaces.Discrete replaces legacy gym.spaces.Discrete',
        'full_agent_imported': False,
        'cityflow_imported_by_loader': False,
        'neural_class_definitions_modified': False,
    }
