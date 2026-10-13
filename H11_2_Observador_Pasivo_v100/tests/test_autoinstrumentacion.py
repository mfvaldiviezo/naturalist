import unittest
import tempfile
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from h11_2_bootstrap import install
from test_h11_2_observador import FakeTraCI

class TestAutoInstrumentation(unittest.TestCase):
    def test_explicit_hook_is_query_only_and_once_per_step(self):
        with tempfile.TemporaryDirectory() as d:
            traci=FakeTraCI()
            # FakeTraCI.simulationStep deliberately raises; substitute a real
            # caller-controlled step and verify hook never adds simulation steps.
            traci.simulationStep=traci.advance
            original=traci.simulationStep
            hook=install(traci,Path(d)/'observed',condition='fixture',seed=101)
            for _ in range(6): traci.simulationStep()
            hook.close()
            self.assertIs(traci.simulationStep,original)
            self.assertEqual(traci.t,6)
            manifest=json.loads((Path(d)/'observed'/'manifest_h11_2.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['observed_steps'],6)
            self.assertEqual(manifest['trajectory_rows'],6) if 'trajectory_rows' in manifest else self.assertEqual(manifest['counts']['trajectory_rows'],6)

if __name__=='__main__': unittest.main()
