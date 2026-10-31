import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
import database as db


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.path=db.build(Path(cls.temp.name)/'test.sqlite3')

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_integrity_and_all_specialized_rows(self):
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
            for kind,table in [('phrase','phrase_details'),('rule','rule_details'),('event','event_details'),('term','term_details')]:
                n=conn.execute('SELECT count(*) FROM records WHERE kind=?',(kind,)).fetchone()[0]
                self.assertEqual(n,conn.execute('SELECT count(*) FROM '+table).fetchone()[0])

    def test_chinese_search_and_category(self):
        with db.connect(self.path) as conn:
            self.assertTrue(db.search(conn,'阀门',category='valves'))
            self.assertTrue(db.search(conn,'婚礼'))
            self.assertTrue(db.search(conn,'生病'))

    def test_accent_free_vietnamese(self):
        with db.connect(self.path) as conn:
            for query in ['ket xe','an trua','cam on','gio']:
                self.assertTrue(db.search(conn,query),query)

    def test_literal_query_no_sql_injection(self):
        with db.connect(self.path) as conn:
            before=conn.execute('SELECT count(*) FROM records').fetchone()[0]
            self.assertFalse(db.search(conn,"' OR 1=1 --"))
            self.assertEqual(before,conn.execute('SELECT count(*) FROM records').fetchone()[0])

    def test_all_cultural_records_have_scoped_sources(self):
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM records r WHERE evidence_type='cultural_reference' AND NOT EXISTS(SELECT 1 FROM record_sources s WHERE s.record_id=r.id)").fetchone()[0],0)

    def test_all_numeric_rules_are_hypotheses(self):
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM records WHERE kind='rule' AND evidence_type!='practice_hypothesis'").fetchone()[0],0)

    def test_show_keeps_examples_and_assumptions(self):
        with db.connect(self.path) as conn:
            row=db.show(conn,'P001')
            self.assertIn('anh',row['phrase']['vietnamese'])
            self.assertIn('假设',row['phrase']['assumptions'])
            self.assertEqual(row['evidence_type'],'authored_example')

    def test_validation_rejects_missing_and_unknown_sources(self):
        data=copy.deepcopy(db.load_data())
        row=next(r for r in data['records'] if r['evidence_type']=='cultural_reference')
        row['sources']=[]
        with self.assertRaises(ValueError):db.validate(data)
        row['sources']=[{'source_id':'DOES_NOT_EXIST','claim_scope':'invalid'}]
        with self.assertRaises(ValueError):db.validate(data)

    def test_validation_rejects_false_numeric_evidence(self):
        data=copy.deepcopy(db.load_data())
        row=next(r for r in data['records'] if r['kind']=='rule')
        row['evidence_type']='authored_example'
        with self.assertRaises(ValueError):db.validate(data)

    def test_fulltext_index_covers_all_records(self):
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM records').fetchone()[0],conn.execute('SELECT count(*) FROM search_index').fetchone()[0])
            self.assertTrue(conn.execute("SELECT record_id FROM search_index WHERE search_index MATCH ?",('"coffee"',)).fetchall())

    def test_unknown_record_and_blank_query(self):
        with db.connect(self.path) as conn:
            with self.assertRaises(ValueError):db.show(conn,'UNKNOWN')
            with self.assertRaises(ValueError):db.search(conn,'  ')


if __name__=='__main__': unittest.main()
