#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H11.3b v1.0: auditoria de identificabilidad y cobertura empirica Quito--SUMO.

NO pretende calibrar ni validar la prevalencia de imprudencia de Quito.
SOLO LECTURA: usa H01 desarrollo autorizado + H11.2 pareado + comandos H08.
Reutiliza verificadores congelados H11.3a/H11.2c. NO accede a RAW, Richard,
ni al conductor sintetico furious, ni entrena/inicia SUMO.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np

VERSION='H11.3b evidencia Quito v1.0.0'
DOI='10.3390/app14146300'
BANDS=(('05_20',5.,20.),('20_40',20.,40.),('40_60',40.,60.),('gt60',60.,float('inf')))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def import_parent(root):
    fn=root/'H11_3a_Contraste_Aplicado_v100'/'h11_3a_contraste_aplicado.py'
    if not fn.is_file():raise FileNotFoundError('Falta el auditor original H11.3a: '+str(fn))
    spec=importlib.util.spec_from_file_location('h113a_parent_preflight',fn)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod,fn


def band(v):
    v=float(v)
    if not math.isfinite(v) or v<=5:return None
    for name,lo,hi in BANDS:
        if lo < v <= hi:return name
    return None


def finite_stats(x):
    a=pd.to_numeric(x,errors='coerce').dropna().to_numpy(float)
    a=a[np.isfinite(a)]
    if a.size==0:return {'n':0,'mean':None,'std':None,'p50':None,'p95_abs':None,'near_zero_005':None}
    return {'n':int(a.size),'mean':float(a.mean()),'std':float(a.std()),
            'p50':float(np.median(a)),'p95_abs':float(np.quantile(np.abs(a),.95)),
            'near_zero_005':float(np.mean(np.abs(a)<=.05))}


def dev_coverage(x):
    """Cobertura de 5 sesiones; NO atribuye imprudencia a clases por umbral de aceleracion."""
    if not len(x):raise ValueError('H01 vacio')
    rows=[]
    for unit,g in x.groupby('entity',sort=True):
        driver,sid=unit.split('|',1)
        a=g.loc[g.moving_a,'a'];j=g.loc[g.moving_j,'jerk']
        rec={'origen':'POLIDriving','driver_id':driver,'session_id':sid,'filas_verificadas':int(len(g)),
             'muestras_vel_gt5':int(g.moving_a.sum()),'pares_jerk_marcha':int(g.moving_j.sum()),
             'dt_mediana_s':float(g.dt.median()),
             'suma_dt_registros_s_no_duracion_sesion':float(g.dt.sum()),
             'vel_media_marcha_kmh':float(g.loc[g.moving_a,'speed_kmh'].mean()) if g.moving_a.any() else None,
             'a_std_marcha':finite_stats(a)['std'],'jerk_std_marcha':finite_stats(j)['std'],
             'jerk_casi_cero_005_marcha':finite_stats(j)['near_zero_005']}
        counts=Counter(band(v) for v in g.loc[g.moving_a,'speed_kmh'])
        for bn,*_ in BANDS:rec['n_vel_'+bn]=counts[bn]
        rows.append(rec)
    return pd.DataFrame(rows)


