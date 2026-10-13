from __future__ import annotations
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import h12_16_auditar_colight as m

ORIGINAL={
 'CoLight_agent.py':b'class CoLightAgent:\n    selfnum="self.num_agents"\n    def MultiHeadsAttModel(self): pass\n',
 'requirements.txt':b'tensorflow==1.11\nkeras==2.1\n',
 'readme.md':b'# CoLight',
 'config.py':b'foo=1\n',
 'anon_env.py':b'foo=2\n'
}
LIB={
 'agent/colight.py':b'''from torch_geometric.nn import MessagePassing
import torch_scatter
@Registry.register_model('colight')
class CoLightAgent(RLAgent):
  def __init__(self):
    self.graph={'sparse_adj': 1}
    self.edge_idx=self.graph['sparse_adj']
    self.sub_agents=len(self.world.intersections)
    self.phase_lengths=[2]
    sorted(list((2,1)))
class ColightNet: pass
class MultiHeadAttModel(MessagePassing): pass
''',
 'agent/colight_pytorch_agent.py':b'class CoLightAgent: pass\n',
 'agent/__init__.py':b'from .colight import CoLightAgent\n',
 'configs/tsc/colight.yml':b'model:\n  name: colight\n  N_LAYERS: 1\n  NUM_HEADS: [5,5]\n  NEIGHBOR_NUM: 4\n',
 'configs/sim/sumo1x1_colight.cfg':b'{"network":"cologne1"}\n',
 'requirements.txt':b'gym==0.21.0\n',
 'run.py':b'# run\n',
 'world/world_sumo.py':b'def create_yellows():pass\n',
 'world/world_cityflow.py':b'\n',
 'trainer/tsc_trainer.py':b'\n'
}

def git(where,*a):
    cmd=['git','-C',str(where),*a]
    r=subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    return r.stdout.strip()


def create_git(where, files, remote):
    where.mkdir(parents=True)
    git(where,'init','-q')
    git(where,'config','user.email','test@example.org')
    git(where,'config','user.name','test')
    git(where,'remote','add','origin','https://github.com/'+remote+'.git')
    for rel,b in files.items():
        dst=where/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b)
    git(where,'add','.')
    git(where,'commit','-qm','fixture')
    sha=git(where,'rev-parse','HEAD')
    return {'repository':remote,'url':'https://github.com/'+remote,'commit':sha,
            'files':{k:m.git_blob_sha(v) for k,v in files.items()}}


def make_fixture(root):
    orig_dir=root/'colight';lib_dir=root/'LibSignal'
    orig=create_git(orig_dir,ORIGINAL,'wingsweihua/colight')
    lib=create_git(lib_dir,LIB,'DaRL-LibSignal/LibSignal')
    repo=root/'project';net=repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml';routes=repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
    net.parent.mkdir(parents=True,exist_ok=True);routes.parent.mkdir(parents=True,exist_ok=True)
    net.write_text('''<net><tlLogic id="A0"><phase state="GGrr"/><phase state="yyrr"/><phase state="rrGG"/><phase state="rryy"/></tlLogic><tlLogic id="B1"><phase state="GGrr"/><phase state="yyrr"/><phase state="rrGG"/><phase state="rryy"/></tlLogic><connection from="X" fromLane="0" tl="A0"/><connection from="Y" fromLane="0" tl="B1"/></net>''',encoding='utf8')
    routes.write_text('<routes/>',encoding='utf8')
    pins={'original':orig,'libsignal':lib,'local_hangzhou_net_sha256':m.sha256_file(net),'local_hangzhou_routes_sha256':m.sha256_file(routes)}
    a14=root/'audit14';a14.mkdir()
    (a14/'dictamen_h12_14.json').write_text(json.dumps({'result':'H12_14_SOTA_AUDIT_OK','resco_reference_inputs':{'net_byte_identical_to_H1212':True,'route_byte_identical_to_H1212':True,'net_sha256':m.sha256_file(net),'route_sha256':m.sha256_file(routes)}}))
    a15=root/'audit15';a15.mkdir()
    (a15/'resultado_h12_15.json').write_text(json.dumps({'result':'H12_15_PHYSICAL_SMOKE_OK'}))
    args=SimpleNamespace(original_dir=orig_dir,libsignal_dir=lib_dir,repo_root=repo,h1214_dir=a14,h1215_dir=a15)
    return pins,args

