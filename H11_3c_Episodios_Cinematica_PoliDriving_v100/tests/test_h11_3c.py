import importlib.util,unittest
from pathlib import Path
import pandas as pd
p=Path(__file__).resolve().parents[1]/'h11_3c_episodios.py'
s=importlib.util.spec_from_file_location('h11_3c',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
    def make(self):
        data=[]
        for d,se in [('alonso','s1'),('andres','s2')]:
            for seg in [1,2]:
                for k,(a,j,v) in enumerate([(0,0,10),(3,4,20),(3,4,20),(0,0,5),(0,0,20)]):
                    data.append(dict(driver_id=d,session_id=se,segment_id=str(seg),raw_row=k+1,
                           a_t_m_s2=a,j_t_observed_m_s3=j,dt_t_s=.5,speed_kmh=v))
        return pd.DataFrame(data)
    def test_masks(self):
        x=self.make(); f=m.thresholds(x,2,3)
        self.assertEqual(int(f['aceleracion_intensa'].sum()),8)
        self.assertEqual(int(f['cualquier_maniobra_intensa'].sum()),8)
    def test_event_boundaries(self):
        x=self.make();f=m.thresholds(x,2,3)
        episodes=m.aggregate_events(x,f['cualquier_maniobra_intensa'],'all','base')
        self.assertEqual(len(episodes),4)
        self.assertTrue(all(q['n_muestras']==2 for q in episodes))
        self.assertTrue(all(q['duracion_exposicion_s']==1. for q in episodes))
    def test_exposure_counts(self):
        x=self.make();per,total,ev=m.analyze(x,[('test',2,3)])
        self.assertEqual(per.n_marcha_gt5.sum(),16)
        self.assertEqual(per.n_muestras_cualquier_maniobra_intensa.sum(),8)
        self.assertEqual(total.loc[total.evento.eq('cualquier_maniobra_intensa'),'n_episodios'].iloc[0],4)
    def test_text_limits(self):
        x=self.make();r=m.report(*m.analyze(x,[('test',2,3)]))
        self.assertIn('NO prueba de imprudencia',r)
        self.assertIn('SENSIBILIDAD',r)
    def test_no_holdout(self):
        self.assertNotIn(('richard','20231227_104130'),m.ALLOWED)
        self.assertNotIn(('alonso','20231229_151643'),m.ALLOWED)
    def test_threshold_sensitivity(self):
        x=self.make();lo=m.thresholds(x,2,3);hi=m.thresholds(x,4,5)
        self.assertGreater(sum(lo['cualquier_maniobra_intensa']),sum(hi['cualquier_maniobra_intensa']))
if __name__=='__main__':unittest.main()
