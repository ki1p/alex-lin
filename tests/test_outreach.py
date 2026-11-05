import tempfile,unittest
from pathlib import Path
from app import App,Store

class OutreachTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.app=App(self.root)
  self.cid=self.app.save_customer(dict(name='Outreach QA',email='one@example.com',emails=['two@example.com']))
 def tearDown(self):self.app.alive=False;self.tmp.cleanup()
 def draft(self,**changes):
  return self.app.save_draft(dict(customer_id=self.cid,recipient='one@example.com',subject='Example circuit review',body='Human reviewed body',**changes))
 def test_brief_survives_save_edit_and_restart(self):
  mid=self.draft(writing_brief={'first_name':'Nick','fact':'HVAC service','fact_source':'https://example.com'})
  self.draft(id=mid)
  self.app.alive=False;self.app=App(self.root)
  self.assertEqual(self.app.state()['messages'][0]['writing_brief']['first_name'],'Nick')
  self.assertFalse(self.app.running);self.assertFalse(self.app.store.rows('SELECT * FROM events'))
 def test_multiple_contact_drafts_keep_evidence_without_queuing(self):
  mid=self.draft(writing_brief={'fact':'HVAC service','fact_source':'Official page','lead_context':'Confirmed inquiry','service_scope':'Inspection only','trial_terms':'MOQ to confirm','subject_claims':'Current quote, approval conditions apply'})
  batch=self.app.contacts.prepare(mid)
  self.assertEqual(len(batch['ids']),2)
  for msg in self.app.state()['messages']:
   self.assertEqual(msg['writing_brief']['fact_source'],'Official page');self.assertEqual(msg['status'],'draft')
   self.assertEqual(msg['writing_brief']['lead_context'],'Confirmed inquiry');self.assertEqual(msg['writing_brief']['service_scope'],'Inspection only')
   self.assertEqual(msg['writing_brief']['trial_terms'],'MOQ to confirm');self.assertEqual(msg['writing_brief']['subject_claims'],'Current quote, approval conditions apply')
 def test_invalid_brief_does_not_save_a_partial_message(self):
  with self.assertRaises(ValueError):self.draft(writing_brief=['invalid'])
  with self.assertRaises(ValueError):self.draft(writing_brief={'fact':'x'*3001})
  self.assertFalse(self.app.store.rows('SELECT * FROM messages'))
 def test_old_database_migrates_without_changing_body_or_status(self):
  mid=self.draft()
  with self.app.store.conn() as db:db.execute('ALTER TABLE messages DROP COLUMN writing_brief')
  Store(self.root/'friesgo.sqlite3')
  msg=self.app.store.rows('SELECT * FROM messages WHERE id=?',(mid,))[0]
  self.assertEqual(msg['body'],'Human reviewed body');self.assertEqual(msg['status'],'draft');self.assertEqual(msg['writing_brief'],'{}')

if __name__=='__main__':unittest.main()
