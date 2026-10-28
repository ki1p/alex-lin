"""FriesGo local mail workbench. Standard library only; never sends at startup."""
from __future__ import annotations
import base64, csv, ctypes, hashlib, hmac, imaplib, io, json, mimetypes, os, re
import secrets, shutil, smtplib, socket, sqlite3, ssl, sys, threading, time, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formataddr, format_datetime, parseaddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo
from excel_sync import ExcelSync, read_template

ROOT = Path(__file__).resolve().parent
DEFAULT_BOOK = 'E:/Document/Tengxun/WeChat/Document/xwechat_files/wxid_9an6z3uh5fwy22_b428/msg/file/2026-10/FriesGo-海外客户开发跟进空白模板.xlsx'
OWNERS = ['余佳林', '吴皓东', '林柏江', '赵国栋']
DEFAULTS = dict(sender_email='friesgoglobal@gmail.com', sender_name='BaiJiang Lin | FriesGo Global',
    smtp_host='smtp.gmail.com', smtp_port=465, smtp_security='ssl', smtp_user='friesgoglobal@gmail.com',
    imap_host='imap.gmail.com', imap_port=993, imap_user='friesgoglobal@gmail.com', imap_enabled=False,
    workbook=DEFAULT_BOOK, daily_limit=20, interval_seconds=120, timezone='Asia/Ho_Chi_Minh',
    hour_start=9, hour_end=18, weekdays=[0,1,2,3,4], owner='林柏江', remember_password=False)
ACTIVE = ('queued','sending')
BLOCKED = ('replied','paused','stopped','bounced')
def now_iso(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def uid(): return uuid.uuid4().hex
def json_dump(obj): return json.dumps(obj, ensure_ascii=False)
def valid_email(value):
    value = str(value or '').strip()
    if len(value)>254 or re.search(r'[\r\n\x00,;<>\s]',value) or not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}',value):
        raise ValueError('请填写一个完整邮箱地址；每封邮件只发给一个收件人。')
    return value.lower()
def text(value, limit=300):
    s=str(value or '').strip()
    if '\x00' in s or len(s)>limit: raise ValueError(f'内容过长，最多 {limit} 个字符。')
    return s
def subject_text(s):
    s=text(s,300)
    if not s or '\r' in s or '\n' in s: raise ValueError('邮件主题不能为空或包含换行。')
    return s
def parse_time(s):
    dt=datetime.fromisoformat(s.replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('发送时间必须包含时区。')
    return dt.astimezone(timezone.utc)
def redact_error(exc, passwords=()):
    s=str(exc)[:600]
    for p in passwords:
        if p: s=s.replace(p,'[已隐藏]')
    return s

class ProtectedSecrets:
    """Windows user-bound DPAPI; otherwise session-only."""
    class Blob(ctypes.Structure):
        _fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_char))]
    @classmethod
    def transform(cls, raw: bytes, encrypt: bool):
        if os.name!='nt': raise ValueError('持久保存密码只支持Windows；其他系统可仅在本次运行中使用。')
        buf=ctypes.create_string_buffer(raw); src=cls.Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char))); out=cls.Blob()
        fn=ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
        if not fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out)): raise OSError('Windows凭据保护失败。')
        try:return ctypes.string_at(out.data,out.size)
        finally:ctypes.windll.kernel32.LocalFree(out.data)

