import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import h12_18_bridge as b

N=list(b.NODES)
EDGES=sorted(set([(i,i+1) for i in range(11)]+[(i+1,i) for i in range(11)]+[
    (0,2),(2,0),(3,5),(5,3),(6,8),(8,6),(9,11),(11,9),(0,5),(5,0)]))
assert len(EDGES)==32

def make_graph():
    return dict(node_order=N,node_to_index={n:i for i,n in enumerate(N)},
                graph_directed_edge_index=[[i for i,j in EDGES],[j for i,j in EDGES]],
                graph_directed_edges=[[N[i],N[j]] for i,j in EDGES],
                geometries={n:dict(lanes_in=[n+'_0'],green_indices=[0,2]) for n in N})

class TestGraph(unittest.TestCase):
    def setUp(self):self.g=make_graph()
    def test_valid(self):
        o=b.verify_graph(self.g)
        self.assertEqual(o['input_dim'],4)
        self.assertEqual(o['output_dim'],2)
        self.assertEqual(len(o['edge_index'][0]),32)
    def test_node_order_changed(self):
        g=copy.deepcopy(self.g);g['node_order'][0]='X'
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_node_to_index_wrong(self):
        g=copy.deepcopy(self.g);g['node_to_index']['B1']=99
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_too_few_edges(self):
        g=copy.deepcopy(self.g);g['graph_directed_edge_index'][0].pop()
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_self_loop_rejected(self):
        g=copy.deepcopy(self.g);g['graph_directed_edge_index'][1][0]=g['graph_directed_edge_index'][0][0]
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_float_node_index_rejected(self):
        g=copy.deepcopy(self.g);g['graph_directed_edge_index'][0][0]=float(g['graph_directed_edge_index'][0][0])
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_bool_node_index_rejected(self):
        g=copy.deepcopy(self.g);g['graph_directed_edge_index'][0][0]=True
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_repeated_edge_rejected(self):
        g=copy.deepcopy(self.g);g['graph_directed_edge_index'][0][1]=g['graph_directed_edge_index'][0][0]
        g['graph_directed_edge_index'][1][1]=g['graph_directed_edge_index'][1][0]
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_unsorted_edge_rejected(self):
        g=copy.deepcopy(self.g)
        for axis in (0,1):g['graph_directed_edge_index'][axis][0],g['graph_directed_edge_index'][axis][1]=g['graph_directed_edge_index'][axis][1],g['graph_directed_edge_index'][axis][0]
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_edge_names_not_aligned(self):
        g=copy.deepcopy(self.g);g['graph_directed_edges'][0][0]='Wrong'
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_missing_tls(self):
        g=copy.deepcopy(self.g);del g['geometries']['B1']
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_three_verdes(self):
        g=copy.deepcopy(self.g);g['geometries']['B1']['green_indices']=[0,2,4]
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_duplicate_lane(self):
        g=copy.deepcopy(self.g);g['geometries']['B1']['lanes_in']=['a','a']
        with self.assertRaises(b.GateError):b.verify_graph(g)
    def test_four_lanes_allowed(self):
        g=copy.deepcopy(self.g);g['geometries']['B1']['lanes_in']=['a','b','c','d']
        self.assertEqual(len(b.verify_graph(g)['incoming_lanes']['B1']),4)
    def test_five_lanes_rejected(self):
        g=copy.deepcopy(self.g);g['geometries']['B1']['lanes_in']=['a','b','c','d','e']
        with self.assertRaises(b.GateError):b.verify_graph(g)

