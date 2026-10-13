#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H12.4 v1.0 | auditoria estatica de la interfaz H08b Vine (sin imports/ejecucion)."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import uuid

NAME = 'ntvc_vine_r_08b_cuota_auditada.py'
CLASS = 'FixedRosterInjector'
METHODS = {'__init__','on_step','step','on_microtick','reset','close','propose','__call__'}
WATCH = {'simulationStep','setAcceleration','setSpeed','setSpeedMode','setTau','setSpeedFactor','setImperfection','getDeltaT','getTime','start','init','close','load','getVehicleIDList','release','getSpeedMode'}
MAX_SOURCE_BYTES = 1_000_000
MAX_SCRIPTS = 350


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_expr(node: ast.AST | None, limit: int=170) -> str:
    if node is None:
        return 'None'
    try:
        s=ast.unparse(node)
    except Exception:
        s=type(node).__name__
    return s[:limit]+('…' if len(s)>limit else '')


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    a=node.args
    return str(node.name) + '(' + ', '.join(
        ([x.arg for x in a.posonlyargs]+(['/' ] if a.posonlyargs else [])+
         [x.arg for x in a.args] +
         (['*'+a.vararg.arg] if a.vararg else (['*'] if a.kwonlyargs else []))+
         [x.arg for x in a.kwonlyargs] +
         (['**'+a.kwarg.arg] if a.kwarg else []))) + ')'


def args_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict]:
    a=node.args
    positional = a.posonlyargs + a.args
    defaults=[None]*(len(positional)-len(a.defaults)) + list(a.defaults)
    out=[]
    for arg, default in zip(positional,defaults):
        out.append({'name':arg.arg,'kind':'positional','default':None if default is None else safe_expr(default),'annotation':safe_expr(arg.annotation) if arg.annotation else None})
    for arg,default in zip(a.kwonlyargs,a.kw_defaults):
        out.append({'name':arg.arg,'kind':'keyword_only','default':None if default is None else safe_expr(default),'annotation':safe_expr(arg.annotation) if arg.annotation else None})
    if a.vararg:out.append({'name':a.vararg.arg,'kind':'var_positional'})
    if a.kwarg:out.append({'name':a.kwarg.arg,'kind':'var_keyword'})
    return out


def calls(node: ast.AST) -> list[dict]:
    out=[]
    for x in ast.walk(node):
        if not isinstance(x,ast.Call):
            continue
        f=x.func
        if isinstance(f,ast.Attribute):
            name=f.attr
            receiver=safe_expr(f.value,100)
        elif isinstance(f,ast.Name):
            name=f.id;receiver=''
        else:continue
        if name in WATCH or name==CLASS:
            out.append({'line':x.lineno,'target':receiver+'.'+name if receiver else name,'keywords':[k.arg for k in x.keywords], 'argc':len(x.args)})
    return sorted(out,key=lambda x:x['line'])[:120]


def parse_h08b(raw:bytes, origin:str) -> dict:
    if len(raw)>MAX_SOURCE_BYTES:raise ValueError('SOURCE_TOO_LARGE')
    tree=ast.parse(raw.decode('utf-8-sig'),filename=origin)
    classes=[x for x in tree.body if isinstance(x,ast.ClassDef) and x.name==CLASS]
    if len(classes)!=1:raise ValueError(f'Se esperaba una clase {CLASS}, encontradas {len(classes)}')
    c=classes[0]
    methods=[x for x in c.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name in METHODS]
    imports=[];topdefs=[];assignments=[]
    for x in tree.body:
        if isinstance(x,ast.Import):imports.extend(a.name for a in x.names)
        if isinstance(x,ast.ImportFrom):imports.append('.'*x.level + (x.module or ''))
        if isinstance(x,(ast.FunctionDef,ast.ClassDef)):
            topdefs.append({'name':x.name,'line':x.lineno})
        if isinstance(x,ast.Assign):
            for n in x.targets:
                if isinstance(n,ast.Name) and (n.id.startswith(('DEFAULT_','FIT_','ACTIVE_','H08','ROOT','DATA_','MAX_'))):
                    assignments.append({'name':n.id,'expression':safe_expr(x.value,120),'line':x.lineno})
    methods_report=[]
    for m in methods:
        methods_report.append({'name':m.name,'signature':signature(m),'arguments':args_info(m),'lineno':m.lineno,
                               'end_lineno':m.end_lineno,'calls':calls(m)})
    method_lookup={m['name']:m for m in methods_report}
    issues=[]
    if 'on_step' not in method_lookup and 'on_microtick' not in method_lookup:
        issues.append('NO_HOOK_ON_STEP_OR_ON_MICROTICK')
    for n in ('on_step','on_microtick'):
        if n in method_lookup:
            sub=method_lookup[n]
            for call in sub['calls']:
                if call['target'].endswith('.simulationStep') or call['target']=='simulationStep':
                    issues.append('DOUBLE_STEP_RISK_'+n+'_line_'+str(call['line']))
                if call['target'].endswith('.setSpeed') or call['target'].endswith('.setSpeedMode'):
                    issues.append('VEHICLE_WRITE_REVIEW_'+call['target']+'_line_'+str(call['line']))
    return {'path':origin,'sha256':digest(raw),'bytes':len(raw),'class':CLASS,'class_line':c.lineno,
            'methods':methods_report,'imports':imports,'top_level_definitions':topdefs[:75],
            'constants':assignments[:70],'warnings':issues,'all_class_calls':calls(c)}


