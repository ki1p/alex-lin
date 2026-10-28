"""Company contact pool and explicit per-recipient draft planning; never sends."""
import json,re,uuid,hashlib

POLICY={'email':'all','whatsapp':'all','skip_existing_contact':True,'stop_on_reply':True}

def email_list(value):
    from app import valid_email
    parts=value if isinstance(value,list) else re.split(r'[\s,;；、]+',str(value or '').strip())
    return list(dict.fromkeys(valid_email(x) for x in parts if str(x).strip()))

def phone_list(value,strict=True):
    from whatsapp import number
    if isinstance(value,list):parts=value
    else:parts=re.split(r'[,;；、/\n]+|\s+(?=\+)',str(value or '').strip())
    out=[]
    for p in parts:
        if not str(p).strip():continue
        try:n=number(p)
        except ValueError:
            if strict:raise
            continue
        if n not in out:out.append(n)
    return out

class Contacts:
    def __init__(self,app):
        self.app=app
        with app.store.conn() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS customer_contacts(customer_id TEXT NOT NULL,channel TEXT NOT NULL,
                recipient TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,source TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(customer_id,channel,recipient),FOREIGN KEY(customer_id) REFERENCES customers(id))''')
            if not app.store.setting('contacts_migrated',False):
                for c in db.execute('SELECT * FROM customers').fetchall():
                    try:emails=email_list(c['email'])
                    except ValueError:emails=[]
                    self.save(db,c['id'],emails,phone_list(c['phone'],False),source='客户档案')
                for r in db.execute('SELECT customer_id,number FROM wa_number_checks').fetchall():
                    self.save(db,r['customer_id'],[],phone_list(r['number'],False),source='已有号码检查')
                for r in db.execute('SELECT DISTINCT customer_id,channel,recipient FROM messages').fetchall():
                    try:self.save(db,r['customer_id'],email_list(r['recipient']) if r['channel']=='email' else [],phone_list(r['recipient'],False) if r['channel']=='whatsapp' else [],source='已有联系记录')
                    except ValueError:pass
                db.execute("INSERT INTO settings VALUES ('contacts_migrated','true') ON CONFLICT(key) DO UPDATE SET value='true'")
        app.store.set('contact_policy',POLICY)
    def save(self,db,cid,emails,phones,replace_email=False,replace_phone=False,source='资料录入'):
        for channel,values,replace in [('email',emails,replace_email),('whatsapp',phones,replace_phone)]:
            if replace:db.execute('UPDATE customer_contacts SET active=0 WHERE customer_id=? AND channel=?',(cid,channel))
            for value in values:
                db.execute('INSERT INTO customer_contacts(customer_id,channel,recipient,source) VALUES(?,?,?,?) ON CONFLICT(customer_id,channel,recipient) DO UPDATE SET active=1,source=excluded.source',(cid,channel,value,source))
    def values(self,cid,channel):return [r['recipient'] for r in self.app.store.rows('SELECT recipient FROM customer_contacts WHERE customer_id=? AND channel=? AND active=1 ORDER BY rowid',(cid,channel))]
    def check_all(self,cid):
        if self.app.wa.running:raise ValueError('请先暂停WhatsApp队列再检查号码。')
        checks=[]
        for recipient in self.values(cid,'whatsapp'):
            # Each result is independent: an unregistered number never ends the company's scan.
            checks.append(self.app.wa.check_number(cid,recipient))
        return checks
    def prepare(self,mid):
        rows=self.app.store.rows('SELECT m.*,c.state FROM messages m JOIN customers c ON c.id=m.customer_id WHERE m.id=?',(mid,))
        if not rows:raise ValueError('消息不存在。')
        source=rows[0];channel=source['channel'];cid=source['customer_id']
        if channel not in ('email','whatsapp') or source['state']!='active':raise ValueError('客户当前不可联系。')
        if source['status']!='draft':raise ValueError('请先保存一份可编辑草稿，再按全部联系方式准备。')
        candidates=list(dict.fromkeys([source['recipient'],*self.values(cid,channel)]));checks=[];ids=[];skipped=[]
        for recipient in candidates:
            prior=self.app.store.rows("SELECT id,status FROM messages WHERE channel=? AND lower(recipient)=lower(?) AND status IN ('queued','sending','submitted','uncertain') LIMIT 1",(channel,recipient))
            if prior:skipped.append(dict(recipient=recipient,reason='已有待发、已发或结果待确认记录',status=prior[0]['status']));continue
            if channel=='whatsapp':
                check=self.app.wa.check_number(cid,recipient);checks.append(check)
                if check['registration']!='registered':skipped.append(dict(recipient=recipient,reason={'not_registered':'未开通WhatsApp','error':'号码检查失败'}.get(check['registration'],'待检查')));continue
            existing=self.app.store.rows("SELECT id FROM messages WHERE customer_id=? AND channel=? AND lower(recipient)=lower(?) AND body=? AND subject=? AND status='draft' ORDER BY created_at LIMIT 1",(cid,channel,recipient,source['body'],source['subject']))
            if existing:ids.append(existing[0]['id']);continue
            data={k:source[k] for k in ('customer_id','body','cn','owner','scheduled_at')};data['recipient']=recipient
            if channel=='email':
                data.update(subject=source['subject'],attachments=json.loads(source['attachments']),followup_days=source['followup_days'],followup_body=source['followup_body'])
                ids.append(self.app.save_draft(data))
            else:ids.append(self.app.wa.draft(data))
        messages=[]
        for message_id in dict.fromkeys(ids):
            m=self.app.store.rows('SELECT id,recipient,body,status FROM messages WHERE id=?',(message_id,))[0];messages.append(m)
        return dict(policy=POLICY,channel=channel,ids=[m['id'] for m in messages],messages=messages,skipped=skipped,checks=checks,started=False)
