import json, shutil, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from app import App, DEFAULT_BOOK
from whatsapp import WhatsApp, number
from excel_sync import read_template

class FakeBridge:
    def __init__(self):self.account='8613800000000';self.status='ready';self.calls=[];self.result={'status':'submitted','remote_id':'fake-message-1'}
    def state(self):return {'status':self.status,'account':self.account,'qr':'','error':''}
    def request(self,op,data,**kwargs):
        if op=='check':return {'account':self.account,'number':data['number'],'registration':'registered'}
        self.calls.append((op,data))
        if isinstance(self.result,Exception):raise self.result
        return self.result

class WhatsAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.book=self.root/'test.xlsx';shutil.copyfile(DEFAULT_BOOK,self.book)
        self.app=App(self.root/'data');self.app.cfg['workbook']=str(self.book);self.fake=FakeBridge();self.app.wa=WhatsApp(self.app,self.fake)
        self.cid=self.app.save_customer({'name':'Example Engineering','email':'buyer@example.com','phone':'+84 912 345 678'})
        self.flush=patch.object(self.app.excel,'flush',return_value={'synced':0});self.flush.start()
    def tearDown(self):self.flush.stop();self.tmp.cleanup()
    def draft(self,**kwargs):return self.app.wa.draft({'customer_id':self.cid,'recipient':'+84 912 345 678','body':'Hello Example Engineering Team, may I share our valve catalogue?','owner':'林柏江',**kwargs})
    def queued(self):
        mid=self.draft();self.app.wa.check_number(self.cid);self.app.wa.enqueue([mid]);self.app.wa.start(self.fake.account);return mid
    def row(self,mid):return self.app.store.rows('SELECT * FROM messages WHERE id=?',(mid,))[0]
    def test_phone_requires_explicit_single_international_number(self):
        self.assertEqual(number('0084 (912) 345-678'),'+84912345678')
        for bad in ('0912345678','+84 912345678 / +84 999999999','+84test','+000000000'):
            with self.assertRaises(ValueError):number(bad)
    def test_preflight_checks_do_not_send_or_write_communication(self):
        r=self.app.wa.check_number(self.cid);self.assertEqual(r['registration'],'registered');self.assertFalse(self.fake.calls);self.assertFalse(self.app.store.rows('SELECT * FROM events'))
    def test_unchecked_or_stale_number_never_sends(self):
        mid=self.draft();self.app.wa.enqueue([mid]);self.app.wa.start(self.fake.account);self.assertFalse(self.app.wa.send_one());self.assertFalse(self.fake.calls)
        self.app.wa.check_number(self.cid)
        with self.app.store.conn() as db:db.execute("UPDATE wa_number_checks SET checked_at='2000-01-01T00:00:00+00:00'")
        self.app.wa.start(self.fake.account);self.assertFalse(self.app.wa.send_one());self.assertFalse(self.fake.calls)
    def test_lookup_error_is_not_unregistered(self):
        with patch.object(self.fake,'request',side_effect=TimeoutError('network')):r=self.app.wa.check_number(self.cid)
        self.assertEqual(r['registration'],'error');self.assertFalse(self.app.store.rows('SELECT * FROM events'))
    def test_draft_and_connect_do_not_send(self):
        self.draft();self.assertFalse(self.app.wa.send_one());self.assertFalse(self.fake.calls);self.assertFalse(self.app.store.rows('SELECT * FROM events'))
    def test_smtp_never_sends_whatsapp_queue(self):
        self.queued();self.app.running=True;self.app.cfg.update(hour_start=0,hour_end=24,weekdays=list(range(7)))
        self.assertFalse(self.app.send_one());self.assertFalse(self.fake.calls)
    def test_wrong_channel_endpoints_reject(self):
        mid=self.draft()
        with self.assertRaises(ValueError):self.app.queue([mid])
        email=self.app.save_draft({'customer_id':self.cid,'body':'Hello','subject':'Test'})
        with self.assertRaises(ValueError):self.app.wa.enqueue([email])
    def test_duplicate_prevented(self):
        mid=self.queued();dup=self.draft()
        with self.assertRaises(ValueError):self.app.wa.enqueue([dup])
        self.app.wa.send_one();self.assertEqual(self.row(mid)['status'],'submitted');self.app.wa.send_one();self.assertEqual(len(self.fake.calls),1)
    def test_account_change_cannot_send(self):
        mid=self.queued();self.fake.account='8613900000000';self.app.wa.send_one();self.assertFalse(self.fake.calls);self.assertFalse(self.app.wa.running);self.assertEqual(self.row(mid)['status'],'queued')
    def test_exact_queue_is_checked_by_backend(self):
        mid=self.draft();self.app.wa.enqueue([mid])
        with self.assertRaises(ValueError):self.app.wa.start(self.fake.account,['wrong-id'])
        self.assertFalse(self.app.wa.running);self.app.wa.start(self.fake.account,[mid]);self.assertTrue(self.app.wa.running)
        with self.assertRaises(ValueError):self.app.wa.enqueue([self.draft(body='Another message')])
    def test_timeout_is_uncertain_and_never_retried(self):
        mid=self.queued();self.fake.result=TimeoutError('response lost');self.app.wa.send_one();self.assertEqual(self.row(mid)['status'],'uncertain');self.assertFalse(self.app.wa.running)
        self.app.wa.send_one();self.assertEqual(len(self.fake.calls),1)
    def test_invalid_account_records_failure(self):
        mid=self.queued();self.fake.result={'status':'failed','error':'No WhatsApp account'};self.app.wa.send_one();self.assertEqual(self.row(mid)['status'],'failed');self.assertFalse(self.app.wa.running)
    def test_disconnect_and_customer_stop(self):
        self.queued();self.fake.status='disconnected';self.app.wa.send_one();self.assertFalse(self.fake.calls)
        self.app.customer_state(self.cid,'stopped');self.assertFalse(self.app.store.rows("SELECT id FROM messages WHERE status='queued'"))
    def test_pending_excel_blocks_send(self):
        mid=self.queued()
        with self.app.store.conn() as db:self.app.event(db,self.row(mid),'uncertain',{'channel':'whatsapp'})
        self.app.wa.send_one();self.assertFalse(self.fake.calls);self.assertFalse(self.app.wa.running)
    def test_receipt_pending_is_flushed_before_next_send(self):
        mid=self.queued()
        with self.app.store.conn() as db:self.app.event(db,self.row(mid),'submitted',{'channel':'whatsapp','receipt':True})
        def sync():
            with self.app.store.conn() as db:db.execute("UPDATE events SET sync_state='synced'")
            return {'synced':1}
        self.app.excel.flush.side_effect=sync
        self.assertTrue(self.app.wa.send_one());self.assertEqual(len(self.fake.calls),1)
    def test_old_synced_reply_does_not_stop_new_message(self):
        mid=self.queued();self.app.wa.send_one()
        self.app.wa.incoming.put({'event':'incoming','number':'84912345678','id':'old-1','account':self.fake.account,'timestamp':1,'body':'Old reply'})
        self.app.wa.drain();self.assertFalse(self.app.store.rows('SELECT * FROM inbound'))
    def test_reply_cancels_future_and_is_idempotent(self):
        mid=self.queued();self.app.wa.send_one();self.app.wa.pause();future=self.draft(body='A later followup');self.app.wa.enqueue([future])
        event={'event':'incoming','number':'84912345678','id':'incoming-1','account':self.fake.account,'body':'Please send details'}
        self.app.wa.incoming.put(event);self.app.wa.incoming.put(event);self.app.wa.drain()
        self.assertEqual(self.row(future)['status'],'cancelled');self.assertEqual(len(self.app.store.rows("SELECT * FROM events WHERE kind='reply'")),1)
        self.app.wa.incoming.put({**event,'id':'unrelated','number':'84999999999'});self.app.wa.drain();self.assertEqual(len(self.app.store.rows('SELECT * FROM inbound')),1)
    def test_restart_recovers_whatsapp_sending_without_resend(self):
        mid=self.draft()
        with self.app.store.conn() as db:db.execute("UPDATE messages SET status='sending' WHERE id=?",(mid,))
        again=App(self.root/'data');self.assertEqual(again.store.rows('SELECT status FROM messages WHERE id=?',(mid,))[0]['status'],'uncertain');self.assertFalse(again.wa.running)
        self.assertEqual(json.loads(again.store.rows('SELECT details FROM events')[0]['details'])['channel'],'whatsapp')
    def test_real_excel_channel_receipts_and_email_preservation(self):
        self.flush.stop()
        email=self.app.save_draft({'customer_id':self.cid,'body':'Email example','subject':'Existing email'})
        with self.app.store.conn() as db:self.app.event(db,self.row(email),'submitted')
        self.app.excel.flush();mid=self.queued();self.app.wa.send_one()
        snap=read_template(self.book);self.assertEqual(snap.rows['跟进记录'][9][6],'邮箱');self.assertEqual(snap.rows['跟进记录'][10][6],'WhatsApp');original_date=snap.rows['跟进记录'][10][3]
        self.assertTrue(any(v.get(7)=='+84912345678' for v in snap.rows['联系人'].values()))
        for ack in (2,3,1):self.app.wa.incoming.put({'event':'ack','message_id':'fake-message-1','ack':ack,'account':self.fake.account})
        self.app.wa.drain();self.app.excel.flush();snap=read_template(self.book)
        self.assertEqual(snap.summary()['log_rows'],2);self.assertEqual(snap.rows['跟进记录'][10][13],'WhatsApp已读');self.assertEqual(snap.rows['跟进记录'][10][3],original_date)
        self.assertEqual(snap.rows['跟进记录'][9][6],'邮箱')
        dest=Path(__file__).resolve().parents[1]/'data/qa/whatsapp-test.xlsx';dest.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(self.book,dest)

if __name__=='__main__':unittest.main()
