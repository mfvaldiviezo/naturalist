#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H11.3c: auditoria no supervisada DESCRIPTIVA, no de imprudencia o riesgo.
Solo lee H01 con integridad SHA256; mantiene reservas inaccesibles.
No modifica fuente ni modelos ni SUMO. Toda etiqueta es CINEMATICA.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

ALLOWED={('alonso','20240103_141959'),('andres','20231222_134710'),('andres','20231226_150915'),('pablo','20231123_094610'),('yolanda','20240111_185718')}
FROZEN='EBBB8BEBE69DBBB55858FCB8F8753A7F33AAAD5CA78B57D4BBA9FEE669162C25'
REQ={'driver_id','session_id','segment_id','raw_row','a_t_m_s2','a_t_minus_1_m_s2','dt_t_s','j_t_observed_m_s3','speed_kmh','speed_class'}
VER='H11.3c v1.0.0'
THRESHOLDS=[('exploratorio_sensible',1.5,2.0),('exploratorio_intermedio',2.0,3.0),('exploratorio_conservador',3.0,5.0)]

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for v in iter(lambda:f.read(1<<20),b''):h.update(v)
    return h.hexdigest()

def load_h01(folder):
    folder=Path(folder);mf=folder/'manifest.json';cp=folder/'cohortes_muestras_verificadas.csv'
    m=json.loads(mf.read_text(encoding='utf-8'))
    if m.get('original_verified_sha256','').upper()!=FROZEN:raise ValueError('Origen congelado distinto')
    if {tuple(map(str,x)) for x in m.get('allowed_sessions',[])}!=ALLOWED:raise ValueError('Sesiones no autorizadas')
    names=('cohortes_muestras_verificadas.csv','vine_marcha_triples_desarrollo.csv','resumen_cohortes_por_sesion.csv','folds_lodo_desarrollo.json')
    for name in names:
        expect=m.get('file_sha256',{}).get(name,'')
        if len(expect)!=64 or not (folder/name).is_file() or sha(folder/name).lower()!=expect.lower():raise ValueError('SHA256 inválido: '+name)
    x=pd.read_csv(cp,dtype={'driver_id':str,'session_id':str,'segment_id':str,'raw_row':'int64'})
    if not REQ.issubset(x.columns):raise ValueError('Columnas H01 ausentes: '+str(REQ-set(x.columns)))
    if len(x)!=62398 or set(zip(x.driver_id,x.session_id))!=ALLOWED:raise ValueError('Poblacion desarrollo distinta de H01')
    if x.duplicated(['driver_id','session_id','segment_id','raw_row']).any():raise ValueError('Filas duplicadas')
    fields=['a_t_m_s2','a_t_minus_1_m_s2','dt_t_s','j_t_observed_m_s3','speed_kmh']
    for n in fields:x[n]=pd.to_numeric(x[n],errors='raise')
    if not np.isfinite(x[fields].to_numpy()).all() or (x.dt_t_s<=0).any() or (x.speed_kmh<0).any():raise ValueError('Valores fisicos invalidos')
    if np.max(np.abs((x.a_t_m_s2-x.a_t_minus_1_m_s2)/x.dt_t_s-x.j_t_observed_m_s3))>.020001:raise ValueError('Jerk inconsistente')
    # H01 ya define la segmentacion temporal: ordenar dentro del segmento, no unir RAW.
    x=x.sort_values(['driver_id','session_id','segment_id','raw_row'],kind='stable').reset_index(drop=True)
    for _,g in x.groupby(['driver_id','session_id','segment_id'],sort=False):
        if len(g)>1 and not np.allclose(g.a_t_m_s2.to_numpy()[:-1],g.a_t_minus_1_m_s2.to_numpy()[1:],atol=1e-7,rtol=0):
            raise ValueError('Segmento discontinuo en aceleracion')
    return x,m

def thresholds(x,amin,jmin):
    a=x.a_t_m_s2.to_numpy(float);j=x.j_t_observed_m_s3.to_numpy(float)
    moving=x.speed_kmh.to_numpy(float)>5
    prior_speed=x.groupby(['driver_id','session_id','segment_id'],sort=False)['speed_kmh'].shift(1).to_numpy(float)
    valid_jerk=moving & (prior_speed>5)
    masks={'aceleracion_intensa':moving&(a>=amin),
           'frenada_intensa':moving&(a<=-amin),
           'jerk_intenso_pos':valid_jerk&(j>=jmin),
           'jerk_intenso_neg':valid_jerk&(j<=-jmin)}
    masks['cualquier_maniobra_intensa']=np.logical_or.reduce(list(masks.values()))
    return masks

