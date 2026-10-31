import json
import unittest
from datetime import datetime
import kb
import contact_planner as cp

class ScreeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=kb.load();cls.countries={c['code']:c for c in cls.data['countries']}
    def test_low_income_markets_excluded(self):
        for c in ['RW','ET']:
            self.assertEqual(self.countries[c]['market_screen']['status'],'excluded_low_income')
            self.assertFalse(self.countries[c]['market_screen']['default_new_development'])
    def test_high_income_not_automatic_stability_approval(self):
        sa=self.countries['SA']['market_screen']
        self.assertEqual(sa['income_group'],'high')
        self.assertEqual(sa['status'],'paused_conflict')
    def test_lower_middle_income_not_all_excluded(self):
        self.assertEqual(self.countries['IN']['market_screen']['status'],'candidate')
        self.assertEqual(self.countries['MA']['market_screen']['status'],'candidate')
        self.assertEqual(self.countries['KE']['market_screen']['status'],'conditional_review')
    def test_default_search_hides_inactive_countries(self):
        with kb.connect() as c:
            self.assertEqual(kb.search(c,'Kabsa',country='SA',include_shared=False),[])
            rows=kb.search(c,'Kabsa',country='SA',include_shared=False,include_inactive=True)
            self.assertTrue(rows)
            self.assertTrue(all(x['country']=='SA' for x in rows))
    def test_default_search_keeps_candidates(self):
        with kb.connect() as c:self.assertTrue(kb.search(c,'Tajine',country='MA',include_shared=False))
    def test_existing_customer_time_advice_not_cancelled(self):
        p=cp.plan('SA',datetime.fromisoformat('2026-11-02T10:00:00+03:00'))
        self.assertEqual(p['status'],'within_contact_window')
        self.assertFalse(p['new_development_recommended'])
        self.assertTrue(any('不属于新开发重点' in w for w in p['warnings']))
    def test_legacy_countries_not_falsely_rescreened(self):
        for c in ['VN','KZ','UZ','KG','TJ','TM']:
            self.assertEqual(self.countries[c]['market_screen']['status'],'linked_not_rescreened')
    def test_screen_file_matches_embedded_country_policy(self):
        screen=json.loads((kb.ROOT/'market_screen.json').read_text(encoding='utf-8'))
        self.assertEqual(screen['countries'],{c:x['market_screen'] for c,x in self.countries.items()})
    def test_no_customer_credit_or_actual_procurement_approval(self):
        for c in self.countries.values():
            x=c['market_screen']
            self.assertFalse(x['payment_verified']);self.assertFalse(x['live_procurement_verified'])

if __name__=='__main__':unittest.main()
