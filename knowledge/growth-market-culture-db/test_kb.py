import json
import sqlite3
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
import kb

class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=kb.load()
    def test_integrity_and_foreign_keys(self):
        with kb.connect() as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_json_matches_sqlite_and_index(self):
        with kb.connect() as c:
            self.assertEqual(kb.stats(c)['records'],len(self.data['records']))
            self.assertEqual(c.execute('SELECT count(*) FROM search_index').fetchone()[0],len(self.data['records']))
    def test_declared_coverage(self):
        self.assertEqual(sum(c['coverage']=='new_full_profile' for c in self.data['countries']),12)
        self.assertEqual(sum(c['coverage']=='linked_existing' for c in self.data['countries']),6)
    def test_references_and_scopes_validate(self):self.assertTrue(kb.validate(self.data))
    def test_chinese_lookup_and_shared_overlay(self):
        with kb.connect() as c:
            rows=kb.search(c,'压差',country='SA',limit=200)
            self.assertTrue(any(r['country']=='GLOBAL' for r in rows))
            self.assertTrue(all(r['country'] in {'GLOBAL','SA'} for r in rows))
    def test_country_only_lookup(self):
        with kb.connect() as c:
            rows=kb.search(c,'谢谢',country='ID',kind='phrase',include_shared=False)
            self.assertTrue(rows)
            self.assertTrue(all(r['country']=='ID' and r['kind']=='phrase' for r in rows))
    def test_source_support_can_be_retrieved(self):
        with kb.connect() as c:
            row=kb.show(c,'SA-001')
            self.assertTrue(row['sources'][0]['supports'])
            self.assertTrue(row['sources'][0]['url'].startswith('https://'))
    def test_read_only_database(self):
        with kb.connect() as c:
            with self.assertRaises(sqlite3.OperationalError):c.execute("DELETE FROM records")
    def test_separate_languages_not_hindi_dialects(self):
        rows=[r for r in self.data['records'] if r['country']=='IN' and r['kind']=='language_variety' and '泰米尔' in r['summary']]
        self.assertTrue(rows)
        self.assertEqual(rows[0]['details']['variety_type'],'separate_language')
    def test_project_status_not_verified_leads(self):
        rows=[r for r in self.data['records'] if r['kind']=='project_signal']
        self.assertEqual(len(rows),12)
        self.assertTrue(all(r['details']['current_procurement_verified'] is False for r in rows))
        stages={r['country']:r['details']['stage'] for r in rows}
        self.assertEqual(stages['ET'],'historical_outcome')
        self.assertEqual(stages['PH'],'financing_approved')
        self.assertEqual(stages['RW'],'not_verified')
    def test_forecasts_keep_their_status(self):
        rows=[r for r in self.data['records'] if r['details'].get('metric')=='real_gdp_growth']
        self.assertEqual({r['country'] for r in rows},{'SA','AE','ID','RW'})
        self.assertTrue(all(r['details']['status']=='forecast' for r in rows))
        self.assertTrue(all(r['details']['ranking_eligible'] is False for r in rows))
    def test_rules_are_not_population_statistics(self):
        rows=[r for r in self.data['records'] if r['kind']=='rule']
        self.assertTrue(rows)
        self.assertTrue(all(r['evidence']=='practice_hypothesis' and r['details']['validation']=='unvalidated_practice_hypothesis' for r in rows))
    def test_no_native_review_claim(self):
        rows=[r for r in self.data['records'] if r['kind']=='phrase']
        self.assertTrue(all(r['details']['native_review_status']=='source_attested_not_native_reviewed' for r in rows))
    def test_sources_have_record_support(self):
        used={x['source'] for r in self.data['records'] for x in r['sources']}
        self.assertEqual({s['id'] for s in self.data['sources']},used)
    def test_linked_markets_do_not_claim_new_full_coverage(self):
        codes={c['code'] for c in self.data['countries'] if c['coverage']=='linked_existing'}
        for c in codes:
            rows=[r for r in self.data['records'] if r['country']==c]
            self.assertEqual(len(rows),1)
            self.assertFalse(rows[0]['details']['new_full_profile'])
    def test_export_retains_records_and_stage_boundaries(self):
        import export_guides
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            for name in ['data.json','contact_policy.json']:
                (target/name).write_bytes((kb.ROOT/name).read_bytes())
            with patch.object(export_guides,'ROOT',target):export_guides.main()
            for country in self.data['countries']:
                name='COMMON.md' if country['code']=='GLOBAL' else country['code']+'.md'
                text=(target/name).read_text(encoding='utf-8')
                for row in [r for r in self.data['records'] if r['country']==country['code']]:
                    self.assertIn(row['id'],text)
                    if row['kind']=='project_signal':self.assertIn('当前采购已核实：**否**',text)
            self.assertIn(str(len(self.data['records']))+'条记录',(target/'README.md').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