def evidence_rows():
    # Fuente empirica = POLIDriving version desarrollo verificado H01 (5 sesiones).
    # La existencia de columnas en dataset publico no equivale a validar su alineacion en H01.
    return [
      dict(codigo='Q01',conducta='cinematica longitudinal',origen_quito='H01 verificado: a_t_m_s2, jerk y dt por segmento',
           medida_sumo='H11.2: accel_m_s2, jerk_observed_m_s3',denominador_quito='pares/muestras elegibles por sesion; no conductores independientes',
           categoria='OBSERVABLE_PARCIAL',limite='diferencia de instrumento, velocidad y dt; H11.3a evidencia discrepancia de jerk',
           proxima_evidencia='equivalencia fisica/temporal y comparacion por conductor/velocidad, sin reentrenar'),
      dict(codigo='Q02',conducta='velocidad absoluta',origen_quito='H01 speed_kmh (no limite legal alineado)',
           medida_sumo='H11.2 speed_m_s',denominador_quito='muestras por sesion, banda y tramo',
           categoria='OBSERVABLE_PARCIAL',limite='rutas, vehiculos y velocidad legal/geométrica no homologados',
           proxima_evidencia='alinear tramos de ruta/contexto, sin consultar datos reservados'),
      dict(codigo='Q03',conducta='exceso de velocidad',origen_quito='dataset publico describe design_speed, NO se verifico ese campo con H01 y no equivale necesariamente a limite legal',
           medida_sumo='H11.2 velocidad / limite configurado de carril',denominador_quito='tiempo o distancia circulada con limite legal validado',
           categoria='NO_IDENTIFICABLE_ACTUALMENTE',limite='no inferir infraccion desde v>60, design_speed o clases de riesgo',
           proxima_evidencia='georreferenciacion, limite legal y tolerancias por tramo; auditoria independiente'),
      dict(codigo='Q04',conducta='seguimiento cercano / headway / TTC',origen_quito='H01 no incorpora seguimiento medido a lider',
           medida_sumo='H11.2 leader_id, gap_m, headway_s, ttc_s',denominador_quito='segundos-vehiculo con lider y deteccion fiable',
           categoria='SIN_ANCLA_EMPIRICA',limite='no transformar aceleracion de PoliDriving en distancia al lider observada',
           proxima_evidencia='instrumentacion longitudinal o videos con lider, velocidad y distancia'),
      dict(codigo='Q05',conducta='cruces en rojo y amarillo',origen_quito='H01 no tiene secuencia observada de fase/stopline/vehiculo',
           medida_sumo='H11.2b eventos proxy fase / transicion de carril',denominador_quito='oportunidades de cruce por fase/vehiculo/interseccion',
           categoria='SIN_ANCLA_EMPIRICA',limite='evento proxy SUMO no estima prevalencia Quito; amarillos no siempre infraccion',
           proxima_evidencia='video campo y codificacion de linea, fase, decision y oportunidades'),
      dict(codigo='Q06',conducta='ocupacion indebida y bloqueo de interseccion',origen_quito='H01 no registra ocupacion/capacidad de despeje',
           medida_sumo='H11.2 episodios de detencion interna candidatos',denominador_quito='entradas con bloqueo/no capacidad y estado downstream',
           categoria='SIN_ANCLA_EMPIRICA',limite='detencion interna no prueba gridlock ni infraccion',
           proxima_evidencia='observacion en video + downstream + confirmacion fisica de bloqueo'),
      dict(codigo='Q07',conducta='etiquetas de riesgo de accidente',origen_quito='POLIDriving publico: 1980 observaciones etiquetadas en cuatro niveles de riesgo (fuera de H01)',
           medida_sumo='H11.2 no observa probabilidad empirica de accidente',denominador_quito='casos con etiqueta y criterio experto; denominador no homogéneo',
           categoria='FUENTE_NO_INTEGRADA',limite='riesgo != infraccion; etiquetas no son clase imprudente observada',
           proxima_evidencia='auditar definicion, sesiones y permisos del subconjunto sin abrir holdout'),
      dict(codigo='Q08',conducta='prevalencia de conductores imprudentes Quito',origen_quito='cinco conductores reales en dataset global; solo cuatro en H01 desarrollo',
           medida_sumo='H09/H08 seleccion experimental 15/30/50 %',denominador_quito='muestreo probabilistico de conductores/vehiculos y exposicion',
           categoria='NO_IDENTIFICABLE_ACTUALMENTE',limite='penetracion 15/30/50 % es parametro experimental, NO prevalencia real',
           proxima_evidencia='muestreo de campo estratificado por vias/franjas y criterios de etiquetado'),
      dict(codigo='Q09',conducta='conductor furious',origen_quito='conductor sintetico publicado, NO observacion humana',
           medida_sumo='NO se usa como validacion empirica',denominador_quito='no aplica',
           categoria='FUENTE_EXCLUIDA',limite='no incorporar en calibracion naturalista como si fuese observacion Quito',
           proxima_evidencia='mantener exclusión documentada'),
    ]


