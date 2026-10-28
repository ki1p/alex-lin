import json,tempfile,unittest
from pathlib import Path
from app import App
from website import Website,website_url

class FakeEgo:
    def __init__(self,result=None):self.calls=[];self.result=result or dict(status='filled',fields=[dict(label='Email',value='friesgoindustrial@gmail.com')])
    def run(self,job,profile,folder):
        self.calls.append((job,profile))
        if isinstance(self.result,Exception):
            if job['mode']=='submit':(folder/'submit-attempted').touch()
            raise self.result
        return self.result

class WebsiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App(Path(self.tmp.name));self.fake=FakeEgo();self.web=Website(self.app,self.fake);self.app.web=self.web
        self.cid=self.app.save_customer(dict(name='Example Engineering',website='https://example.com'))
    def tearDown(self):self.app.alive=False;self.tmp.cleanup()
    def draft(self,**d):return self.web.draft(dict(customer_id=self.cid,body='Hello, supply cooperation for PE pipes and valves.',**d))
    def task(self,mid):return self.app.store.rows('SELECT * FROM website_tasks WHERE id=?',(mid,))[0]
    def test_preview_has_no_email_events_and_uses_snapshotted_profile(self):
        mid=self.draft();self.web.enqueue([mid]);self.web.profile['email']='changed@example.com';self.web.running=True;self.web.run_one()
        self.assertEqual(self.task(mid)['status'],'filled');self.assertEqual(self.fake.calls[0][1]['email'],'friesgoindustrial@gmail.com')
        self.assertFalse(self.app.store.rows('SELECT * FROM messages'));self.assertFalse(self.app.store.rows('SELECT * FROM events'))
    def test_stopped_customers_cancel_tasks(self):
        mid=self.draft();self.web.enqueue([mid]);self.app.customer_state(self.cid,'stopped');self.web.running=True;self.web.run_one()
        self.assertFalse(self.fake.calls);self.assertEqual(self.task(mid)['status'],'cancelled')
    def test_duplicate_domain_and_body_blocked(self):
        a=self.draft();self.web.enqueue([a]);b=self.draft(url='https://www.example.com/contact')
        with self.assertRaises(ValueError):self.web.enqueue([b])
    def test_failed_submit_is_uncertain_never_retried(self):
        mid=self.draft();self.web.enqueue([mid],'submit');self.fake.result=TimeoutError('unknown response');self.web.running=True;self.web.run_one();self.web.run_one()
        self.assertEqual(self.task(mid)['status'],'uncertain');self.assertEqual(len(self.fake.calls),1)
    def test_preview_error_is_attention_not_submission(self):
        mid=self.draft();self.web.enqueue([mid]);self.fake.result=TimeoutError('timeout');self.web.running=True;self.web.run_one()
        self.assertEqual(self.task(mid)['status'],'needs_attention')
    def test_recovery_keeps_submit_uncertain_and_pauses(self):
        mid=self.draft();folder=self.web.root/mid;folder.mkdir();(folder/'submit-attempted').touch()
        with self.app.store.conn() as db:db.execute("UPDATE website_tasks SET status='running',mode='submit' WHERE id=?",(mid,))
        restarted=Website(self.app,self.fake);self.assertFalse(restarted.running);self.assertEqual(self.task(mid)['status'],'uncertain');self.assertTrue((folder/'cancel').exists())
    def test_preview_record_escapes_input(self):
        mid=self.web.draft(dict(customer_id=self.cid,body='<script>alert(1)</script>'))
        page=self.web.preview_html(mid).decode();self.assertIn('&lt;script&gt;',page);self.assertNotIn('<script>',page)
    def test_invalid_modes_and_urls(self):
        for value in ('file:///C:/secret','http://localhost/','http://127.0.0.1/','https://user:pass@example.com'):
            with self.assertRaises(ValueError):website_url(value)
        mid=self.draft()
        with self.assertRaises(ValueError):self.web.enqueue([mid],'unknown')
    def test_queue_batch_is_atomic(self):
        mid=self.draft()
        with self.assertRaises(ValueError):self.web.enqueue([mid,'missing'])
        self.assertEqual(self.task(mid)['status'],'draft')
    def test_smtp_does_not_see_website_tasks(self):
        self.web.enqueue([self.draft()],'submit');self.app.running=True
        self.assertFalse(self.app.send_one())

if __name__=='__main__':unittest.main()
