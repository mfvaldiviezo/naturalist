import csv, importlib.util, json, tempfile, unittest, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(filename,name):
    spec=importlib.util.spec_from_file_location(name,str(ROOT/'scripts'/filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
cmp=load('comparar_factorial_h09_v143.py','cmpv143')
aud=load('auditar_semilla_h09_v143.py','audv143')
agg=load('comparar_multisemilla_h09_v143.py','aggv143')

def writetable(path,rows):
    with path.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

class TestResume(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.make_fixture()
    def make_fixture(self):
        for label,name in cmp.RUNS.items():
            dest=self.root/name;dest.mkdir()
            active=label not in ('baseline','probe')
            nseen=44 if label in ('placebo','S','V') else 45 if active else 0
            cohort=[{'vehicle_id':str(i),'assigned':int(active and i<45)} for i in range(300)]
            exposure=[{'vehicle_id':str(i),'seen':int(i<nseen),'profile_verified':int(i<nseen)} for i in range(45)] if active else []
            traffic=[{'step':i,'mean_speed_kmh':40,'n_halted':8,'arrivals_step':int(i<5),
                     'collisions_step':0,'teleports_start_step':0} for i in range(3)]
            events=[{'vehicle_id':'0','event_type':'stopline','signal_state':'unknown',
                     'classification_quality':'uncertain','speed_mps':'','limit_mps':''}]
            writetable(dest/'cohorte_h09.csv',cohort)
            # Header-only CSV for baseline/probe
            if exposure:writetable(dest/'exposicion_h09.csv',exposure)
            else:(dest/'exposicion_h09.csv').write_text('vehicle_id,seen,profile_verified\n',encoding='utf8')
            writetable(dest/'trafico_h09.csv',traffic);writetable(dest/'eventos_h09.csv',events)
            files=('cohorte_h09.csv','exposicion_h09.csv','trafico_h09.csv','eventos_h09.csv')
            manifest={'status':'SUMO_EXECUTED_EXPLORATORY','mode':'active' if active else label,
                'seed':102,'porcentaje_solicitado':15 if active else 0,
                'profile_parameters':cmp.EXPECTED_PARAMS.get(label),
                'original_hashes_sha256':{
                    '/same/a.sumocfg':'x'*64,'/same/net.net.xml':'y'*64,'/same/route.rou.xml':'z'*64,
                    '/vary/'+label+'.json':label},
                'generated_hashes_sha256':{str(dest/f):cmp.sha_file(dest/f) for f in files},
                'n_seen_total':250,
                'exposure_summary':{'n_assigned':45 if active else 0,'n_roster':300,
                'n_selected_seen':nseen,'n_selected_verified_vtype':nseen,
                'n_selected_never_seen':45-nseen if active else 0,
                'n_expected_selected_without_verified_profile':45-nseen if active else 0},
                'traffic_sha256':cmp.sha_file(dest/'trafico_h09.csv')}
            (dest/'manifest_H09.json').write_text(json.dumps(manifest),encoding='utf8')
    def manifest(self,label):
        fp=self.root/cmp.RUNS[label]/'manifest_H09.json';return fp,json.loads(fp.read_text())
    def mutate_manifest(self,label,callback):
        fp,data=self.manifest(label);callback(data);fp.write_text(json.dumps(data))
    def mutate_exposure(self,label,callback):
        fp=self.root/cmp.RUNS[label]/'exposicion_h09.csv'
        rows=cmp.rows_from(fp);callback(rows);writetable(fp,rows)
        def fix(m):m['generated_hashes_sha256'][str(fp)]=cmp.sha_file(fp)
        self.mutate_manifest(label,fix)
    def test_44_45_accepted_and_reported(self):
        r=cmp.compare(self.root)
        self.assertEqual(r['status'],'PLACEBO_BITWISE_IDENTICAL')
        self.assertEqual({x['scenario'] for x in r['exposure_warnings']},{'placebo','S','V'})
        self.assertEqual(next(x for x in r['rows'] if x['label']=='S')['n_verified'],44)
    def test_validator_realized_exposure(self):
        r=aud.check_seed(ROOT/'scripts/comparar_factorial_h09_v143.py',self.root,102)
        self.assertEqual(r['cohort_n'],45)
    def test_reject_44_seen_43_verified(self):
        self.mutate_manifest('S',lambda m:m['exposure_summary'].update(n_selected_verified_vtype=43,n_expected_selected_without_verified_profile=2))
        self.mutate_exposure('S',lambda rows:rows[0].update(profile_verified='0'))
        with self.assertRaisesRegex(ValueError,'NO verificado'):cmp.compare(self.root)
    def test_reject_45_assigned_46_seen(self):
        self.mutate_manifest('SV',lambda m:m['exposure_summary'].update(n_selected_seen=46))
        with self.assertRaises(ValueError):cmp.compare(self.root)
    def test_reject_inconsistent_not_seen(self):
        self.mutate_manifest('S',lambda m:m['exposure_summary'].update(n_selected_never_seen=0))
        with self.assertRaisesRegex(ValueError,'inconsistentes'):cmp.compare(self.root)
    def test_reject_exposure_checksum_changed(self):
        p=self.root/cmp.RUNS['S']/'exposicion_h09.csv';p.write_text(p.read_text()+'tampered')
        with self.assertRaisesRegex(ValueError,'modificado'):cmp.compare(self.root)
    def test_reject_exposure_missing_selected_id(self):
        self.mutate_exposure('S',lambda rows:rows.pop())
        with self.assertRaisesRegex(ValueError,'Exposicion no cubre'):cmp.compare(self.root)
    def test_reject_duplicate_ids_in_exposure(self):
        self.mutate_exposure('S',lambda rows:rows[1].update(vehicle_id='0'))
        with self.assertRaisesRegex(ValueError,'duplicados'):cmp.compare(self.root)
    def test_reject_duplicate_ids_in_cohort(self):
        fp=self.root/cmp.RUNS['S']/'cohorte_h09.csv';rows=cmp.rows_from(fp)
        rows[1]['vehicle_id']=rows[0]['vehicle_id'];writetable(fp,rows)
        self.mutate_manifest('S',lambda m:m['generated_hashes_sha256'].update({str(fp):cmp.sha_file(fp)}))
        with self.assertRaisesRegex(ValueError,'duplicados'):cmp.compare(self.root)
    def test_reject_45_seen_but_44_csv_seen(self):
        self.mutate_manifest('S',lambda m:m['exposure_summary'].update(n_selected_seen=45,n_selected_verified_vtype=45,n_selected_never_seen=0,n_expected_selected_without_verified_profile=0))
        with self.assertRaisesRegex(ValueError,'CSV y manifest'):cmp.compare(self.root)
    def test_single_run_passes_44_45(self):
        r=aud.check_single(ROOT/'scripts/comparar_factorial_h09_v143.py',self.root,102,'S')
        self.assertEqual((r['n_assigned'],r['n_seen'],r['n_verified']),(45,44,44))
    def test_resume_uses_folder_labels_for_all_seven_runs(self):
        # Caso real: v1.4.2 fallaba tras baseline/probe con KeyError: active_15_placebo.
        for canonical, dirname in cmp.RUNS.items():
            run = aud.check_single(ROOT/'scripts/comparar_factorial_h09_v143.py',self.root,102,dirname)
            self.assertEqual(run['label'],canonical)
        self.assertEqual(aud.normalize_label(cmp,'active_15_placebo'),'placebo')
        self.assertEqual(aud.normalize_label(cmp,'active_15_semaforos'),'S')
        self.assertEqual(aud.normalize_label(cmp,'active_15_velocidad'),'V')
        self.assertEqual(aud.normalize_label(cmp,'active_15_semaforos_velocidad'),'SV')
        self.assertEqual(aud.normalize_label(cmp,'active_15_combinado'),'combinado')

    def test_actual_cli_with_folder_label_runs_successfully(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/auditar_semilla_h09_v143.py'),
             '--comparador',str(ROOT/'scripts/comparar_factorial_h09_v143.py'),
             '--root',str(self.root),'--seed','102','--label','active_15_placebo'],
             capture_output=True,text=True)
        self.assertEqual(result.returncode,0,msg=result.stderr)
        self.assertIn('ETIQUETA NORMALIZADA: active_15_placebo -> placebo',result.stdout)
        self.assertIn('vistos=44, verificados=44',result.stdout)

    def test_unknown_folder_alias_rejected_instead_of_skipped(self):
        with self.assertRaisesRegex(ValueError,'desconocida'):
            aud.check_single(ROOT/'scripts/comparar_factorial_h09_v143.py',self.root,102,'active_15_FALSO')

    def test_alias_validation_rejects_invalid_sha(self):
        path=self.root/cmp.RUNS['placebo']/'trafico_h09.csv'
        path.write_text(path.read_text(encoding='utf-8')+'\nCORRUPT',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'modificado'):
            aud.check_single(ROOT/'scripts/comparar_factorial_h09_v143.py',self.root,102,'active_15_placebo')

    def test_alias_validation_rejects_wrong_seed(self):
        with self.assertRaisesRegex(ValueError,'Semilla'):
            aud.check_single(ROOT/'scripts/comparar_factorial_h09_v143.py',self.root,103,'active_15_placebo')

    def test_single_run_wrong_seed_rejected(self):
        with self.assertRaisesRegex(ValueError,'Semilla'):aud.check_single(ROOT/'scripts/comparar_factorial_h09_v143.py',self.root,103,'S')
    def test_aggregator_stores_exposure(self):
        r=cmp.compare(self.root)
        r2=json.loads(json.dumps(r));r2['seed']=101
        for x in r2['rows']:x['seed']=101
        result=agg.aggregate([r2,r])
        self.assertEqual(result['n_seeds'],2)
        self.assertEqual(next(x for x in result['per_seed'] if x['seed']==102 and x['label']=='S')['n_seen'],44)
        self.assertEqual(len(result['exposure_warnings']),6)
    def test_runner_resume_pattern_no_rewrite(self):
        ps=(ROOT/'ejecutar_reanudar_h09_v143.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('REUTILIZANDO seed=',ps)
        self.assertIn('CORRIDA', (ROOT/'scripts/auditar_semilla_h09_v143.py').read_text())
        self.assertIn('continue',ps)
        self.assertFalse(any(line.lstrip().startswith('python -c') for line in ps.splitlines()))
        self.assertIn('Test-Path -LiteralPath $dest',ps)

if __name__=='__main__':unittest.main()