class UnitTests(unittest.TestCase):
    def test_blob_sha_known(self):
        self.assertEqual(m.git_blob_sha(b'test content\n'),'d670460b4b4aece5915caf5c68d12f560a9fe3e4')
    def test_sha256_known(self):
        self.assertEqual(m.sha256_bytes(b'abc'),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    def test_original_ast_ok(self):
        t=m.assert_python_ast(ORIGINAL['CoLight_agent.py'].decode(),'test')
        self.assertIn('CoLightAgent',m.top_classes(t))
    def test_ast_rejects_syntax(self):
        with self.assertRaises(m.AuditError):m.assert_python_ast('def bad(', 'bad')
    def test_sorted_detect(self):
        a=m.assert_python_ast('sorted([2,1])\nx=sorted([3,4])\n','t')
        self.assertEqual(m.unused_sorted_calls(a),[1])
    def test_unsupported_tf_legacy(self):
        r=dict(ORIGINAL);r['requirements.txt']=b'tensorflow==2.15\nkeras==3\n'
        with self.assertRaises(m.AuditError):m.source_checks(r,LIB)
    def test_wrong_registration(self):
        d=dict(LIB);d['agent/colight.py']=LIB['agent/colight.py'].replace(b"register_model('colight')",b"register_model('other')")
        with self.assertRaises(m.AuditError):m.source_checks(ORIGINAL,d)
    def test_wrong_import(self):
        d=dict(LIB);d['agent/__init__.py']=b'pass\n'
        with self.assertRaises(m.AuditError):m.source_checks(ORIGINAL,d)
    def test_wrong_graph(self):
        d=dict(LIB);d['agent/colight.py']=LIB['agent/colight.py'].replace(b"self.graph['sparse_adj']",b"self.graph['other']")
        # Fixture's graph literal uses a dictionary literal, but the audit requires indexed sparse_adj.
        with self.assertRaises(m.AuditError):m.source_checks(ORIGINAL,d)
    def test_model_config_wrong(self):
        d=dict(LIB);d['configs/tsc/colight.yml']=b'model:\n  name: another\n'
        with self.assertRaises(m.AuditError):m.source_checks(ORIGINAL,d)
    def test_sumocfg_different_network_rejected(self):
        d=dict(LIB);d['configs/sim/sumo1x1_colight.cfg']=b'{"network":"hangzhou"}'
        with self.assertRaises(m.AuditError):m.source_checks(ORIGINAL,d)
    def test_source_checks_valid(self):
        f=m.source_checks(ORIGINAL,LIB)
        self.assertTrue(f['network_attention_verified_in_source'])
        self.assertFalse(f['example_sumo_is_hangzhou'])
        self.assertEqual(f['inert_sorted_lines'],[10])
    def test_require_fails(self):
        with self.assertRaises(m.AuditError):m.require(False,'bad')
    def test_wrong_dtd(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'n.xml';p.write_bytes(b'<!DOCTYPE net><net/>')
            with self.assertRaises(m.AuditError):m.inspect_network(p)
    def test_bad_xml(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'n.xml';p.write_bytes(b'<net>')
            with self.assertRaises(m.AuditError):m.inspect_network(p)
    def test_inventory_no_sumo_no_results(self):
        with tempfile.TemporaryDirectory() as d:
            result=m.main(['--mode','inventory','--results-root',d])
            self.assertEqual(result,0)
            self.assertEqual(list(pathlib.Path(d).iterdir()),[])
    def test_analyze_fails_without_dirs(self):
        self.assertEqual(m.main(['--mode','analyze']),2)
    def test_dependencies_probe_does_not_import_torch(self):
        d=m.dep_inventory();self.assertIn(d['torch'],('present_not_imported','not_found'))
    def test_pins_loaded(self):
        p=m.load_pins();self.assertEqual(p['original']['commit'],'04440b722e7f36d7043a3f2ad8e40c3df301fad3')

@unittest.skipUnless(__import__('shutil').which('git'),'Git no instalado')
class IntegratedFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.pins,self.args=make_fixture(self.root)
    def test_cli_plan_and_analyze(self):
        pinpath=self.root/'pins_fixture.json'
        d=dict(self.pins);d['schema']='H12_16_PINNED_SOURCES_V100'
        pinpath.write_text(json.dumps(d))
        old=m.PIN_FILE
        try:
            m.PIN_FILE=pinpath
            base=['--repo-root',str(self.args.repo_root),'--original-dir',str(self.args.original_dir),
                  '--libsignal-dir',str(self.args.libsignal_dir),'--h1214-dir',str(self.args.h1214_dir),
                  '--h1215-dir',str(self.args.h1215_dir), '--results-root',str(self.root/'results')]
            self.assertEqual(m.main(['--mode','plan',*base]),0)
            self.assertFalse((self.root/'results').exists())
            self.assertEqual(m.main(['--mode','analyze',*base]),0)
            self.assertEqual(len(list((self.root/'results').glob('*/dictamen_h12_16.json'))),1)
        finally:
            m.PIN_FILE=old

    def test_verify_git_original(self):
        result,b=m.verify_git_repo(self.args.original_dir,self.pins['original'])
        self.assertEqual(len(result['files']),len(ORIGINAL))
    def test_audit_end_to_end(self):
        d=m.audit(self.args,self.pins)
        self.assertEqual(d['result'],'H12_16_COLIGHT_SOURCE_AUDIT_OK')
        self.assertEqual(d['local_contract']['network']['n_tls'],2)
        self.assertEqual(d['gates']['sota_resilience'],'BLOCKED')
    def test_plan_does_not_write(self):
        d=m.audit(self.args,self.pins)
        self.assertEqual(d['gates']['node_order_graph_runtime'],'NOT_VERIFIED')
        self.assertFalse((self.root/'results').exists())
    def test_report_writes_three_outputs(self):
        d=m.audit(self.args,self.pins)
        target=m.save_result(self.root/'results',d)
        self.assertTrue((target/'dictamen_h12_16.md').exists())
        self.assertTrue((target/'dictamen_h12_16.json').exists())
        self.assertTrue((target/'fuentes_git_h12_16.csv').exists())
        self.assertIn('CoLight', (target/'dictamen_h12_16.md').read_text(encoding='utf8'))
    def test_wrong_commit_rejected(self):
        bad=dict(self.pins['original']);bad['commit']='0'*40
        with self.assertRaises(m.AuditError):m.verify_git_repo(self.args.original_dir,bad)
    def test_wrong_sha_rejected(self):
        bad=dict(self.pins['original']);bad['files']=dict(bad['files']);bad['files']['config.py']='0'*40
        with self.assertRaises(m.AuditError):m.verify_git_repo(self.args.original_dir,bad)
    def test_modified_file_rejected(self):
        (self.args.original_dir/'requirements.txt').write_text('alterado')
        with self.assertRaises(m.AuditError):m.verify_git_repo(self.args.original_dir,self.pins['original'])
    def test_wrong_remote_rejected(self):
        git(self.args.original_dir,'remote','set-url','origin','https://github.com/other/other.git')
        with self.assertRaises(m.AuditError):m.verify_git_repo(self.args.original_dir,self.pins['original'])
    def test_tamper_network_rejected(self):
        p=self.args.repo_root/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
        p.write_bytes(p.read_bytes()+b'\n<!-- modified -->')
        with self.assertRaises(m.AuditError):m.local_h1214_check(self.args.repo_root,self.pins,self.args.h1214_dir)
    def test_bad_audit14_rejected(self):
        p=self.args.h1214_dir/'dictamen_h12_14.json'
        data=json.loads(p.read_text());data['result']='NOPE';p.write_text(json.dumps(data))
        with self.assertRaises(m.AuditError):m.local_h1214_check(self.args.repo_root,self.pins,self.args.h1214_dir)
    def test_bad_audit15_rejected(self):
        p=self.args.h1215_dir/'resultado_h12_15.json'
        data=json.loads(p.read_text());data['result']='NOPE';p.write_text(json.dumps(data))
        with self.assertRaises(m.AuditError):m.local_h1214_check(self.args.repo_root,self.pins,self.args.h1214_dir,self.args.h1215_dir)
    def test_checkout_clean_not_required(self):
        (self.args.original_dir/'requirements.txt').write_text('alterado')
        x,_=m.verify_git_repo(self.args.original_dir,self.pins['original'],require_clean=False)
        self.assertEqual(x['commit'],self.pins['original']['commit'])
    def test_local_without_prev_audits(self):
        r=m.local_h1214_check(self.args.repo_root,self.pins)
        self.assertEqual(r['H1214'],'NOT_SUPPLIED')
    def test_incorrect_tls_semantics(self):
        net=self.args.repo_root/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
        s=net.read_text();s=s.replace('id="B1"','id="B4"');net.write_text(s)
        with self.assertRaises(m.AuditError):m.inspect_network(net)

if __name__=='__main__':unittest.main()
