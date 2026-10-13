#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoría descriptiva SOLO LECTURA del piloto H10 v1.1.2 (seis condiciones).

No importa módulos de Vine ni abre SUMO. Requiere únicamente Python stdlib.
Preserva íntegros los seis escenarios. Resultados del analizador en carpeta nueva.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics

MODES=('nominal','vine_protegido','vine_contextual','h09','hibrido_protegido','hibrido_contextual')
OLD=f'resultados/h10_vine_h09_imprudencia_v111_piloto_101'
NEW=f'resultados/h10_vine_h09_imprudencia_v112_piloto_101'
DEFAULT_OUTPUT='resultados/h10_auditoria_postpiloto_v120'
METRICS=('arrivals','mean_halted','mean_speed_kmh','collisions','teleports')
EXPECTED_H08B='ee70a04c7f0b698309f7a637a8a0b2b5ddf18434ec3ab6c11dc3346a7a904943'


def sha256(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def get_source(root,label):
    return root/(OLD if label in MODES[:3] else NEW)/label


def load_manifests(root):
    result={}
    input_hashes=None
    for mode in MODES:
        d=get_source(root,mode)
        path=d/'manifest_h10.json'
        if not path.is_file():raise FileNotFoundError('Falta manifiesto H10: '+str(path))
        m=json.loads(path.read_text(encoding='utf-8'))
        if m.get('mode')!=mode or m.get('seed')!=101 or m.get('steps')!=600 or float(m.get('dt',0))!=.5:
            raise ValueError('Parámetros del piloto inconsistentes: '+mode)
        files=m.get('output_sha256')
        if not isinstance(files,dict) or not files:raise ValueError('Manifiesto sin outputs: '+mode)
        for name,digest in files.items():
            file=d/name
            if not file.is_file():raise FileNotFoundError('Archivo faltante: '+str(file))
            if sha256(file)!=str(digest).lower():
                raise ValueError('HASH DE RESULTADO MODIFICADO: '+str(file))
        # El mapa original de fuentes debe coincidir a través de los seis escenarios.
        sources=m.get('source_sha256')
        if not isinstance(sources,dict) or not sources:raise ValueError('Sin hashes de fuentes: '+mode)
        norm={k:str(v).lower() for k,v in sources.items()}
        if input_hashes is None:input_hashes=norm
        elif norm!=input_hashes:raise ValueError('Fuentes no comparables entre escenarios: '+mode)
        if mode=='nominal' or mode=='h09':
            if m.get('historical_traffic_identical') is not True:
                raise ValueError('Control histórico no reproducido: '+mode)
        if 'vine_' in mode or 'hibrido_' in mode:
            v=m.get('vine')
            if not isinstance(v,dict):raise ValueError('Faltan métricas Vine: '+mode)
            if v.get('n_commands')!=v.get('n_commands_confirmed') or v.get('remaining_pending'):
                raise ValueError('Comandos Vine sin confirmar: '+mode)
            if m.get('vine_guard_policy')!=('contextual' if mode.endswith('contextual') else 'protegido'):
                raise ValueError('Política Vine incorrecta: '+mode)
        result[mode]=(d,m)
    return result


def read_csv(path):
    with Path(path).open('r',encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def truthy(s):return str(s).strip().lower() in ('1','true','yes')


def cohort_group(vid,vs,hs):
    if vid in vs and vid in hs:return 'ambas'
    if vid in vs:return 'solo_vine'
    if vid in hs:return 'solo_h09'
    return 'ninguna'


def crossing_totals(rows,vs,hs):
    ctr=Counter()
    for r in rows:
        if r.get('event_type')!='tls_crossing_link':continue
        phase=r.get('signal_state')
        if phase not in ('red','yellow','unknown'):continue
        if phase!='unknown' and r.get('classification_quality')!='confirmed':continue
        group=cohort_group(str(r.get('vehicle_id','')),vs,hs)
        ctr[(phase,'total')]+=1
        ctr[(phase,group)]+=1
        if not r.get('measurement_id'):ctr[(phase,'sin_episodio')]+=1
    return {phase: {key:ctr[(phase,key)] for key in ('total','ambas','solo_vine','solo_h09','ninguna','sin_episodio')}
            for phase in ('red','yellow','unknown')}


def action_stats(rows,vs,hs):
    ctr=Counter(); actual=[]; decision=Counter(); windows=Counter()
    for r in rows:
        decision[r.get('action_decision') or 'sin_decision']+=1
        if not truthy(r.get('command_issued','false')):continue
        vid=str(r['vehicle_id']);actual.append(vid)
        ctr[cohort_group(vid,vs,hs)]+=1
        # El modulo original usa ventanas de 60 s y no añade el ID espacial/TLS.
        try: windows[int(float(r['time_s'])//60)]+=1
        except (TypeError,ValueError):pass
        if not truthy(r.get('matched_t_plus_dt','false')):
            raise ValueError('CSV contiene comando sin confirmación t+dt')
    return {'comandos_csv':len(actual),'vehiculos_distintos':len(set(actual)),
            'vehiculos_por_cohorte':dict(Counter(cohort_group(v,vs,hs) for v in set(actual))),
            'comandos_por_cohorte':dict(ctr),'decisiones':dict(decision),
            'comandos_por_ventana_60s':dict(sorted(windows.items()))}


def analyze(results):
    base=results['h09'][1]['cohorts']
    vs=set(map(str,base['selected_vine']))
    hs=set(map(str,base['selected_h09']))
    if len(vs)!=45 or len(hs)!=45 or len(vs&hs)!=7:
        raise ValueError('Cohortes H10 distintas de 45/45 con 7 compartidos')
    report={'status':'H10_POSTHOC_DESCRIPTIVE_SINGLE_SEED_NOT_QUITO_CALIBRATED',
            'seed':101,'seconds':300,'step_s':.5,
            'cohorts':{'vine_selected':len(vs),'h09_selected':len(hs),'overlap':len(vs&hs)},
            'conditions':{},'contrasts':{},'warnings':[]}
    for mode,(folder,m) in results.items():
        ev=read_csv(folder/'eventos_h09.csv')
        crossing=crossing_totals(ev,vs,hs)
        observed=m['instrumental'].get('signal_states',{})
        for ph in ('red','yellow','unknown'):
            if crossing[ph]['total']!=int(observed.get(ph,0)):
                raise ValueError('Desfase cruces vinculados y estado instrumental: '+mode+' '+ph)
        v=m.get('vine') or {}
        actions=action_stats(read_csv(folder/'acciones_hito08.csv'),vs,hs) if v else None
        if actions and actions['comandos_csv']!=v['n_commands']:
            raise ValueError('Desfase en total de comandos Vine: '+mode)
        observed_vtype=m.get('h09_exposure') or {}
        report['conditions'][mode]={'path':str(folder),'traffic':m['traffic_metrics'],
            'crossing_by_cohort':crossing,
            'h09_exposure':{k:observed_vtype.get(k) for k in (
                'n_assigned','n_roster','n_selected_seen','n_selected_verified_vtype','n_selected_never_seen')},
            'vine':{k:v.get(k) for k in ('n_commands','n_commands_confirmed','n_vehicles_commanded',
                                      'n_safety_eligible','n_action_viable','reasons','safety_halt')},
            'actions':actions,
            'opportunities_v15':m['instrumental'].get('instrumentation_v15',{})}
    n=report['conditions']['nominal'];h=report['conditions']['h09']
    for pol in ('protegido','contextual'):
        v=report['conditions']['vine_'+pol]
        hybrid=report['conditions']['hibrido_'+pol]
        for metric in METRICS:
            N=n['traffic'][metric];H=h['traffic'][metric];V=v['traffic'][metric];B=hybrid['traffic'][metric]
            report['contrasts'][f'{pol}_{metric}']={
                'vine_minus_nominal':V-N,
                'h09_minus_nominal':H-N,
                'hybrid_minus_nominal':B-N,
                'interaction':B-V-H+N}
        for phase in ('red','yellow'):
            N=n['crossing_by_cohort'][phase]['total'];H=h['crossing_by_cohort'][phase]['total']
            V=v['crossing_by_cohort'][phase]['total'];B=hybrid['crossing_by_cohort'][phase]['total']
            report['contrasts'][f'{pol}_{phase}']={
                'vine_minus_nominal':V-N,'h09_minus_nominal':H-N,
                'hybrid_minus_nominal':B-N,'interaction':B-V-H+N}
    report['warnings']=[
        'Sólo una semilla (101); no usar para inferencia estadística ni superioridad de políticas.',
        'Cruces en amarillo no son infracciones automáticamente; crossings son proxies de línea de parada.',
        'Las cohortes Vine (baseline observado) y H09 (300 salidas programadas <300s) tienen bases distintas; XML completo tiene 3600 vehículos.',
        '100 comandos es una cuota saturada, no igualdad de oportunidades/eficacia.',
        'Los archivos de acciones Vine carecen de posición/TLS y no prueban proximidad al semáforo cuando se ordenó cada comando.',
        'Una colisión/frenada no puede atribuirse causalmente a un comando particular sólo con conteos.',
        'speedMode=31 y guard cinemático siguen activos; contextual sólo relaja elegibilidad.',
        'Vine original conserva datos congelados, sin calibración temporal SUMO/PoliDriving ni calibración Quito.',
        'Este análisis no incorpora control semafórico por RL.']
    return report


def flat_rows(report):
    records=[]
    for mode in MODES:
        r=report['conditions'][mode];t=r['traffic'];c=r['crossing_by_cohort']
        v=r['vine'];actions=r['actions'] or {}
        row={'modo':mode,**{k:t.get(k) for k in METRICS},
             'rojos':c['red']['total'],'rojos_ambos':c['red']['ambas'],
             'rojos_solo_h09':c['red']['solo_h09'],'rojos_solo_vine':c['red']['solo_vine'],
             'rojos_ninguno':c['red']['ninguna'],
             'amarillos':c['yellow']['total'],'desconocidos':c['unknown']['total'],
             'comandos_vine':v.get('n_commands',0),'vehiculos_con_comando':actions.get('vehiculos_distintos',0),
             'elegibles_vine_observaciones':v.get('n_safety_eligible',0),
             'viables_vine_observaciones':v.get('n_action_viable',0),
             'ventanas_60s':json.dumps(actions.get('comandos_por_ventana_60s',{}),sort_keys=True)}
        records.append(row)
    return records


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path.cwd())
    ap.add_argument('--output',type=Path,default=None)
    args=ap.parse_args(argv)
    root=args.root.resolve();out=(args.output or (root/DEFAULT_OUTPUT)).resolve()
    approved=(root/'resultados').resolve()
    if approved not in out.parents:raise ValueError('Solo salida nueva dentro de resultados/')
    if out.exists():raise FileExistsError('No sobrescribir análisis anterior: '+str(out))
    results=load_manifests(root)
    report=analyze(results)
    rows=flat_rows(report)
    out.mkdir(parents=True,exist_ok=False)
    p=out/'auditoria_h10_101.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    p=out/'auditoria_h10_101_tabla.csv'
    with p.open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('H10 POSTPILOTO | SEMILLA 101 | SOLO DESCRIPTIVO')
    print('CONDICIÓN'.ljust(22),'ARRIBOS'.rjust(8),'PARADOS'.rjust(10),'KM/H'.rjust(8),'ROJOS'.rjust(7),'AMAR.'.rjust(7),'CMD'.rjust(6),'ID_CMD'.rjust(8),'ELEGIBLES'.rjust(11))
    for r in rows:
        print(r['modo'].ljust(22),str(r['arrivals']).rjust(8),f"{r['mean_halted']:.2f}".rjust(10),
              f"{r['mean_speed_kmh']:.2f}".rjust(8),str(r['rojos']).rjust(7),str(r['amarillos']).rjust(7),
              str(r['comandos_vine']).rjust(6),str(r['vehiculos_con_comando']).rjust(8),
              str(r['elegibles_vine_observaciones']).rjust(11))
    print('\nCRUCES ROJOS POR COHORTE (ambas / solo H09 / solo Vine / ninguna)')
    for m in MODES:
        c=report['conditions'][m]['crossing_by_cohort']['red']
        print(m+':',*[c[k] for k in ('ambas','solo_h09','solo_vine','ninguna')])
    print('\nREPORTES:',str(out))
    print('AVISO: 1 semilla; sin inferencia estadística ni atribución causal de cada frenada.')
    return 0


if __name__=='__main__':raise SystemExit(main())
