import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import auditar_h10_completo as a

class Audit(unittest.TestCase):
    def test_group(self):
        self.assertEqual(a.cohort_group('7',{'7'},{'7'}),'ambas')
        self.assertEqual(a.cohort_group('8',{'8'},{'7'}),'solo_vine')
        self.assertEqual(a.cohort_group('9',{'7'},{'9'}),'solo_h09')
        self.assertEqual(a.cohort_group('10',{'7'},{'9'}),'ninguna')
    def test_crossings_quality(self):
        r=[{'event_type':'tls_crossing_link','signal_state':'red','classification_quality':'confirmed','vehicle_id':'7','measurement_id':'ep'},
           {'event_type':'tls_crossing_link','signal_state':'yellow','classification_quality':'confirmed','vehicle_id':'9','measurement_id':'ep'},
           {'event_type':'tls_crossing_link','signal_state':'red','classification_quality':'unknown','vehicle_id':'8','measurement_id':'ep'},
           {'event_type':'stopline','signal_state':'red','classification_quality':'confirmed','vehicle_id':'7','measurement_id':'ep'}]
        c=a.crossing_totals(r,{'7'},{'7','9'})
        self.assertEqual(c['red']['total'],1);self.assertEqual(c['red']['ambas'],1)
        self.assertEqual(c['yellow']['solo_h09'],1)
    def test_actions_unique(self):
        rows=[{'action_decision':'command_issued','command_issued':'True','matched_t_plus_dt':'True','vehicle_id':'7','time_s':'12'},
              {'action_decision':'command_issued','command_issued':'True','matched_t_plus_dt':'True','vehicle_id':'7','time_s':'12.5'}]
        s=a.action_stats(rows,{'7'},{'7'})
        self.assertEqual(s['comandos_csv'],2);self.assertEqual(s['vehiculos_distintos'],1)
    def test_actions_unconfirmed_block(self):
        with self.assertRaises(ValueError):
            a.action_stats([{'command_issued':'True','matched_t_plus_dt':'False','vehicle_id':'v','time_s':'3'}],set(),set())
    def test_invalid_manifest_block(self):
        with self.assertRaises(FileNotFoundError):a.load_manifests(Path('/this/directory/does/not/exist'))
    def test_commands_cap_counts_vs_unique(self):
        r=[{'action_decision':'total_command_quota','command_issued':'False','vehicle_id':'7','time_s':'9'}]
        s=a.action_stats(r,{'7'},set())
        self.assertEqual(s['comandos_csv'],0)
        self.assertEqual(s['decisiones']['total_command_quota'],1)

if __name__=='__main__':unittest.main()
