import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import auditar_h10_completo as a

class EndToEndFixture(unittest.TestCase):
    def test_run_full(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            baseline=set(str(i) for i in range(45));h09=set(str(i) for i in range(38,83))
            assert len(baseline & h09)==7
            cohorts={'selected_vine':sorted(baseline),'selected_h09':sorted(h09)}
            for mode in a.MODES:
                folder=a.get_source(root,mode);folder.mkdir(parents=True)
                ev=[{'event_type':'tls_crossing_link','signal_state':'red','classification_quality':'confirmed','vehicle_id':'39','measurement_id':'ep'}]
                with (folder/'eventos_h09.csv').open('w',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=ev[0].keys());w.writeheader();w.writerows(ev)
                outputs={'eventos_h09.csv':a.sha256(folder/'eventos_h09.csv')}
                vine=('vine_' in mode or 'hibrido_' in mode)
                if vine:
                    actions=[{'action_decision':'command_issued','command_issued':'True','matched_t_plus_dt':'True','vehicle_id':'39','time_s':'13.5'}]
                    with (folder/'acciones_hito08.csv').open('w',newline='') as f:
                        w=csv.DictWriter(f,fieldnames=actions[0].keys());w.writeheader();w.writerows(actions)
                    outputs['acciones_hito08.csv']=a.sha256(folder/'acciones_hito08.csv')
                m={'mode':mode,'seed':101,'steps':600,'dt':.5,'output_sha256':outputs,
                   'source_sha256':{'same_file':'a'*64},'cohorts':cohorts,
                   'historical_traffic_identical':mode in ('nominal','h09'),
                   'traffic_metrics':{'arrivals':10,'mean_halted':2.1,'mean_speed_kmh':35,'collisions':0,'teleports':0},
                   'instrumental':{'signal_states':{'red':1}},
                   'vine_guard_policy':('contextual' if mode.endswith('contextual') else 'protegido') if vine else None,
                   'vine':({'n_commands':1,'n_commands_confirmed':1,'remaining_pending':0,'n_vehicles_commanded':1,'n_safety_eligible':20,'n_action_viable':5} if vine else None)}
                (folder/'manifest_h10.json').write_text(json.dumps(m))
            result=a.load_manifests(root)
            rep=a.analyze(result)
            self.assertEqual(rep['cohorts']['overlap'],7)
            self.assertEqual(rep['conditions']['hibrido_protegido']['crossing_by_cohort']['red']['ambas'],1)
            self.assertEqual(len(a.flat_rows(rep)),6)

if __name__=='__main__':unittest.main()
