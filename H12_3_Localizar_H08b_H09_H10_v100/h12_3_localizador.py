#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.3: localiza de forma PASIVA módulos de H08b/H09/H10, inclusive dentro de ZIP.

No importa módulos, no ejecuta SUMO, no lee telemetría POLIDriving ni
recorre resultados/ ni modifica proyectos. Solo analiza nombres y AST de .py
que correspondan a los hitos; no descomprime archivos a disco.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import uuid
import zipfile

VERSION = 'H12.3 Localizador H08b/H09/H10 v1.0'
SKIP = {'.git', '__pycache__', '.venv', 'venv', 'env', 'site-packages',
        'node_modules', 'resultados', 'results', 'outputs', 'raw', 'processed',
        'datasets', 'data', '.mypy_cache', '.pytest_cache', 'dist', 'build'}
SCRIPT_RE = re.compile(r'(ntvc_vine_r_0[3468]|ntvc_vine_r_08b|h0?[89][a-z0-9_\-.]*|h10[a-z0-9_\-.]*|vine.*(?:h08|h09|h10))', re.I)
ZIP_RE = re.compile(r'(^|[/_\-])(H0?[89]|H10|Vine_H09|Vine)([_\-.]|$)', re.I)
MAIN_RE = re.compile(r'ntvc_vine_r_08b_cuota_auditada\.py$', re.I)
OTHER_RE = re.compile(r'(ntvc_vine_r_0[3468]|ntvc_vine_r_08b|h0?[89]|h10)',re.I)
MAX_MODULE_BYTES = 2_000_000
MAX_SCRIPT_RECORDS = 650
MAX_ZIP_ENTRIES = 35_000


def digest(data: bytes):
    return hashlib.sha256(data).hexdigest()


def class_info(source: bytes):
    try:
        tree = ast.parse(source.decode('utf-8-sig'))
    except (UnicodeDecodeError, SyntaxError) as exc:
        return {'parse': type(exc).__name__, 'definitions': [], 'imports': []}
    defs = []
    imports = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append({'symbol':node.name,'kind':'class' if isinstance(node,ast.ClassDef) else 'function',
                         'lineno':node.lineno})
            if isinstance(node,ast.ClassDef):
                for method in node.body:
                    if isinstance(method,(ast.FunctionDef,ast.AsyncFunctionDef)) and method.name in (
                        '__init__','on_step','step','on_microtick','propose','load','reset','build','create','__call__'):
                        args=[a.arg for a in method.args.posonlyargs+method.args.args+method.args.kwonlyargs]
                        if method.args.vararg:args.append('*'+method.args.vararg.arg)
                        if method.args.kwarg:args.append('**'+method.args.kwarg.arg)
                        defs.append({'symbol':node.name+'.'+method.name,'kind':'method',
                                     'params':args,'lineno':method.lineno})
            elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                args=[a.arg for a in node.args.posonlyargs+node.args.args+node.args.kwonlyargs]
                if node.args.vararg:args.append('*'+node.args.vararg.arg)
                if node.args.kwarg:args.append('**'+node.args.kwarg.arg)
                defs[-1]['params']=args
        elif isinstance(node,ast.Import):
            imports.extend(x.name for x in node.names)
        elif isinstance(node,ast.ImportFrom):
            imports.append((('.'*node.level)+(node.module or '')))
    return {'parse':'OK','definitions':defs[:160],'imports':imports[:100]}


def record(path:str, raw:bytes, *, origin='file', archive=None, member=None):
    out={'path':path,'source':origin,'bytes':len(raw),'sha256':digest(raw)}
    if archive is not None:
        out['zip_path']=archive
        out['zip_member']=member
    out.update(class_info(raw))
    out['contains_FixedRosterInjector'] = any(d['symbol']=='FixedRosterInjector' for d in out['definitions'])
    out['contains_on_step'] = any(d['symbol'].endswith('.on_step') for d in out['definitions'])
    return out


def walks(root:Path):
    """Recorre solo código/paquetes; omite datos brutos y resultados."""
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    for folder, dirs, filenames in os.walk(root):
        rel=Path(folder).relative_to(root)
        depth=len(rel.parts) if rel!=Path('.') else 0
        dirs[:] = sorted(x for x in dirs if x.lower() not in SKIP and not x.startswith('.'))
        if depth>=7:
            dirs.clear()
        for filename in sorted(filenames):
            path=Path(folder)/filename
            lower=filename.lower()
            if lower.endswith('.py'):
                hit = bool(SCRIPT_RE.search(filename)) or (
                    any(OTHER_RE.search(part) for part in rel.parts) and not filename.startswith('test_'))
                if hit:
                    yield ('py',path)
            elif lower.endswith('.zip') and (ZIP_RE.search(filename) or
                                              any(OTHER_RE.search(part) for part in rel.parts)):
                yield ('zip',path)


