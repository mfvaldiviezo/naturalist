import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import pandas as pd

SCRIPT=Path(__file__).resolve().parents[1]/'h11_3a_bandas_velocidad.py'
spec=importlib.util.spec_from_file_location('auditor_3a_bandas',SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PruebasBandas(unittest.TestCase):
    def frame(self, entity='x',a=(0,1,-1),speed=(6,20,21),metric_j=None, cohort='vine_only'):
        if metric_j is None: metric_j=[0]*len(a)
        return pd.DataFrame(dict(entity=[entity]*len(a),cohort=[cohort]*len(a),
              a=list(a),jerk=list(metric_j),dt=[.5]*len(a),speed_kmh=list(speed),
              moving_a=[True]*len(a),moving_j=[True]*len(a)))

    def test_boundary_5_excluded(self):
        d=self.frame(a=[0,0,0,0,0,0],speed=[5,5.01,20,40,60,60.01])
        bins=list(m.assign_speed_bins(d).speed_bin.astype(str))
        self.assertEqual(bins,['nan','05_20','05_20','20_40','40_60','gt60'])

    def test_units_and_zeros(self):
        df=self.frame(a=[0,.04,.11],speed=[15,15,15])
        r=m.column_statistics(df,'a',df.moving_a)
        self.assertEqual(r['n'],3)
        self.assertEqual(r['entities'],1)
        self.assertAlmostEqual(r['p_abs_le_005'],2/3)
        self.assertAlmostEqual(r['p_abs_le_010'],2/3)

    def test_no_unsupported_distances(self):
        a=m.assign_speed_bins(self.frame(speed=(6,6,6)))
        c=m.compare_bin(a,a,'a','05_20')
        self.assertEqual(c['status'],'INSUFFICIENT_SUPPORT')
        self.assertIsNone(c['wasserstein'])

    def test_distances_equal(self):
        a=m.assign_speed_bins(self.frame(a=np.arange(40).astype(float),speed=[10]*40,metric_j=[0]*40))
        c=m.compare_bin(a,a,'a','05_20')
        self.assertEqual(c['status'],'DESCRIPTIVE_ONLY')
        self.assertAlmostEqual(c['wasserstein'],0)
        self.assertAlmostEqual(c['ks'],0)

    def test_nominal_cohort_unpaired(self):
        nominal=pd.concat([self.frame('id1'),self.frame('id2')],ignore_index=True)
        nominal['cohort']='unclassified'
        hybrid=self.frame('id1',cohort='both')
        r=m.enrich_nominal_cohorts(nominal,hybrid)
        self.assertEqual(set(r[r.entity=='id1'].cohort),{'both'})
        self.assertEqual(set(r[r.entity=='id2'].cohort),{'not_in_hybrid'})

    def test_paired_requires_min_samples(self):
        n=m.assign_speed_bins(self.frame(a=(1,)*10,speed=(15,)*10))
        h=m.assign_speed_bins(self.frame(a=(2,)*10,speed=(15,)*10))
        res=m.per_vehicle_paired(n,h)
        row=res[(res.banda_kmh=='05_20')&(res.variable=='a')&(res.cohorte=='vine_only')].iloc[0]
        self.assertEqual(row.n_vehiculos,1)
        self.assertAlmostEqual(row.media_delta_abs,1)

    def test_paired_suppresses_short_exposure(self):
        n=m.assign_speed_bins(self.frame(a=(1,)*9,speed=(15,)*9))
        h=m.assign_speed_bins(self.frame(a=(2,)*10,speed=(15,)*10))
        row=m.per_vehicle_paired(n,h).query("banda_kmh=='05_20' and variable=='a' and cohorte=='vine_only'").iloc[0]
        self.assertEqual(row.n_vehiculos,0)

    def test_command_context_and_consistency(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);actions=base/'act.csv';(base/'tele').mkdir()
            pd.DataFrame([
                dict(vehicle_id='210',time_s=2.5,target_time_s=3,command_issued=True,matched_t_plus_dt=True,proposed_a=.1,guarded_a=.1,observed_a_next=-1.8,guard_intervened=False),
                dict(vehicle_id='8',time_s=2.5,target_time_s=3,command_issued=True,matched_t_plus_dt=True,proposed_a=-3,guarded_a=-3,observed_a_next=-3,guard_intervened=False),
            ]).to_csv(actions,index=False)
            pd.DataFrame([
                dict(vehicle_id='210',time_s=2.5,speed_m_s=15,leader_id='56',gap_m=30,accel_m_s2=.2),
                dict(vehicle_id='210',time_s=3,speed_m_s=14,leader_id='56',gap_m=24,accel_m_s2=-1.8),
                dict(vehicle_id='56',time_s=2.5,speed_m_s=0,leader_id='',gap_m=np.nan,accel_m_s2=0),
                dict(vehicle_id='8',time_s=2.5,speed_m_s=10,leader_id='5',gap_m=10,accel_m_s2=-2),
                dict(vehicle_id='8',time_s=3,speed_m_s=8,leader_id='5',gap_m=8,accel_m_s2=-3),
                dict(vehicle_id='5',time_s=2.5,speed_m_s=0,leader_id='',gap_m=np.nan,accel_m_s2=0),
            ]).to_csv(base/'tele'/'trayectorias_h11.csv',index=False)
            result=m.command_and_leader(actions,base/'tele')
            self.assertEqual(len(result),2)
            self.assertEqual(int(result.error_gt_0_1.sum()),1)
            self.assertEqual(int(result.ttc_lt3.sum()),2)
            self.assertEqual(int((result.command_positive & result.ttc_lt3).sum()),1)

    def test_observer_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);(base/'tele').mkdir()
            pd.DataFrame([dict(vehicle_id='a',time_s=2.5,target_time_s=3,command_issued=True,matched_t_plus_dt=True,proposed_a=.1,guarded_a=.1,observed_a_next=999,guard_intervened=False)]).to_csv(base/'a.csv',index=False)
            pd.DataFrame([dict(vehicle_id='a',time_s=2.5,speed_m_s=10,leader_id='',gap_m=np.nan,accel_m_s2=.1),dict(vehicle_id='a',time_s=3,speed_m_s=10,leader_id='',gap_m=np.nan,accel_m_s2=0)]).to_csv(base/'tele'/'trayectorias_h11.csv',index=False)
            with self.assertRaises(ValueError):m.command_and_leader(base/'a.csv',base/'tele')

    def test_cannot_compute_future_closing_as_current(self):
        # El TTC instante de emisión solo utiliza el líder en t, jamás t+dt.
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);(base/'tele').mkdir()
            pd.DataFrame([dict(vehicle_id='71',time_s=2.5,target_time_s=3,command_issued=True,matched_t_plus_dt=True,proposed_a=1,guarded_a=1,observed_a_next=.8,guard_intervened=False)]).to_csv(base/'a.csv',index=False)
            pd.DataFrame([dict(vehicle_id='71',time_s=2.5,speed_m_s=12,leader_id='52',gap_m=13,accel_m_s2=1),dict(vehicle_id='71',time_s=3,speed_m_s=13,leader_id='52',gap_m=12,accel_m_s2=.8),dict(vehicle_id='52',time_s=2.5,speed_m_s=12.01,leader_id='',gap_m=np.nan,accel_m_s2=-1),dict(vehicle_id='52',time_s=3,speed_m_s=10,leader_id='',gap_m=np.nan,accel_m_s2=-2)]).to_csv(base/'tele'/'trayectorias_h11.csv',index=False)
            a=m.command_and_leader(base/'a.csv',base/'tele')
            self.assertTrue(pd.isna(a.ttc_cv_s.iloc[0]))

if __name__=='__main__':unittest.main()
