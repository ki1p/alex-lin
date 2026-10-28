"""WhatsApp queue, isolated from SMTP. Local linked-device adapter over stdin/stdout."""
import json, os, queue, re, subprocess, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from excel_sync import read_template, NODE

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def number(value):
    value=str(value or '').strip()
    if not re.fullmatch(r'(?:\+|00)[0-9 ()-]+',value):
        raise ValueError('填写一个含国家区号的号码，例如 +84…；多个号码请分开核实。')
    value=re.sub(r'[ ()-]','',value)
    if value.startswith('00'):value='+'+value[2:]
    if not re.fullmatch(r'\+[1-9]\d{7,14}',value):raise ValueError('国际号码格式无效。')
    return value

class Bridge:
    def __init__(self,app,callback):
        self.app=app;self.callback=callback;self.proc=None;self.pending={};self.lock=threading.Lock();self.write_lock=threading.Lock()
        self.status='disconnected';self.account='';self.qr='';self.error=''
    def state(self):return dict(status=self.status,account=self.account,qr=self.qr,error=self.error)
    def connect(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                if self.status not in ('disconnected','error'):return
                self.proc.stdin.close();self.proc.wait(timeout=15)
            root=Path(__file__).parent;chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
            if not chrome.exists():raise ValueError('未找到Google Chrome，请安装后再连接。')
            if not (root/'wa-bridge/node_modules/whatsapp-web.js').is_dir():raise ValueError('WhatsApp依赖未安装，请运行wa-bridge中的npm install。')
            env={**os.environ,'FRIESGO_WA_DATA':str(self.app.data/'whatsapp'),'FRIESGO_CHROME':str(chrome)}
            log=open(self.app.data/'whatsapp-bridge.log','a',encoding='utf-8')
            self.proc=subprocess.Popen([str(NODE),str(root/'wa-bridge/bridge.cjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=log,text=True,encoding='utf-8',env=env,cwd=root/'wa-bridge',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            log.close();self.status='connecting';self.error='';self.qr=''
            threading.Thread(target=self._read,args=(self.proc,),daemon=True).start()
        self.request('connect',{},timeout=10)
    def _read(self,proc):
        try:
            for line in proc.stdout:
                try:d=json.loads(line)
                except ValueError:continue
                if d.get('id'):
                    with self.lock:waiter=self.pending.get(d['id'])
                    if waiter:waiter.put(d)
                elif d.get('event')=='state':
                    self.status=d['status'];self.account=d.get('account','');self.qr=d.get('qr','');self.error=d.get('error','')
                    self.callback(d)
                else:self.callback(d)
        finally:
            if self.proc is proc:
                self.status='disconnected';self.account='';self.qr='';self.callback({'event':'state','status':'disconnected'})
    def request(self,op,data,timeout=60):
        if not self.proc or self.proc.poll() is not None:raise ValueError('WhatsApp连接未启动。')
        rid=uuid.uuid4().hex;waiter=queue.Queue()
        with self.lock:self.pending[rid]=waiter
        try:
            with self.write_lock:self.proc.stdin.write(json.dumps({'id':rid,'op':op,**data},ensure_ascii=False)+'\n');self.proc.stdin.flush()
            try:r=waiter.get(timeout=timeout)
            except queue.Empty:raise TimeoutError('WhatsApp返回超时。请核实聊天记录，勿直接重发。')
            if r.get('error'):raise ValueError(r['error'])
            return r['result']
        finally:
            with self.lock:self.pending.pop(rid,None)
    def close(self):
        if self.proc and self.proc.poll() is None:
            try:self.proc.stdin.close()
            except OSError:pass

class WhatsApp:
    def __init__(self,app,bridge=None):
        self.app=app;self.lock=threading.RLock();self.running=False;self.reason='WhatsApp队列已暂停';self.incoming=queue.Queue()
        self.bridge=bridge or Bridge(app,self.incoming.put)
        self.settings={'daily_limit':20,'interval_seconds':120,**app.store.setting('wa_config',{})}
        with app.store.conn() as db:db.execute('CREATE TABLE IF NOT EXISTS wa_number_checks(customer_id TEXT NOT NULL,number TEXT NOT NULL,account TEXT NOT NULL,registration TEXT NOT NULL,checked_at TEXT NOT NULL,error TEXT NOT NULL,PRIMARY KEY(number,account))')
    def state(self):return {**self.bridge.state(),'running':self.running,'reason':self.reason,'settings':self.settings,'number_checks':self.app.store.rows('SELECT * FROM wa_number_checks ORDER BY checked_at DESC')}
    def check_number(self,cid,recipient=None):
        with self.lock:
            if self.running:raise ValueError('请先暂停WhatsApp发送，再检查号码。')
            rows=self.app.store.rows('SELECT phone FROM customers WHERE id=?',(cid,))
            if not rows:raise ValueError('客户不存在。')
            phone=number(recipient or rows[0]['phone']);bs=self.bridge.state()
            if bs['status']!='ready' or not bs['account']:
                diagnostics=self.bridge.request('diagnostics',{},timeout=10)
                if diagnostics.get('connection')!='CONNECTED' or not diagnostics.get('account'):raise ValueError('WhatsApp号码查询尚未就绪，未检查号码。')
                bs={**bs,'account':diagnostics['account']}
            result={'customer_id':cid,'number':phone,'account':bs['account'],'registration':'error','checked_at':now(),'error':''}
            try:
                r=self.bridge.request('check',{'number':phone,'account':bs['account']},timeout=25)
                if r.get('account')!=bs['account'] or r.get('number')!=phone or r.get('registration') not in ('registered','not_registered'):raise ValueError('号码检查返回不完整，未确认。')
                result['registration']=r['registration']
            except Exception as e:result['error']=str(e)[:500]
            with self.app.store.conn() as db:db.execute('INSERT OR REPLACE INTO wa_number_checks VALUES (?,?,?,?,?,?)',tuple(result[k] for k in ('customer_id','number','account','registration','checked_at','error')))
            return result
    def pause(self):self.running=False;self.reason='已暂停；正在提交的一条可能仍会完成'
    def configure(self,d):
        if self.running:raise ValueError('请先暂停WhatsApp队列。')
        cfg={k:int(d.get(k,self.settings[k])) for k in self.settings}
        if not 1<=cfg['daily_limit']<=100 or not 30<=cfg['interval_seconds']<=86400:raise ValueError('每日1–100条，间隔至少30秒。')
        self.settings=cfg;self.app.store.set('wa_config',cfg)
    def draft(self,d):
        from app import text, uid, subject_text, OWNERS, parse_time
        app=self.app;cid=d.get('customer_id');customers=app.store.rows('SELECT * FROM customers WHERE id=?',(cid,))
        if not customers:raise ValueError('客户不存在。')
        recipient=number(d.get('recipient'));body=text(d.get('body'),12000)
        if not body or re.search(r'\{\{.+?\}\}|\[Company Name\]',body):raise ValueError('请填写完整消息，替换占位内容。')
        owner=d.get('owner',app.cfg['owner'])
        if owner not in OWNERS:raise ValueError('业务员无效。')
        mid=d.get('id') or uid();schedule=parse_time(d.get('scheduled_at') or now()).isoformat()
        with self.lock,app.store.conn() as db:
            old=db.execute('SELECT * FROM messages WHERE id=?',(mid,)).fetchone()
            if old and (old['status']!='draft' or old['channel']!='whatsapp'):raise ValueError('只能编辑WhatsApp草稿。')
            values=(recipient,body,text(d.get('cn'),12000),owner,schedule)
            if old:db.execute('UPDATE messages SET recipient=?,body=?,cn=?,owner=?,scheduled_at=? WHERE id=?',(*values,mid))
            else:db.execute("INSERT INTO messages(id,customer_id,recipient,body,cn,owner,scheduled_at,subject,created_at,message_id,channel) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (mid,cid,*values,'WhatsApp · '+customers[0]['name'],now(),'wa:'+uid(),'whatsapp'))
            self.app.contacts.save(db,cid,[],[recipient],source='WhatsApp草稿')
        return mid
    def enqueue(self,ids):
        if not ids:raise ValueError('请选择已预览的消息。')
        account=self.bridge.state().get('account')
        if self.bridge.state()['status']!='ready' or not account:raise ValueError('先连接WhatsApp，确认发件号码后加入队列。')
        with self.lock,self.app.store.conn() as db:
            if self.running:raise ValueError('请先暂停WhatsApp队列，再添加消息。')
            db.execute('BEGIN IMMEDIATE')
            for mid in set(ids):
                m=db.execute("SELECT m.*,c.state FROM messages m JOIN customers c ON c.id=m.customer_id WHERE m.id=?",(mid,)).fetchone()
                if not m or m['channel']!='whatsapp' or m['status']!='draft' or m['state']!='active':raise ValueError('消息不是可发送的WhatsApp草稿，或客户已暂停/回复。')
                if db.execute("SELECT id FROM messages WHERE channel='whatsapp' AND id<>? AND recipient=? AND body=? AND status IN ('queued','sending','submitted','uncertain')",(mid,m['recipient'],m['body'])).fetchone():raise ValueError('已有相同消息在队列或发送记录中。')
                db.execute("UPDATE messages SET status='queued',wa_account=?,error='' WHERE id=?",(account,mid))
        return len(set(ids))
    def start(self,account,expected_ids=None):
        with self.lock:
            if self.bridge.state()['status']!='ready' or not account or self.bridge.state()['account']!=account:raise ValueError('WhatsApp账号已变化，请重新确认。')
            rows=self.app.store.rows("SELECT id,wa_account FROM messages WHERE channel='whatsapp' AND status='queued'")
            if expected_ids is not None and {r['id'] for r in rows}!=set(expected_ids):raise ValueError('待发送队列已变化，请重新核对具体消息。')
            if not rows:raise ValueError('没有待发送的WhatsApp消息。')
            if any(r['wa_account']!=account for r in rows):raise ValueError('队列绑定了不同账号，请取消后重新准备。')
            read_template(self.app.cfg['workbook']);self.app.excel.flush()
            if self.app.store.rows("SELECT id FROM events WHERE sync_state='pending'"):raise ValueError('先完成Excel补写。')
            self.running=True;self.reason='等待发送';self.app.last_error=''
    def emit(self,db,m,kind,extra=None,event_id=None):
        self.app.event(db,m,kind,{'channel':'whatsapp','remote_id':m.get('wa_remote_id',''),'delivery':m.get('wa_delivery',''),**(extra or {})},event_id)
    def send_one(self):
        from app import parse_time
        with self.lock,self.app.send_lock:
            if not self.running:return False
            app=self.app;bs=self.bridge.state()
            if bs['status']!='ready':self.pause();self.reason='连接已断开，队列暂停';return False
            if app.store.rows("SELECT id FROM events WHERE sync_state='pending'"):
                try:app.excel.flush()
                except Exception as e:self.pause();self.reason='Excel待补写：'+str(e);return False
                if app.store.rows("SELECT id FROM events WHERE sync_state='pending'"):
                    self.pause();self.reason='Excel有待补写记录，请补写后再启动';return False
            last=app.store.setting('wa_last_attempt','')
            if last and (datetime.now(timezone.utc)-parse_time(last)).total_seconds()<self.settings['interval_seconds']:
                self.reason='等待WhatsApp发送间隔';return False
            midnight=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
            if app.store.rows("SELECT COUNT(*) n FROM messages WHERE channel='whatsapp' AND attempted_at>=?",(midnight,))[0]['n']>=self.settings['daily_limit']:
                self.reason='已达WhatsApp每日上限（UTC）';return False
            snap=read_template(app.cfg['workbook'])
            rows=app.store.rows("SELECT m.*,c.state,c.code,c.name FROM messages m JOIN customers c ON c.id=m.customer_id WHERE m.channel='whatsapp' AND m.status='queued' AND m.scheduled_at<=? ORDER BY m.scheduled_at,m.created_at",(now(),))
            chosen=None
            with app.store.conn() as db:
                for m in rows:
                    if m['state']!='active' or snap.customer_stage(m['code'],m['name']) not in ('','待开发','已联系'):
                        db.execute("UPDATE messages SET status='cancelled',error='客户状态已变化' WHERE id=?",(m['id'],));continue
                    if m['wa_account']!=bs['account']:self.pause();self.reason='登录账号与队列不一致';return False
                    verified=app.store.rows("SELECT * FROM wa_number_checks WHERE number=? AND account=? AND registration='registered'",(m['recipient'],bs['account']))
                    if not verified or (datetime.now(timezone.utc)-parse_time(verified[0]['checked_at'])).total_seconds()>86400:
                        self.pause();self.reason='请先检查并确认号码已开通WhatsApp（检查24小时内有效）';return False
                    chosen=m;break
                if not chosen:
                    self.reason='没有到期消息'
                    if not app.store.rows("SELECT id FROM messages WHERE channel='whatsapp' AND status='queued'"):self.running=False
                    return False
                chosen['attempted_at']=now();db.execute("UPDATE messages SET status='sending',attempted_at=? WHERE id=?",(chosen['attempted_at'],chosen['id']))
            app.store.set('wa_last_attempt',chosen['attempted_at']);self.reason='正在发送：'+chosen['name']
            if not self.running:result={'status':'failed','error':'发送前已暂停，未调用WhatsApp。'}
            else:
                try:result=self.bridge.request('send',{'key':chosen['id'],'number':chosen['recipient'],'body':chosen['body'],'account':chosen['wa_account']})
                except Exception as e:result={'status':'uncertain','error':str(e)[:500]}
            status=result.get('status')
            if status not in ('submitted','failed','uncertain'):status='uncertain'
            chosen.update(submitted_at=now() if status=='submitted' else None,wa_remote_id=result.get('remote_id',''),wa_delivery='submitted' if status=='submitted' else '')
            with app.store.conn() as db:
                db.execute('UPDATE messages SET status=?,submitted_at=?,error=?,wa_remote_id=?,wa_delivery=? WHERE id=?',
                    (status,chosen['submitted_at'],result.get('error',''),chosen['wa_remote_id'],chosen['wa_delivery'],chosen['id']))
                self.emit(db,chosen,status,{'error':result.get('error','')})
            if status!='submitted':self.pause();self.reason='发送失败或结果待确认，请核实后再启动'
            try:app.excel.flush()
            except Exception as e:self.pause();self.reason='Excel待补写：'+str(e);app.last_error=self.reason
            return True
    def drain(self):
        for _ in range(200):
            try:e=self.incoming.get_nowait()
            except queue.Empty:break
            if e.get('event')=='state':
                if e.get('status')!='ready' and self.running:self.pause();self.reason='WhatsApp连接变化，队列已暂停'
                continue
            app=self.app
            if e.get('event')=='ack':
                rows=app.store.rows("SELECT * FROM messages WHERE channel='whatsapp' AND wa_remote_id=? AND wa_account=? AND status='submitted'",(e.get('message_id'),e.get('account')))
                if not rows:continue
                m=rows[0];rank={'submitted':0,'sent':1,'delivered':2,'read':3};ack=int(e.get('ack',0))
                level='failed_delivery' if ack<0 else {1:'sent',2:'delivered',3:'read',4:'read'}.get(ack,'submitted')
                if level!='failed_delivery' and rank.get(level,0)<=rank.get(m['wa_delivery'],0):continue
                m['wa_delivery']=level
                if level=='failed_delivery':self.pause();self.reason='收到投递失败回执，请核实后继续'
                with app.send_lock,app.store.conn() as db:
                    db.execute('UPDATE messages SET wa_delivery=? WHERE id=?',(level,m['id']))
                    self.emit(db,m,'submitted',{'receipt':True},event_id='waack:'+m['id']+':'+level)
            elif e.get('event')=='incoming':
                try:phone=number('+'+str(e['number']))
                except (ValueError,KeyError):continue
                rows=app.store.rows("SELECT * FROM messages WHERE channel='whatsapp' AND recipient=? AND wa_account=? AND status='submitted' ORDER BY submitted_at DESC LIMIT 1",(phone,e.get('account')))
                if not rows:continue
                m=rows[0];key='wa-in:'+e['id']
                if e.get('timestamp') and m.get('submitted_at'):
                    if float(e['timestamp'])<datetime.fromisoformat(m['submitted_at']).timestamp():continue
                with app.send_lock,app.store.conn() as db:
                    if db.execute('SELECT 1 FROM inbound WHERE key=?',(key,)).fetchone():continue
                    db.execute('INSERT INTO inbound VALUES (?,?)',(key,now()))
                    db.execute("UPDATE customers SET state='replied' WHERE id=? AND state NOT IN ('paused','stopped')",(m['customer_id'],))
                    db.execute("UPDATE messages SET status='cancelled',error='收到WhatsApp回复，停止后续自动发送' WHERE customer_id=? AND status='queued'",(m['customer_id'],))
                    self.emit(db,m,'reply',{'inbound_key':key,'reply_from':phone,'reply_subject':'WhatsApp回复','reply_body':str(e.get('body',''))[:12000]})
    def resolve(self,mid,outcome):
        if outcome not in ('submitted','failed'):raise ValueError('核对结果无效')
        with self.lock,self.app.store.conn() as db:
            r=db.execute("SELECT * FROM messages WHERE id=? AND channel='whatsapp' AND status='uncertain'",(mid,)).fetchone()
            if not r:raise ValueError('仅核对结果待确认的WhatsApp消息')
            m=dict(r);m['submitted_at']=now() if outcome=='submitted' else None
            db.execute('UPDATE messages SET status=?,submitted_at=?,error=? WHERE id=?',(outcome,m['submitted_at'],'用户已核对WhatsApp聊天记录',mid))
            self.emit(db,m,outcome,{'error':'用户已核对WhatsApp聊天记录；未自动重发'})
