"""Outbound-only sync to the owner-private Sales Site. Never queues or sends mail."""
import hashlib,json,threading,time,uuid,urllib.request,urllib.error
from pathlib import Path

SITE_URL='https://friesgo-sales-workbench.astral-sky-1170.chatgpt.site'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('网站同步不允许重定向，请核对网站连接。')

class SitesBridge:
 def __init__(self,app,transport=None):
  self.app=app;self.transport=transport;self.lock=threading.Lock();self.last_success=0;self.error='';self.busy=False;self.token=''
  self.device=app.store.setting('sites_device') or uuid.uuid4().hex;app.store.set('sites_device',self.device)
  self.enabled=app.store.setting('sites_enabled',False);self.secret_file=app.data/'sites-bridge.dpapi'
  self.last_sync=app.store.setting('sites_last_sync','');self.summary=app.store.setting('sites_summary',{})
  with app.store.conn() as db:
   db.execute('CREATE TABLE IF NOT EXISTS sites_map(local_id TEXT PRIMARY KEY,remote_id TEXT NOT NULL UNIQUE)')
   db.execute('CREATE TABLE IF NOT EXISTS sites_hash(kind TEXT NOT NULL,id TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(kind,id))')
  if self.secret_file.exists():
   try:
    from app import ProtectedSecrets
    self.token=ProtectedSecrets.transform(self.secret_file.read_bytes(),False).decode()
   except Exception:self.error='网站连接凭据无法读取，请重新配置连接。'
 def configure(self,token):
  from app import ProtectedSecrets
  if not isinstance(token,str) or len(token)<20:raise ValueError('网站服务凭据无效。')
  raw=ProtectedSecrets.transform(token.encode(),True);tmp=self.secret_file.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(self.secret_file)
  self.token=token;self.enabled=True;self.app.store.set('sites_enabled',True)
 def state(self):return dict(configured=bool(self.token or self.transport),enabled=self.enabled,busy=self.busy,url=SITE_URL,last_sync=self.last_sync,error=self.error,summary=self.summary)
 def fresh(self):return time.monotonic()-self.last_success<90
 def request(self,payload=None):
  if self.transport:return self.transport(payload)
  if not self.token:raise ValueError('网站尚未连接。')
  req=urllib.request.Request(SITE_URL+'/api/bridge',data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),headers={'OAI-Sites-Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
  try:
   with opener.open(req,timeout=45) as r:
    if 'application/json' not in r.headers.get('Content-Type',''):raise ValueError('网站返回了登录页，请更新连接凭据。')
    return json.load(r)
  except urllib.error.HTTPError as e:
   if e.code in (401,403):raise ValueError('网站连接授权已过期，请重新连接。') from None
   raise ValueError('网站同步失败（HTTP %s），记录仍保存在本机。'%e.code) from None
 def mapping(self):return {x['local_id']:x['remote_id'] for x in self.app.store.rows('SELECT * FROM sites_map')}
 def map(self,local,remote):
  with self.app.store.conn() as db:db.execute('INSERT INTO sites_map VALUES(?,?) ON CONFLICT(local_id) DO UPDATE SET remote_id=excluded.remote_id',(local,remote))
 def changed(self,kind,rows):
  known={x['id']:x['digest'] for x in self.app.store.rows('SELECT * FROM sites_hash WHERE kind=?',(kind,))};out=[]
  for row in rows:
   digest=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
   if known.get(row['id'])!=digest:out.append((row,digest))
  return out
 def upload(self,kind,rows):
  changed=self.changed(kind,rows);count=0
  for pos in range(0,len(changed),10):
   batch=changed[pos:pos+10];data=self.request(dict(device_id=self.device,device_name='FriesGo 本机邮件工作台',**{kind:[r for r,h in batch]}))
   for local,remote in data.get('mapping',{}).items():self.map(local,remote)
   with self.app.store.conn() as db:
    for row,digest in batch:db.execute('INSERT INTO sites_hash VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET digest=excluded.digest',(kind,row['id'],digest))
   count+=len(batch)
  return count
 def pull(self,data):
  from contacts import email_list
  mapping=self.mapping();reverse={v:k for k,v in mapping.items()};states={s['account_id']:s for s in data.get('states',[])}
  for remote in data.get('accounts',[]):
   cid=reverse.get(remote['id']);old=self.app.store.rows('SELECT * FROM customers WHERE id=?',(cid,)) if cid else []
   c=old[0] if old else {};addresses=[]
   values=[remote.get('email',''),*remote.get('bridge_emails',[]),*[x.get('email','') for x in data.get('contacts',[]) if x.get('account_id')==remote['id']]]
   for value in values:
    try:addresses.extend(email_list(value))
    except ValueError:continue
   # Website edits are primary; retain additional verified local addresses.
   if c:addresses+=self.app.contacts.values(cid,'email')
   fields={**c,'name':remote['name'],'country':remote.get('country') or c.get('country',''),'website':remote.get('url') or c.get('website',''),'email':addresses[0] if addresses else c.get('email',''),'emails':list(dict.fromkeys(addresses)),'phone':remote.get('phone') or c.get('phone',''),'note':c.get('note') or remote.get('note','')}
   if not c:fields.update(id=uuid.uuid5(uuid.NAMESPACE_URL,self.device+':'+remote['id']).hex,code='WEB-'+hashlib.sha256(remote['id'].encode()).hexdigest()[:12])
   cid=self.app.save_customer(fields);self.map(cid,remote['id']);reverse[remote['id']]=cid
   status=states.get(remote['id'],{}).get('status');target={'停止联系':'stopped','暂停':'paused','人工回复':'replied'}.get(status)
   local_state=self.app.store.rows('SELECT state FROM customers WHERE id=?',(cid,))[0]['state']
   if target and local_state!=target and local_state!='stopped' and not(local_state=='replied' and target=='paused'):self.app.customer_state(cid,target)
  return reverse
 def jobs(self,data,reverse):
  results=[]
  for j in data.get('jobs',[]):
   if j.get('target_device_id') and j['target_device_id']!=self.device:continue
   mid=uuid.uuid5(uuid.NAMESPACE_URL,self.device+':'+j['id']).hex
   try:
    cid=reverse.get(j['account_id'])
    if not cid:raise ValueError('客户尚未同步。')
    c=self.app.store.rows('SELECT * FROM customers WHERE id=?',(cid,))[0]
    if c['state']!='active':raise ValueError('客户已暂停、回复或停止联系。')
    existing=self.app.store.rows('SELECT * FROM messages WHERE id=?',(mid,))
    if existing:
     if any(existing[0][k]!=j[k] for k in ('recipient','subject','body')):raise ValueError('任务已存在但正文不同，未覆盖。')
    else:self.app.save_draft(dict(id=mid,customer_id=cid,recipient=j['recipient'],subject=j['subject'],body=j['body'],cn=j.get('cn',''),followup_days=0))
    results.append(dict(id=j['id'],local_message_id=mid))
   except Exception as e:results.append(dict(id=j['id'],error=str(e)[:300]))
  if results:self.request(dict(device_id=self.device,job_results=results))
 def sync(self):
  if not self.lock.acquire(False):return self.state()
  self.busy=True
  try:
   if not self.enabled:raise ValueError('网站同步已暂停。')
   # Apply website contact restrictions before exporting or preparing anything.
   snapshot=self.request();known=self.mapping();cloud_ids={a['id'] for a in snapshot.get('accounts',[])}
   if any(r not in cloud_ids for r in known.values()):raise ValueError('网站客户关联缺失，请核对后再同步。')
   # Existing website links can be pulled immediately; unmapped website customers
   # are imported only after local accounts have been deduplicated by the server.
   self.pull({**snapshot,'accounts':[a for a in snapshot.get('accounts',[]) if a['id'] in set(known.values())]})
   mapping=self.mapping();accounts=[]
   for c in self.app.store.rows('SELECT * FROM customers'):
    accounts.append({**c,'remote_id':mapping.get(c['id']),'emails':self.app.contacts.values(c['id'],'email')})
   counts={'accounts':self.upload('accounts',accounts)}
   snapshot=self.request();reverse=self.pull(snapshot);self.jobs(snapshot,reverse)
   messages=self.app.store.rows('SELECT id,customer_id,channel,recipient,subject,body,cn,owner,status,created_at,scheduled_at,attempted_at,submitted_at,message_id,error,wa_delivery FROM messages')
   counts['messages']=self.upload('messages',messages)
   events=self.app.store.rows("SELECT id,customer_id,kind,created_at,details FROM events WHERE kind IN ('reply','auto_reply','bounce')")
   for e in events:e['details']=json.loads(e['details'])
   counts['events']=self.upload('events',events)
   self.request(dict(device_id=self.device))
   from app import now_iso
   self.last_sync=now_iso();self.last_success=time.monotonic();self.error='';self.summary=counts
   self.app.store.set('sites_last_sync',self.last_sync);self.app.store.set('sites_summary',counts)
   return self.state()
  except Exception as e:
   self.error=str(e).replace(self.token,'[已隐藏]') if self.token else str(e);raise
  finally:self.busy=False;self.lock.release()
 def worker(self):
  while self.app.alive:
   if self.enabled and (self.token or self.transport):
    try:self.sync()
    except Exception:pass
   for _ in range(30):
    if not self.app.alive:return
    time.sleep(1)