class Store:
    def __init__(self, path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.conn() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS customers (id TEXT PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,
              country TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',website TEXT NOT NULL DEFAULT '',
              state TEXT NOT NULL DEFAULT 'active',note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,recipient TEXT NOT NULL,
              subject TEXT NOT NULL,body TEXT NOT NULL,cn TEXT NOT NULL DEFAULT '',owner TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',
              scheduled_at TEXT NOT NULL,created_at TEXT NOT NULL,attempted_at TEXT,submitted_at TEXT,
              message_id TEXT UNIQUE NOT NULL,parent_id TEXT UNIQUE,error TEXT NOT NULL DEFAULT '',
              attachments TEXT NOT NULL DEFAULT '[]',followup_days INTEGER NOT NULL DEFAULT 0,followup_body TEXT NOT NULL DEFAULT '',
              FOREIGN KEY(customer_id) REFERENCES customers(id));
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,message_id TEXT,customer_id TEXT NOT NULL,
              kind TEXT NOT NULL,created_at TEXT NOT NULL,details TEXT NOT NULL,sync_state TEXT NOT NULL DEFAULT 'pending',sync_error TEXT NOT NULL DEFAULT '',
              FOREIGN KEY(customer_id) REFERENCES customers(id));
            CREATE TABLE IF NOT EXISTS attachments (id TEXT PRIMARY KEY,name TEXT NOT NULL,path TEXT NOT NULL,size INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS inbound (key TEXT PRIMARY KEY,created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS queue_idx ON messages(status,scheduled_at);
            ''')
            columns={r['name'] for r in db.execute('PRAGMA table_info(messages)')}
            for col,definition in {'channel':"TEXT NOT NULL DEFAULT 'email'",'wa_account':"TEXT NOT NULL DEFAULT ''",'wa_remote_id':"TEXT NOT NULL DEFAULT ''",'wa_delivery':"TEXT NOT NULL DEFAULT ''"}.items():
                if col not in columns:db.execute(f'ALTER TABLE messages ADD COLUMN {col} {definition}')
    @contextmanager
    def conn(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        try:yield db;db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
    def rows(self,sql,args=()):
        with self.conn() as db:return [dict(r) for r in db.execute(sql,args)]
    def setting(self,key,default=None):
        r=self.rows('SELECT value FROM settings WHERE key=?',(key,));return json.loads(r[0]['value']) if r else default
    def set(self,key,value):
        with self.conn() as db:db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json_dump(value)))

class SMTPTransport:
    def __init__(self):self.phase='connect'
    def connect(self,cfg,password):
        ctx=ssl.create_default_context()
        if cfg['smtp_security']=='ssl': s=smtplib.SMTP_SSL(cfg['smtp_host'],cfg['smtp_port'],timeout=30,context=ctx)
        else:
            s=smtplib.SMTP(cfg['smtp_host'],cfg['smtp_port'],timeout=30);s.ehlo();s.starttls(context=ctx);s.ehlo()
        try:
            self.phase='login';s.login(cfg['smtp_user'],password);return s
        except Exception:s.close();raise
    def send(self,msg,cfg,password,attachments,can_send):
        self.phase='connect';s=self.connect(cfg,password)
        try:
            if not can_send(): raise ValueError('发送已暂停。')
            mail=EmailMessage();mail['From']=formataddr((cfg['sender_name'],cfg['sender_email']))
            mail['To']=msg['recipient'];mail['Subject']=msg['subject'];mail['Date']=format_datetime(datetime.now(timezone.utc))
            mail['Message-ID']=msg['message_id'];mail['Reply-To']=cfg['sender_email']
            if msg.get('parent_message_id'):
                mail['In-Reply-To']=msg['parent_message_id'];mail['References']=msg['parent_message_id']
            mail.set_content(msg['body'])
            for item in attachments:
                mime=mimetypes.guess_type(item['name'])[0] or 'application/octet-stream';main,sub=mime.split('/',1)
                mail.add_attachment(Path(item['path']).read_bytes(),maintype=main,subtype=sub,filename=item['name'])
            self.phase='data';refused=s.send_message(mail,from_addr=cfg['sender_email'],to_addrs=[msg['recipient']])
            if refused:raise smtplib.SMTPRecipientsRefused(refused)
            self.phase='accepted'
        finally:
            try:s.quit()
            except Exception:s.close()

class App:
    def __init__(self,data_dir=None,transport_factory=SMTPTransport):
        self.data=Path(data_dir or ROOT/'data');self.data.mkdir(parents=True,exist_ok=True)
        self.store=Store(self.data/'friesgo.sqlite3');self.cfg={**DEFAULTS,**self.store.setting('config',{})}
        if not self.store.setting('config') and Path(DEFAULT_BOOK).is_file():
            working=(ROOT.parent/'outputs'/'01a1710d-684d-7fa2-98d1-0f1a906eb267'/'FriesGo-自动发送跟进工作表.xlsx') if self.data.resolve()==(ROOT/'data').resolve() else self.data/'跟进工作表.xlsx'
            working.parent.mkdir(parents=True,exist_ok=True)
            if not working.exists():shutil.copyfile(DEFAULT_BOOK,working)
            self.cfg['workbook']=str(working);self.store.set('config',self.cfg)
        self.password='';self.imap_password='';self.transport_factory=transport_factory
        self.running=False;self.monitoring=False;self.alive=True;self.token=secrets.token_urlsafe(32)
        self.port=8877;self.last_error='';self.last_poll='';self.reason='队列已暂停';self.send_lock=threading.RLock();self.poll_lock=threading.Lock()
        self.excel=ExcelSync(self);self._secret_file=self.data/'credentials.dpapi'
        if self._secret_file.exists() and self.cfg.get('remember_password'):
            try:
                sec=json.loads(ProtectedSecrets.transform(self._secret_file.read_bytes(),False));self.password=sec.get('smtp','');self.imap_password=sec.get('imap','')
            except Exception:self.last_error='已保存的邮箱凭据无法解密，请重新输入。'
        self.recover()
        from whatsapp import WhatsApp
        self.wa=WhatsApp(self)
        from contacts import Contacts
        self.contacts=Contacts(self)
        from website import Website
        self.web=Website(self)
    def config_public(self):return {**self.cfg,'password_saved':bool(self.password),'imap_password_saved':bool(self.imap_password or self.password)}
    def recover(self):
        with self.store.conn() as db:
            for m in db.execute("SELECT * FROM messages WHERE status='sending'").fetchall():
                db.execute("UPDATE messages SET status='uncertain',error=? WHERE id=?",('程序中断，发送结果待人工确认，不会自动重发。',m['id']))
                self.event(db,dict(m),'uncertain',{'error':'程序中断，结果待确认。'})
    def event(self,db,msg,kind,extra=None,event_id=None):
        detail={k:msg.get(k) for k in ('recipient','subject','body','cn','owner','message_id','submitted_at','attempted_at','followup_days','channel')}
        detail.update(extra or {});eid=event_id or uid()
        db.execute('INSERT OR IGNORE INTO events(id,message_id,customer_id,kind,created_at,details) VALUES (?,?,?,?,?,?)',(eid,msg['id'],msg['customer_id'],kind,now_iso(),json_dump(detail)))
    def save_config(self,changes):
        with self.send_lock,self.excel.lock:
            if self.running:raise ValueError('请先暂停发送，再修改设置。')
            if self.wa.running:raise ValueError('请先暂停WhatsApp发送，再修改邮箱和工作表设置。')
            if self.poll_lock.locked():raise ValueError('正在检查回复，请稍后保存设置。')
            cfg={**self.cfg,**{k:v for k,v in changes.items() if k in DEFAULTS}}
            cfg['sender_email']=valid_email(cfg['sender_email']);cfg['smtp_user']=text(cfg['smtp_user'],300)
            cfg['sender_name']=subject_text(cfg['sender_name']);cfg['imap_user']=text(cfg['imap_user'],300)
            for k in ['smtp_host','imap_host']:
                cfg[k]=text(cfg[k],250)
                if not re.fullmatch(r'[a-zA-Z0-9.-]+',cfg[k]):raise ValueError('邮箱服务器地址格式不正确。')
            for k in ['smtp_port','imap_port']:
                cfg[k]=int(cfg[k])
                if not 1<=cfg[k]<=65535:raise ValueError('端口超出范围。')
            for k,low,high in [('daily_limit',1,500),('interval_seconds',30,86400),('hour_start',0,23),('hour_end',1,24)]:
                cfg[k]=int(cfg[k])
                if not low<=cfg[k]<=high:raise ValueError(f'{k} 超出允许范围。')
            if cfg['hour_start']>=cfg['hour_end']:raise ValueError('结束时间需要晚于开始时间。')
            if cfg['smtp_security'] not in ['ssl','starttls']:raise ValueError('需要SSL或STARTTLS加密连接。')
            ZoneInfo(cfg['timezone']);cfg['weekdays']=sorted(set(int(d) for d in cfg['weekdays']))
            if not cfg['weekdays'] or any(x<0 or x>6 for x in cfg['weekdays']):raise ValueError('至少选择一个有效发送日。')
            if cfg['owner'] not in OWNERS:raise ValueError('业务员需与Excel下拉选项一致。')
            p=Path(cfg['workbook']).expanduser().resolve()
            if p.suffix.lower()!='.xlsx' or not p.is_file():raise ValueError('请选择现有的 .xlsx 跟进表路径。')
            cfg['workbook']=str(p);read_template(p)
            if getattr(p.stat(),'st_file_attributes',0)&1:raise ValueError('该Excel文件为只读，请另存为可编辑工作表后选择新路径。')
            cfg['remember_password']=bool(cfg['remember_password']);cfg['imap_enabled']=bool(cfg['imap_enabled'])
            newpass=changes.get('smtp_password') or self.password;newimap=changes.get('imap_password') or self.imap_password
            if changes.get('clear_password'):newpass='';newimap=''
            if cfg['remember_password']:
                protected=ProtectedSecrets.transform(json_dump({'smtp':newpass,'imap':newimap}).encode(),True)
                temp=self.data/'credentials.tmp';temp.write_bytes(protected);os.replace(temp,self._secret_file)
            elif self._secret_file.exists():self._secret_file.unlink()
            self.cfg=cfg;self.password=newpass;self.imap_password=newimap;self.store.set('config',cfg)
            if not cfg['imap_enabled']:self.monitoring=False
            return self.config_public()
    def save_customer(self,d):
        name=text(d.get('name'),200)
        if not name:raise ValueError('请填写公司名称。')
        from contacts import email_list,phone_list
        emails=email_list(d.get('email',''))+email_list(d.get('emails',[]))
        phones=phone_list(d.get('phone',''),False)+phone_list(d.get('whatsapp_numbers',[]))
        address=emails[0] if emails else ''
        code=text(d.get('code'),60);country=text(d.get('country'),100)
        if code and not re.fullmatch(r'[A-Za-z0-9_-]+',code):raise ValueError('客户编号只使用字母、数字、下划线或短横线。')
        with self.store.conn() as db:
            existing=db.execute('SELECT * FROM customers WHERE id=?',(d.get('id',''),)).fetchone()
            if not existing:
                if code:existing=db.execute('SELECT * FROM customers WHERE code=?',(code,)).fetchone()
                if not existing:existing=db.execute('SELECT * FROM customers WHERE lower(name)=lower(?) AND country=?',(name,country)).fetchone()
            cid=existing['id'] if existing else uid();code=existing['code'] if existing else code or 'FG'+uid()[:10].upper()
            website=text(d.get('website'),1000)
            if website and urlparse(website).scheme not in ('http','https'):raise ValueError('官网链接需以http://或https://开头。')
            if existing:
                db.execute('UPDATE customers SET name=?,country=?,email=?,phone=?,website=?,note=? WHERE id=?',(name,country,address,text(d.get('phone')),website,text(d.get('note'),4000),cid))
            else:db.execute('INSERT INTO customers(id,code,name,country,email,phone,website,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(cid,code,name,country,address,text(d.get('phone')),website,text(d.get('note'),4000),now_iso()))
            self.contacts.save(db,cid,list(dict.fromkeys(emails)),list(dict.fromkeys(phones)),replace_email='emails' in d,replace_phone='whatsapp_numbers' in d)
        return cid
    def save_draft(self,d):
        cid=d.get('customer_id');customer=self.store.rows('SELECT * FROM customers WHERE id=?',(cid,))
        if not customer:raise ValueError('请先选择客户。')
        recipient=valid_email(d.get('recipient') or customer[0]['email']);subject=subject_text(d.get('subject'));body=text(d.get('body'),24000)
        if not body:raise ValueError('请填写实际发送的正文。')
        if re.search(r'\{\{[^}]+\}\}|\[Company Name\]',body+subject):raise ValueError('请替换正文中的公司名称等占位内容。')
        cn=text(d.get('cn'),24000);owner=d.get('owner') or self.cfg['owner']
        if owner not in OWNERS:raise ValueError('业务员不在模板名单中。')
        schedule=parse_time(d.get('scheduled_at') or now_iso()).isoformat(timespec='seconds')
        days=int(d.get('followup_days',0));follow=text(d.get('followup_body'),24000)
        if days<0 or days>60:raise ValueError('跟进间隔需为0至60天。')
        if days and not follow:raise ValueError('请填写自动跟进信正文。')
        attachments=list(dict.fromkeys(d.get('attachments') or []));total=0
        for aid in attachments:
            a=self.store.rows('SELECT * FROM attachments WHERE id=?',(aid,))
            if not a or not Path(a[0]['path']).exists():raise ValueError('附件不存在，请重新上传。')
            total+=a[0]['size']
        if total>12*1024*1024:raise ValueError('单封附件总大小不能超过12MB。')
        mid=d.get('id') or uid()
        with self.store.conn() as db:
            old=db.execute('SELECT * FROM messages WHERE id=?',(mid,)).fetchone()
            if old and (old['status']!='draft' or old['channel']!='email'):raise ValueError('只允许编辑邮件草稿；队列中的内容已固定。')
            args=(recipient,subject,body,cn,owner,schedule,json_dump(attachments),days,follow)
            if old:db.execute('UPDATE messages SET recipient=?,subject=?,body=?,cn=?,owner=?,scheduled_at=?,attachments=?,followup_days=?,followup_body=? WHERE id=?',(*args,mid))
            else:db.execute('INSERT INTO messages(recipient,subject,body,cn,owner,scheduled_at,attachments,followup_days,followup_body,id,customer_id,created_at,message_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(*args,mid,cid,now_iso(),f'<{uid()}@friesgo.local>'))
            self.contacts.save(db,cid,[recipient],[],source='开发信草稿')
        return mid
    def queue(self,ids):
        if not ids:raise ValueError('请选择已预览的草稿。')
        read_template(Path(self.cfg['workbook']))
        with self.store.conn() as db:
            db.execute('BEGIN IMMEDIATE')
            for mid in list(dict.fromkeys(ids)):
                m=db.execute('SELECT m.*,c.state FROM messages m JOIN customers c ON m.customer_id=c.id WHERE m.id=?',(mid,)).fetchone()
                if not m or m['status']!='draft' or m['channel']!='email':raise ValueError('仅邮件草稿可加入邮件队列。')
                if m['state']!='active':raise ValueError('客户已回复、暂停、退信或停止联系，不能加入自动队列。')
                if m['followup_days'] and not self.cfg['imap_enabled']:raise ValueError('自动跟进需要先启用IMAP回复检测。')
                duplicate=db.execute("SELECT id FROM messages WHERE id<>? AND customer_id=? AND lower(recipient)=lower(?) AND subject=? AND body=? AND status IN ('queued','sending','submitted','uncertain')",(mid,m['customer_id'],m['recipient'],m['subject'],m['body'])).fetchone()
                if duplicate:raise ValueError('这位客户已有相同邮件在队列中或已发送，已阻止重复加入。')
                db.execute("UPDATE messages SET status='queued',error='' WHERE id=?",(mid,))
        return len(ids)
    def customer_state(self,cid,state):
        if state not in ('active',*BLOCKED):raise ValueError('客户状态无效。')
        with self.send_lock,self.store.conn() as db:
            c=db.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone()
            if not c:raise ValueError('客户不存在。')
            db.execute('UPDATE customers SET state=? WHERE id=?',(state,cid))
            if state!='active':db.execute("UPDATE messages SET status='cancelled',error='客户状态已变更，后续发送已取消。' WHERE customer_id=? AND status='queued'",(cid,))
            db.execute('INSERT INTO events(id,customer_id,kind,created_at,details) VALUES(?,?,?,?,?)',(uid(),cid,'state',now_iso(),json_dump({'state':state,'owner':self.cfg['owner']})))
        if state!='active':self.web.cancel_customer(cid)
    def state(self):
        customers=self.store.rows('SELECT * FROM customers ORDER BY code,name')
        contact_map={}
        for item in self.store.rows('SELECT customer_id,channel,recipient FROM customer_contacts WHERE active=1 ORDER BY rowid'):
            contact_map.setdefault((item['customer_id'],item['channel']),[]).append(item['recipient'])
        for c in customers:
            c['emails']=contact_map.get((c['id'],'email'),[]);c['whatsapp_numbers']=contact_map.get((c['id'],'whatsapp'),[])
        msgs=self.store.rows('SELECT m.*,c.name,c.code,c.state AS customer_state FROM messages m JOIN customers c ON c.id=m.customer_id ORDER BY m.created_at DESC')
        events=self.store.rows('SELECT e.*,c.name FROM events e JOIN customers c ON c.id=e.customer_id ORDER BY e.created_at DESC,e.rowid DESC LIMIT 300')
        for m in msgs:m['attachments']=json.loads(m['attachments'])
        for e in events:e['details']=json.loads(e['details'])
        counts={x:sum(m['status']==x for m in msgs) for x in ['draft','queued','sending','submitted','failed','uncertain','cancelled']}
        from contacts import POLICY
        return dict(customers=customers,messages=msgs,events=events,counts=counts,config=self.config_public(),contact_policy=POLICY,
            attachments=self.store.rows('SELECT id,name,size FROM attachments'),running=self.running,monitoring=self.monitoring,
            last_error=self.last_error,reason=self.reason,last_poll=self.last_poll,pending_sync=len(self.store.rows("SELECT id FROM events WHERE sync_state='pending'")),owners=OWNERS,whatsapp=self.wa.state(),website=self.web.state(),version='contacts-1')
    def start(self):
        with self.send_lock:
            if not self.password:raise ValueError('请先在设置中填写邮箱授权密码。')
            read_template(Path(self.cfg['workbook']))
            if getattr(Path(self.cfg['workbook']).stat(),'st_file_attributes',0)&1:raise ValueError('跟进表为只读，不能启动发送，请先选择可写工作表。')
            self.excel.flush()
            if self.store.rows("SELECT id FROM events WHERE sync_state='pending'"):raise ValueError('Excel还有未写入记录，请先修复同步。')
            self.running=True;self.reason='等待下一个发送时段';self.last_error=''
            if self.cfg['imap_enabled']:self.monitoring=True
    def send_one(self,at=None):
        with self.send_lock:
            if not self.running:return False
            at=at or datetime.now(timezone.utc);local=at.astimezone(ZoneInfo(self.cfg['timezone']))
            if local.weekday() not in self.cfg['weekdays'] or not self.cfg['hour_start']<=local.hour<self.cfg['hour_end']:
                self.reason='当前不在发送时段';return False
            last=self.store.setting('last_attempt','')
            if last and (at-parse_time(last)).total_seconds()<self.cfg['interval_seconds']:
                self.reason='等待发送间隔';return False
            midnight=local.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
            if self.store.rows("SELECT COUNT(*) n FROM messages WHERE channel='email' AND attempted_at>=?",(midnight,))[0]['n']>=self.cfg['daily_limit']:
                self.reason='已达当日发送上限';return False
            try:
                snapshot=read_template(Path(self.cfg['workbook']))
            except Exception as e:self.running=False;self.last_error='跟进表不可用：'+str(e);return False
            with self.store.conn() as db:
                db.execute('BEGIN IMMEDIATE')
                rows=db.execute("SELECT m.*,c.name,c.code,c.state FROM messages m JOIN customers c ON c.id=m.customer_id WHERE m.channel='email' AND m.status='queued' AND m.scheduled_at<=? ORDER BY m.scheduled_at,m.created_at",(at.isoformat(),)).fetchall()
                chosen=None
                for row in rows:
                    m=dict(row);book_state=snapshot.customer_stage(m['code'],m['name'])
                    if m['state']!='active' or book_state in ('暂停跟进','停止联系','已回复','需求确认','待报价','已报价','样品处理中','商务洽谈','已成交'):
                        db.execute("UPDATE messages SET status='cancelled',error='客户状态或Excel跟进阶段已变化。' WHERE id=?",(m['id'],));continue
                    if m['parent_id'] and (not self.monitoring or not self.last_poll or (at-parse_time(self.last_poll)).total_seconds()>360):
                        self.reason='自动跟进正在等待有效的回复检查';continue
                    chosen=m;break
                if not chosen:self.reason='没有到期的可发送邮件';return False
                chosen['attempted_at']=at.isoformat(timespec='seconds')
                db.execute("UPDATE messages SET status='sending',attempted_at=? WHERE id=? AND status='queued'",(chosen['attempted_at'],chosen['id']))
                if chosen['parent_id']:
                    parent=db.execute('SELECT message_id FROM messages WHERE id=?',(chosen['parent_id'],)).fetchone()
                    chosen['parent_message_id']=parent['message_id'] if parent else None
            self.store.set('last_attempt',chosen['attempted_at']);self.reason='正在发送：'+chosen['name']
            transport=self.transport_factory();status='submitted';err='';recipient_rejected=False
            try:
                attachments=[]
                for aid in json.loads(chosen['attachments']):
                    item=self.store.rows('SELECT * FROM attachments WHERE id=?',(aid,))
                    if not item:raise ValueError('附件已丢失。')
                    attachments.append(item[0])
                transport.send(chosen,self.cfg,self.password,attachments,lambda:self.running)
            except Exception as e:
                err=redact_error(e,(self.password,self.imap_password))
                recipient_rejected=isinstance(e,smtplib.SMTPRecipientsRefused)
                definite=isinstance(e,(smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused,smtplib.SMTPDataError,smtplib.SMTPAuthenticationError,ValueError,FileNotFoundError))
                status='uncertain' if getattr(transport,'phase','connect')=='data' and not definite else 'failed'
            chosen['submitted_at']=now_iso() if status=='submitted' else None
            with self.store.conn() as db:
                db.execute('UPDATE messages SET status=?,submitted_at=?,error=? WHERE id=?',(status,chosen['submitted_at'],err,chosen['id']))
                self.event(db,chosen,status,{'error':err})
                if status=='submitted' and chosen['followup_days']:
                    follow_id=uid();due=(parse_time(chosen['submitted_at'])+timedelta(days=chosen['followup_days'])).isoformat(timespec='seconds')
                    db.execute('INSERT OR IGNORE INTO messages(id,customer_id,recipient,subject,body,owner,status,scheduled_at,created_at,message_id,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (follow_id,chosen['customer_id'],chosen['recipient'],'Re: '+chosen['subject'],chosen['followup_body'],chosen['owner'],'queued',due,now_iso(),f'<{uid()}@friesgo.local>',chosen['id']))
            other_contact=recipient_rejected and self.store.rows("SELECT id FROM messages WHERE customer_id=? AND channel='email' AND status='queued' AND lower(recipient)<>lower(?)",(chosen['customer_id'],chosen['recipient']))
            if status!='submitted' and not other_contact:self.running=False;self.last_error=f'发送{("结果待确认" if status=="uncertain" else "失败")}，队列已暂停：{err}'
            elif other_contact:self.reason='该收件地址被拒绝，继续尝试本公司的其他邮箱'
            try:self.excel.flush()
            except Exception as e:self.running=False;self.last_error='发送结果已保存在本机，Excel待补写：'+str(e)
            return True
    def record_inbound(self,raw,key):
        mail=BytesParser(policy=policy.default).parsebytes(raw)
        refs=' '.join(str(mail.get(h,'')) for h in ('In-Reply-To','References'))
        ids=re.findall(r'<[^<>\s]+>',refs);m=None
        for mid in reversed(ids):
            rows=self.store.rows("SELECT * FROM messages WHERE message_id=? AND status IN ('submitted','uncertain')",(mid,))
            if rows:m=rows[0];break
        if not m:return False
        auto=bool(mail.get('Auto-Submitted') and mail.get('Auto-Submitted').lower()!='no') or bool(mail.get('X-Autoreply') or mail.get('X-Autorespond'))
        bounce=mail.get_content_type()=='multipart/report' and mail.get_param('report-type')=='delivery-status'
        kind='bounce' if bounce else 'auto_reply' if auto else 'reply'
        content=[]
        for part in mail.walk():
            if part.get_content_type()=='text/plain' and part.get_content_disposition()!='attachment':
                try:content.append(part.get_content())
                except Exception:pass
        summary='\n'.join(content)[:12000] or '[邮件未包含可读取的纯文本正文]'
        with self.send_lock,self.store.conn() as db:
            if db.execute('SELECT 1 FROM inbound WHERE key=?',(key,)).fetchone():return False
            db.execute('INSERT INTO inbound VALUES(?,?)',(key,now_iso()))
            if kind in ('reply','bounce'):
                db.execute("UPDATE customers SET state=? WHERE id=? AND state NOT IN ('paused','stopped')",('bounced' if bounce else 'replied',m['customer_id']))
                db.execute("UPDATE messages SET status='cancelled',error='客户已回复或发生退信，后续自动发送已取消。' WHERE customer_id=? AND status='queued'",(m['customer_id'],))
            self.event(db,m,kind,{'reply_subject':str(mail.get('Subject',''))[:300],'reply_from':str(mail.get('From',''))[:400],
                'reply_body':summary,'inbound_id':str(mail.get('Message-ID',''))[:300],'inbound_key':key})
        return True
    def poll_replies(self):
        if not self.cfg['imap_enabled']:raise ValueError('请先启用IMAP回复检测。')
        password=self.imap_password or self.password
        if not password:raise ValueError('请先填写邮箱授权密码。')
        if not self.poll_lock.acquire(blocking=False):return 0
        count=0
        try:
            with imaplib.IMAP4_SSL(self.cfg['imap_host'],self.cfg['imap_port'],ssl_context=ssl.create_default_context(),timeout=30) as mailbox:
                mailbox.login(self.cfg['imap_user'],password);typ,_=mailbox.select('INBOX',readonly=True)
                if typ!='OK':raise ValueError('无法读取收件箱。')
                validity=mailbox.response('UIDVALIDITY')[1];identity=hashlib.sha256((self.cfg['imap_host']+self.cfg['imap_user']+str(validity)).encode()).hexdigest()[:24]
                cursor=int(self.store.setting('imap_cursor_'+identity,0))
                since=(datetime.now(timezone.utc)-timedelta(days=30)).strftime('%d-%b-%Y')
                typ,data=mailbox.uid('search',None,'SINCE',since)
                if typ!='OK':raise ValueError('无法查询收件箱。')
                nums=sorted(int(x) for x in data[0].split() if int(x)>cursor)
                for n in nums[:200]:
                    typ,parts=mailbox.uid('fetch',str(n),'(BODY.PEEK[]<0.65536>)')
                    if typ!='OK':raise ValueError('读取邮件失败，稍后重试。')
                    raw=next((p[1] for p in parts if isinstance(p,tuple)),None)
                    if raw is None:raise ValueError('收件箱返回空邮件，游标未推进。')
                    count+=bool(self.record_inbound(raw,f'{identity}:{n}'))
                    self.store.set('imap_cursor_'+identity,n)
                if len(nums)<=200:self.last_poll=now_iso()
                else:self.last_poll='';self.reason='正在分批检查历史回复'
            self.excel.flush();return count
        finally:self.poll_lock.release()
    def upload(self,d):
        name=Path(str(d.get('name','file')).replace('\\','/')).name
        if not name or len(name)>180:raise ValueError('附件名称不正确。')
        raw=base64.b64decode(d.get('base64',''),validate=True)
        if not raw or len(raw)>12*1024*1024:raise ValueError('附件大小需在1字节至12MB之间。')
        aid=uid();path=self.data/'attachments'/aid;path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
        with self.store.conn() as db:db.execute('INSERT INTO attachments VALUES (?,?,?,?)',(aid,name,str(path),len(raw)))
        return {'id':aid,'name':name,'size':len(raw)}
    def import_csv(self,content):
        reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')));count=0;errors=[]
        aliases={'公司名称':'name','客户编号':'code','国家／地区':'country','国家':'country','邮箱':'email','电话':'phone','官网':'website','备注':'note','主题':'subject','英文正文':'body','中文翻译':'cn'}
        aliases.update({'全部邮箱':'emails','其他邮箱':'emails','WhatsApp':'whatsapp_numbers','WhatsApp号码':'whatsapp_numbers'})
        for n,row in enumerate(reader,2):
            if n>5001:raise ValueError('一次最多导入5000行。')
            d={aliases.get(k,k):v for k,v in row.items() if k}
            try:
                cid=self.save_customer(d);count+=1
                if d.get('subject') and d.get('body') and d.get('email'):
                    existing=self.store.rows('SELECT id FROM messages WHERE customer_id=? AND subject=? AND body=?',(cid,d['subject'].strip(),d['body'].strip()))
                    if not existing:self.save_draft({**d,'customer_id':cid,'recipient':self.contacts.values(cid,'email')[0]})
            except Exception as e:errors.append(f'第{n}行：{e}')
        return dict(imported=count,errors=errors[:50])
    def worker(self):
        next_poll=0;next_sync=0
        while self.alive:
            try:
                self.wa.drain()
                if self.monitoring and time.monotonic()>=next_poll:
                    try:self.poll_replies()
                    except Exception as e:self.last_poll='';self.last_error='回复检查失败：'+redact_error(e,(self.password,self.imap_password))
                    next_poll=time.monotonic()+60
                if time.monotonic()>=next_sync:
                    try:self.excel.flush()
                    except Exception as e:self.last_error='Excel待补写：'+str(e);self.running=False;self.wa.pause()
                    next_sync=time.monotonic()+20
                self.send_one()
                self.wa.send_one()
            except Exception as e:
                self.running=False;self.wa.pause();self.last_error='任务暂停：'+redact_error(e,(self.password,self.imap_password))
            time.sleep(1)

def make_handler(app):
 class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def response(self,status,body,content_type='application/json; charset=utf-8'):
        payload=body if isinstance(body,bytes) else json_dump(body).encode()
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(payload)
    def host_ok(self):return self.headers.get('Host','') in (f'127.0.0.1:{app.port}',f'localhost:{app.port}')
    def do_GET(self):
        if not self.host_ok():return self.response(403,{'error':'仅允许本机访问。'})
        path=urlparse(self.path).path
        if path=='/api/web/preview':
            job=parse_qs(urlparse(self.path).query).get('id',[''])[0]
            try:return self.response(200,app.web.preview_html(job),'text/html; charset=utf-8')
            except ValueError as e:return self.response(404,{'error':str(e)})
        if path=='/api/bootstrap':return self.response(200,{'token':app.token,'state':app.state()})
        if path=='/api/state':return self.response(200,app.state())
        if path=='/api/export-log':
            rows=app.store.rows('SELECT e.created_at,c.code,c.name,e.kind,e.details,e.sync_state FROM events e JOIN customers c ON c.id=e.customer_id ORDER BY e.created_at')
            s=io.StringIO();w=csv.writer(s);w.writerow(['时间','客户编号','公司名称','事件','记录','Excel同步'])
            for r in rows:w.writerow([("'"+str(v)) if str(v).startswith(('=','+','-','@')) else str(v) for v in r.values()])
            return self.response(200,s.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8')
        files={'/':'index.html','/message':'index.html','/app.js':'app.js','/whatsapp.js':'whatsapp.js','/website.js':'website.js','/contacts.js':'contacts.js','/style.css':'style.css'}
        if path not in files:return self.response(404,{'error':'页面不存在。'})
        f=ROOT/'static'/files[path];return self.response(200,f.read_bytes(),mimetypes.guess_type(f.name)[0]+'; charset=utf-8')
    def do_POST(self):
        origin=self.headers.get('Origin')
        if not self.host_ok() or (origin and origin not in (f'http://127.0.0.1:{app.port}',f'http://localhost:{app.port}')) or not hmac.compare_digest(self.headers.get('X-FriesGo-Token',''),app.token):
            return self.response(403,{'error':'请求已过期或来源不正确，请刷新页面。'})
        try:
            size=int(self.headers.get('Content-Length',0))
            if size<0 or size>18*1024*1024:raise ValueError('请求内容过大。')
            d=json.loads(self.rfile.read(size) or b'{}');path=urlparse(self.path).path;result={}
            if path=='/api/config':result=app.save_config(d)
            elif path=='/api/contacts/prepare':result=app.contacts.prepare(d.get('message_id'))
            elif path=='/api/contacts/check-whatsapp':result={'checks':app.contacts.check_all(d.get('customer_id'))}
            elif path=='/api/web/profile':result=app.web.configure(d)
            elif path=='/api/web/draft':result={'id':app.web.draft(d)}
            elif path=='/api/web/queue':result={'queued':app.web.enqueue(d.get('ids',[]),d.get('mode','preview'))}
            elif path=='/api/web/start':app.web.start()
            elif path=='/api/web/pause':app.web.pause()
            elif path=='/api/web/cancel':app.web.cancel(d.get('id'))
            elif path=='/api/wa/connect':app.wa.bridge.connect()
            elif path=='/api/wa/diagnostics':result={'diagnostics':app.wa.bridge.request('diagnostics',{},timeout=10)}
            elif path=='/api/wa/reconnect':
                app.wa.pause()
                with app.wa.lock:app.wa.bridge.request('reconnect',{},timeout=30)
            elif path=='/api/wa/config':app.wa.configure(d)
            elif path=='/api/wa/draft':result={'id':app.wa.draft(d)}
            elif path=='/api/wa/check-number':result={'check':app.wa.check_number(d.get('customer_id'),d.get('recipient'))}
            elif path=='/api/wa/queue':result={'queued':app.wa.enqueue(d.get('ids',[]))}
            elif path=='/api/wa/start':app.wa.start(d.get('account'),d.get('expected_ids'))
            elif path=='/api/wa/pause':app.wa.pause()
            elif path=='/api/wa/resolve':app.wa.resolve(d.get('id'),d.get('outcome'))
            elif path=='/api/customer':result={'id':app.save_customer(d)}
            elif path=='/api/customer-state':app.customer_state(d['id'],d['state'])
            elif path=='/api/draft':result={'id':app.save_draft(d)}
            elif path=='/api/queue':result={'queued':app.queue(d['ids'])}
            elif path=='/api/start':app.start()
            elif path=='/api/pause':app.running=False;app.reason='已暂停；正在发送的一封可能仍会完成'
            elif path=='/api/cancel':
                with app.store.conn() as db:db.execute("UPDATE messages SET status='cancelled',error='用户取消' WHERE id=? AND status IN ('draft','queued')",(d['id'],))
            elif path=='/api/resolve':
                if d.get('outcome') not in ('submitted','failed'):raise ValueError('核对结果无效。')
                with app.send_lock,app.store.conn() as db:
                    m=db.execute("SELECT * FROM messages WHERE id=? AND status='uncertain' AND channel='email'",(d['id'],)).fetchone()
                    if not m:raise ValueError('仅发送结果待确认的任务可以核对。')
                    msg=dict(m);msg['submitted_at']=now_iso() if d['outcome']=='submitted' else None
                    db.execute('UPDATE messages SET status=?,submitted_at=?,error=? WHERE id=?',(d['outcome'],msg['submitted_at'],'用户人工核对；未自动重发。',m['id']))
                    app.event(db,msg,d['outcome'],{'error':'用户人工核对发送结果，未自动安排新的跟进。','followup_days':0})
            elif path=='/api/sync':
                result=app.excel.flush()
                if app.last_error.startswith(('Excel待补写','发送结果已保存在本机')):app.last_error=''
            elif path=='/api/inspect-book':result=read_template(Path(app.cfg['workbook'])).summary()
            elif path=='/api/check-mail':
                if not app.password:raise ValueError('请先填写授权密码。')
                s=SMTPTransport().connect(app.cfg,app.password)
                try:s.noop()
                finally:s.close()
                result={'message':'SMTP连接及登录成功，未发送测试邮件。'}
            elif path=='/api/poll':result={'matched':app.poll_replies()};app.monitoring=True
            elif path=='/api/monitor':app.monitoring=bool(d.get('enabled')) and app.cfg['imap_enabled']
            elif path=='/api/attachment':result=app.upload(d)
            elif path=='/api/import':result=app.import_csv(d.get('csv',''))
            elif path=='/api/import-workbook':
                snap=read_template(Path(app.cfg['workbook']));n=0
                for row in snap.import_customers():
                    cid=app.save_customer(row);n+=1
                    if row['state']!='active':
                        with app.store.conn() as db:
                            db.execute("UPDATE customers SET state=? WHERE id=? AND state<>'stopped'",(row['state'],cid))
                            db.execute("UPDATE messages SET status='cancelled',error='导入的Excel阶段已暂停自动联系。' WHERE customer_id=? AND status='queued'",(cid,))
                result={'imported':n,'errors':[]}
            elif path=='/api/import-known':result=app.import_csv((ROOT/'assets'/'胡志明市工程客户.csv').read_text(encoding='utf-8-sig'))
            else:return self.response(404,{'error':'接口不存在。'})
            self.response(200,{'ok':True,**(result or {})})
        except Exception as e:self.response(400,{'error':redact_error(e,(app.password,app.imap_password))})
 return Handler

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8877);parser.add_argument('--data-dir');parser.add_argument('--no-worker',action='store_true');args=parser.parse_args()
    data=Path(args.data_dir or ROOT/'data');data.mkdir(parents=True,exist_ok=True)
    lock=open(data/'app.lock','a+b')
    try:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:raise SystemExit('此数据目录已有程序运行，请打开 http://127.0.0.1:8877')
    app=App(data);app.port=args.port
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(app));server.daemon_threads=True
    if not args.no_worker:threading.Thread(target=app.worker,daemon=True).start()
    print(f'FriesGo 已启动：http://127.0.0.1:{args.port}  发送队列默认暂停。',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:app.running=False;app.web.pause();app.wa.pause();app.wa.bridge.close();app.alive=False;server.server_close();lock.close()
if __name__=='__main__':main()