class TestStates(unittest.TestCase):
    def setUp(self):
        self.lanes={n:[n+'_0'] for n in N};self.counts={n+'_0':float(i) for i,n in enumerate(N)}
    def test_shape(self):
        x=b.counts_to_x(self.lanes,self.counts)
        self.assertEqual(len(x),12);self.assertEqual(x[4],[4.,0,0,0])
    def test_full_row(self):
        self.lanes['B1']=['a','b','c','d'];self.counts.update(a=1,b=2,c=3,d=4)
        self.assertEqual(b.counts_to_x(self.lanes,self.counts)[3],[1.,2.,3.,4.])
    def test_zero_accepted(self):self.assertEqual(b.counts_to_x(self.lanes,self.counts)[0][0],0)
    def test_missing_sensor(self):
        del self.counts['B1_0']
        with self.assertRaises(b.GateError):b.counts_to_x(self.lanes,self.counts)
    def test_negative_sensor(self):
        self.counts['B1_0']=-1
        with self.assertRaises(b.GateError):b.counts_to_x(self.lanes,self.counts)
    def test_nan_sensor(self):
        self.counts['B1_0']=float('nan')
        with self.assertRaises(b.GateError):b.counts_to_x(self.lanes,self.counts)
    def test_inf_sensor(self):
        self.counts['B1_0']=float('inf')
        with self.assertRaises(b.GateError):b.counts_to_x(self.lanes,self.counts)
    def test_bool_sensor(self):
        self.counts['B1_0']=True
        with self.assertRaises(b.GateError):b.counts_to_x(self.lanes,self.counts)
    def test_string_sensor(self):
        self.counts['B1_0']='2'
        with self.assertRaises(b.GateError):b.counts_to_x(self.lanes,self.counts)
    def test_extra_node(self):
        self.lanes['X']=['z']
        with self.assertRaises(b.GateError):b.counts_to_x(self.lanes,self.counts)
    def test_unsorted_lanes(self):
        self.lanes['B1']=['c','a'];self.counts.update(c=5,a=4)
        with self.assertRaises(b.GateError):b.counts_to_x(self.lanes,self.counts)

