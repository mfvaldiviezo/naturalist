import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import sys

BASE=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('h1214_test_module',BASE/'h12_14_auditar.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def fixture(tmp):
    tmp=pathlib.Path(tmp)
    repo=tmp/'traffic_project'; rev=tmp/'revision'; rev.mkdir()
    base=repo/'baselines/RESCO/resco_benchmark'
    h12=rev/'H12_12_Entorno_Homologado_B1_v100';h12.mkdir()
    sm=rev/'resultados/h12_12_mock';sm.mkdir(parents=True)
    net=repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
    route=repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
    net.parent.mkdir(parents=True);route.parent.mkdir(parents=True)
    lights=['GGggrrrrGGggrrrr','yyyyrrrryyyyrrrr','rrrrGGggrrrrGGgg','rrrryyyyrrrryyyy']
    data=['<net><tlLogic id="B1" type="actuated" programID="0">']
    for i,s in enumerate(lights):data.append(f'<phase duration="{3 if i%2 else 42}" state="{s}"/>')
    data.append('</tlLogic>')
    for j,inbound in enumerate(['B2B1','C1B1','B0B1','A1B1']):
        data.append(f'<connection tl="B1" from="{inbound}" fromLane="0" to="OUT{j}" toLane="0" linkIndex="{j}"/>')
    data.append('</net>');net.write_text(''.join(data),encoding='utf-8')
    route.write_text('<routes/>',encoding='utf8')
    n2=base/'environments/hangzhou/hangzhou.net.xml'
    r2=base/'environments/hangzhou/hangzhou.rou.xml'
    n2.parent.mkdir(parents=True)
    n2.write_bytes(net.read_bytes());r2.write_bytes(route.read_bytes())
    for name,(part,cl,mod,state,reward,scope) in a.CHECKS.items():
        p=base/part;p.parent.mkdir(parents=True,exist_ok=True)
        suffix={'MPLight':'# phase_pairs build_comp_mask FRAP\n','CoSLight':'# len(obs_act) SharedAgent\n','IPPO':'# PPO( PFRLPPOAgent\n', 'MAXPRESSURE':'# WaveAgent\n'}.get(name,'')
        p.write_text(suffix+f'class {cl}: pass\n',encoding='utf8')
    for v in a.EXTRA.values():
        for file in v:
            p=base/file;p.parent.mkdir(parents=True,exist_ok=True)
            if not p.exists():p.write_text('class Helper: pass\n',encoding='utf8')
    yamltext=''.join(f'{k}:\n  module: {v[2]}\n  state: {v[3]}\n  reward: {v[4]}\n' for k,v in a.CHECKS.items())
    (base/'config').mkdir(parents=True,exist_ok=True)
    (base/'config/agent.yaml').write_text(yamltext,encoding='utf8')
    (base/'config/config.yaml').write_text('example: true\n',encoding='utf8')
    (repo/'baselines/RESCO/README.rst').write_text('RESCO\n',encoding='utf8')
    for f in ['h12_12_contract.py','h12_12_env.py','h12_12_homologar.py']:
        (h12/f).write_text('# fake fixture\n',encoding='utf8')
    checks={str(path.resolve()):a.sha(path) for path in [net,route,*h12.glob('*.py')]}
    manifest={'schema':'H12_12_B1_GREEN2_OBS34_V100','network':str(net.resolve()),'routes':str(route.resolve()),
              'sources_sha256':checks,'actions':{'type':'Discrete(2)'},
              'simulation':{'microtick_seconds':0.5,'decision_seconds':5.0},
              'network_contract':{'green_indices':[0,2]},'tls_id':'B1'}
    mp=sm/'manifiesto_h12_12.json';mp.write_text(json.dumps(manifest),encoding='utf8')
    (sm/'runtime_h12_12.json').write_text(json.dumps({'sumo_version':['SUMO Version 1.26.0']}),encoding='utf8')
    (sm/'smoke_h12_12.json').write_text(json.dumps({'result':'H12_12_SUMO_SMOKE_OK', 'manifest_sha256':a.sha(mp),
                                                    'steps':12,'microticks':120}),encoding='utf8')
    return repo,rev,sm,h12,net,route,base


class TestAudit(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.repo,self.rev,self.sm,self.h12,self.net,self.route,self.base=fixture(self.t.name)
        self.pn=patch.object(a,'EXPECTED_NET',a.sha(self.net));self.pn.start();self.addCleanup(self.pn.stop)
        self.pr=patch.object(a,'EXPECTED_ROUTES',a.sha(self.route));self.pr.start();self.addCleanup(self.pr.stop)

    def call(self,mode='plan',training=None):
        arg=['--repo-root',str(self.repo),'--revision-root',str(self.rev),'--smoke-dir',str(self.sm),
             '--h1212-dir',str(self.h12),'--mode',mode]
        if training:arg+=['--h1213-run',str(training)]
        return a.run(arg)

    def test_validate_ok(self):
        d=a.audit(self.repo,self.sm,self.h12)
        self.assertEqual(d['result'],'H12_14_SOTA_AUDIT_OK')
        self.assertEqual([x['controller'] for x in d['controllers']],list(a.CHECKS))
    def test_plan_no_results(self):
        self.assertEqual(self.call(),0)
        self.assertFalse(list((self.rev/'resultados').glob('h12_14_sota_*')))
    def test_analyze_writes_three_files(self):
        self.assertEqual(self.call('analyze'),0)
        runs=list((self.rev/'resultados').glob('h12_14_sota_*'))
        self.assertEqual(len(runs),1)
        self.assertTrue((runs[0]/'matriz_sota_h12_14.csv').is_file())
        d=json.loads((runs[0]/'dictamen_h12_14.json').read_text(encoding='utf8'))
        self.assertEqual(d['gates']['SOTA_full_comparison'],'BLOCKED')
    def test_missing_source_fails(self):
        (self.base/'agents/action_value/mplight.py').unlink()
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_wrong_yaml_module(self):
        p=self.base/'config/agent.yaml';p.write_text(p.read_text().replace('action_value.mplight','action_value.mlp'),encoding='utf8')
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_wrong_yaml_state(self):
        p=self.base/'config/agent.yaml';p.write_text(p.read_text().replace('state: drq','state: wrong'),encoding='utf8')
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_malformed_source(self):
        p=self.base/'agents/static/fixed.py';p.write_text('class test(:\n')
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_wrong_class(self):
        p=self.base/'agents/static/fixed.py';p.write_text('class NotFixed: pass\n')
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_bad_smoke_status(self):
        p=self.sm/'smoke_h12_12.json';o=json.loads(p.read_text());o['result']='INVALID';p.write_text(json.dumps(o))
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_smoke_manifest_tamper(self):
        p=self.sm/'manifiesto_h12_12.json';p.write_text(p.read_text()+' ')
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_h1212_source_tamper(self):
        (self.h12/'h12_12_env.py').write_text('tampered')
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_geometry_green_change(self):
        self.net.write_text(self.net.read_text().replace('GGggrrrrGGggrrrr','rrrrrrrrrrrrrrrr'))
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_geometry_yellow_change(self):
        self.net.write_text(self.net.read_text().replace('duration="3"','duration="2"'))
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_wrong_route_hash(self):
        self.route.write_text('<routes><vehicle/></routes>')
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12)
    def test_reference_route_mismatch_is_reported(self):
        (self.base/'environments/hangzhou/hangzhou.rou.xml').write_text('<routes id="different"/>')
        d=a.audit(self.repo,self.sm,self.h12)
        self.assertFalse(d['resco_reference_inputs']['route_byte_identical_to_H1212'])
        self.assertEqual(d['gates']['resco_hangzhou_routes_identity'],'NOT_IDENTICAL')
    def test_no_checkpoint_certified(self):
        d=a.audit(self.repo,self.sm,self.h12)
        self.assertTrue(all(not row['checkpoint_verified'] and not row['can_execute_directly_on_H1212'] for row in d['controllers']))
    def test_coSLight_single_scope_blocked(self):
        d=a.audit(self.repo,self.sm,self.h12)
        self.assertEqual(next(x for x in d['controllers'] if x['controller']=='CoSLight')['scope'],'multiagent_rl')
    def test_unknown_training_dir(self):
        with self.assertRaises(FileNotFoundError):a.audit(self.repo,self.sm,self.h12,self.rev/'missing')
    def test_unapproved_training_fails(self):
        p=self.rev/'resultados/h12_13_mock';p.mkdir()
        (p/'resultado_h12_13.json').write_text(json.dumps({'result':'FAIL'}))
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12,p)
    def test_training_pilot_only(self):
        p=self.rev/'resultados/h12_13_mock';p.mkdir()
        (p/'resultado_h12_13.json').write_text(json.dumps({'result':'H12_13_PILOT_OK', 'n_models':2, 'reports':[{'architecture':'hsarg_b1'},{'architecture':'coop_sarg_b1'}]}))
        d=a.audit(self.repo,self.sm,self.h12,p)
        self.assertEqual(d['H1213']['H1213'],'H12_13_PILOT_OK')
        self.assertEqual(d['gates']['SOTA_model_training'],'NOT_ACCREDITED')
    def test_training_full_is_not_SOTA(self):
        p=self.rev/'resultados/h12_13_train';p.mkdir()
        (p/'resultado_h12_13.json').write_text(json.dumps({
            'result':'H12_13_TRAINING_OK', 'n_models':2,
            'reports':[{'architecture':'hsarg_b1'},{'architecture':'coop_sarg_b1'}]}))
        d=a.audit(self.repo,self.sm,self.h12,p)
        self.assertEqual(d['H1213']['H1213'],'H12_13_TRAINING_OK')
        self.assertEqual(d['gates']['SOTA_model_training'],'NOT_ACCREDITED')
    def test_training_bad_arch_rejected(self):
        p=self.rev/'resultados/h12_13_bad_arch';p.mkdir()
        (p/'resultado_h12_13.json').write_text(json.dumps({
            'result':'H12_13_PILOT_OK','n_models':2,
            'reports':[{'architecture':'hsarg_b1'},{'architecture':'imitation'}]}))
        with self.assertRaises(a.AuditError):a.audit(self.repo,self.sm,self.h12,p)
    def test_source_tamper_postflight(self):
        d=a.audit(self.repo,self.sm,self.h12)
        (self.base/'agents/static/fixed.py').write_text('class FIXED: pass\n# modified')
        with self.assertRaises(a.AuditError):a.assert_sources(d)
    def test_markdown_contains_clear_limitations(self):
        s=a.md(a.audit(self.repo,self.sm,self.h12))
        self.assertIn('NO controladores entrenados',s)
        self.assertIn('CoSLight',s)
        self.assertIn('H12.12',s)
    def test_fail_closed_cli(self):
        self.net.unlink()
        with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(self.call(),2)
    def test_source_identical_test(self):
        d=a.audit(self.repo,self.sm,self.h12)
        self.assertTrue(d['resco_reference_inputs']['net_byte_identical_to_H1212'])
        self.assertTrue(d['resco_reference_inputs']['route_byte_identical_to_H1212'])

if __name__=='__main__':unittest.main()
