#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H11.2 × H10 v112: paired, fresh-process, read-only-instrumented comparison.

Does not alter H10, H09, H08b, frozen data or historical result directories.
Runs one H10 mode twice, each in a new process and separate output directory;
one run is uninstrumented, the other adds ONLY passive post-step TraCI reads.
Fails closed on unexpected H10 digest, missing manifests, or mismatched traffic.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

EXPECTED_H10_SHA = '42a6fb5674307560688164c5ebbe7f06160a5df55b58c8fb021e1daac6211e7b'
H10_RELATIVE = Path('H10_Vine_H09_Imprudencia_v112/scripts/piloto_hibrido_h10.py')
MODES = ('nominal','vine_protegido','vine_contextual','h09','hibrido_protegido','hibrido_contextual')
COMPARE_FILES = ('trafico_h09.csv','eventos_h09.csv','cohortes_h10.csv','cohorte_h09.csv',
                 'exposicion_h09.csv','acciones_hito08.csv','trafico_hito08.csv',
                 'asignacion_hito08.csv','rutas_modificadas_H09.rou.xml')
ACK1='EXPERIMENTAL_ONLY'
ACK2='NOT_CALIBRATED'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''):h.update(part)
    return h.hexdigest()


def assert_h10(root):
    path=(root/H10_RELATIVE).resolve()
    if not path.is_file():raise FileNotFoundError('No se encontro el H10 v112 original: '+str(path))
    digest=sha(path)
    if digest!=EXPECTED_H10_SHA:
        raise RuntimeError('H10 NO COINCIDE con el preflight auditado. Sin cambios permitidos. '+digest)
    return path


def fresh_dir(root,mode):
    parent=root/'resultados'
    if not parent.is_dir():raise FileNotFoundError(parent)
    return parent/('h11_2_pareado_h10_'+mode+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))


