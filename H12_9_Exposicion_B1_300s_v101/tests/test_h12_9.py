import copy
import ast
import subprocess
import importlib.util
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('h129',ROOT/'h12_9_exposicion.py')
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


def fixture(mode):
    rows=[]; micro=[]; dec=[]
    for j in range(600):
        ids=['V1'] if j%10<5 else []
        rows.append({'tick':j,'time_s':(j+1)*0.5,'n_b1':len(ids),'halted_b1':0,
                     'waiting_b1_s':0.0,'vine_selected_b1':ids,'h09_selected_b1':[],
                     'b1_mean_speed_m_s':7.0 if ids else 0.,
                     'vine_selected_speeds_m_s':{'V1':7.0} if ids else {},
                     'lanes':[]})
        micro.append({'tick':j,'time_s':(j+1)*0.5,'collisions':0,'teleports_start':0})
    for i in range(60):
        vec=[0.0]*34;vec[28]=1.;vec[32]=i/24;vec[33]=i/24
        dec.append({'i':i,'sim_time_s':(i+1)*5.,'action':0,'phase':0,
                    'reward':0.,'queue':0.,'delay_proxy':0.,
                    'state_before_34d':list(vec),'state_after_34d':list(vec)})
    return {'result':'SMOKE_OK','mode':mode,'model':'ppo_ideal','checkpoint_sha256':'abc',
            'h10_reference_path':'ref','h10_reference_n':300,'h10_source_sha256':{'a':'bc'},
            'inputs':{'net_sha256':'n','routes_sha256':'r','cfg_original_sha256':'c'},
            'trace_sha256':'nom' if mode!='active' else 'act',
            'commands':0 if mode!='active' else 20,'end_time_s':300.0,
            'n_decisions':60,'n_microticks':600,'decisions':dec,'microticks':micro,
            'extra':{'vine':{'n_commands':20,'n_commands_confirmed':20,'remaining_pending':0}},
            'h12_7_diagnostic':{'initial_state_34d':[0.]*34,
              'b1_microticks':rows,
              'controlled_lanes_unique_raw':['a','b','c','d'],
              'controlled_lanes_used_12':['a','b','c']+['d']*9,
              'outgoing_lanes':[], 'green_phases':[0,2]}}


