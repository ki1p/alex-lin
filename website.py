"""Persistent website tasks. No SMTP use; no desktop input; no startup execution."""
import hashlib, html, ipaddress, json, os, shutil, subprocess, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent
PROFILE=dict(first_name='BaiJiang',last_name='Lin',title='Sales Manager',company='FriesGO Global',
    email='friesgoindustrial@gmail.com',phone='+86 17731796591',website='https://friesgoglobal.com',
    country='China',province='Hebei',city='Cangzhou',street='',postcode='',products='Valves; Cables and Wires; PE Pipes')
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def dump(x):return json.dumps(x,ensure_ascii=False)
def website_url(value):
    value=str(value or '').strip()
    if value and '://' not in value:value='https://'+value
    u=urlparse(value)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:raise ValueError('请填写完整的公开公司官网地址。')
    host=u.hostname.lower()
    if host=='localhost' or '.' not in host or host.endswith(('.local','.localhost')):raise ValueError('只接受公开公司官网。')
    try:
        if not ipaddress.ip_address(host).is_global:raise ValueError('不接受内网地址。')
    except ValueError as e:
        if str(e)=='不接受内网地址。':raise
    return value

class EgoExecutor:
    def __init__(self,app):self.app=app
    @staticmethod
    def executable():
        return shutil.which('ego-browser') or str(Path.home()/'.local/share/ego/active_version_dir/ego-browser.exe')
    def run(self,job,profile,folder):
        exe=self.executable()
        if not Path(exe).is_file():raise ValueError('未找到 ego-browser，请打开 ego lite 并完成初始化。')
        request=folder/'request.json';result=folder/'result.json'
        request.write_text(dump(dict(id=job['id'],url=job['url'],body=job['body'],subject=job['subject'],
            profile=profile,mode=job['mode'],folder=str(folder).replace('\\','/'))),encoding='utf-8')
        entry=folder/'entry.mjs'
        entry.write_text('const {run}=await import('+json.dumps((ROOT/'ego-website.mjs').as_uri())+');\nawait run('+json.dumps(str(request).replace('\\','/'))+');',encoding='utf-8')
        proc=subprocess.Popen([exe,'nodejs','-e',"await import('"+entry.as_uri()+"')"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:out,err=proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            (folder/'cancel').touch();proc.kill();proc.communicate();raise TimeoutError('ego lite 执行超时；任务未自动重试。')
        if result.exists():return json.loads(result.read_text(encoding='utf-8'))
        raise RuntimeError((err or out or 'ego lite 未返回执行结果')[-1500:])

class Website:
    def __init__(self,app,executor=None):
        self.app=app;self.executor=executor or EgoExecutor(app);self.lock=threading.RLock();self.running=False;self.reason='官网队列已暂停';self.thread=None
        self.profile={**PROFILE,**app.store.setting('web_profile',{})}
        self.root=app.data/'website';self.root.mkdir(exist_ok=True)
        with app.store.conn() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS website_tasks(id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,
                url TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,mode TEXT NOT NULL DEFAULT 'preview',
                status TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',result TEXT NOT NULL DEFAULT '{}',fingerprint TEXT NOT NULL,
                profile TEXT NOT NULL DEFAULT '{}',FOREIGN KEY(customer_id) REFERENCES customers(id))''')
            # A crashed preview can be inspected; a submission checkpoint must never be retried.
            for row in db.execute("SELECT id FROM website_tasks WHERE status='running'").fetchall():
                folder=self.root/row['id'];attempted=(folder/'submit-attempted').exists()
                (folder/'cancel').touch() if folder.exists() else None
                db.execute('UPDATE website_tasks SET status=?,error=? WHERE id=?',('uncertain' if attempted else 'needs_attention','上次执行中断，结果已保留，不自动重试。',row['id']))
    def state(self):
        jobs=self.app.store.rows('SELECT w.*,c.name,c.state AS customer_state FROM website_tasks w JOIN customers c ON c.id=w.customer_id ORDER BY w.created_at DESC,w.rowid DESC')
        for job in jobs:job['result']=json.loads(job['result']);job.pop('profile',None)
        return dict(running=self.running,reason=self.reason,profile=self.profile,jobs=jobs,ego_available=Path(EgoExecutor.executable()).is_file())
    def configure(self,d):
        from app import valid_email,text
        with self.lock:
            if self.running:raise ValueError('请先暂停官网任务，再修改资料。')
            p={k:text(d.get(k,self.profile[k]),500) for k in PROFILE};p['email']=valid_email(p['email']);p['website']=website_url(p['website'])
            for k in ('first_name','company','phone','country'):
                if not p[k]:raise ValueError('姓名、公司、电话和国家不能为空。')
            self.profile=p;self.app.store.set('web_profile',p);return p
    def draft(self,d):
        from app import text
        rows=self.app.store.rows('SELECT * FROM customers WHERE id=?',(d.get('customer_id'),))
        if not rows:raise ValueError('请先选择客户。')
        c=rows[0]
        if c['state']!='active':raise ValueError('这位客户当前不可自动联系。')
        url=website_url(d.get('url') or c['website']);body=text(d.get('body'),8000);subject=text(d.get('subject') or 'Supply cooperation | FriesGO Global',300)
        if not body:raise ValueError('请填写留言正文。')
        mid=d.get('id') or uuid.uuid4().hex
        host=urlparse(url).hostname.lower().removeprefix('www.')
        fingerprint=hashlib.sha256((host+'\n'+body).encode()).hexdigest()
        with self.app.store.conn() as db:
            old=db.execute('SELECT * FROM website_tasks WHERE id=?',(mid,)).fetchone()
            if old:
                if old['status']!='draft' or old['customer_id']!=c['id']:raise ValueError('仅允许编辑原客户的草稿。')
                db.execute('UPDATE website_tasks SET url=?,subject=?,body=?,fingerprint=?,updated_at=? WHERE id=?',(url,subject,body,fingerprint,now(),mid))
            else:db.execute('INSERT INTO website_tasks(id,customer_id,url,subject,body,created_at,updated_at,fingerprint) VALUES(?,?,?,?,?,?,?,?)',(mid,c['id'],url,subject,body,now(),now(),fingerprint))
        return mid
    def enqueue(self,ids,mode='preview'):
        if mode not in ('preview','submit'):raise ValueError('执行模式无效。')
        ids=list(dict.fromkeys(ids))
        if not ids:raise ValueError('请选择任务。')
        with self.lock,self.app.store.conn() as db:
            db.execute('BEGIN IMMEDIATE')
            for mid in ids:
                job=db.execute('SELECT w.*,c.state FROM website_tasks w JOIN customers c ON c.id=w.customer_id WHERE w.id=?',(mid,)).fetchone()
                if not job or job['status']!='draft' or job['state']!='active':raise ValueError('只能安排可联系客户的草稿。')
                dup=db.execute("SELECT id FROM website_tasks WHERE id<>? AND fingerprint=? AND status IN ('queued','running','submitted','uncertain')",(mid,job['fingerprint'])).fetchone()
                if dup:raise ValueError('同一官网已有相同留言待执行或已提交，已阻止重复。')
                db.execute("UPDATE website_tasks SET status='queued',mode=?,profile=?,updated_at=? WHERE id=?",(mode,dump(self.profile),now(),mid))
        return len(ids)
    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                if self.running:return
                raise ValueError('上一条正在结束，请稍后启动。')
            if not self.app.store.rows("SELECT id FROM website_tasks WHERE status='queued'"):raise ValueError('没有待执行的官网任务。')
            self.running=True;self.reason='正在自动填写';self.thread=threading.Thread(target=self._worker,daemon=True);self.thread.start()
    def pause(self):
        with self.lock:
            self.running=False;self.reason='已暂停，当前任务将在下一检查点停止'
            for r in self.app.store.rows("SELECT id FROM website_tasks WHERE status='running'"):
                folder=self.root/r['id'];folder.mkdir(exist_ok=True);(folder/'cancel').touch()
    def cancel(self,mid):
        with self.lock,self.app.store.conn() as db:
            job=db.execute('SELECT status FROM website_tasks WHERE id=?',(mid,)).fetchone()
            if not job:raise ValueError('任务不存在。')
            if job['status']=='running':(self.root/mid/'cancel').touch()
            else:db.execute("UPDATE website_tasks SET status='cancelled',updated_at=? WHERE id=? AND status IN ('draft','queued')",(now(),mid))
    def cancel_customer(self,cid):
        for r in self.app.store.rows("SELECT id FROM website_tasks WHERE customer_id=? AND status IN ('draft','queued','running')",(cid,)):self.cancel(r['id'])
    def _worker(self):
        try:
            while self.running and self.app.alive:
                if not self.run_one():break
                for _ in range(30):
                    if not self.running:break
                    time.sleep(.1)
        finally:self.running=False;self.reason='任务已结束；可查看预览和异常原因'
    def run_one(self):
        with self.lock,self.app.store.conn() as db:
            if not self.running:return False
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT w.*,c.state FROM website_tasks w JOIN customers c ON c.id=w.customer_id WHERE w.status='queued' ORDER BY w.created_at,w.rowid LIMIT 1").fetchone()
            if not row:return False
            job=dict(row)
            if job['state']!='active':db.execute("UPDATE website_tasks SET status='cancelled',error='客户不可联系' WHERE id=?",(job['id'],));return True
            db.execute("UPDATE website_tasks SET status='running',updated_at=? WHERE id=?",(now(),job['id']))
        folder=self.root/job['id'];folder.mkdir(exist_ok=True)
        try:
            result=self.executor.run(job,json.loads(job['profile']),folder)
            status=result.get('status')
            if status not in ('filled','needs_attention','submitted','uncertain','cancelled'):raise ValueError('执行器返回未知状态。')
            if job['mode']=='preview' and status in ('submitted','uncertain'):raise RuntimeError('预览模式返回了异常提交状态。')
        except Exception as e:
            status='uncertain' if (folder/'submit-attempted').exists() else 'needs_attention';result=dict(status=status,error=str(e)[:1800])
        with self.app.store.conn() as db:db.execute('UPDATE website_tasks SET status=?,result=?,error=?,updated_at=? WHERE id=?',(status,dump(result),result.get('error',''),now(),job['id']))
        return True
    def preview_html(self,mid):
        rows=self.app.store.rows('SELECT w.*,c.name FROM website_tasks w JOIN customers c ON c.id=w.customer_id WHERE w.id=?',(mid,))
        if not rows:raise ValueError('任务不存在。')
        r=rows[0];result=json.loads(r['result']);e=html.escape
        fields=''.join('<tr><td>'+e(str(f.get('label','')))+('</td><td>')+e(str(f.get('value','')))+('</td></tr>') for f in result.get('fields',[]))
        issues='；'.join(result.get('issues',[])) or r['error']
        return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><link rel="stylesheet" href="/style.css"><title>官网留言预览</title><body><main><h1>'+e(r['name'])+'</h1><p>状态：'+e(r['status'])+' · 模式：'+e(r['mode'])+'</p><p>'+e(result.get('url',r['url']))+'</p><p>'+e(issues)+'</p><h2>实际填写字段</h2><table>'+fields+'</table><h2>留言正文</h2><pre>'+e(r['body'])+'</pre><p>任务空间：'+e(str(result.get('spaceId','')))+'。网页保留在 ego lite，刷新可能清空输入。预览模式不会点击提交或 PREVIEW。</p></main></body></html>').encode()
