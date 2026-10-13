import copy
import importlib.util
from pathlib import Path
import unittest

src=Path(__file__).resolve().parents[1]/'h12_8_auditar.py'
spec=importlib.util.spec_from_file_location('h128',src)
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


def mock(mode='nominal',halt_at_boundary=False,local_diff=False):
    active=mode=='active'
    lanes=['a','b','c','d']+['d']*8
    series=[];traffic=[]
    for i in range(20):
        stop=(i==9 and halt_at_boundary)
        lane_vals=[{'lane':lane,'n':int(i>=4 and j==0),
                    'halted':int(stop and j==0),
                    'wait_s':float(stop and j==0)} for j,lane in enumerate(['a','b','c','d'])]
        row={'tick':i,'time_s':.5*(i+1), 'n_b1':sum(x['n'] for x in lane_vals),
             'halted_b1':sum(x['halted'] for x in lane_vals),
             'waiting_b1_s':sum(x['wait_s'] for x in lane_vals),'lanes':lane_vals}
        if local_diff and active and i==7:
            row['n_b1']+=1;row['lanes'][0]['n']+=1
        series.append(row)
        traffic.append({'tick':i,'time_s':row['time_s']})
    decisions=[]
    for i in range(2):
        state=[0.0]*34;state[28]=1;state[32]=float(i)/24.;state[33]=float(i)/24.
        decisions.append({'i':i,'sim_time_s':(i+1)*5.,'action':0,'reward':0.,'phase':0,
            'queue':0.,'delay_proxy':0.,'gini':0.,'state_before_34d':state[:],
            'state_after_34d':state[:]})
    diag={'b1_microticks':series,'initial_state_34d':decisions[0]['state_before_34d'],
      'controlled_lanes_unique_raw':['a','b','c','d'],'controlled_lanes_used_12':lanes,
      'outgoing_lanes':[],'green_phases':[0,2]}
    return {'result':'SMOKE_OK','mode':mode,'model':'ppo_ideal','checkpoint_sha256':'modelsha',
      'inputs':{'net_sha256':'netsha','routes_sha256':'rsha','cfg_original_sha256':'cfgsha'},
      'h10_source_sha256':{'src':'sha'},'n_decisions':2,'n_microticks':20,
      'decisions':decisions,'microticks':traffic,'h12_7_diagnostic':diag,
      'trace_sha256':'different' if active else 'original', 'commands':1 if active else 0}

class TestH128(unittest.TestCase):
    def setUp(self):
        self.n=mock();self.a=mock('active')
    def test_full_analysis(self):
        r=h.compare(self.n,self.a)
        self.assertEqual(r['status'],'H12_8_OFFLINE_OK')
        self.assertEqual(r['representation']['action_to_sumo_phase'],{'0':0,'1':2,'2':0,'3':2})
        self.assertEqual(r['representation']['controlled_lanes_unique_in_12'],4)
        self.assertEqual(r['exposure']['n_microticks_B1_count_difference'],0)
    def test_mismatch_queue(self):
        self.n=mock(halt_at_boundary=True)
        self.a=mock('active',halt_at_boundary=True)
        r=h.compare(self.n,self.a)
        self.assertEqual(r['exposure']['n_halt_queue_inconsistencies'],1)
    def test_local_diff_between_actions(self):
        self.a=mock('active',local_diff=True)
        r=h.compare(self.n,self.a)
        self.assertEqual(r['exposure']['first_B1_aggregate_difference_s'],4.)
        self.assertEqual(r['exposure']['n_decision_boundary_34d_differences'],0)
    def test_checkpoint_changed_rejected(self):
        self.a['checkpoint_sha256']='wrong'
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_routes_changed_rejected(self):
        self.a['inputs']['routes_sha256']='wrong'
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_same_trace_rejected(self):
        self.a['trace_sha256']=self.n['trace_sha256']
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_broken_microtick_time_rejected(self):
        self.a['h12_7_diagnostic']['b1_microticks'][2]['time_s']=99
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_missing_34d_rejected(self):
        self.a['decisions'][0]['state_before_34d']=[0.]*33
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_missing_decision_tick_rejected(self):
        self.a['microticks'][-1]['time_s']=10.5
        self.a['h12_7_diagnostic']['b1_microticks'][-1]['time_s']=10.5
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_nonfinite_state_rejected(self):
        self.a['decisions'][0]['state_after_34d'][2]=float('nan')
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_truncated_rejected(self):
        self.a['decisions'].pop()
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_swapped_mode_rejected(self):
        self.a['mode']='probe'
        with self.assertRaises(ValueError):h.compare(self.n,self.a)
    def test_md_shows_warnings(self):
        self.n=mock(halt_at_boundary=True);self.a=mock('active',halt_at_boundary=True)
        md=h.render_markdown(h.compare(self.n,self.a))
        self.assertIn('ALERTA SENSOR',md)
        self.assertIn('0→0',md)

if __name__=='__main__':unittest.main()