def decisions():
    return [
      dict(id='P0-01_A',cuestion='dependencias Vine y calidad del ajuste',evidencia_actual='H01 y validaciones temporales anteriores; H11.3a contraste aplicado',estado='PARCIAL',
           puerta_cierre='dependencias y transferencia comparadas frente a baselines por conductor/condicion; evitar claim de calibracion universal'),
      dict(id='P0-01_B',cuestion='fidelidad de trayectorias a/jerk en SUMO',evidencia_actual='H11.3a: divergencia de jerk incluso velocidad+dt comparables',estado='NO_ACREDITADO',
           puerta_cierre='compatibilidad instrumental y contraste en soporte observable; comunicar discrepancias'),
      dict(id='P0-01_C',cuestion='representatividad infracciones Quito',evidencia_actual='H01 no tiene semaforos, lider ni oportunidad real; H09 experimental',estado='NO_IDENTIFICABLE',
           puerta_cierre='dato externo con denominadores por oportunidad y contexto comparable'),
      dict(id='P0-02_A',cuestion='imprudencia naturalista separada de bloqueo forzado',evidencia_actual='H10-H11 nominal/hibrido sin inferir gridlock desde detencion interna',estado='PARCIAL',
           puerta_cierre='nominal, Vine solo, H09 solo e hibrido sin hard blocking; controles pareados multisemilla'),
      dict(id='P0-02_B',cuestion='bloqueo estatico separado',evidencia_actual='no evaluado en esta auditoria',estado='PENDIENTE',
           puerta_cierre='brazo independiente de bloqueo explicito, no llamarlo imprudencia naturalista'),
    ]


def prep_paths(args,parent):
    root=args.root.resolve()
    if args.h01:h01=parent.guarded_path(args.h01,root)
    else:
        candidates=[root/'resultados'/'ntvc_vine_r_01_cohortes_movimiento_regenerado',
                    root/'resultados'/'ntvc_vine_r_01_cohortes_movimiento']
        h01=next((x for x in candidates if (x/'manifest.json').is_file()),None)
        if h01 is None:raise FileNotFoundError('No se encontró H01 en rutas autorizadas')
    nom=parent.guarded_path(args.nom,root)
    hib=parent.guarded_path(args.hib,root)
    act=parent.guarded_path(args.vine_actions,root)
    required=(hib.parent/'hibrido_contextual'/'acciones_hito08.csv').resolve()
    if act!=required:raise ValueError('Archivo de acciones no corresponde al brazo híbrido observado')
    return root,h01,nom,hib,act


def check_sources(parent,root,h01,nom,hib,act):
    meta,_,_=parent.summarize(root,h01,nom,hib,act,verify_only=True)
    # Chequeo independiente de la composicion de H11 (sin repetir analisis de indicadores).
    cols_nom=set(pd.read_csv(nom/'trayectorias_h11.csv',nrows=0).columns)
    cols_hib=set(pd.read_csv(hib/'trayectorias_h11.csv',nrows=0).columns)
    needed={'vehicle_id','time_s','speed_m_s','accel_m_s2','posted_lane_limit_m_s',
            'headway_s','ttc_s','gap_m','leader_id','cohort'}
    if not needed.issubset(cols_nom & cols_hib):
        raise ValueError('H11.2 no tiene columnas esperadas: '+str(sorted(needed-(cols_nom & cols_hib))))
    return meta