class TestExtension(unittest.TestCase):
    def setUp(self):
        self.n=fixture('nominal');self.p=fixture('probe');self.a=fixture('active')

    def test_good(self):
        r=m.compare(self.n,self.p,self.a)
        self.assertEqual(r['status'],'H12_9_EXTENDED_OK')
        self.assertEqual(r['vine_confirmed'],20)
        self.assertEqual(r['metrics']['nominal']['ticks_with_selected_vine_in_b1'],300)
    def test_active_traces_have_diff(self):
        self.a['trace_sha256']='nom'
        with self.assertRaisesRegex(RuntimeError,'EFECTO'):m.compare(self.n,self.p,self.a)
    def test_probe_sha_changed(self):
        self.p['trace_sha256']='new'
        with self.assertRaisesRegex(RuntimeError,'IDENTICOS'):m.compare(self.n,self.p,self.a)
    def test_checkpoint_mismatch(self):
        self.a['checkpoint_sha256']='other'
        with self.assertRaisesRegex(RuntimeError,'checkpoint_sha256'):m.compare(self.n,self.p,self.a)
    def test_routes_mismatch(self):
        self.a['inputs']['routes_sha256']='other'
        with self.assertRaisesRegex(RuntimeError,'routes_sha256'):m.compare(self.n,self.p,self.a)
    def test_unconfirmed(self):
        self.a['extra']['vine']['n_commands_confirmed']=19
        with self.assertRaisesRegex(RuntimeError,'CONFIRMACION'):m.compare(self.n,self.p,self.a)
    def test_pending(self):
        self.a['extra']['vine']['remaining_pending']=1
        with self.assertRaisesRegex(RuntimeError,'CONFIRMACION'):m.compare(self.n,self.p,self.a)
    def test_collision_rejected(self):
        self.a['microticks'][50]['collisions']=1
        with self.assertRaisesRegex(RuntimeError,'COLISION'):m.compare(self.n,self.p,self.a)
    def test_teleport_rejected(self):
        self.n['microticks'][50]['teleports_start']=1
        with self.assertRaisesRegex(RuntimeError,'COLISION'):m.compare(self.n,self.p,self.a)
    def test_observation_diff(self):
        self.a['decisions'][7]['state_before_34d'][1]=0.12
        self.a['decisions'][7]['action']=1
        r=m.compare(self.n,self.p,self.a)
        self.assertEqual(r['obs34d_boundaries_different'],1)
        self.assertEqual(r['actions_different'],1)
        self.assertEqual(r['obs34d_segment_boundaries_different']['cola_12'],1)
    def test_b1_local_diff(self):
        self.a['h12_7_diagnostic']['b1_microticks'][22]['halted_b1']=1
        r=m.compare(self.n,self.p,self.a)
        self.assertEqual(r['b1_local_aggregate_microticks_different'],1)
    def test_local_speed_difference_detected(self):
        self.a['h12_7_diagnostic']['b1_microticks'][10]['b1_mean_speed_m_s']=6.5
        self.a['h12_7_diagnostic']['b1_microticks'][10]['vine_selected_speeds_m_s']['V1']=6.5
        r=m.compare(self.n,self.p,self.a)
        self.assertEqual(r['b1_local_mean_speed_microticks_different'],1)
        self.assertEqual(r['b1_selected_vine_speed_records_different'],1)
    def test_lane_contract(self):
        self.a['h12_7_diagnostic']['controlled_lanes_used_12'][0]='another'
        with self.assertRaisesRegex(RuntimeError,'LANES'):m.compare(self.n,self.p,self.a)
    def test_phase_contract(self):
        self.a['h12_7_diagnostic']['green_phases']=[0,2,4]
        with self.assertRaisesRegex(RuntimeError,'FASES'):m.compare(self.n,self.p,self.a)
    def test_replace_ambiguous(self):
        with self.assertRaisesRegex(RuntimeError,'FAIL-CLOSED'):
            m.replace_once('a a','a','b')
    def test_overlay_real_source(self):
        base=ROOT.parent/'H12_5_Integracion_Vine_Gymnasium_v100/h12_5_integrar.py'
        diag=ROOT.parent/'H12_7_Diagnostico_Estado_B1_v100/h12_7_estado_b1.py'
        if not base.is_file() or not diag.is_file():
            self.skipTest('Se prueba en distribución junto a H12.5 y H12.7')
        spec=importlib.util.spec_from_file_location('h127_test',diag)
        mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
        s=m.extend_h127_text(mod.patch_h125(base.read_text(encoding='utf-8-sig')))
        self.assertIn('hook.h129_vine_ids',s)
        self.assertIn('Se requieren 2..60',s)
        self.assertIn('getLastStepVehicleIDs',s)
    def test_importlib_util_imported_explicitly(self):
        source=(ROOT/'h12_9_exposicion.py').read_text(encoding='utf-8')
        parsed=ast.parse(source)
        names={alias.name for node in ast.walk(parsed) if isinstance(node,ast.Import) for alias in node.names}
        self.assertIn('importlib.util',names)
        self.assertNotIn("__import__('importlib').util",source)

    def test_loader_in_clean_python_interpreter(self):
        # Regression: the previous source relied on importlib.util having been imported
        # indirectly by unittest or by the execution environment.
        upstream=ROOT.parent
        if not ((upstream/'H12_5_Integracion_Vine_Gymnasium_v100/h12_5_integrar.py').is_file()
                and (upstream/'H12_7_Diagnostico_Estado_B1_v100/h12_7_estado_b1.py').is_file()):
            self.skipTest('Requires neighboring H12.5 and H12.7 source modules')
        code=("from pathlib import Path\n"
              "import runpy\n"
              "path=Path("+repr(str(ROOT/'h12_9_exposicion.py'))+")\n"
              "module=runpy.run_path(str(path))\n"
              "overlay, hashes=module['load_source_overlay'](Path("+repr(str(upstream))+"))\n"
              "assert overlay.__name__.startswith('_h129_h125_overlay_')\n"
              "assert len(hashes['overlay_sha256'])==64\n"
              "print('ISOLATED_OVERLAY_OK')\n")
        proc=subprocess.run([sys.executable,'-S','-c',code],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stdout+'\n'+proc.stderr)
        self.assertIn('ISOLATED_OVERLAY_OK',proc.stdout)

    def test_nonfinite(self):
        with self.assertRaisesRegex(RuntimeError,'NO FINITO'):m.finite(float('nan'))
    def test_markdown(self):
        report=m.markdown(m.compare(self.n,self.p,self.a))
        self.assertIn('300 segundos',report)
        self.assertIn('NO se ha corregido',report)


if __name__=='__main__':unittest.main()