def audit(root:Path):
    root=root.resolve()
    rec=[]; archives=[]; errors=[]; scanned=0
    for kind,path in walks(root):
        scanned+=1
        rel=str(path.relative_to(root))
        if kind=='py':
            try:
                if path.stat().st_size>MAX_MODULE_BYTES:
                    errors.append({'path':rel,'issue':'PY_TOO_LARGE'})
                    continue
                rec.append(record(rel,path.read_bytes()))
            except OSError as exc:
                errors.append({'path':rel,'issue':type(exc).__name__})
        else:
            zinfo={'path':rel,'sha256':None,'matched_scripts':0,'all_members':0}
            try:
                with zipfile.ZipFile(path) as z:
                    members=z.infolist()
                    zinfo['all_members']=len(members)
                    if len(members)>MAX_ZIP_ENTRIES:
                        errors.append({'path':rel,'issue':'ZIP_TOO_MANY_ENTRIES'})
                        archives.append(zinfo)
                        continue
                    for member in members:
                        if member.is_dir() or not member.filename.lower().endswith('.py'):
                            continue
                        filepart=PurePosixPath(member.filename).name
                        is_hit=bool(SCRIPT_RE.search(filepart)) or (
                            any(OTHER_RE.search(x) for x in PurePosixPath(member.filename).parts) and
                            not filepart.startswith('test_'))
                        if not is_hit or member.file_size>MAX_MODULE_BYTES:
                            continue
                        raw=z.read(member)
                        zinfo['matched_scripts']+=1
                        rec.append(record(rel+' :: '+member.filename,raw,origin='zip',
                                          archive=rel,member=member.filename))
                zinfo['sha256']=digest(path.read_bytes()) if path.stat().st_size<=150_000_000 else 'NOT_HASHED_LARGE'
            except (zipfile.BadZipFile, RuntimeError, OSError,ValueError) as exc:
                errors.append({'path':rel,'issue':type(exc).__name__})
            archives.append(zinfo)
        if len(rec)>MAX_SCRIPT_RECORDS:
            errors.append({'path':rel,'issue':'SCRIPT_LIMIT_EXCEEDED'})
            break
    matches=[r for r in rec if r['contains_FixedRosterInjector']]
    exact=[r for r in rec if MAIN_RE.search(PurePosixPath(r.get('zip_member') or r['path']).name)]
    return {'version':VERSION,'revision_root':str(root),'items_scanned':scanned,
            'scripts':rec,'archives':archives,'errors':errors,
            'fixed_roster_classes':[r['path'] for r in matches],
            'expected_h08b_filenames':[r['path'] for r in exact],
            'ready_for_integration':bool(matches) and bool(exact)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision-root',type=Path,required=True)
    p.add_argument('--search-root',type=Path,default=None, help='Carpeta de busqueda, si es distinta de revision-root.')
    p.add_argument('--guardar',action='store_true')
    a=p.parse_args(argv)
    out=audit(a.search_root or a.revision_root)
    print('H12.3 | LOCALIZADOR SOLO LECTURA')
    print('Buscando en:',out['revision_root'])
    print('Scripts de hitos:',len(out['scripts']),' | ZIP:',len(out['archives']))
    print('FixedRosterInjector:',len(out['fixed_roster_classes']))
    print('Archivo esperado H08b:',len(out['expected_h08b_filenames']))
    for found in out['expected_h08b_filenames'][:12]:
        print(' H08b ->',found)
    for found in out['fixed_roster_classes'][:12]:
        print(' Class ->',found)
    for error in out['errors'][:12]:
        print(' AVISO',error)
    if not out['ready_for_integration']:
        print('PENDIENTE: H08b no fue identificado en los paquetes inspeccionados; no crear hook a ciegas.')
    else:
        print('LOCALIZADO: revisar dependencias y firmas; aun NO se ha conectado Vine ni H09.')
    if not a.guardar:
        print('SIN ESCRITURA. Use --guardar para generar informe nuevo en resultados/.')
        return 0
    result_root=(a.revision_root.resolve()/'resultados')
    result_root.mkdir(exist_ok=True)
    dest=result_root/('h12_3_localizador_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:5])
    dest.mkdir(exist_ok=False)
    (dest/'simbolos_h08b_h09_h10.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    summary = ('# H12.3 — Hallazgos de interfaz (solo lectura)\n\n'
               f"- Archivos Python identificados: **{len(out['scripts'])}**\n"
               f"- ZIP inspeccionados: **{len(out['archives'])}**\n"
               f"- Definiciones de `FixedRosterInjector`: **{len(out['fixed_roster_classes'])}**\n"
               f"- Archivos H08b esperados: **{len(out['expected_h08b_filenames'])}**\n\n"
               'Este paso no ejecuta SUMO, no importa módulos y no modifica el proyecto.\n'
               'La localización de un archivo no certifica su integridad, configuración ni conexión.\n')
    (dest/'hallazgos_h12_3.md').write_text(summary,encoding='utf-8')
    print('INFORME:',dest)
    return 0


if __name__=='__main__':
    sys.exit(main())