def aggregate_events(x,mask,kind,threshold_name):
    # Evento: racha de muestras consecutivas dentro de MISMO segmento con condición verdadera.
    if len(x)!=len(mask):raise ValueError('Mascara desalineada')
    rows=[]
    for (driver,sess,seg),g in x.groupby(['driver_id','session_id','segment_id'],sort=False):
        ix=g.index.to_numpy();ff=np.asarray(mask,dtype=bool)[ix]
        starts=np.flatnonzero(ff & ~np.r_[False,ff[:-1]])
        ends=np.flatnonzero(ff & ~np.r_[ff[1:],False])
        for local_id,(start,end) in enumerate(zip(starts,ends),1):
            z=g.iloc[start:end+1]
            rows.append(dict(escenario=threshold_name,evento=kind,driver_id=driver,session_id=sess,segment_id=seg,
                ordinal_en_segmento=int(local_id),raw_row_inicio=int(z.raw_row.iloc[0]),raw_row_fin=int(z.raw_row.iloc[-1]),
                n_muestras=int(len(z)),duracion_exposicion_s=float(z.dt_t_s.sum()),
                velocidad_media_kmh=float(z.speed_kmh.mean()),
                max_abs_a_m_s2=float(z.a_t_m_s2.abs().max()),max_abs_jerk_m_s3=float(z.j_t_observed_m_s3.abs().max())))
    return rows

def analyze(x,threshold_config=THRESHOLDS):
    sample=[];events=[];session=[]
    for name,amin,jmin in threshold_config:
        masks=thresholds(x,amin,jmin)
        for (dr,se),g in x.groupby(['driver_id','session_id'],sort=False):
            idx=g.index.to_numpy();eligible=g.speed_kmh>5
            ex=float(g.loc[eligible,'dt_t_s'].sum())
            d={'escenario':name,'driver_id':dr,'session_id':se,'umbral_abs_a_m_s2':amin,'umbral_abs_jerk_m_s3':jmin,
               'n_registros_total':len(g),'n_marcha_gt5':int(eligible.sum()),'exposicion_dt_marcha_s':ex,
               'n_segmentos_total':int(g.segment_id.nunique())}
            for k,mask in masks.items():
                v=mask[idx];d['n_muestras_'+k]=int(v.sum())
                d['fraccion_muestras_'+k]=(float(v.sum()/eligible.sum()) if eligible.sum() else None)
                d['tiempo_marcado_'+k+'_s']=float(g.loc[v,'dt_t_s'].sum())
                d['fraccion_exposicion_'+k]=float(d['tiempo_marcado_'+k+'_s']/ex) if ex else None
            session.append(d)
        for kind,mask in masks.items():
            sample.append({'escenario':name,'evento':kind,'n_muestras':int(mask.sum()),'n_episodios':None,
                           'tiempo_marcado_s':float(x.loc[mask,'dt_t_s'].sum())})
            rows=aggregate_events(x,mask,kind,name)
            sample[-1]['n_episodios']=len(rows)
            events.extend(rows)
    return pd.DataFrame(session),pd.DataFrame(sample),pd.DataFrame(events)

