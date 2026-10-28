import tempfile,unittest
from pathlib import Path
from app import App
from contacts import email_list,phone_list
from unittest.mock import patch

class ContactTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=App(Path(self.tmp.name));self.cid=self.app.save_customer(dict(name='Contact QA',email='one@example.com',emails=['two@example.com','ONE@example.com'],phone='+84 900000001',whatsapp_numbers=['+84 900000002','+84900000001']))
 def tearDown(self):self.app.alive=False;self.tmp.cleanup()
 def email(self):return self.app.save_draft(dict(customer_id=self.cid,recipient='one@example.com',subject='Supply cooperation',body='Approved body'))
 def test_normalize_and_deduplicate(self):
  self.assertEqual(email_list('A@example.com; a@example.com\nb@example.com'),['a@example.com','b@example.com'])
  self.assertEqual(phone_list('+84 900000001 / 0084 (900) 000-001'),['+84900000001'])
 def test_all_emails_prepared_separately_without_sending(self):
  batch=self.app.contacts.prepare(self.email());self.assertEqual([m['recipient'] for m in batch['messages']],['one@example.com','two@example.com']);self.assertFalse(batch['started'])
  self.assertTrue(all(m['status']=='draft' for m in batch['messages']));self.assertFalse(self.app.store.rows('SELECT * FROM events'))
 def test_repeated_planning_reuses_drafts(self):
  mid=self.email();a=self.app.contacts.prepare(mid);b=self.app.contacts.prepare(mid);self.assertEqual(a['ids'],b['ids'])
 def test_sent_and_uncertain_addresses_skipped(self):
  mid=self.email();batch=self.app.contacts.prepare(mid)
  with self.app.store.conn() as db:
   db.execute("UPDATE messages SET status='submitted' WHERE id=?",(mid,));db.execute("UPDATE messages SET status='uncertain' WHERE id=?",(batch['ids'][1],))
  source=self.email();batch=self.app.contacts.prepare(source);self.assertEqual(batch['ids'],[]);self.assertEqual(len(batch['skipped']),2)
 def test_failed_first_whatsapp_does_not_prevent_second(self):
  mid=self.app.wa.draft(dict(customer_id=self.cid,recipient='+84900000001',body='Approved WhatsApp body'))
  calls=[]
  def check(cid,n):calls.append(n);return dict(number=n,registration='not_registered' if n.endswith('1') else 'registered')
  with patch.object(self.app.wa,'check_number',side_effect=check):batch=self.app.contacts.prepare(mid)
  self.assertEqual(calls,['+84900000001','+84900000002']);self.assertEqual([m['recipient'] for m in batch['messages']],['+84900000002']);self.assertEqual(len(batch['skipped']),1)
  self.assertFalse(self.app.store.rows("SELECT * FROM messages WHERE status='queued'"))
 def test_check_all_continues_after_lookup_error(self):
  with patch.object(self.app.wa,'check_number',side_effect=[{'registration':'error'},{'registration':'registered'}]) as check:
   results=self.app.contacts.check_all(self.cid)
  self.assertEqual(check.call_count,2);self.assertEqual(results[1]['registration'],'registered')
 def test_email_history_does_not_block_whatsapp(self):
  mid=self.email()
  with self.app.store.conn() as db:db.execute("UPDATE messages SET status='submitted' WHERE id=?",(mid,))
  wa=self.app.wa.draft(dict(customer_id=self.cid,recipient='+84900000001',body='Approved body'))
  with patch.object(self.app.wa,'check_number',return_value={'registration':'registered'}):batch=self.app.contacts.prepare(wa)
  self.assertEqual(len(batch['ids']),2)
 def test_manual_contact_edit_deactivates_removed_addresses(self):
  self.app.save_customer(dict(id=self.cid,name='Contact QA',email='one@example.com',emails=['three@example.com'],phone='',whatsapp_numbers=[]))
  self.assertEqual(self.app.contacts.values(self.cid,'email'),['one@example.com','three@example.com']);self.assertEqual(self.app.contacts.values(self.cid,'whatsapp'),[])
 def test_customer_state_blocks_all_contacts(self):
  mid=self.email();self.app.customer_state(self.cid,'stopped')
  with self.assertRaises(ValueError):self.app.contacts.prepare(mid)
 def test_invalid_address_does_not_partially_save_customer(self):
  with self.assertRaises(ValueError):self.app.save_customer(dict(id=self.cid,name='Bad edit',email='one@example.com',emails=['invalid']))
  self.assertEqual(self.app.store.rows('SELECT name FROM customers WHERE id=?',(self.cid,))[0]['name'],'Contact QA')
 def test_multiple_emails_in_import(self):
  r=self.app.import_csv('公司名称,邮箱,主题,英文正文\nImported,"first@example.com;second@example.com",Hello,Approved body')
  self.assertFalse(r['errors']);cid=self.app.store.rows("SELECT id FROM customers WHERE name='Imported'")[0]['id'];self.assertEqual(len(self.app.contacts.values(cid,'email')),2)

if __name__=='__main__':unittest.main()
