import base64, importlib.util, json, math, tempfile, unittest, zipfile
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'h12_1_verificar.py'
spec=importlib.util.spec_from_file_location('h121',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Tests(unittest.TestCase):
 def test_temporal_detect(self):
  d=m.inspect_temporal('for _ in range(self.delta_t):\n    traci.simulationStep()',0.5,5)
  self.assertTrue(d['pattern_substeps_detected']);self.assertEqual(d['desired_substeps_if_constant_microtick'],10)
  self.assertEqual(d['physical_time_if_delta_t_5_s'],2.5)
 def test_temporal_invalid(self):
  with self.assertRaises(ValueError):m.inspect_temporal('',0,5)
 def test_noninteger_time(self):
  self.assertIsNone(m.inspect_temporal('',0.3,5)['desired_substeps_if_constant_microtick'])
 def test_zip_does_not_unpickle(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'ppo_ideal.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('data',json.dumps({'num_timesteps':20480,'observation_space':{':type:':'Box',':serialized:':base64.b64encode(b'EVIL PICKLE SHOULD NOT LOAD').decode()},'action_space':{':type:':'Discrete',':serialized:':base64.b64encode(b'X').decode()}}))
   d=m.inspect_zip(p);self.assertEqual(d['n_timesteps'],20480);self.assertEqual(d['contract_34d_4actions'],'NO_VERIFICADO')
 def test_missing(self):
  self.assertEqual(m.inspect_zip(Path('foo_missing.zip'))['zip_integrity'],'NO_ENCONTRADO')
 def test_corrupt(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'bad.zip';p.write_text('notzip');self.assertEqual(m.inspect_zip(p)['zip_integrity'],'ERROR')
 def test_gather_no_repo(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(FileNotFoundError):m.gather(Path(td),.5,5)
 def test_space_status(self):
  self.assertEqual(m._space_summary({':type:':'X',':serialized:':'@@'})[1],'SERIALIZACION_BASE64_INVALIDA')

if __name__=='__main__':unittest.main()