def load_h10(path):
    spec=importlib.util.spec_from_file_location('_h11_h10_v112_original',str(path))
    if not spec or spec.loader is None:raise ImportError(path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare_pair(control,observed,mode):
    a=control/mode;b=observed/mode
    l=(a/'manifest_h10.json');r=(b/'manifest_h10.json')
    if not l.is_file() or not r.is_file():raise RuntimeError('No hay dos manifest_h10.json completos; comparación imposible')
    ma=json.loads(l.read_text(encoding='utf-8'))
    mb=json.loads(r.read_text(encoding='utf-8'))
    if ma.get('mode')!=mode or mb.get('mode')!=mode:raise RuntimeError('Modos H10 distintos')
    for key in ('seed','steps','dt','source_sha256','cohorts','vine_guard_policy','vine_guard_parameters',
                'h09_profile','status','bridge_sha256'):
        if ma.get(key)!=mb.get(key):raise RuntimeError('Metadatos base diferentes: '+key)
    results={};all_equal=True
    for file in COMPARE_FILES:
        pa,pb=a/file,b/file
        if pa.is_file()!=pb.is_file():
            results[file]=dict(identical=False,reason='Archivo presente en un solo brazo')
            all_equal=False;continue
        if not pa.is_file():continue
        left,right=sha(pa),sha(pb)
        results[file]=dict(identical=left==right,sha_control=left,sha_observado=right)
        if left!=right:all_equal=False
    # Require all original H10 files recorded in its manifest and validation of the raw traffic file
    if 'trafico_h09.csv' not in results:raise RuntimeError('H10 sin trafico_h09.csv')
    for m,folder in ((ma,a),(mb,b)):
        for filename,digest in m.get('output_sha256',{}).items():
            if sha(folder/filename)!=digest:raise RuntimeError('H10: archivo alterado '+str(folder/filename))
        if not m.get('output_sha256'):raise RuntimeError('H10: falta output_sha256')
    return dict(status='INVARIANZA_BYTE_A_BYTE_VERIFICADA' if all_equal else 'INVARIANZA_NO_DEMOSTRADA',
                mode=mode,comparison=results,meta_equal=True)


def one_arm(a):
    root=a.root.resolve()
    h10path=assert_h10(root)
    if a.arm not in ('control','observado'):raise ValueError('Brazo invalido')
    if not a.dest.is_absolute():raise ValueError('Destino del brazo debe ser absoluto')
    base=a.dest.resolve()
    if (root/'resultados').resolve() not in base.parents:
        raise ValueError('Destino fuera de resultados/')
    if not base.is_dir() or any(base.iterdir()):
        raise FileExistsError('Carpeta de brazo debe existir y estar vacía: '+str(base))

    h10=load_h10(h10path)
    ns=argparse.Namespace(root=root,vine_scripts=a.vine_scripts,
        reference_baseline_dir=a.reference_baseline_dir,data_dir=a.data_dir,
        sumo_binary=a.sumo_binary,seed=101,steps=600,dt=0.5,max_commands=100)
    ctx=h10.prepare(ns)
    p=ctx[0]
    p['out']=base
    # Never reuse outputs; only a NEW paired experiment is writable.
    p['legacy']=base/'__legacy_disabled__'
    cohorts=ctx[11]
    has_vine=a.escenario.startswith(('vine_','hibrido_'))
    has_h09=a.escenario=='h09' or a.escenario.startswith('hibrido_')
    vine=set(cohorts['selected_vine']) if has_vine else set()
    h09=set(cohorts['selected_h09']) if has_h09 else set()
    metadata=dict(arm=a.arm,scenario=a.escenario,seed=101,steps=600,dt_s=0.5,
                  original_h10_sha256=sha(h10path),vine_selected=len(vine),
                  h09_selected=len(h09),intersection=len(vine&h09),
                  note='Vine and H09 rosters passed ONLY if activated in this scenario; no Quito calibration.')
    with (base/'h11_2_brazo.json').open('x',encoding='utf-8') as f:
        json.dump(metadata,f,indent=2,ensure_ascii=False)
    print('H11.2 BRAZO',a.arm,'ESCENARIO',a.escenario,'COHORTES',
          len(vine),len(h09),len(vine&h09),flush=True)
    hook=None
    try:
        if a.arm=='observado':
            import traci
            from h11_2_bootstrap import install
            hook=install(traci,base/'telemetria',condition=a.escenario,seed=101,
                         vine_ids=vine,h09_ids=h09)
        # H10 original performs the actual SUMO run, with ONE simulationStep per time step.
        result=h10.run_one(a.escenario,ctx,ns)
    finally:
        if hook:hook.close()
    # El ejecutor de H10 debe permanecer bit a bit intacto tras cada brazo.
    assert_h10(root)
    if a.arm=='observado':
        telemetry=base/'telemetria'
        if not (telemetry/'manifest_h11_2.json').is_file():
            raise RuntimeError('Sin telemetria H11.2 completa')
        # local validator is structural and runs without modifying source archives
        validator=Path(__file__).parent/'h11_2_validar.py'
        subprocess.run([sys.executable,str(validator),'--telemetria',str(telemetry),
                        '--expected-steps','600'],check=True)
    print('BRAZO COMPLETADO:',a.arm,str(base/a.escenario),flush=True)


def create_parser():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--escenario',choices=MODES,default='nominal')
    p.add_argument('--vine-scripts',type=Path)
    p.add_argument('--reference-baseline-dir',type=Path)
    p.add_argument('--data-dir',type=Path)
    p.add_argument('--sumo-binary')
    p.add_argument('--ejecutar',action='store_true',help='Lanza dos episodios nuevos, control y observado')
    p.add_argument('--ack-active',default='')
    p.add_argument('--ack-time-scale',default='')
    p.add_argument('--_arm',dest='arm',choices=['control','observado'],help=argparse.SUPPRESS)
    p.add_argument('--_dest',dest='dest',type=Path,help=argparse.SUPPRESS)
    return p


def main(argv=None):
    p=create_parser();a=p.parse_args(argv)
    root=a.root.resolve()
    original=assert_h10(root)
    if a.arm:
        if a.dest is None:raise ValueError('Falta --_dest')
        return one_arm(a)
    print('H11.2 H10 v112 PREPARADO | SIN MODIFICAR CODIGO HISTORICO',flush=True)
    print('Original H10:',original,'SHA256:',sha(original),flush=True)
    print('Escenario:',a.escenario,'semilla 101, 600 pasos, 0.5s',flush=True)
    print('Modo pareja: dos procesos Python independientes (sin observador / con observador)',flush=True)
    if not a.ejecutar:
        print('PLAN SOLAMENTE: para ejecutar agregue --ejecutar y los dos acuses explícitos.',flush=True)
        return 0
    if a.ack_active!=ACK1 or a.ack_time_scale!=ACK2:
        p.error('Ejecutar requiere --ack-active EXPERIMENTAL_ONLY --ack-time-scale NOT_CALIBRATED')
    folder=fresh_dir(root,a.escenario)
    folder.mkdir(parents=False,exist_ok=False)
    (folder/'control').mkdir();(folder/'observado').mkdir()
    args=[sys.executable,'-u',str(Path(__file__).resolve()),'--root',str(root),
          '--escenario',a.escenario]
    for key,field in (('--vine-scripts',a.vine_scripts),
                      ('--reference-baseline-dir',a.reference_baseline_dir),
                      ('--data-dir',a.data_dir),('--sumo-binary',a.sumo_binary)):
        if field is not None:args += [key,str(field)]
    try:
        for arm in ('control','observado'):
            cmd=args+['--_arm',arm,'--_dest',str((folder/arm).resolve())]
            print('INICIANDO',arm,'SIN REUTILIZAR RESULTADOS',flush=True)
            env=os.environ.copy()
            env['PYTHONHASHSEED']='0'  # iguala el orden de hashing en ambos procesos
            subprocess.run(cmd,cwd=root,env=env,check=True)
        invariance=compare_pair(folder/'control',folder/'observado',a.escenario)
        invariance['original_h10_sha256']=sha(original)
        invariance['results_folder']=str(folder)
        with (folder/'comparacion_h11_2.json').open('x',encoding='utf-8') as f:
            json.dump(invariance,f,ensure_ascii=False,indent=2)
        print('COMPARACION:',invariance['status'],flush=True)
        for name,item in invariance['comparison'].items():
            print('  ',name,'IGUAL' if item['identical'] else 'DISTINTO',flush=True)
        if invariance['status']!='INVARIANZA_BYTE_A_BYTE_VERIFICADA':
            raise RuntimeError('H11.2 no demostró invariancia; NO usar aún en experimentos de tesis')
        print('H11.2 PAREADO SUPERADO:',folder,flush=True)
        return 0
    except Exception as exc:
        print('H11.2 NO VALIDADO:',str(exc),flush=True)
        print('Carpeta parcial preservada:',folder,flush=True)
        raise

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(type(exc).__name__+': '+str(exc),file=sys.stderr)
        raise SystemExit(2)