def create_report(coverage, sources, parent_hashes, root):
    total=int(coverage.filas_verificadas.sum())
    drivers=int(coverage.driver_id.nunique());sessions=int(len(coverage))
    mt=int(coverage.muestras_vel_gt5.sum())
    lines=[
       '# H11.3b — Dictamen de identificabilidad, NO de calibración Quito',
       '',f'- **H01 desarrollo verificado:** {total:,} transiciones; {drivers} conductores reales; {sessions} sesiones autorizadas.',
       f'- **Muestras en marcha (>5 km/h):** {mt:,}.',
       '- Las observaciones por fila no son independientes; la duración sumada de `dt` no equivale a duración total de sesión.',
       '- **Richard, la sesión Alonso de reserva y `furious` sintético no se abrieron.**',
       '- **H11.2 nominal/híbrido:** integridad e invariancia pareada revalidadas con el auditor histórico H11.2c.',
       '', '## Interpretación epistemológica',
       'POLIDriving proporciona mediciones reales de cinemática de recorridos en Quito, pero no un marco muestral de infractores,',
       'ni headways, TTC, fases semafóricas, probabilidades de incumplimiento o gridlock confirmados.',
       'La variable `design_speed` descrita en el dataset público NO se ha homologado con límites legales por tramo para H01.',
       'Las 1980 etiquetas de riesgo en la descripción pública no se usaron para construir una tasa de infracción.',
       'La presencia del conductor sintético `furious` en el repositorio tampoco lo convierte en evidencia de campo.',
       '', '## Puertas científicas',
       '- P0-01: la cadena TraCI funciona, pero el contraste H11.3a detectó falta de fidelidad de jerk; validez naturalista no acreditada.',
       '- P0-02: ningún indicador de frenado, parada interna o cola debe etiquetarse como bloqueo causado por imprudencia sin validación.',
       '- Las tasas H09 del 15/30/50 % son niveles de intervención, no prevalencias de infractores de Quito.',
       '- Este informe NO estima prevalencia, NO da calibración, NO demuestra seguridad vial y NO evalúa controladores semafóricos.',
       '', '## Siguiente evidencia necesaria',
       '1. Registro de campo de cruce ante semáforos con denominadores por oportunidad y fase.',
       '2. Seguimiento longitudinal con distancia al líder y velocidad relativa, estratificado por tipo de vía.',
       '3. Límites legales georreferenciados, tipo de vía, velocidad y hora para contrastar exceso de velocidad.',
       '4. Puente instrumental de aceleración/jerk y evaluación por conductor; sin manipular la referencia para mejorar W1.',
       '5. Congelar escenarios de perturbación naturalista sin bloqueo, separar los de bloqueo artificial y recién entonces evaluar controladores.',
       '', '## Fuentes bibliográficas',
       '- Marcillo et al. (2024), POLIDriving, Applied Sciences 14(14), 6300. DOI: https://doi.org/'+DOI,
       '- Repositorio oficial: https://github.com/laboratorioAI/polidriving',
       '- Matriz de observaciones del tutor y del PDF T-ITS (P0-01/P0-02), ya auditada en la revisión.',
       '', '## Integridad técnica',
       '- SHA H01: `'+parent_hashes['h01']['csv_sha256']+'`',
       '- SHA acciones: `'+parent_hashes['vine_actions_sha256']+'`',
       '', '**Dictamen: H11.3b inventario de evidencia completado; representatividad Quito sigue NO ACREDITADA.**',''
    ]
    return '\n'.join(lines)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--h01',type=Path)
    p.add_argument('--nom',type=Path,required=True)
    p.add_argument('--hib',type=Path,required=True)
    p.add_argument('--vine-actions',type=Path,required=True)
    p.add_argument('--guardar',action='store_true')
    p.add_argument('--out',type=Path)
    a=p.parse_args(argv)
    if a.out and not a.guardar:p.error('--out requiere --guardar')
    root=a.root.resolve();parent,code=import_parent(root)
    root,h01,nom,hib,act=prep_paths(a,parent)
    integrity=check_sources(parent,root,h01,nom,hib,act)
    print('=== H11.3b | INVENTARIO DE EVIDENCIA E IDENTIFICABILIDAD | SOLO LECTURA ===')
    print('H01: 5 sesiones desarrollo, SHA OK; test Richard y sesiones reserva excluidos')
    print('H11.2:',integrity['nominal']['pareado']['status'],'/',integrity['hibrido']['pareado']['status'])
    print('PoliDriving: fuente Quito real; etiquetas de riesgo != infracciones observadas; furious sintetico excluido')
    print('Controladores NO evaluados. No hard blocking. No SUMO, entrenamiento ni RAW.')
    if not a.guardar:
        print('PREFLIGHT OK. --guardar genera inventario/puertas de validacion sin alterar fuentes.')
        return 0
    dev=parent.load_h01(h01/'cohortes_muestras_verificadas.csv')
    coverage=dev_coverage(dev)
    expected_sessions={(x[0],x[1]) for x in parent.DEV_SESSIONS}
    found_sessions=set(zip(coverage.driver_id,coverage.session_id))
    if found_sessions!=expected_sessions:
        raise ValueError('Sesiones no coinciden con el desarrollo congelado')
    rows=evidence_rows();gates=decisions()
    out=a.out.resolve() if a.out else root/'resultados'/('h11_3b_evidencia_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if not out.is_relative_to(root/'resultados') or out.exists():
        raise ValueError('La salida debe ser NUEVA y permanecer bajo resultados/')
    # Solo se crea despues de comprobar todas las fuentes.
    out.mkdir(parents=True)
    files={
      'cobertura_polidriving_desarrollo_h11_3b.csv':coverage,
      'matriz_evidencia_quito_h11_3b.csv':pd.DataFrame(rows),
      'puertas_director_pdf_h11_3b.csv':pd.DataFrame(gates),
    }
    for name,df in files.items():df.to_csv(out/name,index=False,encoding='utf-8-sig')
    report=create_report(coverage,rows,integrity,root)
    (out/'dictamen_h11_3b.md').write_text(report,encoding='utf-8')
    output_hashes={n:sha(out/n) for n in [*files,'dictamen_h11_3b.md']}
    manifest={'version':VERSION,'created_utc':datetime.now(timezone.utc).isoformat(),
              'h11_3b_code_sha256':sha(Path(__file__)),
              'parent_code_sha256':sha(code),
              'calibrated_quito':False,'claims_prevalence_quito':False,
              'test_richard_read':False,'synthetic_furious_read':False,'sumo_executed':False,
              'source_sha256':{'H01':integrity['h01']['csv_sha256'],
                               'H01_manifest':integrity['h01']['manifest_sha256'],
                               'nominal_trajectory':integrity['nominal']['fuente']['sha_outputs']['trayectorias_h11.csv'],
                               'hybrid_trajectory':integrity['hibrido']['fuente']['sha_outputs']['trayectorias_h11.csv'],
                               'Vine_actions':integrity['vine_actions_sha256']},
              'n_sessions':len(coverage),'n_drivers':int(coverage.driver_id.nunique()),
              'n_development_rows':int(coverage.filas_verificadas.sum()),
              'n_development_moving':int(coverage.muestras_vel_gt5.sum()),
              'output_sha256':output_hashes,
              'limitations':['No existe muestreo representativo de conductores Quito',
                             'No hay medidas longitudinales directas de lider/TTC en H01',
                             'No hay fase/semaforo/stopline de campo en H01',
                             'No se confunde design_speed con velocidad legal',
                             'Riesgo de accidente != comportamiento imprudente observado',
                             'No inferencia causal ni prevalencia, ni calibracion generalizable']}
    (out/'manifiesto_h11_3b.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\nCOBERTURA:')
    print(coverage[['driver_id','session_id','filas_verificadas','muestras_vel_gt5','pares_jerk_marcha','dt_mediana_s']].to_string(index=False))
    print('\nMATRIZ:')
    print(pd.DataFrame(rows)[['codigo','conducta','categoria']].to_string(index=False))
    print('\nP0 DIRECTOR/PDF:')
    print(pd.DataFrame(gates)[['id','estado']].to_string(index=False))
    print('DICTAMEN:',out)
    print('Sin apertura de Richard ni RAW, sin reentrenamiento ni inferencia de tasas Quito.')
    return 0


if __name__=='__main__':raise SystemExit(main())
