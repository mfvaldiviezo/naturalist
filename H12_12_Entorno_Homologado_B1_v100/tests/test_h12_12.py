import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from h12_12_contract import (ContractError, PhaseScheduler, observation_34,
                             reward_components, gini, cvar95, read_geometry,
                             transition_path, sha256_file)
from h12_12_homologar import parser, plan


STATES=['GGggrrrrGGggrrrr','yyyyrrrryyyyrrrr',
        'rrrrGGggrrrrGGgg','rrrryyyyrrrryyyy']


def network_fixture(path, *, yellow=3, program_type='actuated', corrupt=None):
    n=ET.Element('net')
    tl=ET.SubElement(n,'tlLogic',id='B1',type=program_type,programID='0',offset='0')
    durations=[42,yellow,42,yellow]
    for d,s in zip(durations,STATES):
        ET.SubElement(tl,'phase',duration=str(d),state=s)
    for i in range(16):
        frm=['B2B1','C1B1','B0B1','A1B1'][i//4]
        outgoing=['B1A1','B1B0','B1C1','B1B2'][i%4]
        ET.SubElement(n,'connection',{'from':frm,'fromLane':'0','to':outgoing,'toLane':'0',
                                       'tl':'B1','linkIndex':str(i)})
    if corrupt=='phase-length':tl[0].set('state','rrr')
    if corrupt=='duplicate-index':n[-1].set('linkIndex','0')
    if corrupt=='missing-yellow':tl[1].set('state','rrrrrrrrrrrrrrrr')
    if corrupt=='third-green':tl[1].set('state',STATES[0])
    ET.ElementTree(n).write(path,encoding='utf-8',xml_declaration=True)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.net=self.base/'hangzhou.net.xml'
        network_fixture(self.net)
        self.g=read_geometry(self.net)

    def test_green_indices(self):self.assertEqual(self.g.green_indices,(0,2))
    def test_real_four_inbound(self):self.assertEqual(len(self.g.lanes_in),4)
    def test_unique_inbound(self):self.assertEqual(len(set(self.g.lanes_in)),4)
    def test_downstream_nonempty(self):self.assertTrue(all(x[1] for x in self.g.lane_out_by_in))
    def test_original_actuated_metadata(self):self.assertEqual(self.g.original_program_type,'actuated')
    def test_sha_deterministic(self):self.assertEqual(self.g.source_xml_sha256,sha256_file(self.net))
    def test_one_to_three(self):self.assertEqual(transition_path(self.g,0,2),(1,2))
    def test_three_to_one(self):self.assertEqual(transition_path(self.g,2,0),(3,0))
    def test_same_green_raises(self):
        with self.assertRaises(ContractError):transition_path(self.g,0,0)
    def test_invalid_green_raises(self):
        with self.assertRaises(ContractError):transition_path(self.g,1,2)
    def test_bad_yellow_reject(self):
        network_fixture(self.net,yellow=2)
        with self.assertRaisesRegex(ContractError,'amarilla'):read_geometry(self.net)
    def test_bad_phase_width_reject(self):
        network_fixture(self.net,corrupt='phase-length')
        with self.assertRaisesRegex(ContractError,'Longitud'):read_geometry(self.net)
    def test_duplicate_link_index_reject(self):
        network_fixture(self.net,corrupt='duplicate-index')
        with self.assertRaisesRegex(ContractError,'duplicado'):read_geometry(self.net)
    def test_missing_yellow_reject(self):
        network_fixture(self.net,corrupt='missing-yellow')
        with self.assertRaisesRegex(ContractError,'sin ámbar'):read_geometry(self.net)
    def test_intermediate_green_reject(self):
        network_fixture(self.net,corrupt='third-green')
        with self.assertRaises(ContractError):read_geometry(self.net)
    def test_dtd_reject(self):
        self.net.write_text('<!DOCTYPE net [<!ENTITY bad SYSTEM "file:///etc/passwd">]><net/>')
        with self.assertRaises(ContractError):read_geometry(self.net)

    def test_stage_no_green_jump(self):
        s=PhaseScheduler(self.g,10)
        stages=[]
        for tick in range(90):
            action=1 if tick>=10 else 0
            stages.append(s.advance(0.5,action))
        groups=[]
        for k,st in enumerate(stages):
            if not groups or st!=groups[-1][0]:groups.append([st,1])
            else:groups[-1][1]+=1
        self.assertGreaterEqual(len(groups),3)
        self.assertEqual([x[0] for x in groups[:3]],[STATES[0],STATES[1],STATES[2]])
        self.assertEqual(groups[1][1],6)
        self.assertGreaterEqual(groups[0][1],20)

    def test_both_directions_yellow(self):
        s=PhaseScheduler(self.g,10)
        history=[]
        for tick in range(130):
            act=0 if tick<35 or tick>=85 else 1
            history.append(s.advance(0.5,act))
        for prev,nxt in zip(history,history[1:]):
            self.assertFalse((prev==STATES[0] and nxt==STATES[2]) or
                             (prev==STATES[2] and nxt==STATES[0]))
        self.assertIn(STATES[1],history)
        self.assertIn(STATES[3],history)

    def test_small_min_green_reject(self):
        with self.assertRaises(ContractError):PhaseScheduler(self.g,0)
    def test_scheduler_illegal_action(self):
        with self.assertRaises(ContractError):PhaseScheduler(self.g).advance(0.5,4)
    def test_scheduler_illegal_tick(self):
        with self.assertRaises(ContractError):PhaseScheduler(self.g).advance(2,1)

    def _obs(self,phase=0,age=10.0):
        inputs=list(self.g.lanes_in)
        out=dict(self.g.lane_out_by_in)
        lanes=set(inputs)
        for ls in out.values(): lanes.update(ls)
        counts={l:4 for l in lanes}; halts={l:1 for l in inputs}; waits={l:5 for l in inputs}
        return observation_34(inputs,counts,halts,waits,out,phase,age,self.g.green_indices,10),counts,halts,waits,out

    def test_observation_34(self):self.assertEqual(len(self._obs()[0]),34)
    def test_observation_box(self):self.assertTrue(all(0<=x<=1 for x in self._obs(age=500)[0]))
    def test_zero_fill_neutral(self):
        o,*_=self._obs()
        self.assertEqual(o[4:12],[0.0]*8)
        self.assertEqual(o[16:24],[0.0]*8)
    def test_pressure_neutral(self):self.assertEqual(self._obs()[0][24:28],[0.5]*4)
    def test_phase_one_hot(self):self.assertEqual(self._obs()[0][28:32],[1,0,0,0])
    def test_yellow_onehot_zero(self):self.assertEqual(self._obs(phase=1)[0][28:32],[0]*4)
    def test_age_both_clipped(self):self.assertEqual(self._obs(age=500)[0][32:34],[1,1])
    def test_pressure_downstream_sensed(self):
        o,c,h,w,down=self._obs()
        for dest in down[self.g.lanes_in[0]]:c[dest]=14
        changed=observation_34(self.g.lanes_in,c,h,w,down,0,10,self.g.green_indices,10)
        self.assertLess(changed[24],o[24])
    def test_no_duplicate_lane_in_state(self):
        inputs=[self.g.lanes_in[0]]*4
        o,c,h,w,d=self._obs()
        with self.assertRaises(ContractError):observation_34(inputs,c,h,w,d,0,10,(0,2),10)
    def test_negative_sensor_reject(self):
        o,c,h,w,d=self._obs();h[self.g.lanes_in[0]]=-1
        with self.assertRaises(ContractError):observation_34(self.g.lanes_in,c,h,w,d,0,10,(0,2),10)
    def test_gini_uniform(self):self.assertEqual(gini([4,4,4,4]),0)
    def test_gini_unbalanced(self):self.assertAlmostEqual(gini([0,0,0,8]),0.75)
    def test_cvar95(self):self.assertEqual(cvar95([0,1,2,10]),10)
    def test_zero_reward(self):self.assertEqual(reward_components([0]*4)['reward'],0)
    def test_reward_negative(self):self.assertLess(reward_components([0,10,20,30])['reward'],0)
    def test_reward_finite(self):self.assertTrue(math.isfinite(reward_components([1e8,0,0,0])['reward']))

    def test_plan_valid(self):
        repo=self.base/'repo';revision=self.base/'revision';revision.mkdir();
        n=repo/'tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml'
        n.parent.mkdir(parents=True);n.write_bytes(self.net.read_bytes())
        routes=repo/'tsc_framework/sumo_configs/routes/hangzhou/hangzhou_dense.rou.xml'
        routes.parent.mkdir(parents=True);routes.write_text('<routes/>',encoding='utf8')
        for name in ['src/core/tsc_env.py','scripts/train.py','config/default_config.yaml']:
            x=repo/'tsc_framework'/name;x.parent.mkdir(parents=True,exist_ok=True);x.write_text('dummy',encoding='utf8')
        args=parser().parse_args(['--repo-root',str(repo),'--revision-root',str(revision),'--mode','plan'])
        m=plan(args)
        self.assertEqual(m['actions']['type'],'Discrete(2)')
        self.assertEqual(m['observation']['shape'],[34])
        self.assertEqual(len(m['sources_sha256']),8)
        self.assertFalse((revision/'resultados').exists())

if __name__=='__main__':unittest.main()
