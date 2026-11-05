import copy,tempfile,unittest
from pathlib import Path
from app import App

class FakeSite:
 def __init__(self):self.accounts=[];self.states=[];self.messages={};self.jobs=[];self.events={};self.fail_after_message=False
 def snapshot(self):return copy.deepcopy(dict(accounts=self.accounts,states=self.states,contacts=[],jobs=[j for j in self.jobs if j['status']=='pending']))
 def __call__(self,payload):
  if payload is None:return self.snapshot()
  mapping={}
  for a in payload.get('accounts',[]):
   old=next((c for c in self.accounts if c['id']==a.get('remote_id') or c['name']==a['name']),None)
   if not old:
    old=dict(id='site-'+a['id'],name=a['name'],country=a.get('country',''),email=a.get('email',''),url=a.get('website',''));self.accounts.append(old);self.states.append(dict(account_id=old['id'],status='未联系'))
   mapping[a['id']]=old['id']
  for m in payload.get('messages',[]):self.messages[m['id']]=copy.deepcopy(m)
  if payload.get('messages') and self.fail_after_message:self.fail_after_message=False;raise TimeoutError('ack lost')
  for e in payload.get('events',[]):self.events[e['id']]=copy.deepcopy(e)
  for result in payload.get('job_results',[]):
   j=next(j for j in self.jobs if j['id']==result['id']);j.update(status='error' if result.get('error') else 'prepared',**result)
  return dict(mapping=mapping,**self.snapshot())

class BridgeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=App(Path(self.tmp.name));self.site=FakeSite();self.app.bridge.transport=self.site;self.app.bridge.enabled=True
  self.cid=self.app.save_customer(dict(name='Example Buyer',country='QA',email='one@example.com'))
  self.mid=self.app.save_draft(dict(customer_id=self.cid,subject='Example review',body='Reviewed actual text',recipient='one@example.com'))
 def tearDown(self):self.app.alive=False;self.tmp.cleanup()
 def test_sync_is_repeatable_and_does_not_queue_or_send(self):
  self.app.bridge.sync();self.app.bridge.sync();self.app.bridge.sync()
  self.assertEqual(len(self.site.accounts),1);self.assertEqual(len(self.site.messages),1)
  self.assertEqual(self.app.store.rows('SELECT status FROM messages')[0]['status'],'draft');self.assertFalse(self.app.running)
  self.assertFalse(self.app.store.rows('SELECT * FROM events'))
  self.assertEqual(self.app.bridge.summary['messages'],0)
 def test_lost_ack_replays_same_message_without_duplicate(self):
  self.site.fail_after_message=True
  with self.assertRaises(TimeoutError):self.app.bridge.sync()
  self.app.bridge.sync();self.assertEqual(len(self.site.messages),1);self.assertEqual(len(self.site.accounts),1)
 def test_website_stop_cancels_existing_queue(self):
  self.app.bridge.sync();self.site.states[0]['status']='停止联系'
  with self.app.store.conn() as db:db.execute("UPDATE messages SET status='queued' WHERE id=?",(self.mid,))
  self.app.bridge.sync()
  self.assertEqual(self.app.store.rows('SELECT state FROM customers')[0]['state'],'stopped')
  self.assertEqual(self.app.store.rows('SELECT status FROM messages')[0]['status'],'cancelled')
 def test_website_job_creates_exactly_one_draft_and_keeps_snapshot(self):
  self.app.bridge.sync();self.site.jobs=[dict(id='job-example',account_id=self.site.accounts[0]['id'],target_device_id=self.app.bridge.device,recipient='one@example.com',subject='Website reviewed subject',body='Frozen website text',cn='Chinese QA reference',status='pending')]
  self.app.bridge.sync();self.site.jobs[0]['status']='pending';self.app.bridge.sync()
  rows=self.app.store.rows('SELECT * FROM messages');self.assertEqual(len(rows),2)
  self.assertTrue(all(m['status']=='draft' for m in rows));self.assertEqual(rows[1]['body'],'Frozen website text')
 def test_old_local_stop_is_never_automatically_resumed(self):
  self.app.bridge.sync();self.app.customer_state(self.cid,'stopped');self.app.bridge.sync()
  self.assertEqual(self.app.store.rows('SELECT state FROM customers')[0]['state'],'stopped')
 def test_stale_connection_blocks_sending_before_transport(self):
  self.app.running=True;self.assertFalse(self.app.send_one());self.assertFalse(self.app.running)
  self.assertFalse(self.app.store.rows("SELECT * FROM messages WHERE status='submitted'"))
 def test_pull_new_customer_preserves_existing_local_contact_pool(self):
  self.app.bridge.sync();self.site.accounts[0]['email']='two@example.com';self.site.accounts.append(dict(id='new-remote',name='New Website Buyer',country='QA',email='new@example.com',url=''))
  self.app.bridge.sync();self.app.bridge.sync()
  self.assertEqual(len(self.app.store.rows('SELECT * FROM customers')),2)
  self.assertEqual(set(self.app.contacts.values(self.cid,'email')),{'one@example.com','two@example.com'})

if __name__=='__main__':unittest.main()
