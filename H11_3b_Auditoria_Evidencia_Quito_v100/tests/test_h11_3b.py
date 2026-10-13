import importlib.util
import math
import unittest
from pathlib import Path
import pandas as pd
p=Path(__file__).resolve().parents[1]/'h11_3b_auditar_evidencia.py'
s=importlib.util.spec_from_file_location('h11_3b',p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

class TestH113b(unittest.TestCase):
    def test_bin_bounds(self):
        for value,expected in [(5,None),(5.0001,'05_20'),(20,'05_20'),(40,'20_40'),(60,'40_60'),(60.0001,'gt60')]:
            self.assertEqual(m.band(value),expected)
    def test_bad_speeds(self):
        self.assertIsNone(m.band(-10));self.assertIsNone(m.band(float('nan')))
    def test_nonrepresentative_statuses(self):
        rows={r['codigo']:r for r in m.evidence_rows()}
        for i in ('Q03','Q08'):self.assertEqual(rows[i]['categoria'],'NO_IDENTIFICABLE_ACTUALMENTE')
        self.assertEqual(rows['Q09']['categoria'],'FUENTE_EXCLUIDA')
    def test_signal_and_headway_not_grounded(self):
        rows={r['codigo']:r for r in m.evidence_rows()}
        for i in ('Q04','Q05','Q06'):self.assertEqual(rows[i]['categoria'],'SIN_ANCLA_EMPIRICA')
    def test_p0_not_closed(self):
        rows={r['id']:r for r in m.decisions()}
        self.assertNotEqual(rows['P0-01_C']['estado'],'ACREDITADO')
        self.assertEqual(rows['P0-02_B']['estado'],'PENDIENTE')
    def test_finite_stats(self):
        x=m.finite_stats(pd.Series([0.,1.,-1.,float('nan')]))
        self.assertEqual(x['n'],3);self.assertAlmostEqual(x['mean'],0.)
    def test_coverage_sessions(self):
        rows=[]
        for driver,session in [('alonso','s1'),('pablo','s2')]:
            for v in [5.,10.,20.,40.,60.,61.]:
                rows.append({'entity':driver+'|'+session,'moving_a':v>5,'moving_j':v>5,
                             'speed_kmh':v,'a':0.,'jerk':0.1,'dt':.5})
        cov=m.dev_coverage(pd.DataFrame(rows))
        self.assertEqual(cov.filas_verificadas.sum(),12)
        self.assertEqual(cov.muestras_vel_gt5.sum(),10)
        self.assertEqual(cov.n_vel_gt60.sum(),2)
    def test_report_explicit_limits(self):
        cov=pd.DataFrame([{'driver_id':'alonso','session_id':'s1','filas_verificadas':2,'muestras_vel_gt5':1}])
        text=m.create_report(cov,[],{'h01':{'csv_sha256':'abc'},'vine_actions_sha256':'def'},Path('.'))
        for literal in ('NO de calibración Quito','NO estima prevalencia','P0-02','furious','Richard'):
            self.assertIn(literal,text)
    def test_no_raw_in_runtime_sources(self):
        # Protege la lista de evidencia y los metadatos; codigo verifica H01, H11 y acciones.
        x=Path(m.__file__).read_text(encoding='utf-8')
        self.assertIn('parent.load_h01',x)
        self.assertIn('parent.summarize',x)
        self.assertNotIn('pd.read_csv(root/',x)

if __name__=='__main__':unittest.main()
