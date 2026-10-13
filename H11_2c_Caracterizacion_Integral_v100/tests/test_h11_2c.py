# -*- coding: utf-8 -*-
import csv
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SRC=Path(__file__).resolve().parents[1]/'h11_2c_caracterizar.py'
spec=importlib.util.spec_from_file_location('auditor_h112c',SRC)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def csvwrite(path,columns,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)


def traj(t,v,cohort,v_mps=10,limit=9,leader='L',gap=5,head=.5,ttc=1,a=-1,jerk=2,internal=False):
    return dict(time_s=t,dt_s=.5,vehicle_id=v,cohort=cohort,lane_id='A0B0_0',
                internal_lane=str(internal).lower(),speed_m_s=v_mps,
                posted_lane_limit_m_s=limit,accel_m_s2=a,jerk_observed_m_s3=jerk,
                leader_id=leader,gap_m=gap,headway_s=head,ttc_s=ttc)


def make_source(root,scenario,rows,inter=None,safety=None):
    base=root/scenario/'observado'/'telemetria'
    base.mkdir(parents=True)
    csvwrite(base/'trayectorias_h11.csv',sorted(m.TRAJ_REQUIRED),rows)
    csvwrite(base/'eventos_semaforicos_h11.csv',['vehicle_id','event_kind','time_s'],[])
    csvwrite(base/'eventos_interseccion_h11.csv',sorted(m.INTER_REQUIRED),inter or [])
    csvwrite(base/'seguridad_h11.csv',sorted(m.SAFE_REQUIRED),safety or
        [dict(time_s=(i+1)*.5,colliding_vehicles_count=0,teleport_start_count=0,emergency_stop_count=0) for i in range(4)])
    manifest=dict(condition=scenario,empirically_calibrated_quito=False,observed_steps=4,
                  seed=101,version='H11.2-test',outputs_sha256={name:m.sha(base/name) for name in m.FILES})
    (base/'manifest_h11_2.json').write_text(json.dumps(manifest),encoding='utf-8')
    return base


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name);(self.root/'resultados').mkdir()
        self.st=dict(steps=4,dt=.5,speed_margin_kmh=3.6,strong_brake=-4.5,extreme_brake=-7.0,jerk_threshold=8.0)
        times=(.5,1,1.5,2)
        nr=[traj(t,'A','unclassified',a=-9 if i==1 else -1,jerk=-10 if i==1 else 1,
                 head=.5 if i in (0,1) else 1.5,ttc=1 if i in (0,1) else 3) for i,t in enumerate(times)]
        nr += [traj(t,'B','unclassified',v_mps=8,limit=10,leader='',gap='',head='',ttc='') for t in times]
        hr=[traj(t,'A','both',a=-9 if i in (1,2) else -1,jerk=-10 if i==1 else 1,
                 head=.5 if i in (0,1,2) else 1.5,ttc=1 if i in (0,1,2) else 3) for i,t in enumerate(times)]
        hr += [traj(t,'B','neither',v_mps=8,limit=10,leader='',gap='',head='',ttc='') for t in times]
        self.nom=make_source(self.root/'resultados','nominal',nr)
        self.hib=make_source(self.root/'resultados','hibrido_contextual',hr,inter=[dict(vehicle_id='A',cohort='both',
            start_s=.5,end_s=2,duration_s=1.5,event_kind='stopped_on_internal_lane_candidate',
            gridlock_confirmed='false',censored_end='false')])

    def tearDown(self):self.tmp.cleanup()

    def _run(self):
        return m.analyze(self.nom,self.hib,self.st,require_paired=False)

    def test_verify_source_and_sha(self):
        self.assertEqual(m.verify_source(self.nom,'nominal',4)['observed_steps'],4)
    def test_sha_tamper_reject(self):
        with (self.hib/'trayectorias_h11.csv').open('a') as f:f.write('corrupt\n')
        with self.assertRaisesRegex(ValueError,'INTEGRIDAD FALLIDA'):self._run()
    def test_cohort_target_nominal(self):
        *_,result=self._run()
        self.assertEqual(result['vehiculos']['nominal'],2)
        self.assertEqual(result['emparejamiento']['presentes_en_ambos'],2)
    def test_nominal_actual_unclassified_but_target_both(self):
        data,vs,eps,groups,pairs,*rest=self._run()
        v=next(x for x in vs if x['escenario']=='nominal' and x['vehicle_id']=='A')
        self.assertEqual(v['cohorte_actual'],'unclassified')
        self.assertEqual(v['cohorte_objetivo'],'both')
    def test_episodes_consecutive_and_duration(self):
        data,vs,eps,*_=self._run()
        ep=[x for x in eps if x['escenario']=='hibrido_contextual' and x['vehicle_id']=='A' and x['indicador']=='headway_lt_1s']
        self.assertEqual(len(ep),1)
        self.assertEqual(ep[0]['duracion_observada_s'],1.5)
        self.assertTrue(ep[0]['censura_izquierda'])
        self.assertFalse(ep[0]['censura_derecha'])
    def test_different_denominators(self):
        _,vs,*_=self._run()
        v=next(x for x in vs if x['escenario']=='nominal' and x['vehicle_id']=='B')
        self.assertEqual(v['headway_lt_1s_validos'],0)
        self.assertIsNone(v['headway_lt_1s_tasa'])
        self.assertEqual(v['exceso_limite_bruto_validos'],4)
    def test_flags_safety(self):
        r=traj(.5,'X','both',a=-9,jerk=-15)
        flags=m.indicator_flags(r)
        self.assertTrue(flags['frenada_extrema']);self.assertTrue(flags['jerk_alto'])
    def test_speed_margin_effect(self):
        r=traj(.5,'X','both',v_mps=10,limit=9)
        fl=m.indicator_flags(r,tolerance_kmh=3.6)
        self.assertTrue(fl['exceso_limite_bruto'])
        self.assertFalse(fl['exceso_limite_margen'])
    def test_paired_delta(self):
        _,_,_,_,pairs,*_=self._run()
        a=next(x for x in pairs if x['vehicle_id']=='A')
        self.assertGreater(a['headway_lt_1s_delta_tasa'],0)
    def test_no_confirm_gridlock(self):
        self.assertEqual(len(m.summarize_intersections(self.hib,'hibrido_contextual',{'A':'both'})),1)
        r=m.summarize_intersections(self.hib,'hibrido_contextual',{'A':'both'})[0]
        self.assertIs(r['gridlock_confirmado'],False)
    def test_refuse_fake_gridlock(self):
        csvwrite(self.hib/'eventos_interseccion_h11.csv',sorted(m.INTER_REQUIRED),[
          dict(vehicle_id='A',cohort='both',start_s=.5,end_s=2,duration_s=1.5,
               event_kind='stopped_on_internal_lane_candidate',gridlock_confirmed='true',censored_end='false')])
        with self.assertRaisesRegex(ValueError,'no puede acreditar gridlock'):
            m.summarize_intersections(self.hib,'hibrido_contextual',{'A':'both'})
    def test_save_manifest_is_json_serializable(self):
        *_,summary=self._run()
        json.dumps(summary,ensure_ascii=False)
    def test_safe_outside(self):
        with self.assertRaises(ValueError):m.safe_output(self.root,self.root/'oops',[self.nom,self.hib])
    def test_requires_real_paired_provenance(self):
        with self.assertRaises(FileNotFoundError):self._run_requires()
    def _run_requires(self):return m.analyze(self.nom,self.hib,self.st,require_paired=True)
    def test_end_to_end_outputs(self):
        import contextlib,io
        out=self.root/'resultados'/'audit-test'
        with contextlib.redirect_stdout(io.StringIO()):
            rc=m.main(['--root',str(self.root),'--nom',str(self.nom),'--hib',str(self.hib),
                       '--steps','4','--guardar','--out',str(out)])
        self.assertEqual(rc,0)
        self.assertEqual(len(list(out.iterdir())),10)
        mf=json.loads((out/'manifiesto_h11_2c.json').read_text(encoding='utf-8'))
        self.assertIn('vehiculos_h11_2c.csv',mf['sha256_reportes'])
    def test_no_overwrite(self):
        folder=self.root/'resultados'/'audit-existing';folder.mkdir()
        with self.assertRaises(FileExistsError):m.safe_output(self.root,folder,[self.nom,self.hib])
    def test_quantile_singleton(self):
        self.assertEqual(m.quantile([3],.95),3)
        self.assertIsNone(m.quantile([],.95))
    def test_gap_starts_new_episode(self):
        row={'flags':{'headway_lt_1s':True},'a':None,'j':None,'v':2,'dt':.5}
        eps=m.build_contiguous_episodes([{'t':.5,**row},{'t':1.5,**row}],'headway_lt_1s')
        self.assertEqual(len(eps),2)
    def test_zero_events_with_valid_denominator(self):
        data,vs,*_=self._run()
        b=next(x for x in vs if x['escenario']=='nominal' and x['vehicle_id']=='B')
        self.assertEqual(b['frenada_fuerte_tasa'],0)
    def test_revalidate_valid_paired_files(self):
        for scenario in ('nominal','hibrido_contextual'):
            base=self.root/'resultados'/scenario
            content=b'invariant original traffic\n'
            for side in ('control','observado'):
                p=base/side/scenario/'trafico_h09.csv'
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(content)
            digest=hashlib.sha256(content).hexdigest()
            audit=dict(mode=scenario,status='INVARIANZA_BYTE_A_BYTE_VERIFICADA',
                comparison={'trafico_h09.csv':{'identical':True,'sha_control':digest,'sha_observado':digest}})
            (base/'comparacion_h11_2.json').write_text(json.dumps(audit))
        self.assertEqual(m.verify_paired(self.nom,'nominal')['status'],'INVARIANZA_PAREADA_REVERIFICADA')
        *_,summary=m.analyze(self.nom,self.hib,self.st,require_paired=True)
        self.assertEqual(summary['integridad']['pareado_hibrido']['archivos_revalidados'],2)
    def test_cannot_fake_paired_identical_files(self):
        base=self.root/'resultados'/'nominal'
        for side in ('control','observado'):
            p=base/side/'nominal'/'trafico_h09.csv'
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(b'different bytes' if side=='control' else b'original')
        digest=hashlib.sha256(b'original').hexdigest()
        audit=dict(mode='nominal',status='INVARIANZA_BYTE_A_BYTE_VERIFICADA',
            comparison={'trafico_h09.csv':{'identical':True,'sha_control':digest,'sha_observado':digest}})
        (base/'comparacion_h11_2.json').write_text(json.dumps(audit))
        with self.assertRaisesRegex(ValueError,'Archivo pareado alterado'):
            m.verify_paired(self.nom,'nominal')
    def test_risk_extreme_is_actual_metric(self):
        row={'flags':{'headway_lt_1s':True},'a':None,'j':None,'v':15,'dt':.5,'headway':.25,'ttc':4,'limit':10}
        ep=m.build_contiguous_episodes([{'t':.5,**row}],'headway_lt_1s')
        self.assertEqual(ep[0]['valor_extremo'],.25)
    def test_context_stratification(self):
        data,*_=self._run()
        contexts=m.road_context(data)
        self.assertEqual(len(contexts),4)
        external=next(r for r in contexts if r['escenario']=='hibrido_contextual' and r['tipo_carril']=='externo')
        self.assertEqual(external['muestras'],8)
    def test_unknown_target_is_not_neither(self):
        nom=[traj(.5,'Z','unclassified')]
        # Direct read pipeline after rehash; target not in hybrid remains unknown
        csvwrite(self.nom/'trayectorias_h11.csv',sorted(m.TRAJ_REQUIRED),nom)
        with self.assertRaises(ValueError):m.read_trajectories(self.nom,'nominal',{},self.st,{})

if __name__=='__main__':unittest.main()