def report(per,tot,evt):
    lines=['# H11.3c — Caracterización de maniobras cinemáticas en POLIDriving (desarrollo)',
           '', '**Dictamen:** eventos cinemáticos intensos candidatos; NO etiquetas de imprudencia ni infracciones.',
           'No se utilizaron las etiquetas expertas de riesgo, datos sintéticos, Richard ni la sesión reservada de Alonso.',
           '', '## Sensibilidad exploratoria — umbrales simétricos NO normativos',
           '| Escenario | Evento | muestras | episodios | Σdt de muestras marcadas (s) |','|---|---|---:|---:|---:|']
    for _,r in tot.iterrows():lines.append(f"| {r.escenario} | {r.evento} | {int(r.n_muestras)} | {int(r.n_episodios)} | {r.tiempo_marcado_s:.2f} |")
    lines.extend(['','## Interpretación obligatoria',
      '- `SIN BANDERA` significa sin cruce de los umbrales analizados, NO conducción nominal verificada.',
      '- `CON BANDERA` significa cinemática intensa observada, NO prueba de imprudencia ni responsabilidad del conductor.',
      '- Se excluye v<=5 km/h por comparabilidad con H01; para flag de jerk se exige además velocidad anterior >5 km/h dentro del mismo segmento.',
      '- El jerk se deriva de aceleración con dt irregular: considerar ruido y cuantización de instrumentos.',
      '- Umbrales 1.5/2/3 m/s² y 2/3/5 m/s³ son una grilla de SENSIBILIDAD, NO umbrales legales, naturales ni validados.',
      '- Las tasas de muestras/episodios describen SOLAMENTE las cinco sesiones de desarrollo; episodios no independientes.',
      '- La duración es suma de intervalos de muestra elegibles y NO necesariamente tiempo cronológico completo del trayecto.',
      '- Eventos por racha solo fusionan dentro del mismo segment_id; no se unen segmentos ni sesiones.',
      '- Aceleración intensa también puede ser necesaria o segura; posible falta de contexto humano/geométrico.',
      '- Sin labels independientes de imprudencia no se pueden reportar precision, recall o accuracy.',
      '- No convertir el 15/30/50% de H09 en prevalencia de conductores de Quito.',
      '', '## Pregunta respondida',
      '**¿Existen maniobras cinemáticamente intensas?** Ver conteos calculados. **¿Demuestran conducción imprudente?** No por sí solas.',
      '', '## Decisión para siguiente fase',
      'Si hay episodios: muestrear episodios para revisión ciega con vídeo/contexto independiente (si legalmente accesible);',
      'si no existe el material, presentar resultados como conducción no nominal cinemática, no como imprudencia comprobada.',
      'No reentrenar Vine ni alterar SUMO en este hito.',''])
    return '\n'.join(lines)

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path('.'))
    ap.add_argument('--h01',type=Path)
    ap.add_argument('--guardar',action='store_true')
    a=ap.parse_args(argv)
    root=a.root.resolve(); allowed_root=(root/'resultados').resolve()
    src=(a.h01 if a.h01 is not None else root/'resultados'/'ntvc_vine_r_01_cohortes_movimiento_regenerado').resolve()
    if not src.is_relative_to(allowed_root):raise ValueError('H01 fuera de resultados')
    if not (src/'manifest.json').is_file() and a.h01 is None:src=(root/'resultados'/'ntvc_vine_r_01_cohortes_movimiento').resolve()
    x,manifest=load_h01(src)
    print(f'FUENTE H01 OK: {len(x):,} muestras, {x.driver_id.nunique()} conductores, {x.session_id.nunique()} sesiones; SHA verificado')
    per,summary,episodes=analyze(x)
    for _,row in summary.iterrows():print(f"{row.escenario:27} {row.evento:27} muestras={int(row.n_muestras):6} episodios={int(row.n_episodios):6}")
    print('NOTA: NINGUNA BANDERA ES UNA ETIQUETA DE IMPRUDENCIA NI UN DIAGNOSTICO LEGAL.')
    if not a.guardar:
        print('PREFLIGHT+ANALISIS en memoria OK; sin escritura. Añadir --guardar para reportes nuevos.');return 0
    out=root/'resultados'/('h11_3c_cinematica_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if out.exists():raise ValueError('Salida existente')
    out.mkdir(parents=True)
    files={'resumen_por_sesion_h11_3c.csv':per,'resumen_por_umbral_h11_3c.csv':summary,'episodios_candidatos_h11_3c.csv':episodes}
    for name,df in files.items():df.to_csv(out/name,index=False,encoding='utf-8-sig')
    (out/'dictamen_h11_3c.md').write_text(report(per,summary,episodes),encoding='utf-8')
    m={'version':VER,'input_h01':str(src),'source_h01_sha256':sha(src/'cohortes_muestras_verificadas.csv'),
       'source_manifest_sha256':sha(src/'manifest.json'),'n_rows':len(x),'n_sessions':x.session_id.nunique(),
       'n_drivers':x.driver_id.nunique(),'threshold_grid':[dict(name=n,abs_accel=a,abs_jerk=j) for n,a,j in THRESHOLDS],
       'ground_truth_imprudence':False,'holdout_read':False,'trained':False,'sumo_run':False,
       'outputs_sha256':{n:sha(out/n) for n in [*files,'dictamen_h11_3c.md']},
       'timestamp_utc':datetime.now(timezone.utc).isoformat()}
    (out/'manifiesto_h11_3c.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    print('INFORME:',out);return 0

if __name__=='__main__':raise SystemExit(main())