class TestGit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
        (self.p/'agent').mkdir(); (self.p/'configs/tsc').mkdir(parents=True)
        (self.p/'agent/colight.py').write_text('class ColightNet: pass\n',encoding='utf8')
        (self.p/'configs/tsc/colight.yml').write_text('model: {}\n',encoding='utf8')
        subprocess.run(['git','init','-q',str(self.p)],check=True)
        subprocess.run(['git','-C',str(self.p),'add','agent/colight.py','configs/tsc/colight.yml'],check=True)
        subprocess.run(['git','-C',str(self.p),'-c','user.email=test@example.com','-c','user.name=Test','commit','-qm','base'],check=True)
        self.commit=b.git_cmd(self.p,'rev-parse','HEAD').decode().strip()
        self.blob=b.git_cmd(self.p,'rev-parse','HEAD:agent/colight.py').decode().strip()
        self.yblob=b.git_cmd(self.p,'rev-parse','HEAD:configs/tsc/colight.yml').decode().strip()
        self.prior={'libsignal':{'commit':self.commit,'local_path':str(self.p),
            'files':[{'path':'agent/colight.py','blob_sha1':self.blob},
                     {'path':'configs/tsc/colight.yml','blob_sha1':self.yblob}]}}
    def tearDown(self):self.tmp.cleanup()
    def test_pinned_git_source_valid(self):
        with mock.patch.object(b,'LIBSIGNAL_COMMIT',self.commit),mock.patch.object(b,'LIBSIGNAL_MAIN_BLOB',self.blob):
            x=b.git_source(self.p,self.prior)
        self.assertEqual(x['blob_sha1'],self.blob)
    def test_dirty_worktree_blocked(self):
        (self.p/'agent/colight.py').write_text('modificado\n',encoding='utf8')
        with mock.patch.object(b,'LIBSIGNAL_COMMIT',self.commit),mock.patch.object(b,'LIBSIGNAL_MAIN_BLOB',self.blob):
            with self.assertRaises(b.GateError):b.git_source(self.p,self.prior)
    def test_wrong_pin_blocked(self):
        with mock.patch.object(b,'LIBSIGNAL_COMMIT','0'*40):
            with self.assertRaises(b.GateError):b.git_source(self.p,self.prior)
    def test_changed_config_blocks(self):
        (self.p/'configs/tsc/colight.yml').write_text('model: {modified: yes}\n',encoding='utf8')
        with mock.patch.object(b,'LIBSIGNAL_COMMIT',self.commit),mock.patch.object(b,'LIBSIGNAL_MAIN_BLOB',self.blob):
            with self.assertRaises(b.GateError):b.git_source(self.p,self.prior)
    def test_unmatched_yaml_pin_blocks(self):
        self.prior['libsignal']['files'][1]['blob_sha1']='a'*40
        with mock.patch.object(b,'LIBSIGNAL_COMMIT',self.commit),mock.patch.object(b,'LIBSIGNAL_MAIN_BLOB',self.blob):
            with self.assertRaises(b.GateError):b.git_source(self.p,self.prior)
    def test_wrong_prior_folder_blocked(self):
        self.prior['libsignal']['local_path']='/does-not-exist'
        with mock.patch.object(b,'LIBSIGNAL_COMMIT',self.commit),mock.patch.object(b,'LIBSIGNAL_MAIN_BLOB',self.blob):
            with self.assertRaises(b.GateError):b.git_source(self.p,self.prior)

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
        self.r=self.p/'repo';self.r.mkdir()
        self.d=self.p/'smoke';self.d.mkdir()
        (self.r/'tsc_framework/sumo_configs/networks').mkdir(parents=True)
        (self.r/'tsc_framework/sumo_configs/routes/hangzhou').mkdir(parents=True)
        self.net=self.r/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
        self.route=self.r/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
        self.net.write_text('net fixture');self.route.write_text('route fixture')
        self.source=self.p/'h12_17_env.py';self.source.write_text('source')
        self.m={'network':str(self.net),'routes':str(self.route),'network_sha256':b.sha(self.net),
           'route_sha256':b.sha(self.route),'graph':make_graph(),
           'source_sha256':{str(self.net):b.sha(self.net),str(self.route):b.sha(self.route),str(self.source):b.sha(self.source)}}
        self.sm={'result':'H12_17_MULTI_TLS_SMOKE_OK','n_tls':12,'n_decisions':12,
                'n_microticks':120,'node_order':list(N),'edge_index':make_graph()['graph_directed_edge_index'],
                'integrity_postflight':'PASS','data':[{'step':i} for i in range(12)]}
        (self.d/'runtime_h12_17.json').write_text('{}')
        self._write()
    def tearDown(self):self.tmp.cleanup()
    def _write(self):
        (self.d/'manifiesto_h12_17.json').write_text(json.dumps(self.m))
        self.sm['manifest_sha256']=b.sha(self.d/'manifiesto_h12_17.json')
        self.sm['runtime_sha256']=b.sha(self.d/'runtime_h12_17.json')
        (self.d/'smoke_h12_17.json').write_text(json.dumps(self.sm))
    def test_smoke_checked(self):
        with mock.patch.object(b,'NET_SHA',b.sha(self.net)),mock.patch.object(b,'ROUTE_SHA',b.sha(self.route)):
            x=b.verify_h1217(self.d,self.p,self.r)
        self.assertEqual(x[2]['graph']['input_dim'],4)
    def test_tampered_manifest_rejected(self):
        self.m['extra']='changed';(self.d/'manifiesto_h12_17.json').write_text(json.dumps(self.m))
        with self.assertRaises(b.GateError):b.verify_h1217(self.d,self.p,self.r)
    def test_tampered_source_rejected(self):
        self.source.write_text('changed')
        with mock.patch.object(b,'NET_SHA',b.sha(self.net)),mock.patch.object(b,'ROUTE_SHA',b.sha(self.route)):
            with self.assertRaises(b.GateError):b.verify_h1217(self.d,self.p,self.r)
    def test_wrong_graph_rejected(self):
        self.sm['node_order'][0]='X';self._write()
        with mock.patch.object(b,'NET_SHA',b.sha(self.net)),mock.patch.object(b,'ROUTE_SHA',b.sha(self.route)):
            with self.assertRaises(b.GateError):b.verify_h1217(self.d,self.p,self.r)
    def test_wrong_steps_rejected(self):
        self.sm['n_microticks']=119;self._write()
        with self.assertRaises(b.GateError):b.verify_h1217(self.d,self.p,self.r)
    def test_h1217_wrong_status_blocks(self):
        self.sm['result']='NOT_RUN';self._write()
        with self.assertRaises(b.GateError):b.verify_h1217(self.d,self.p,self.r)
    def test_h1217_incomplete_rows_blocks(self):
        self.sm['data']=self.sm['data'][:9];self._write()
        with mock.patch.object(b,'NET_SHA',b.sha(self.net)),mock.patch.object(b,'ROUTE_SHA',b.sha(self.route)):
            with self.assertRaises(b.GateError):b.verify_h1217(self.d,self.p,self.r)
    def test_model_deps_fail_closed(self):
        a=type('Args',(),{'libsignal_dir':self.p})()
        process=type('Result',(),{'returncode':1,'stdout':'','stderr':'ModuleNotFoundError: torch_scatter'})()
        plan={'provenance':{'libsignal':{'worktree_sha256':'a'*64,
                         'config_worktree_sha256':'b'*64}}}
        with mock.patch.object(b.subprocess,'run',return_value=process):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(b.GateError):b.deps(a,plan)
    def test_plan_links_previous_audits(self):
        a=type('Args',(),dict(revision_root=self.p,repo_root=self.r,h1217_dir=self.d,
                    h1216_dir=self.p/'h16',libsignal_dir=self.p/'lib'))()
        h16p=self.p/'h16/dictamen_h12_16.json';h16p.parent.mkdir();h16p.write_text('report')
        mf={'prior':{'h1216_report_path':str(h16p),'h1216_report_sha256':b.sha(h16p),
                       'h1212_smoke_path':str(h16p),'h1212_smoke_report_sha256':b.sha(h16p)}}
        src={'committed_file_sha256':'123'}
        with mock.patch.object(b,'verify_h1217',return_value=(mf,{},dict(graph=b.verify_graph(make_graph()),run_dir=str(self.d)))),\
             mock.patch.object(b,'verify_h1216',return_value=({},src,dict(report_sha256=b.sha(h16p),run_dir=str(h16p.parent)))):
            plan=b.make_plan(a)
        self.assertEqual(plan['adapter']['state_shape'],[12,4])
        self.assertEqual(plan['gates']['training'],'NOT_RUN')
    def test_report_scope(self):
        s=b.report({},None)
        self.assertIn('sin checkpoint',s.lower()) if False else self.assertIn('Sin checkpoint',s)
        self.assertIn('no se ejecutan',s)
    def test_shadow_ack_rejected_before_deps(self):
        args=type('Args',(),dict(ack_online_control='',ack_shadow_model='',rl_steps=12,min_green=10,seed=101))()
        with mock.patch.object(b,'deps') as d:
            with self.assertRaises(b.GateError):b.shadow(args,{})
            d.assert_not_called()
    def test_cli_missing_args(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):b.parse_args([])
    def test_cli_no_fake_inference(self):
        x=b.parse_args(['--repo-root','x','--revision-root','x','--h1216-dir','x',
                        '--h1217-dir','x','--libsignal-dir','x','--mode','plan'])
        self.assertEqual(x.mode,'plan')
    def test_plan_prints_success_mock(self):
        params=['--repo-root',str(self.r),'--revision-root',str(self.p),'--h1216-dir',str(self.d),
            '--h1217-dir',str(self.d),'--libsignal-dir',str(self.d),'--mode','plan']
        with mock.patch.object(b,'make_plan',return_value={'valid':True}):
            with contextlib.redirect_stdout(io.StringIO()) as o:
                self.assertEqual(b.main(params),0)
            self.assertIn('H12_18_PLAN_OK',o.getvalue())
    def test_missing_runtime_blocks(self):
        (self.d/'runtime_h12_17.json').unlink()
        with self.assertRaises(b.GateError):b.verify_h1217(self.d,self.p,self.r)

if __name__=='__main__':unittest.main()
