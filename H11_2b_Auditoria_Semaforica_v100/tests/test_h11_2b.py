import csv, hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'h11_2b_auditar_semaforos.py'
spec=importlib.util.spec_from_file_location('h11_2b',SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def csvwrite(path, rows, headers):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)


def src(root,scenario,mode,change_color=False):
    folder=root/scenario;folder.mkdir()
    ev=[];tr=[];safe=[]
    v='2';cohort='both' if mode=='hybrid' else 'unclassified'
    for t,state,dist,speed,acc in [
        (10,'G',60,15,0),(10.5,'y',52,15,0),(11,'y',44,15,-1),(11.5,'r',36,14,-2),
        (12,'r',28,13,-3),(12.5,'r',20,11,-4)]:
        tr.append(dict(time_s=t,vehicle_id=v,cohort=cohort,lane_id='B0B1_0',speed_m_s=speed,
             accel_m_s2=acc,tls_id='B1',tls_link_index='8',tls_state=state,tls_distance_m=dist))
    # a fully observed yellow approach; only hybrid crosses in red
    for t,c in [(10,'green'),(10.5,'yellow'),(11.5,'red')]:
        ev.append(dict(time_s=t,vehicle_id=v,cohort=cohort,event_kind='approach_opportunity_proxy',
           tls_id='B1',link_index='8',episode_id='2|B1|8|1',lane_before='B0B1_0',lane_after='',
           color_label=c,quality='opportunity_proxy_not_human_decision',
           distance_previous_m={10:60,10.5:52,11.5:36}[t],
           speed_previous_m_s=15))
    ev.append(dict(time_s=13,vehicle_id=v,cohort=cohort,event_kind='crossing_proxy',
          tls_id='B1',link_index='8',episode_id='2|B1|8|1',lane_before='B0B1_0',lane_after=':B1_8_0',
          color_label='red' if mode=='hybrid' else 'green',quality='PROXY_signal_stable',
          distance_previous_m=2,speed_previous_m_s=10))
    # A separate observed opportunity with no detected crossing (censored)
    tr.append(dict(time_s=19,vehicle_id='99',cohort='neither' if mode=='hybrid' else 'unclassified',
                lane_id='C0C1_0',speed_m_s=5,accel_m_s2=0,tls_id='C1',tls_link_index='1',
                tls_state='y',tls_distance_m=20))
    ev.append(dict(time_s=19,vehicle_id='99',cohort='neither' if mode=='hybrid' else 'unclassified',
             event_kind='approach_opportunity_proxy',tls_id='C1',link_index='1',
             episode_id='99|C1|1|1',lane_before='C0C1_0',lane_after='',color_label='yellow',
             quality='opportunity_proxy_not_human_decision',distance_previous_m=20,speed_previous_m_s=5))
    headers_e=['time_s','vehicle_id','cohort','event_kind','tls_id','link_index','episode_id',
               'lane_before','lane_after','color_label','quality','distance_previous_m','speed_previous_m_s']
    headers_t=['time_s','vehicle_id','cohort','lane_id','speed_m_s','accel_m_s2','tls_id',
               'tls_link_index','tls_state','tls_distance_m']
    csvwrite(folder/'eventos_semaforicos_h11.csv',ev,headers_e)
    csvwrite(folder/'trayectorias_h11.csv',tr,headers_t)
    csvwrite(folder/'eventos_interseccion_h11.csv',[],['vehicle_id'])
    csvwrite(folder/'seguridad_h11.csv',[],['step'])
    hashes={p.name:m.sha(p) for p in folder.glob('*.csv')}
    (folder/'manifest_h11_2.json').write_text(json.dumps(dict(condition=scenario,observed_steps=3,
         empirically_calibrated_quito=False,outputs_sha256=hashes)),encoding='utf-8')
    return folder


