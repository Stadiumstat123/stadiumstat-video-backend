import unittest
from service.scoring import observation, parse_clock, parse_period, clean_timeline, rate

class ScoringTests(unittest.TestCase):
    def test_parsers_reject_noise(self):
        self.assertIsNone(parse_clock('99:99'))
        self.assertEqual(parse_clock('0:03.5'), 3.5)
        self.assertEqual(parse_clock('10.55'),655)
        self.assertEqual(parse_clock('59.9'),59.9)
        self.assertEqual(parse_period('4TH'), 4)
        self.assertEqual(parse_period('2OT'), 6)
        self.assertIsNone(parse_period('27'))
        self.assertIsNone(observation({'home':('99',.1),'away':('97',1),'period':('4',1),'clock':('0:03',1)},10))
    def full_game(self):
        rows=[]
        for q in range(1,5):
            for second in range(0,721,5):
                elapsed=(q-1)*720+second
                rows.append({'video_time':elapsed*2,'elapsed':elapsed,'home':elapsed//30+1,'away':elapsed//30,'period':q,'clock':720-second,'confidence':.95})
        return rows
    def test_missing_footage_withholds_final(self):
        self.assertIsNone(rate([],100)['rating'])
        self.assertIsNone(rate(self.full_game()[-20:],20)['rating'])
        self.assertIsNone(rate([x for x in self.full_game() if x['period']!=2],600)['rating'])
    def test_complete_fixture_deterministic(self):
        rows=self.full_game();a=rate(rows,len(rows))
        self.assertEqual(a,rate(rows,len(rows)))
        self.assertTrue(a['coverage_checks_passed']);self.assertTrue(1<=a['rating']<=10)
        self.assertEqual(len(a['components']),3);self.assertEqual(len(a['model_hash']),64)
    def test_replay_rejected(self):
        rows=self.full_game()[:30];cleaned,rejected=clean_timeline(rows+[rows[0]])
        self.assertEqual(len(cleaned),len(rows));self.assertEqual(rejected,1)
if __name__=='__main__':unittest.main()
