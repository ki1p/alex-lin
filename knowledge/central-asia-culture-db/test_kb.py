import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
import kb


class KnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.path=kb.build(Path(cls.temp.name)/'test.sqlite3')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_integrity_and_index(self):
        with kb.connect(self.path) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],c.execute('SELECT count(*) FROM search_index').fetchone()[0])

    def test_readonly_search_connection(self):
        with kb.connect(self.path) as c:
            with self.assertRaises(sqlite3.OperationalError):c.execute('DELETE FROM records')

    def test_context_releases_file_handle(self):
        with kb.connect(self.path) as c:
            self.assertEqual(c.execute('SELECT 1').fetchone()[0],1)
        with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')

    def test_country_and_shared_filter(self):
        with kb.connect(self.path) as c:
            rows=kb.search(c,'目录',country='KZ')
            self.assertTrue(rows)
            self.assertTrue(all(r['country'] in {'KZ','CA'} for r in rows))
            rows=kb.search(c,'目录',country='KZ',include_shared=False)
            self.assertTrue(rows)
            self.assertTrue(all(r['country']=='KZ' for r in rows))

    def test_chinese_search(self):
        with kb.connect(self.path) as c:
            for query in ['婚礼','面包','帕米尔','阀门','Сәлеметсіз']:
                self.assertTrue(kb.search(c,query),query)

    def test_native_and_romanized_phrases(self):
        with kb.connect(self.path) as c:
            self.assertTrue(kb.search(c,'Salamatsyzby',country='KG'))
            self.assertTrue(kb.search(c,'Bagyslan',country='TM'))
            self.assertTrue(kb.search(c,"O'g'uz",country='UZ'))
            self.assertTrue(kb.search(c,'челек',country='KG'))

    def test_fulltext_index(self):
        with kb.connect(self.path) as c:
            self.assertTrue(c.execute('SELECT record_id FROM search_index WHERE search_index MATCH ?',('"каталог"',)).fetchall())

    def test_literal_query_is_not_sql(self):
        with kb.connect(self.path) as c:
            self.assertFalse(kb.search(c,"' OR 1=1 --"))
            self.assertEqual(kb.stats(c)['records'],301)

    def test_references_have_scoped_sources(self):
        with kb.connect(self.path) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM records r WHERE evidence IN ('cultural_reference','source_attested_phrase') AND NOT EXISTS(SELECT 1 FROM citations s WHERE s.record_id=r.id)").fetchone()[0],0)

    def test_all_numeric_rules_are_hypotheses(self):
        with kb.connect(self.path) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM records WHERE kind='rule' AND evidence!='practice_hypothesis'").fetchone()[0],0)

    def test_no_false_native_review_claims(self):
        data=kb.load()
        for r in data['records']:
            if r['kind']=='phrase':self.assertIn('not_native_reviewed',r['details']['native_review_status'])

    def test_script_and_language_are_distinct(self):
        data=kb.load()
        script=next(r for r in data['records'] if r['title']=='跨境文字不同')
        self.assertEqual(script['details']['variety_type'],'script_variation')
        for title in ['帕米尔诸语言','雅格诺比语','卡拉卡尔帕克语']:
            r=next(r for r in data['records'] if r['title']==title)
            self.assertEqual(r['details']['variety_type'],'separate_language')

    def test_missing_or_unknown_sources_rejected(self):
        data=copy.deepcopy(kb.load())
        row=next(r for r in data['records'] if r['evidence']=='cultural_reference')
        row['sources']=[]
        with self.assertRaises(ValueError):kb.validate(data)
        row['sources']=[{'source':'MISSING','supports':'test'}]
        with self.assertRaises(ValueError):kb.validate(data)

    def test_invalid_ranges_and_country_rejected(self):
        data=copy.deepcopy(kb.load())
        row=next(r for r in data['records'] if r['kind']=='rule')
        row['details']['min']=100;row['details']['max']=1
        with self.assertRaises(ValueError):kb.validate(data)
        row['details']['min']=0;row['country']='UNKNOWN'
        with self.assertRaises(ValueError):kb.validate(data)

    def test_show_and_invalid_input(self):
        with kb.connect(self.path) as c:
            row=kb.show(c,'KZ-P001')
            self.assertEqual(row['details']['text'],'Сәлеметсіз бе?')
            self.assertTrue(row['sources'])
            with self.assertRaises(ValueError):kb.show(c,'MISSING')
            with self.assertRaises(ValueError):kb.search(c,' ')


if __name__=='__main__':unittest.main()