def runner_sites(root:Path, source:Path) -> list[dict]:
    selected=[]
    candidates=root/'scripts'
    if candidates.is_dir():
        selected.extend(sorted(candidates.glob('*.py'))[:MAX_SCRIPTS])
    for folder in sorted(root.glob('H10_*'))+sorted(root.glob('H08*'))+sorted(root.glob('H09_*')):
        if folder.is_dir():selected.extend(sorted(folder.glob('*.py'))[:40])
    seen=set();found=[]
    for py in selected[:MAX_SCRIPTS]:
        if py.resolve()==source.resolve() or py.resolve() in seen:continue
        seen.add(py.resolve())
        try:
            if py.stat().st_size>MAX_SOURCE_BYTES:continue
            txt=py.read_text(encoding='utf-8-sig')
            if CLASS not in txt and 'ntvc_vine_r_08b' not in txt:continue
            tree=ast.parse(txt,filename=str(py))
            related=[]
            for n in ast.walk(tree):
                if isinstance(n,ast.Call):
                    f=n.func
                    name=f.id if isinstance(f,ast.Name) else f.attr if isinstance(f,ast.Attribute) else None
                    if name==CLASS:
                        related.append({'line':n.lineno,'call':'FixedRosterInjector',
                                        'arguments':[safe_expr(a,80) for a in n.args][:15],
                                        'keywords':[{k.arg:safe_expr(k.value,100)} for k in n.keywords][:35]})
                if isinstance(n,ast.ImportFrom) and n.module and 'ntvc_vine_r_08b' in n.module:
                    related.append({'line':n.lineno,'import_from':n.module,'names':[v.name for v in n.names]})
            found.append({'file':str(py.relative_to(root)),'sha256':digest(py.read_bytes()), 'related':related[:12]})
        except (OSError,SyntaxError,UnicodeError):continue
    return found[:80]


def inspect(root:Path, source:Path | None=None) -> dict:
    root=root.resolve()
    file=(source or (root/'scripts'/NAME)).resolve()
    if file.name!=NAME: raise ValueError(f'Se requiere un archivo denominado {NAME}')
    if not file.is_file():raise FileNotFoundError(file)
    # Fuente fuera de revision_naturalista se rechaza (evita barridos accidentales).
    if root not in file.parents:raise ValueError('La fuente debe pertenecer a revision-root')
    report=parse_h08b(file.read_bytes(),str(file))
    report['reference_scripts']=runner_sites(root,file)
    report['status']='LOCATED_STATIC_CONTRACT_ONLY'
    report['limitations']=[
        'No se han importado ni ejecutado los módulos H08b.',
        'No se han inspeccionado ni alterado datasets, muestras ni artefactos Vine.',
        'No está probada todavía la conexión del inyector a Gymnasium.',
        'El contrato temporal y las restricciones de seguridad deben probarse con hook real antes de active.',
    ]
    return report


def write_report(revision:Path, rep:dict) -> Path:
    revision=revision.resolve()
    results=(revision/'resultados').resolve()
    if revision not in results.parents:raise ValueError('Carpeta resultados insegura')
    results.mkdir(parents=True,exist_ok=True)
    out=results/('h12_4_interfaz_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:5])
    out.mkdir(exist_ok=False)
    (out/'interfaz_h08b.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# H12.4 — Contrato estático de FixedRosterInjector','',
           '- Fuente: `'+rep['path']+'`','- SHA-256: `'+rep['sha256']+'`',
           '- Estado: **localizado, NO conectado a Gymnasium**','']
    lines+=['## Métodos','']
    for m in rep['methods']:
        lines+=['- `'+m['signature']+'` (línea '+str(m['lineno'])+')']
        for call in m['calls']:
            lines+=['  - llamada: `'+call['target']+'` (línea '+str(call['line'])+')']
    lines+=['','## Referencias H08b en scripts vecinos','']
    for x in rep['reference_scripts'][:40]:
        lines+=['- `'+x['file']+'` — '+str(len(x['related']))+' referencias AST']
    lines+=['','## Advertencias','']
    lines.extend('- '+v for v in (rep['warnings'] or ['Ninguna identificada estáticamente; no es validación dinámica']))
    lines+=['','## Límites','']
    lines.extend('- '+v for v in rep['limitations'])
    (out/'dictamen_interfaz_h12_4.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return out


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision-root',type=Path,required=True)
    ap.add_argument('--source',type=Path,default=None)
    ap.add_argument('--guardar',action='store_true')
    a=ap.parse_args(argv)
    try:
        r=inspect(a.revision_root,a.source)
        print('H12.4 | CONTRATO H08b | SOLO AST, SIN IMPORTAR, SIN SUMO')
        print('Fuente:',r['path'])
        print('SHA-256:',r['sha256'])
        for method in r['methods']:
            print('METODO:',method['signature'],'linea:',method['lineno'])
            for call in method['calls']:
                print('  LLAMADA:',call['target'],'linea:',call['line'])
        print('Referencias cercanas:',len(r['reference_scripts']))
        for item in r['reference_scripts'][:8]:
            print(' REFERENCIA:',item['file'], 'AST:',len(item['related']))
        if r['warnings']:
            for i in r['warnings']:print('ADVERTENCIA:',i)
        if a.guardar:
            print('INFORME:',write_report(a.revision_root,r))
        else:print('SIN ESCRITURA: use --guardar para guardar los informes')
        return 0
    except (OSError,ValueError,SyntaxError,UnicodeError) as e:
        print('FAIL-CLOSED:',type(e).__name__,str(e),file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(main())
