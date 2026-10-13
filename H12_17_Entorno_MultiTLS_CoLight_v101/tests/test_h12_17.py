import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json
import types
import xml.etree.ElementTree as ET
import hashlib

HERE=Path(__file__).resolve().parents[1]
REV=HERE.parent
H1212=REV/'H12_12_Entorno_Homologado_B1_v100'
if not (H1212/'h12_12_contract.py').is_file():
    raise RuntimeError('Antes de probar H12.17 hay que descomprimir H12.12 en revision_naturalista')
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(H1212))
from h12_17_contract import (ContractError,parse_network,PhaseScheduler,Phase,Geometry,
                            transition_path,validate_route,sha256_file,read_safe_xml,
                            Network,EXPECTED_TLS,SCHEMA)
from h12_12_contract import observation_34,reward_components
import h12_17_multi_tls as cli


def fake_network(tmp,n=12,retain_green=False):
    names=list(EXPECTED_TLS)[:n]
    root=ET.Element('net')
    # Directed ring assures all TLS have inbound/outbound lanes and graph connected.
    for i,name in enumerate(names):
        suc=names[(i+1)%n]
        ET.SubElement(root,'edge',id=name+'_'+suc,**{'from':name,'to':suc})
        ET.SubElement(root,'edge',id=suc+'_'+name,**{'from':suc,'to':name})
    for i,name in enumerate(names):
        logic=ET.SubElement(root,'tlLogic',id=name,type='actuated',programID='0')
        states=('GGrr', 'Gyrr' if retain_green else 'yyrr', 'rrGG','rryy')
        for k,state in enumerate(states):
            ET.SubElement(logic,'phase',duration='3' if k%2 else '42',state=state)
        prev=names[(i-1)%n];nxt=names[(i+1)%n]
        for ix in range(4):
            source=prev if ix<2 else nxt
            destination=nxt if ix<2 else prev
            ET.SubElement(root,'connection',**{'from':source+'_'+name,
                'to':name+'_'+destination, 'fromLane':'0', 'toLane':'0',
                'tl':name,'linkIndex':str(ix)})
    path=tmp/'net.xml'
    ET.ElementTree(root).write(path,encoding='utf8')
    return path

def geo(kind='normal'):
    phases=(Phase(0,'GGrr',42),Phase(1,'Gyrr' if kind=='retained' else 'yyrr',3),
            Phase(2,'rrGG',42),Phase(3,'rryy',3))
    return Geometry('X','sha','0','actuated',('x_0','y_0'),
        (('x_0',('out_x_0',)),('y_0',('out_y_0',))),phases,(0,2),3.)

