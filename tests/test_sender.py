import hashlib,json,os,shutil,smtplib,tempfile,threading,unittest,urllib.request,urllib.error,zipfile
from datetime import datetime,timezone,timedelta
from email.message import EmailMessage
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch
from app import App,DEFAULT_BOOK,SMTPTransport,ProtectedSecrets,make_handler
from excel_sync import read_template,NS
from http.server import ThreadingHTTPServer

class Accepted:
 calls=[]
 phase='connect'
 def send(self,msg,cfg,password,attachments,can_send):
  assert can_send();self.phase='accepted';self.calls.append(msg['message_id'])
class Uncertain:
 phase='connect'
 def send(self,*args):self.phase='data';raise TimeoutError('response lost')
class Rejected:
 phase='connect'
 def send(self,*args):self.phase='data';raise smtplib.SMTPRecipientsRefused({'buyer@example.com':(550,b'not found')})

class SenderTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.original_hash=hashlib.sha256(Path(DEFAULT_BOOK).read_bytes()).hexdigest()
 @classmethod
 def tearDownClass(cls):assert cls.original_hash==hashlib.sha256(Path(DEFAULT_BOOK).read_bytes()).hexdigest(),'原始模板被修改'
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.book=self.root/'客户跟进.xlsx';shutil.copyfile(DEFAULT_BOOK,self.book)
  self.app=App(self.root/'data',Accepted);self.app.cfg.update(workbook=str(self.book),hour_start=0,hour_end=24,weekdays=list(range(7)),daily_limit=20,interval_seconds=30)
  self.app.password='dummy-test-not-real';Accepted.calls=[]
  self.cid=self.app.save_customer({'code':'TEST0001','name':'Example Engineering','country':'越南','email':'buyer@example.com'})
 def tearDown(self):self.temp.cleanup()
 def draft(self,**extra):return self.app.save_draft({'customer_id':self.cid,'recipient':'buyer@example.com','subject':'Valve options','body':'Dear Example Engineering Team,\nWater circuit valves.','cn':'中文不应发送','owner':'林柏江',**extra})
 def queue(self,**extra):
  mid=self.draft(**extra);self.app.queue([mid]);self.app.running=True;return mid
 def test_startup_paused_and_seed_not_auto_send(self):
  self.assertFalse(self.app.running);r=self.app.import_csv((Path(__file__).resolve().parents[1]/'assets'/'胡志明市工程客户.csv').read_text(encoding='utf-8-sig'))
  self.assertEqual(r['imported'],26);self.assertFalse(r['errors']);self.assertFalse(self.app.store.rows("SELECT * FROM messages WHERE status<>'draft'"));self.assertEqual(len(self.app.store.rows('SELECT * FROM messages')),24)
  self.app.import_csv((Path(__file__).resolve().parents[1]/'assets'/'胡志明市工程客户.csv').read_text(encoding='utf-8-sig'));self.assertEqual(len(self.app.store.rows('SELECT * FROM messages')),24)
 def test_accepted_then_excel_and_idempotent_replay(self):
  mid=self.queue();self.assertTrue(self.app.send_one());self.assertEqual(len(Accepted.calls),1)
  snap=read_template(self.book);self.assertEqual(snap.rows['跟进记录'][9][13],'已提交发送服务');self.assertEqual(snap.rows['跟进记录'][9][9],'未回复');self.assertEqual(snap.rows['客户总表'][9][9],'已联系')
  self.assertIn('林柏江',snap.rows['跟进记录'][9].values());self.assertTrue(snap.formulas['跟进记录']['B9']);self.assertFalse(self.app.store.rows("SELECT id FROM events WHERE sync_state='pending'"))
  with self.app.store.conn() as db:db.execute("UPDATE events SET sync_state='pending'")
  self.app.excel.flush();self.assertEqual(read_template(self.book).summary()['log_rows'],1);self.assertEqual(len(Accepted.calls),1)
  with zipfile.ZipFile(self.book) as z:
   tables=[ET.fromstring(z.read(x)) for x in z.namelist() if x.startswith('xl/tables/') and x.endswith('.xml')]
   logs=[t for t in tables if any(x.attrib.get('name')=='消息编号' for x in t.findall('m:tableColumns/m:tableColumn',NS))]
   self.assertEqual(len(logs),1);self.assertEqual(logs[0].attrib['ref'],'A8:N208')
   sheet=ET.fromstring(z.read('xl/worksheets/sheet3.xml'));self.assertTrue(sheet.findall('m:hyperlinks/m:hyperlink',NS))
 def test_duplicate_and_blocked_customers(self):
  self.queue();dup=self.draft()
  with self.assertRaises(ValueError):self.app.queue([dup])
  self.app.customer_state(self.cid,'stopped');self.assertFalse(self.app.store.rows("SELECT id FROM messages WHERE status='queued'"))
  with self.assertRaises(ValueError):self.app.queue([dup])
  self.app.save_customer({'name':'Example Engineering','country':'越南','email':'buyer@example.com'});self.assertEqual(self.app.store.rows('SELECT state FROM customers WHERE id=?',(self.cid,))[0]['state'],'stopped')
 def test_unknown_outcome_never_retries_after_restart(self):
  self.app.transport_factory=Uncertain;mid=self.queue();self.app.send_one()
  self.assertEqual(self.app.store.rows('SELECT status FROM messages WHERE id=?',(mid,))[0]['status'],'uncertain');self.assertFalse(self.app.running)
  self.app.running=True;self.app.store.set('last_attempt','');self.assertFalse(self.app.send_one())
  with self.app.store.conn() as db:db.execute("UPDATE messages SET status='sending' WHERE id=?",(mid,))
  restarted=App(self.root/'data',Accepted);self.assertFalse(restarted.running);self.assertEqual(restarted.store.rows('SELECT status FROM messages WHERE id=?',(mid,))[0]['status'],'uncertain')
 def test_failed_send_is_logged_not_contacted(self):
  self.app.transport_factory=Rejected;self.queue();self.app.send_one();snap=read_template(self.book)
  self.assertEqual(snap.rows['跟进记录'][9][13],'发送失败');self.assertEqual(snap.rows['客户总表'][9][9],'待开发');self.assertFalse(snap.rows['客户总表'][9].get(13))
 def test_recipient_rejected_continues_other_company_address(self):
  self.app.save_customer({'id':self.cid,'name':'Example Engineering','country':'越南','email':'buyer@example.com','emails':['other@example.com']})
  batch=self.app.contacts.prepare(self.draft());self.app.queue(batch['ids']);self.app.running=True
  transports=iter([Rejected(),Accepted()]);self.app.transport_factory=lambda:next(transports)
  self.assertTrue(self.app.send_one());self.assertTrue(self.app.running)
  self.assertTrue(self.app.send_one(datetime.now(timezone.utc)+timedelta(seconds=35)));self.assertEqual(len(Accepted.calls),1)
 def test_excel_locked_keeps_pending_and_does_not_resend(self):
  mid=self.queue();lock=self.book.with_name('~$'+self.book.name);lock.write_text('excel open')
  self.app.send_one();self.assertEqual(len(Accepted.calls),1);self.assertFalse(self.app.running);self.assertTrue(self.app.store.rows("SELECT id FROM events WHERE sync_state='pending'"))
  lock.unlink();self.app.excel.flush();self.assertEqual(read_template(self.book).summary()['log_rows'],1);self.assertEqual(len(Accepted.calls),1)
 def test_reply_stops_all_customer_followups_and_preserves_stop(self):
  self.app.cfg['imap_enabled']=True;mid=self.queue(followup_days=3,followup_body='Follow up');self.app.send_one()
  msg=self.app.store.rows('SELECT * FROM messages WHERE id=?',(mid,))[0];self.assertEqual(len(self.app.store.rows("SELECT id FROM messages WHERE status='queued'")),1)
  reply=EmailMessage();reply['From']='buyer@example.com';reply['To']='friesgoglobal@gmail.com';reply['Subject']='Re: Valve options';reply['In-Reply-To']=msg['message_id'];reply['Message-ID']='<reply@example.com>';reply.set_content('Please send specifications.')
  self.assertTrue(self.app.record_inbound(reply.as_bytes(),'mailbox:1'));self.assertFalse(self.app.record_inbound(reply.as_bytes(),'mailbox:1'));self.app.excel.flush()
  self.assertFalse(self.app.store.rows("SELECT id FROM messages WHERE status='queued'"));self.assertEqual(self.app.store.rows('SELECT state FROM customers WHERE id=?',(self.cid,))[0]['state'],'replied');self.assertEqual(read_template(self.book).rows['客户总表'][9][9],'已回复')
  self.app.customer_state(self.cid,'stopped');self.app.record_inbound(reply.as_bytes(),'mailbox:2');self.assertEqual(self.app.store.rows('SELECT state FROM customers WHERE id=?',(self.cid,))[0]['state'],'stopped')
 def test_auto_reply_does_not_become_human_reply(self):
  mid=self.queue();self.app.send_one();m=self.app.store.rows('SELECT * FROM messages WHERE id=?',(mid,))[0]
  mail=EmailMessage();mail['In-Reply-To']=m['message_id'];mail['Auto-Submitted']='auto-replied';mail.set_content('Out of office')
  self.app.record_inbound(mail.as_bytes(),'auto:1');self.assertEqual(self.app.store.rows('SELECT state FROM customers WHERE id=?',(self.cid,))[0]['state'],'active')
 def test_time_window_and_cap_are_enforced(self):
  self.queue();at=datetime.now(timezone.utc);local=at.astimezone(__import__('zoneinfo').ZoneInfo(self.app.cfg['timezone']))
  self.app.cfg['weekdays']=[(local.weekday()+1)%7];self.assertFalse(self.app.send_one(at));self.assertFalse(Accepted.calls)
  self.app.cfg['weekdays']=list(range(7));self.app.cfg['daily_limit']=1;self.app.send_one(at)
  self.queue(subject='Different reviewed email');self.app.store.set('last_attempt','');self.assertFalse(self.app.send_one());self.assertEqual(len(Accepted.calls),1)
 def test_header_injection_and_unresolved_template(self):
  with self.assertRaises(ValueError):self.draft(recipient='buyer@example.com\nBcc:evil@example.com')
  with self.assertRaises(ValueError):self.draft(subject='X\r\nBcc: x')
  with self.assertRaises(ValueError):self.draft(body='Dear {{company}}')
 def test_smtp_mime_attachments_and_quit_error(self):
  attachment=self.root/'catalogue.pdf';attachment.write_bytes(b'%PDF-TEST')
  captured=[]
  class Connection:
   def send_message(self,mail,**kw):captured.append((mail,kw));return {}
   def quit(self):raise OSError('quit disconnected after acceptance')
   def close(self):pass
  transport=SMTPTransport();mid=self.draft();msg=self.app.store.rows('SELECT * FROM messages WHERE id=?',(mid,))[0]
  with patch.object(transport,'connect',return_value=Connection()):transport.send(msg,self.app.cfg,'fake',[{'name':'catalogue.pdf','path':str(attachment)}],lambda:True)
  self.assertEqual(transport.phase,'accepted');mail,envelope=captured[0];self.assertEqual(envelope['to_addrs'],['buyer@example.com']);self.assertNotIn('中文不应发送',mail.as_string());self.assertEqual(list(mail.iter_attachments())[0].get_filename(),'catalogue.pdf')
 def test_readonly_book_prevents_start(self):
  if os.name!='nt':self.skipTest('Windows only')
  os.chmod(self.book,0o444)
  try:
   with self.assertRaises(ValueError):self.app.start()
   self.assertFalse(self.app.running)
  finally:os.chmod(self.book,0o666)
 def test_concurrent_workers_only_send_once(self):
  self.queue();threads=[threading.Thread(target=self.app.send_one) for _ in range(2)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(len(Accepted.calls),1)
 def test_followup_waits_for_fresh_reply_scan(self):
  self.app.cfg['imap_enabled']=True;mid=self.queue(followup_days=1,followup_body='Follow up');self.app.send_one();self.app.store.set('last_attempt','')
  with self.app.store.conn() as db:db.execute("UPDATE messages SET scheduled_at=? WHERE parent_id=?",(datetime.now(timezone.utc).isoformat(),mid))
  self.app.running=True;self.app.monitoring=True;self.assertFalse(self.app.send_one());self.assertEqual(len(Accepted.calls),1)
  self.app.last_poll=datetime.now(timezone.utc).isoformat();self.assertTrue(self.app.send_one());self.assertEqual(len(Accepted.calls),2)
 def test_excel_identity_conflict_blocks_send(self):
  self.queue();self.app.send_one()
  with self.app.store.conn() as db:db.execute('UPDATE customers SET name=? WHERE id=?',('Another Company',self.cid))
  self.queue(subject='New reviewed email');self.app.store.set('last_attempt','')
  with self.assertRaises(ValueError):self.app.send_one()
  self.assertEqual(len(Accepted.calls),1)
 def test_import_workbook_preserves_stopped_state(self):
  self.app.customer_state(self.cid,'stopped');self.app.excel.flush()
  self.assertEqual(list(read_template(self.book).import_customers())[0]['state'],'stopped')
  with self.app.store.conn() as db:db.execute("UPDATE customers SET state='active' WHERE id=?",(self.cid,))
  mid=self.queue()
  server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app));self.app.port=server.server_port
  threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/import-workbook',data=b'{}',headers={'X-FriesGo-Token':self.app.token,'Content-Type':'application/json'})
   result=json.load(urllib.request.urlopen(request));self.assertTrue(result['ok']);self.assertEqual(self.app.store.rows('SELECT state FROM customers WHERE id=?',(self.cid,))[0]['state'],'stopped')
   self.assertEqual(self.app.store.rows('SELECT status FROM messages WHERE id=?',(mid,))[0]['status'],'cancelled')
  finally:server.shutdown();server.server_close()
 def test_http_requires_csrf_and_rejects_bad_host(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app));self.app.port=server.server_port
  t=threading.Thread(target=server.serve_forever,daemon=True);t.start();base=f'http://127.0.0.1:{server.server_port}'
  try:
   d=json.load(urllib.request.urlopen(base+'/api/bootstrap'));self.assertNotIn('dummy-test-not-real',json.dumps(d))
   req=urllib.request.Request(base+'/api/start',data=b'{}',headers={'Content-Type':'application/json'})
   with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
   self.assertEqual(e.exception.code,403)
   req=urllib.request.Request(base+'/api/state',headers={'Host':'untrusted.example'})
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
  finally:server.shutdown();server.server_close()
 @unittest.skipUnless(os.name=='nt','Windows only')
 def test_password_dpapi_roundtrip(self):
  raw=b'fake-test-password';encrypted=ProtectedSecrets.transform(raw,True);self.assertNotIn(raw,encrypted);self.assertEqual(ProtectedSecrets.transform(encrypted,False),raw)
 def test_expand_beyond_200_and_preserve_other_sheets(self):
  before=read_template(self.book)
  with self.app.store.conn() as db:
   for i in range(201):
    m={'id':None,'customer_id':self.cid,'recipient':'buyer@example.com','subject':f'Historical record {i}','body':'Test copy only','owner':'林柏江','message_id':f'<test-{i}@example.com>'}
    self.app.event(db,m,'failed',{'error':'Simulated test, not sent'})
  for _ in range(3):self.app.excel.flush()
  after=read_template(self.book);self.assertEqual(after.summary()['log_rows'],201);self.assertEqual(after.capacity,408)
  self.assertIn('$408',after.formulas['跟进记录']['B209']);self.assertEqual(after.rows['跟进记录'][209][13],'发送失败')
  for sheet in ['询盘报价','样品记录','订单记录','填写说明']:
   for row,vals in before.rows[sheet].items():self.assertEqual(vals,after.rows[sheet].get(row,{}))
  with zipfile.ZipFile(self.book) as z:
   root=ET.fromstring(z.read('xl/worksheets/sheet3.xml'));dvs=root.findall('m:dataValidations/m:dataValidation',NS)
   self.assertTrue(any(x.attrib['sqref']=='D9:D408' for x in dvs))
  dest=Path(__file__).resolve().parents[1]/'data'/'qa'/'验证用跟进表.xlsx';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(self.book,dest)

if __name__=='__main__':unittest.main()
