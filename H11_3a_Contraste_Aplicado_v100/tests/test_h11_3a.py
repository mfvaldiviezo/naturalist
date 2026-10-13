import importlib.util, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
SRC=Path(__file__).resolve().parents[1]/'h11_3a_contraste_aplicado.py'
spec=importlib.util.spec_from_file_location('h11_3a',SRC)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class TestAuditor(unittest.TestCase):
    def test_h01_sessions_guard(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fake.csv'
            pd.DataFrame([dict(driver_id='richard',session_id='20231227_104130',segment_id=1,raw_row=1,
                              a_t_m_s2=0,a_t_minus_1_m_s2=0,j_t_observed_m_s3=0,dt_t_s=.5,speed_kmh=10)]).to_csv(p,index=False)
            with self.assertRaisesRegex(ValueError,'reservada'):
                m.load_h01(p)
    def test_h01_manifest_guard_and_sha(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'cohortes_muestras_verificadas.csv';p.write_text('a\n1\n')
            doc={'original_verified_sha256':m.H01_SOURCE_SHA,'allowed_sessions':[list(t) for t in sorted(m.DEV_SESSIONS)],'file_sha256':{p.name:m.sha(p)}}
            (root/'manifest.json').write_text(json.dumps(doc))
            # Faltan columnas, pero verificamos que el hash y sesiones pasaron, no la lectura del test.
            with self.assertRaisesRegex(ValueError,'campos ausentes'):m.verify_h01(root)
            p.write_text('a\n2\n')
            with self.assertRaisesRegex(ValueError,'SHA'):m.verify_h01(root)
    def test_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'other').mkdir()
            with self.assertRaisesRegex(ValueError,'fuera'):m.guarded_path(root/'other',root)
    def test_metric_compare_nodata(self):
        ref=pd.DataFrame({'a':[1,2,3]}); sim=pd.DataFrame({'a':[3,2,1]})
        r=m.metric_compare(ref,sim,'a',ref.a.notna(),sim.a.notna(),'g')
        self.assertEqual(r['nota'],'POCAS_MUESTRAS')
    def test_metric_compare_equal(self):
        ref=pd.DataFrame({'a':np.arange(40,dtype=float)});sim=ref.copy()
        r=m.metric_compare(ref,sim,'a',ref.a.notna(),sim.a.notna(),'g')
        self.assertAlmostEqual(r['wasserstein'],0.0)
        self.assertAlmostEqual(r['ks'],0.0)
    def test_individual_metrics_conditional(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'traj.csv'
            rows=[]
            for driver, sess in sorted(m.DEV_SESSIONS):
                for i in range(4):
                    rows.append(dict(driver_id=driver,session_id=sess,segment_id=1,raw_row=i+5,
                      a_t_m_s2=float(i%2),a_t_minus_1_m_s2=float((i-1)%2) if i else 0,
                      j_t_observed_m_s3=2 if i%2 else -2,dt_t_s=.5,speed_kmh=10))
            pd.DataFrame(rows).to_csv(p,index=False)
            o=m.load_h01(p)
            self.assertEqual(int(o.moving_a.sum()),20)
            self.assertEqual(int(o.moving_j.sum()),15)
    def test_sim_continuity_and_cohorts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);t=root/'trayectorias_h11.csv'
            pd.DataFrame([dict(vehicle_id='1',time_s=t0,dt_s=.5,cohort='vine_only',speed_m_s=10,accel_m_s2=1,jerk_observed_m_s3=0) for t0 in [0.5,1,2]]).to_csv(t,index=False)
            dta=m.load_h11(root,'hibrido_contextual')
            self.assertEqual(int(dta.moving_j.sum()),1)
    def test_temporal_gap_not_bridged(self):
        data=pd.DataFrame({'entity':['x']*3,'segment':['s']*3,'a':[0,0,0],
                           'moving_a':[True]*3,'adjacent_pair':[False,True,True],
                           'dt':[.5]*3,'time_s':[.5,1.,3.]})
        r=m.temporal_descriptive(data)
        self.assertEqual(r['zero_runs'],2)
        self.assertEqual(r['lag1_pairs'],1)

    def test_end_to_end_synthetic_without_training(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);h01=root/'h01';nom=root/'nom';hib=root/'hib'
            for p in [h01,nom,hib]:p.mkdir()
            rows=[]
            for driver,sess in sorted(m.DEV_SESSIONS):
                for i in range(8):
                    a=float(i%2)
                    rows.append({'driver_id':driver,'session_id':sess,'segment_id':1,'raw_row':i+10,
                      'a_t_m_s2':a,'a_t_minus_1_m_s2':float((i-1)%2) if i else 0,
                      'j_t_observed_m_s3':(2 if i%2 else -2),'dt_t_s':.5,'speed_kmh':10.})
            pd.DataFrame(rows).to_csv(h01/'cohortes_muestras_verificadas.csv',index=False)
            manifest={'original_verified_sha256':m.H01_SOURCE_SHA,
              'allowed_sessions':[list(t) for t in sorted(m.DEV_SESSIONS)],
              'file_sha256':{'cohortes_muestras_verificadas.csv':m.sha(h01/'cohortes_muestras_verificadas.csv')}}
            (h01/'manifest.json').write_text(json.dumps(manifest))
            for path,cohort in [(nom,'unclassified'),(hib,'vine_only')]:
                rs=[dict(vehicle_id='1',time_s=.5*i,dt_s=.5,cohort=cohort,
                   speed_m_s=10,accel_m_s2=float(i%2),jerk_observed_m_s3=2.) for i in range(1,9)]
                pd.DataFrame(rs).to_csv(path/'trayectorias_h11.csv',index=False)
            acts=root/'actions.csv'
            pd.DataFrame([{'vehicle_id':'1','target_time_s':1.,'command_issued':True}]).to_csv(acts,index=False)
            with patch.object(m,'verify_h11',return_value={'pareado':{'status':'INVARIANZA_PAREADA_REVERIFICADA'}}):
                result,stats,dist=m.summarize(root,h01,nom,hib,acts)
            self.assertEqual(result['counts']['vine_targets_con_muestra'],1)
            self.assertEqual(result['counts']['polidriving'],40)
            self.assertIn('lag1_acf_macro',stats.columns)
            self.assertEqual(len(dist),14)

    def test_actuation_exact_targets(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'actions.csv';pd.DataFrame([dict(vehicle_id='1',target_time_s=1.,command_issued=True),dict(vehicle_id='1',target_time_s=1.5,command_issued=False)]).to_csv(p,index=False)
            a=m.get_command_times(p)
            t=pd.DataFrame({'entity':['1','1'],'time_s':[1.0,1.5],'cohort':['vine_only','vine_only']})
            r=m.label_actuation(t,a)
            self.assertEqual(r.actuacion.tolist(),[True,False])
            t.loc[0,'cohort']='h09_only'
            with self.assertRaises(ValueError):m.label_actuation(t,a)

if __name__=='__main__': unittest.main()
