import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('h126',ROOT/'h12_6_auditar.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(mode):
    rows=[]; decisions=[]
    for i in range(120):
        rows.append({'tick':i,'time_s':(i+1)*.5,'n_active':2,'n_halted':1,
            'mean_speed_kmh':30 if mode!='active' else 29,
            'arrivals':1 if i==30 else 0,'departures':1 if i==1 else 0,
            'collisions':0,'teleports_start':0,
            'vehicle_kinematics_sha256':'base'+str(i) if mode!='active' or i<10 else 'changed'+str(i)})
    for i in range(12):
        decisions.append({'i':i,'sim_time_s':(i+1)*5,'action':0 if mode!='active' else (1 if i>=2 else 0),
           'reward':-2,'queue':1,'delay_proxy':5,'gini':.2})
    active=mode=='active'
    info={'n_commands':20,'n_commands_confirmed':20,'n_vehicles_commanded':6,
          'remaining_pending':0,'safety_halt':False,
          'commands_by_window':{'0':20},'n_safety_eligible':196,'n_action_viable':20}
    return {'result':'SMOKE_OK','mode':mode,'model':'ppo_ideal','checkpoint_sha256':'abc',
      'n_decisions':12,'n_microticks':120,'start_time_s':0,'end_time_s':60,
      'h10_reference_n':300,'h10_reference_path':'H08-reference','h10_source_sha256':{'A':'same'},
      'inputs':{'cfg_original_sha256':'cfg','net_sha256':'net','routes_sha256':'routes'},
      'commands':20 if active else 0,'command_records':[{}]*20 if active else [],
      'h09_selected_n':0,'vine_assigned_n':45 if active else 0,
      'trace_sha256':'SHA-a' if active else 'SHA-n','microticks':rows,'decisions':decisions,
      'extra':{'vine':info} if active else {}}


class TestReport(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.pair=self.root/'pair'
        self.active_dir=self.root/'active'
        (self.pair/'nominal').mkdir(parents=True)
        (self.pair/'probe').mkdir(parents=True)
        (self.active_dir/'active').mkdir(parents=True)
        for mode,path in [('nominal',self.pair/'nominal'),('probe',self.pair/'probe'),('active',self.active_dir/'active')]:
            (path/'piloto_h12_5.json').write_text(json.dumps(fixture(mode)),encoding='utf-8')
        (self.pair/'pareado_h12_5.json').write_text(json.dumps({'status':'PAREADO_NOMINAL_PROBE_OK',
            'decisions':12,'microticks':120,'traffic_sha256':'SHA-n'}),encoding='utf-8')
        self.csv=self.active_dir/'active'/'acciones_h08b.csv'
        with self.csv.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['command_issued','matched_t_plus_dt','guarded_a','observed_a_next','vehicle_id'])
            w.writeheader()
            for i in range(20): w.writerow({'command_issued':True,'matched_t_plus_dt':True,
                'guarded_a':1,'observed_a_next':1+1e-14,'vehicle_id':str(i%6)})

    def tearDown(self):self.temp.cleanup()
    def run_report(self):
        return m.compare(m.load(self.pair/'nominal/piloto_h12_5.json'),
            m.load(self.pair/'probe/piloto_h12_5.json'),
            m.load(self.active_dir/'active/piloto_h12_5.json'),self.pair,self.active_dir/'active')

    def test_full_report(self):
        r=self.run_report()
        self.assertEqual(r['status'],'H12_6_AUDITORIA_OK')
        self.assertEqual(r['first_kinematics_difference_time_s'],5.5)
        self.assertEqual(r['n_different_signal_actions'],10)
        self.assertEqual(r['metrics']['nominal']['halted_vehicle_seconds'],60.)
        self.assertEqual(r['metrics']['nominal']['arrivals_total'],1)
        self.assertEqual(r['active_minus_nominal']['mean_speed_time_kmh'],-1)
        self.assertLess(r['vine_evidence']['max_abs_acceleration_error_m_s2'],1e-10)
        self.assertIn('Auditoría offline',m.markdown(r))

    def test_wrong_checkpoint_rejected(self):
        x=m.load(self.active_dir/'active/piloto_h12_5.json')
        x['checkpoint_sha256']='different'
        (self.active_dir/'active/piloto_h12_5.json').write_text(json.dumps(x))
        with self.assertRaisesRegex(m.AuditFailure,'checkpoint'):self.run_report()

    def test_demand_change_rejected(self):
        x=m.load(self.active_dir/'active/piloto_h12_5.json');x['inputs']['routes_sha256']='changed'
        (self.active_dir/'active/piloto_h12_5.json').write_text(json.dumps(x))
        with self.assertRaisesRegex(m.AuditFailure,'routes_sha256'):self.run_report()

    def test_missing_confirmed_rejected(self):
        x=m.load(self.active_dir/'active/piloto_h12_5.json');x['extra']['vine']['n_commands_confirmed']=19
        (self.active_dir/'active/piloto_h12_5.json').write_text(json.dumps(x))
        with self.assertRaisesRegex(m.AuditFailure,'no confirmados'):self.run_report()

    def test_collision_rejected(self):
        x=m.load(self.active_dir/'active/piloto_h12_5.json');x['microticks'][28]['collisions']=1
        (self.active_dir/'active/piloto_h12_5.json').write_text(json.dumps(x))
        with self.assertRaisesRegex(m.AuditFailure,'colisiones'):self.run_report()

    def test_truncated_rejected(self):
        x=m.load(self.active_dir/'active/piloto_h12_5.json');x['microticks'].pop()
        (self.active_dir/'active/piloto_h12_5.json').write_text(json.dumps(x))
        with self.assertRaisesRegex(m.AuditFailure,'telemetría incompleta'):self.run_report()

    def test_probe_sha_rejected(self):
        x=m.load(self.pair/'probe/piloto_h12_5.json');x['trace_sha256']='mismatch'
        (self.pair/'probe/piloto_h12_5.json').write_text(json.dumps(x))
        with self.assertRaisesRegex(m.AuditFailure,'SHA'):self.run_report()

    def test_csv_unconfirmed_rejected(self):
        with self.csv.open(encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        rows[4]['matched_t_plus_dt']='False'
        with self.csv.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]))
            w.writeheader();w.writerows(rows)
        with self.assertRaisesRegex(m.AuditFailure,'sin observación'):self.run_report()

    def test_no_double_counting_departures(self):
        r=m.metrics(fixture('nominal'))
        self.assertEqual(r['departures_total'],1)
        self.assertAlmostEqual(r['mean_speed_vehicle_weighted_kmh'],30.)

    def test_reward_not_stat_test(self):
        r=self.run_report()
        self.assertIn('single_seed_paired_pilot_not_resilience',r['comparison_type'])
        self.assertTrue(any('inferencia estadística' in s for s in r['limitations']))


if __name__=='__main__':unittest.main()