class H112BTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'resultados').mkdir()
        self.nom=src(self.root,'nominal','nominal');self.hib=src(self.root,'hibrido_contextual','hybrid')
        self.actions=self.root/'acciones_hito08.csv'
        csvwrite(self.actions,[dict(vehicle_id='2',time_s='11',command_issued='False',action_decision='cooldown'),
                   dict(vehicle_id='2',time_s='12',command_issued='True',action_decision='command_issued')],
                 ['vehicle_id','time_s','command_issued','action_decision'])
        self.h09=self.root/'eventos_h09.csv'
        csvwrite(self.h09,[dict(vehicle_id='2',site_id='B1',time_s='13',event_type='tls_crossing_link',
                            signal_state='red',classification_quality='confirmed')],
                 ['vehicle_id','site_id','time_s','event_type','signal_state','classification_quality'])

    def test_source_verified(self):
        x=m.verify_source(self.nom,'nominal',expected_steps=3)
        self.assertEqual(x['verified_files'],4)

    def test_tamper_hash_rejected(self):
        with (self.nom/'trayectorias_h11.csv').open('a') as f:f.write('garbage\n')
        with self.assertRaisesRegex(ValueError,'INTEGRIDAD FALLIDA'):
            m.verify_source(self.nom,'nominal',expected_steps=3)

    def test_condition_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'Condición errónea'):
            m.verify_source(self.nom,'hibrido_contextual',expected_steps=3)

    def test_episodes_and_censor(self):
        eps,_=m.load_events(self.hib)
        self.assertEqual(len(eps),2)
        lookup,membership,max_t,n=m.load_trajectories(self.hib)
        self.assertEqual(membership['2'],'both')
        self.assertEqual(n,7)
        e=[v for v in eps.values() if v['vehicle_id']=='99'][0]
        output=m.classify_episode(e,'hibrido_contextual',lookup,membership,
                 actual_cohorts=membership,actions={},reference_a=4.5,max_t=max_t)
        self.assertEqual(output['resultado'],'sin_cruce_observado')
        self.assertTrue(output['oportunidad_amarilla'])
        self.assertTrue(output['censura_sin_cruce'])

    def test_full_workflow(self):
        eps,pa,g,recon,sumry=m.run(self.nom,self.hib,self.h09,self.actions,4.5,3)
        self.assertEqual(len(eps),4)
        self.assertEqual(sumry['totales']['nominal']['episodios'],2)
        self.assertEqual(sumry['totales']['hibrido_contextual']['cruces_rojo'],1)
        self.assertEqual(sumry['totales']['hibrido_contextual']['sin_cruce'],1)
        self.assertEqual(sumry['parejas']['ambos'],2)
        self.assertEqual(sumry['parejas']['verde_a_rojo'],1)
        self.assertEqual(sumry['reconciliacion_h09']['coincidencias'],1)
        h=[e for e in eps if e['escenario']=='hibrido_contextual' and e['vehicle_id']=='2'][0]
        self.assertTrue(h['factible_reaccion_05'])
        self.assertEqual(h['vine_comandos_ventana'],1)
        self.assertEqual(h['vine_propuestas_ventana'],2)

    def test_nominal_cohort_counterfactual_only(self):
        eps,*_=m.run(self.nom,self.hib,expected_steps=3)
        n=next(e for e in eps if e['escenario']=='nominal' and e['vehicle_id']=='2')
        self.assertEqual(n['cohort_actual'],'unclassified')
        self.assertEqual(n['cohorte_contrafactual'],'both')

    def test_no_h09_reconcile(self):
        out,counts=m.h09_reconcile([],None)
        self.assertEqual(counts['status'],'NO_SUMINISTRADO')

    def test_unknown_color(self):
        self.assertEqual(m.color('r'),'red')
        self.assertEqual(m.color('G'),'green')
        self.assertEqual(m.color('unknown'),'unknown')
        self.assertEqual(m.color('rG'),'unknown')

    def test_feasibility_reaction_sensitivity(self):
        # at 15 m/s and 52 m: reaction .5 => 32.5m, reaction 1 => 40m: both feasible
        eps,*_=m.run(self.nom,self.hib,expected_steps=3)
        h=next(e for e in eps if e['escenario']=='hibrido_contextual' and e['vehicle_id']=='2')
        self.assertAlmostEqual(h['distancia_necesaria_reaccion_05_m'],32.5)
        self.assertAlmostEqual(h['distancia_necesaria_reaccion_10_m'],40)
        self.assertTrue(h['factible_reaccion_10'])

    def test_cannot_overwrite(self):
        (self.root/'resultados'/'existing').mkdir()
        with self.assertRaises(FileExistsError):
            m.safe_destination(self.root,self.root/'resultados'/'existing',[self.nom,self.hib])

    def test_no_input_overlap(self):
        with self.assertRaises(ValueError):
            m.safe_destination(self.root,self.hib/'salida',[self.nom,self.hib])

    def test_success_files(self):
        dest=self.root/'resultados'/'nuevo'
        rc=m.main(['--root',str(self.root),'--nom',str(self.nom),'--hib',str(self.hib),
                   '--h09-events',str(self.h09),'--vine-actions',str(self.actions),
                   '--expected-steps','3','--output',str(dest),'--guardar'])
        self.assertEqual(rc,0)
        self.assertTrue((dest/'informe_h11_2b.md').exists())
        with (dest/'movimientos_emparejados_h11_2b.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(len(list(csv.DictReader(f))),2)

    def test_counterfactual_group_separate_from_actual(self):
        data,*_=m.run(self.nom,self.hib,expected_steps=3)
        targets=m.counterfactual_groups(data)
        row=next(r for r in targets if r['escenario']=='nominal' and r['cohorte_objetivo']=='both')
        self.assertEqual(row['tipo_asignacion'],'SOLO_ETIQUETA_CONTRAFACTUAL_SIN_INTERVENCION')
        self.assertEqual(row['episodios_con_oportunidad'],1)

    def test_strict_pair_requires_provenance(self):
        with self.assertRaises(ValueError):
            m.verify_paired_provenance(self.nom,'nominal',strict=True)

    def test_paired_provenance_reverification(self):
        pair=self.root/'resultados'/'pareado_nominal';(pair/'observado'/'nominal').mkdir(parents=True)
        (pair/'control'/'nominal').mkdir(parents=True)
        file='trafico_h09.csv'
        for arm in ('observado','control'):
            (pair/arm/'nominal'/file).write_text('col\n1\n',encoding='utf-8')
        target=(pair/'observado'/'telemetria');target.mkdir()
        digest=m.sha(pair/'observado'/'nominal'/file)
        (pair/'comparacion_h11_2.json').write_text(json.dumps({
           'mode':'nominal','status':'INVARIANZA_BYTE_A_BYTE_VERIFICADA',
           'comparison':{file:{'identical':True,'sha_control':digest,'sha_observado':digest}}}),encoding='utf-8')
        self.assertEqual(m.verify_paired_provenance(target,'nominal',strict=True)['status'],
                         'INVARIANZA_PAREADA_REVERIFICADA')
        (pair/'control'/'nominal'/file).write_text('ALTERADO',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'alterado'):
            m.verify_paired_provenance(target,'nominal',strict=True)

    def test_preflight_no_report(self):
        dest=self.root/'resultados'/'no-creado'
        rc=m.main(['--root',str(self.root),'--nom',str(self.nom),'--hib',str(self.hib),
                   '--expected-steps','3'])
        self.assertEqual(rc,0);self.assertFalse(dest.exists())

if __name__=='__main__':unittest.main()
