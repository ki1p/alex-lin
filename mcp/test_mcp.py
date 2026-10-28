import asyncio,copy,importlib.util,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

spec=importlib.util.spec_from_file_location('friesgo_mcp_server',Path(__file__).with_name('server.py'));srv=importlib.util.module_from_spec(spec);spec.loader.exec_module(srv)
class MockAPI:
    def __init__(self):
        self.calls=[];self.s={'customers':[{'id':'c1','name':'Example Team','code':'TEST1','phone':'+84912345678','state':'active'}],
            'messages':[],'events':[],'pending_sync':0,'last_error':'','config':{'owner':'林柏江','secret_fixture':'never-return'},
            'whatsapp':{'status':'ready','account':'1234567890','qr':'SECRET_QR','running':False,'reason':'paused','settings':{},'number_checks':[
                {'customer_id':'c1','number':'+84912345678','account':'1234567890','registration':'registered','checked_at':datetime.now(timezone.utc).isoformat()}]}}
    def state(self):return copy.deepcopy(self.s)
    def post(self,path,data=None):
        self.calls.append((path,data))
        if path=='/api/wa/draft':
            self.s['messages'].append({**data,'channel':'whatsapp','status':'draft','wa_account':'','scheduled_at':data.get('scheduled_at',datetime.now(timezone.utc).isoformat())})
        return {'ok':True}

class GuardTests(unittest.TestCase):
    def setUp(self):self.api=MockAPI();self.p=patch.object(srv,'api',self.api);self.p.start()
    def tearDown(self):self.p.stop()
    def draft(self):return srv.whatsapp_prepare_message('c1','+84912345678','Hello Example Team','request-001')['message']['id']
    def queue(self):
        mid=self.draft();self.api.s['messages'][0].update(status='queued',wa_account='1234567890');return mid
    def test_status_excludes_qr_and_config(self):
        result=json.dumps(srv.whatsapp_status());self.assertNotIn('SECRET_QR',result);self.assertNotIn('never-return',result)
    def test_prepare_is_idempotent_and_never_starts(self):
        self.draft();self.draft();self.assertEqual(len(self.api.calls),1);self.assertEqual(self.api.calls[0][0],'/api/wa/draft')
    def test_request_key_cannot_overwrite_other_content(self):
        self.draft()
        with self.assertRaises(ValueError):srv.whatsapp_prepare_message('c1','+84912345678','Different content','request-001')
    def test_stopped_customer_cannot_prepare(self):
        self.api.s['customers'][0]['state']='stopped'
        with self.assertRaises(ValueError):self.draft()
    def test_unknown_cannot_requeue(self):
        mid=self.queue();self.api.s['messages'][0]['status']='uncertain'
        with self.assertRaises(ValueError):srv.whatsapp_queue_messages([mid])
    def test_start_rejects_account_mismatch(self):
        mid=self.queue()
        with self.assertRaises(ValueError):srv.whatsapp_start_sending([mid],'different')
    def test_start_rejects_unrequested_queue_member(self):
        mid=self.queue();self.api.s['messages'].append({**self.api.s['messages'][0],'id':'unexpected'})
        with self.assertRaises(ValueError):srv.whatsapp_start_sending([mid],'1234567890')
    def test_start_requires_unexpired_preflight(self):
        mid=self.queue();self.api.s['whatsapp']['number_checks'][0]['checked_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        with self.assertRaises(ValueError):srv.whatsapp_start_sending([mid],'1234567890')
    def test_exact_start_passes_expected_ids_to_backend(self):
        mid=self.queue();r=srv.whatsapp_start_sending([mid],'1234567890')
        self.assertTrue(r['started']);self.assertEqual(self.api.calls[-1],('/api/wa/start',{'account':'1234567890','expected_ids':[mid]}))
    def test_history_does_not_expose_email(self):
        self.api.s['messages'].append({'id':'email','channel':'email','body':'PRIVATE_EMAIL'})
        self.assertNotIn('PRIVATE_EMAIL',json.dumps(srv.whatsapp_history()))

async def protocol_smoke():
    params=StdioServerParameters(command=sys.executable,args=['-X','utf8',str(Path(__file__).with_name('server.py'))])
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            init=await session.initialize();listing=await session.list_tools()
            assert len(listing.tools)==11
            if '--connect' in sys.argv:
                connection=await session.call_tool('whatsapp_connect',{})
                assert not connection.isError, connection
            status=await session.call_tool('whatsapp_status',{})
            assert not status.isError
            result={'server':init.serverInfo.name,'tools':[t.name for t in listing.tools],'status':status.structuredContent}
            if status.structuredContent.get('workbench_running'):
                customers=await session.call_tool('whatsapp_list_customers',{'limit':1})
                history=await session.call_tool('whatsapp_history',{'limit':5})
                assert not customers.isError and not history.isError
                result.update(customers=customers.structuredContent['total'],whatsapp_records=history.structuredContent['total'])
            print(json.dumps(result,ensure_ascii=False))
    if result['status'].get('workbench_running'):
        await asyncio.sleep(1)
        assert srv.api.state()['version']=='whatsapp-1'
        print(json.dumps({'workbench_survived_mcp_exit':True}))

if __name__=='__main__':
    if '--smoke' in sys.argv:asyncio.run(protocol_smoke())
    else:unittest.main()