class TestContract(unittest.TestCase):
    def test_phase_yellow_priority(self):
        self.assertEqual(Phase(1,'yyyrrrGyy',3).kind,'yellow')
    def test_phase_green(self):
        self.assertEqual(Phase(0,'Ggrr',42).kind,'green')
    def test_phase_red(self):
        self.assertEqual(Phase(0,'rrrr',3).kind,'all_red')
    def test_transition_0_2(self):
        self.assertEqual(transition_path(geo(),0,2),(1,2))
    def test_transition_2_0(self):
        self.assertEqual(transition_path(geo(),2,0),(3,0))
    def test_retained_green_transition_allowed(self):
        self.assertEqual(transition_path(geo('retained'),0,2),(1,2))
    def test_new_green_during_yellow_rejected(self):
        g=geo();p=list(g.phases);p[1]=Phase(1,'yyGr',3)
        b=Geometry(g.tls_id,g.source_xml_sha256,g.program_id,g.original_program_type,
                   g.lanes_in,g.lane_out_by_in,tuple(p),g.green_indices,3.)
        with self.assertRaises(ContractError):transition_path(b,0,2)
    def test_stage_min_green(self):
        s=PhaseScheduler(geo(),10)
        for _ in range(20):self.assertEqual(s.advance(.5,1),'GGrr')
        self.assertEqual(s.advance(.5,1),'yyrr')
    def test_yellow_completed(self):
        s=PhaseScheduler(geo(),10)
        for _ in range(21):s.advance(.5,1)
        for _ in range(5):self.assertEqual(s.advance(.5,0),'yyrr')
        self.assertEqual(s.advance(.5,0),'rrGG')
    def test_yellow_request_ignored(self):
        s=PhaseScheduler(geo(),10)
        for _ in range(21):s.advance(.5,1)
        for _ in range(6):s.advance(.5,0)
        self.assertEqual(s.stage,2)
    def test_scheduler_reject_float_action(self):
        with self.assertRaises(ContractError):PhaseScheduler(geo()).advance(.5,1.0)
    def test_scheduler_reject_invalid_dt(self):
        with self.assertRaises(ContractError):PhaseScheduler(geo()).advance(1.5,1)
    def test_scheduler_reject_boolean(self):
        with self.assertRaises(ContractError):PhaseScheduler(geo()).advance(.5,True)
    def test_scheduler_initial_yellow_rejected(self):
        with self.assertRaises(ContractError):PhaseScheduler(geo(),initial_phase=1)
    def test_network_12nodes_graph(self):
        with tempfile.TemporaryDirectory() as x:
            net=parse_network(fake_network(Path(x)),require_hangzhou=False)
            self.assertEqual(net.node_ids,EXPECTED_TLS)
            self.assertEqual(len(net.directed_edges),24)
            d=net.as_json()
            self.assertEqual(d['node_to_index']['B1'],3)
            self.assertEqual(len(d['graph_directed_edge_index']),2)
            self.assertEqual(len(d['graph_directed_edge_index'][0]),24)
            self.assertTrue(all(set(p)=={0,2} for p in (g.green_indices for g in net.geometries)))
    def test_synthetic_retain_green_accepted(self):
        with tempfile.TemporaryDirectory() as x:
            net=parse_network(fake_network(Path(x),retain_green=True),require_hangzhou=False)
            self.assertEqual(len(net.geometries),12)
            self.assertEqual(net.geometries[0].phases[1].kind,'yellow')
    def test_sha_guard(self):
        with tempfile.TemporaryDirectory() as x:
            with self.assertRaises(ContractError):parse_network(fake_network(Path(x)),require_hangzhou=True)
    def test_no_duplicate_tls(self):
        with tempfile.TemporaryDirectory() as x:
            p=fake_network(Path(x),3);r=ET.parse(p);a=r.getroot().find('tlLogic');r.getroot().append(ET.fromstring(ET.tostring(a)));r.write(p)
            with self.assertRaises(ContractError):parse_network(p,False)
    def test_isolated_graph_rejected(self):
        with tempfile.TemporaryDirectory() as x:
            p=fake_network(Path(x),3);r=ET.parse(p);root=r.getroot()
            for edge in list(root.findall('edge')):root.remove(edge)
            r.write(p)
            with self.assertRaises(ContractError):parse_network(p,False)
    def test_yellow_too_short_rejected(self):
        with tempfile.TemporaryDirectory() as x:
            p=fake_network(Path(x),3);r=ET.parse(p)
            r.getroot().find('tlLogic').findall('phase')[1].set('duration','2');r.write(p)
            with self.assertRaises(ContractError):parse_network(p,False)
    def test_invalid_link_index_rejected(self):
        with tempfile.TemporaryDirectory() as x:
            p=fake_network(Path(x),3);r=ET.parse(p)
            r.getroot().find('connection').set('linkIndex','99');r.write(p)
            with self.assertRaises(ContractError):parse_network(p,False)
    def test_incomplete_index_rejected(self):
        with tempfile.TemporaryDirectory() as x:
            p=fake_network(Path(x),3);r=ET.parse(p)
            r.getroot().remove(r.getroot().find('connection'));r.write(p)
            with self.assertRaises(ContractError):parse_network(p,False)
    def test_invalid_xml_rejected(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/'bad.xml';p.write_text('<!DOCTYPE x><net/>')
            with self.assertRaises(ContractError):read_safe_xml(p)
    def test_route_guard(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/'route.xml';p.write_text('<routes/>')
            self.assertEqual(validate_route(p,None),sha256_file(p))
            with self.assertRaises(ContractError):validate_route(p,'00')
    def test_route_wrong_root(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/'route.xml';p.write_text('<config/>')
            with self.assertRaises(ContractError):validate_route(p,None)
    def test_graph_deterministic(self):
        with tempfile.TemporaryDirectory() as x:
            p=fake_network(Path(x),12)
            a=parse_network(p,False).as_json();b=parse_network(p,False).as_json()
            self.assertEqual(a['graph_directed_edge_index'],b['graph_directed_edge_index'])
            self.assertEqual(a['node_order'],b['node_order'])
    def test_node_order_not_from_xml_insertion(self):
        with tempfile.TemporaryDirectory() as x:
            p=fake_network(Path(x),12);r=ET.parse(p);root=r.getroot()
            nodes=list(root.findall('tlLogic'))
            for node in nodes:root.remove(node)
            for node in reversed(nodes):root.insert(0,node)
            r.write(p)
            self.assertEqual(parse_network(p,False).node_ids,EXPECTED_TLS)
    def test_h1212_obs34_same_semantics(self):
        x=['B2B1_0','C1B1_0','B0B1_0','A1B1_0'];d={k:[f'out_{k}'] for k in x}
        counts={k:3. for k in x};counts.update({f'out_{k}':1. for k in x})
        halt={k:1. for k in x};wait={k:5. for k in x}
        vals=observation_34(x,counts,halt,wait,d,0,15.,(0,2),10.)
        self.assertEqual(len(vals),34);self.assertAlmostEqual(vals[24],.52)
        self.assertEqual(vals[28:32],[1.,0.,0.,0.])
    def test_reward_independent_local(self):
        self.assertLess(reward_components([3.,0.])['reward'],0)
    def test_xml_root_not_net(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/'no.xml';p.write_text('<routes/>')
            with self.assertRaises(ContractError):parse_network(p,False)
    def test_wrong_green_from_yellow_kind(self):
        g=geo('retained');self.assertEqual([p.kind for p in g.phases],['green','yellow','green','yellow'])

class TestAuditAndEvents(unittest.TestCase):
    def test_event_checker_valid(self):
        d=[{'tls':'B1','stage':0,'event':'online_initialization','t_s':0.},
           {'tls':'B1','stage':1,'event':'enter_stage','t_s':10.,'kind':'yellow'},
           {'tls':'B1','stage':2,'event':'enter_stage','t_s':13.,'kind':'green'}]
        ans=cli.validate_events(d,['B1'],10,12)
        self.assertEqual(ans['n_yellow_entries'],1)
    def test_event_checker_jump_green_rejected(self):
        d=[{'tls':'B1','stage':0,'event':'online_initialization','t_s':0.},
           {'tls':'B1','stage':2,'event':'enter_stage','t_s':10.,'kind':'green'}]
        with self.assertRaises(ContractError):cli.validate_events(d,['B1'],10,12)
    def test_event_checker_short_yellow_rejected(self):
        d=[{'tls':'B1','stage':0,'event':'online_initialization','t_s':0.},
           {'tls':'B1','stage':1,'event':'enter_stage','t_s':10.,'kind':'yellow'},
           {'tls':'B1','stage':2,'event':'enter_stage','t_s':12.,'kind':'green'}]
        with self.assertRaises(ContractError):cli.validate_events(d,['B1'],10,12)
    def test_event_checker_short_green_rejected(self):
        d=[{'tls':'B1','stage':0,'event':'online_initialization','t_s':0.},
           {'tls':'B1','stage':1,'event':'enter_stage','t_s':2.,'kind':'yellow'}]
        with self.assertRaises(ContractError):cli.validate_events(d,['B1'],10,12)
    def test_report_never_calls_sota(self):
        plan={'graph':{'node_order':['B1'],'graph_directed_edges':[['B1','A1']],
               'geometries':{'B1':{'lanes_in':['x'],'green_indices':[0,2],
               'phases':[{'index':i,'state':x} for i,x in enumerate(['Grr','yrr','rrG','rry'])]}}}}
        txt=cli.render_report(plan)
        self.assertIn('NO CoLight',txt)
        self.assertIn('PENDIENTE',txt)
    def test_unique_results(self):
        with tempfile.TemporaryDirectory() as x:
            p=cli.unique_dir(Path(x));q=cli.unique_dir(Path(x))
            self.assertNotEqual(p,q)
    def test_exclusive_json(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/'o.json';cli.write_json_unique(p,{'ok':1})
            with self.assertRaises(FileExistsError):cli.write_json_unique(p,{'ok':2})
    def test_cli_plan_arg_required(self):
        import contextlib,io
        p=cli.arg_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):p.parse_args(['--mode','plan'])
    def test_cli_smoke_ack_rejection_before_import(self):
        with tempfile.TemporaryDirectory() as x:
            manifest={'network':'a','routes':'b','prior':{'h1212_source':str(Path(x)/'h12_12_contract.py')}}
            with self.assertRaises(ContractError):cli.run_smoke(cli.arg_parser().parse_args([
                '--repo-root',x,'--revision-root',x,'--h1212-smoke-dir',x,'--h1216-dir',x,
                '--mode','smoke']),manifest,Path(x))
    def test_schema(self):
        self.assertIn('V100',SCHEMA)

if __name__=='__main__':unittest.main()

class TestMultiTLSRuntimeMock(unittest.TestCase):
    """Integración de interfaz sin SUMO instalado (mock explícito, NO smoke real)."""
    def setUp(self):
        import numpy as np
        import importlib
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.net=fake_network(self.root,12,retain_green=True)
        self.route=self.root/'routes.rou.xml';self.route.write_text('<routes/>')
        self.network=parse_network(self.net,require_hangzhou=False)
        gg=types.ModuleType('gymnasium')
        ss=types.ModuleType('gymnasium.spaces')
        class Env:
            def reset(self,seed=None):return None
        class Box:
            def __init__(self,low,high,shape,dtype):self.shape=shape
            def contains(self,x):
                a=np.asarray(x)
                return a.shape==self.shape and np.isfinite(a).all() and (a>=0).all() and (a<=1).all()
        class MultiDiscrete:
            def __init__(self,nvec):self.nvec=nvec
        ss.Box=Box;ss.MultiDiscrete=MultiDiscrete;gg.Env=Env;gg.spaces=ss
        self.fgym=gg;self.fspaces=ss
        class FakeTrafficLights:
            def __init__(self,network):
                self.geo={g.tls_id:g for g in network.geometries}
                self.lights={g.tls_id:g.phases[0].state for g in network.geometries}
            def getIDList(self):return list(self.geo)
            def getControlledLanes(self,id_):return list(self.geo[id_].lanes_in)*2
            def getProgram(self,id_):return '0'
            def getAllProgramLogics(self,id_):
                phases=[types.SimpleNamespace(state=p.state) for p in self.geo[id_].phases]
                return [types.SimpleNamespace(programID='0',phases=phases)]
            def getPhase(self,id_):return 0
            def getRedYellowGreenState(self,id_):return self.lights[id_]
            def setRedYellowGreenState(self,id_,state):self.lights[id_]=state
        class FakeLane:
            def getLastStepVehicleNumber(self,id_):return 1
            def getLastStepHaltingNumber(self,id_):return 0
            def getWaitingTime(self,id_):return 0
        class FakeSimulation:
            def __init__(self):self.time=0
            def getTime(self):return self.time
            def getCollidingVehiclesNumber(self):return 0
        class FakeConnection:
            def __init__(self,network):
                self.trafficlight=FakeTrafficLights(network)
                self.lane=FakeLane()
                self.simulation=FakeSimulation()
                self.closed=False
            def simulationStep(self):self.simulation.time+=.5
            def close(self):self.closed=True
        self.connection=FakeConnection(self.network)
        fake_traci=types.ModuleType('traci')
        fake_traci.__file__='C:/fake/traci.py'
        fake_traci.start=lambda *args,**kw:None
        fake_traci.getConnection=lambda *args,**kw:self.connection
        self.ftraci=fake_traci
        # importar módulo con stubs, evitar contaminar más pruebas
        self.patcher=patch.dict(sys.modules,{'gymnasium':gg,'gymnasium.spaces':ss,'traci':fake_traci})
        self.patcher.start();self.addCleanup(self.patcher.stop)
        if 'h12_17_env' in sys.modules:del sys.modules['h12_17_env']
        self.env_module=importlib.import_module('h12_17_env')
        self.addCleanup(lambda:sys.modules.pop('h12_17_env',None))
        self.patch_net=patch.object(self.env_module,'parse_network',return_value=self.network)
        self.patch_route=patch('h12_17_contract.validate_route',return_value=sha256_file(self.route))
        self.patch_which=patch.object(self.env_module.shutil,'which',return_value='sumo')
        for p in [self.patch_net,self.patch_route,self.patch_which]:p.start();self.addCleanup(p.stop)
        self.env=self.env_module.MultiTLSHomologado(
            net_file=self.net,route_file=self.route,output_dir=self.root,
            sumocfg_file=self.root/'custom.sumocfg',max_rl_steps=12)
        self.addCleanup(self.env.close)

    def test_online_start_nodes_and_graph(self):
        obs,info=self.env.reset()
        self.assertEqual(obs.shape,(12,34))
        self.assertEqual(info['node_order'],list(EXPECTED_TLS))
        self.assertEqual(info['edge_index'],self.network.as_json()['graph_directed_edge_index'])
        self.assertEqual(len(self.env.events),12)
        self.assertEqual(len(self.connection.trafficlight.lights),12)

    def test_twelve_steps_yellows_all_nodes(self):
        import numpy as np
        self.env.reset()
        for k in range(12):
            act=np.asarray([((k//4)+(i%2))%2 for i in range(12)])
            obs,r,term,trunc,info=self.env.step(act)
            self.assertEqual(obs.shape,(12,34))
            self.assertTrue(-1<=r<=0)
            self.assertFalse(term)
        self.assertTrue(trunc)
        self.assertEqual(self.env._ticks,120)
        self.assertEqual(self.connection.simulation.getTime(),60.)
        z=cli.validate_events(self.env.events,EXPECTED_TLS,10,12)
        self.assertGreaterEqual(z['n_yellow_entries'],12)
        self.assertEqual(len(info['local']),12)
    def test_float_actions_rejected(self):
        self.env.reset()
        with self.assertRaises(ContractError):self.env.step([.0]*12)
    def test_bad_shape_rejected(self):
        self.env.reset()
        with self.assertRaises(ContractError):self.env.step([0]*11)
    def test_out_of_range_actions_rejected(self):
        self.env.reset()
        with self.assertRaises(ContractError):self.env.step([2]+[0]*11)
    def test_unexpected_tls_state_blocked(self):
        self.env.reset()
        fn=self.connection.trafficlight.getRedYellowGreenState
        self.connection.trafficlight.getRedYellowGreenState=lambda id_: 'xxxx' if self.connection.simulation.getTime()>.2 else fn(id_)
        with self.assertRaises(ContractError):self.env.step([0]*12)
    def test_repeat_sumocfg_sha_guard(self):
        self.env.reset()
        self.env.close()
        (self.root/'custom.sumocfg').write_text('edited')
        with self.assertRaises(ContractError):self.env.reset()
    def test_repeat_episode_restarts_clean(self):
        self.env.reset()
        self.env.step([0]*12)
        self.connection.simulation.time=0
        obs,info=self.env.reset()
        self.assertEqual(self.env._ticks,0)
        self.assertEqual(len(self.env.events),12)
        self.assertEqual(obs.shape,(12,34))
    def test_no_train_modules_imported(self):
        self.env.reset()
        self.assertNotIn('torch_geometric',sys.modules)


class TestPreflightSynthetic(unittest.TestCase):
    """Plan completo sobre artefactos sintéticos; no representa la red real."""
    def setUp(self):
        from dataclasses import replace
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)
        self.repo=p/'traffic_project';self.revision=p/'revision_naturalista'
        self.revision.mkdir();self.repo.mkdir()
        self.net=self.repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
        self.route=self.repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
        self.net.parent.mkdir(parents=True);self.route.parent.mkdir(parents=True)
        nettmp=fake_network(p,12)
        self.net.write_bytes(nettmp.read_bytes());self.route.write_text('<routes/>')
        self.netsha=sha256_file(self.net);self.routsha=sha256_file(self.route)
        orig=parse_network(self.net,False)
        updated=[]
        for g in orig.geometries:
            if g.tls_id=='B1':
                lanes=['A1B1_0','B0B1_0','B2B1_0','C1B1_0']
                g=replace(g,lanes_in=tuple(lanes),
                      lane_out_by_in=tuple((l,(f'out_{l}',)) for l in lanes))
            updated.append(g)
        self.network=Network(orig.net_sha256,orig.node_ids,tuple(updated),orig.directed_edges)
        self.h1212src=self.revision/cli.H1212_DIR_DEFAULT/'h12_12_contract.py'
        self.h1212src.parent.mkdir(parents=True)
        self.h1212src.write_bytes((H1212/'h12_12_contract.py').read_bytes())
        self.smoke=self.revision/'resultados'/'old_smoke';self.smoke.mkdir(parents=True)
        manifest={'schema':'H12_12_B1_GREEN2_OBS34_V100',
                  'network':str(self.net.resolve()),'routes':str(self.route.resolve()),
                  'network_contract':{'green_indices':[0,2],
                      'lanes_in':['A1B1_0','B0B1_0','B2B1_0','C1B1_0']},
                  'sources_sha256':{str(self.net.resolve()):self.netsha,
                                    str(self.route.resolve()):self.routsha,
                                    str(self.h1212src.resolve()):sha256_file(self.h1212src)}}
        mf=self.smoke/'manifiesto_h12_12.json'
        mf.write_text(json.dumps(manifest))
        (self.smoke/'smoke_h12_12.json').write_text(json.dumps({
            'result':'H12_12_SUMO_SMOKE_OK','manifest_sha256':sha256_file(mf)}))
        self.audit=self.revision/'resultados'/'old_audit';self.audit.mkdir()
        self.auditfile=self.audit/'dictamen_h12_16.json'
        self.auditfile.write_text(json.dumps({
          'result':'H12_16_COLIGHT_SOURCE_AUDIT_OK',
          'local_contract':{'network_sha256':self.netsha,'route_sha256':self.routsha},
          'gates':{'upstream_orig_authenticity':'PASSED_PINNED_COMMIT_AND_BLOBS',
                   'upstream_libsignal_authenticity':'PASSED_PINNED_COMMIT_AND_BLOBS'}}))
        self.args=cli.arg_parser().parse_args(['--repo-root',str(self.repo),
            '--revision-root',str(self.revision),
            '--h1212-smoke-dir',str(self.smoke),'--h1216-dir',str(self.audit)])
        patches=[patch.object(cli,'parse_network',return_value=self.network),
                 patch.object(cli,'validate_route',return_value=self.routsha),
                 patch.object(cli,'EXPECTED_NET_SHA',self.netsha),
                 patch.object(cli,'EXPECTED_ROUTE_SHA',self.routsha)]
        for q in patches:q.start();self.addCleanup(q.stop)

    def test_complete_preflight(self):
        m=cli.make_plan(self.args)
        self.assertEqual(m['result'],'H12_17_PLAN_CONTRACT_OK')
        self.assertEqual(m['schema'],SCHEMA)
        self.assertEqual(m['network_sha256'],self.netsha)
        self.assertEqual(m['graph']['node_to_index']['B1'],3)
        self.assertIn(str(self.auditfile.resolve()),m['source_sha256'])
    def test_h1212_source_tamper_rejected(self):
        # Manipular bytes: la prueba valida integridad SHA, no decodificacion regional.
        self.h1212src.write_bytes(self.h1212src.read_bytes() + b'\n#tampered')
        with self.assertRaises(ContractError):cli.make_plan(self.args)
    def test_h1212_manifest_tamper_rejected(self):
        p=self.smoke/'manifiesto_h12_12.json';p.write_text(p.read_text()+' ')
        with self.assertRaises(ContractError):cli.make_plan(self.args)
    def test_h1216_wrong_status_rejected(self):
        d=json.loads(self.auditfile.read_text());d['result']='NOT_OK'
        self.auditfile.write_text(json.dumps(d))
        with self.assertRaises(ContractError):cli.make_plan(self.args)
    def test_h1216_wrong_sha_rejected(self):
        d=json.loads(self.auditfile.read_text());d['local_contract']['network_sha256']='bad'
        self.auditfile.write_text(json.dumps(d))
        with self.assertRaises(ContractError):cli.make_plan(self.args)
    def test_h1216_incomplete_pins_rejected(self):
        d=json.loads(self.auditfile.read_text());d['gates']['upstream_libsignal_authenticity']='NOT_VERIFIED'
        self.auditfile.write_text(json.dumps(d))
        with self.assertRaises(ContractError):cli.make_plan(self.args)
    def test_wrong_routes_sha_rejected(self):
        self.route.write_text('<routes><vehicle/></routes>')
        with self.assertRaises(ContractError):cli.make_plan(self.args)
    def test_main_plan_does_not_create_results(self):
        import contextlib,io
        before=set(self.revision.glob('resultados/h12_17_*'))
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            code=cli.main(['--repo-root',str(self.repo), '--revision-root',str(self.revision),
                           '--h1212-smoke-dir',str(self.smoke),'--h1216-dir',str(self.audit)])
        after=set(self.revision.glob('resultados/h12_17_*'))
        self.assertEqual(before,after)
        self.assertEqual(code,0)
        self.assertIn('H12_17_PLAN_OK',stream.getvalue())

