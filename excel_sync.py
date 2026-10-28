"""Read template with Open XML; authored updates are made by artifact-tool."""
from __future__ import annotations
import hashlib, json, os, re, subprocess, threading, uuid, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
NODE=Path(os.environ.get('FRIESGO_NODE',r'C:/Users/LBJ/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'))
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def colnum(name):
 n=0
 for c in name:n=n*26+ord(c)-64
 return n
def addr(col,row):
 s=''
 while col:col,r=divmod(col-1,26);s=chr(65+r)+s
 return s+str(row)
def local_serial(value,date_only=False):
 if not value:return None
 if len(value)==10:dt=datetime.fromisoformat(value)
 else:dt=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
 if date_only:dt=dt.replace(hour=0,minute=0,second=0,microsecond=0)
 return (dt-datetime(1899,12,30)).total_seconds()/86400

class Snapshot:
 def __init__(self,path):
  self.path=Path(path);self.rows={};self.capacity=208;self.formulas={};self.headers={}
  with zipfile.ZipFile(path) as z:
   self.files=set(z.namelist());strings=[]
   if 'xl/sharedStrings.xml' in self.files:
    strings=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)]
   rels={e.attrib['Id']:e.attrib['Target'] for e in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
   book=ET.fromstring(z.read('xl/workbook.xml'))
   for sh in book.findall('m:sheets/m:sheet',NS):
    name=sh.attrib['name'];target=rels[sh.attrib['{'+NS['r']+'}id']]
    target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
    root=ET.fromstring(z.read(target));rows={};formulas={}
    for c in root.findall('m:sheetData/m:row/m:c',NS):
     ref=c.attrib['r'];letters=''.join(x for x in ref if x.isalpha());row=int(''.join(x for x in ref if x.isdigit()));col=colnum(letters)
     v=c.findtext('m:v',default='',namespaces=NS)
     if c.attrib.get('t')=='s':v=strings[int(v)] if v else ''
     elif c.attrib.get('t')=='inlineStr':v=''.join(c.find('m:is',NS).itertext())
     if c.find('m:f',NS) is not None:formulas[ref]=c.findtext('m:f',namespaces=NS)
     if v!='':rows.setdefault(row,{})[col]=v
    self.rows[name]=rows;self.formulas[name]=formulas;self.headers[name]=rows.get(8,{})
    if name=='客户总表':self.capacity=max([208]+[int(''.join(filter(str.isdigit,x))) for x in formulas])
  for name,checks in {'客户总表':{1:'客户编号',2:'公司名称',9:'当前阶段',13:'最近联系日期',18:'跟进提醒（自动）'},
    '联系人':{1:'客户编号',6:'邮箱'},'跟进记录':{1:'客户编号',3:'沟通日期',8:'沟通内容／需求',9:'本次联系结果',12:'资料／沟通记录链接'}}.items():
   if name not in self.rows or any(self.headers[name].get(c)!=s for c,s in checks.items()):raise ValueError(f'工作簿的「{name}」表结构与FriesGo模板不一致。')
  self.codes={};self.names={}
  for col,title in ((13,'发送状态'),(14,'消息编号')):
   existing=self.headers['跟进记录'].get(col)
   if existing and existing!=title:raise ValueError(f'跟进记录第{col}列已有其他用途，需先调整表格。')
  for row,d in self.rows['客户总表'].items():
   if row<9 or not d.get(1):continue
   code=str(d[1]).strip()
   if code in self.codes:raise ValueError(f'Excel客户编号重复：{code}')
   self.codes[code]=row;self.names.setdefault(str(d.get(2,'')).strip().casefold(),[]).append(row)
 def customer_stage(self,code,name):
  row=self.codes.get(code)
  if row and str(self.rows['客户总表'][row].get(2,'')).strip().casefold()!=name.strip().casefold():raise ValueError('Excel客户编号与公司名称不匹配，请先核对：'+code)
  if row is None:
   match=self.names.get(name.strip().casefold(),[])
   if len(match)>1:raise ValueError(f'Excel中有多个同名客户：{name}，请先核对客户编号。')
   row=match[0] if match else None
  return self.rows['客户总表'].get(row,{}).get(9,'')
 def summary(self):return {'sheets':list(self.rows),'customers':len(self.codes),'log_rows':sum(r>=9 and bool(d.get(1)) for r,d in self.rows['跟进记录'].items()),'capacity':self.capacity-8,'path':str(self.path)}
 def import_customers(self):
  contacts={}
  for row,d in self.rows['联系人'].items():
   if row>=9 and d.get(1) and d.get(6):contacts.setdefault(str(d[1]),d)
  for code,row in self.codes.items():
   c=self.rows['客户总表'][row];person=contacts.get(code,{})
   stage=c.get(9,'');state='stopped' if stage=='停止联系' else 'paused' if stage=='暂停跟进' else 'active' if stage in ('','待开发','已联系') else 'replied'
   yield {'code':code,'name':c.get(2,''),'country':c.get(3,''),'email':person.get(6,''),'phone':person.get(8,''),'website':c.get(11,''),'state':state,'note':'从跟进表导入；原有阶段：'+stage}

def read_template(path):
 if not Path(path).is_file():raise ValueError('跟进表不存在，请检查路径。')
 return Snapshot(path)

def preserve_native_features(source,output,old_capacity,capacity,writes):
 """The artifact API has no table resize/native hyperlink method. Preserve these XML features explicitly."""
 main=NS['m'];relationship=NS['r'];package='http://schemas.openxmlformats.org/package/2006/relationships'
 ET.register_namespace('',main);ET.register_namespace('r',relationship)
 with zipfile.ZipFile(source) as z:original={n:z.read(n) for n in z.namelist()}
 with zipfile.ZipFile(output) as z:files={n:z.read(n) for n in z.namelist()}
 def extend(s):return re.sub(r'(\$?[A-Z]+\$?)'+str(old_capacity)+r'\b',lambda m:m[1]+str(capacity),s)
 oldtables={ET.fromstring(v).attrib['name']:ET.fromstring(v) for n,v in original.items() if re.fullmatch(r'xl/tables/table\d+\.xml',n)}
 for n,v in list(files.items()):
  if not re.fullmatch(r'xl/tables/table\d+\.xml',n):continue
  new=ET.fromstring(v);table=oldtables.get(new.attrib['name'])
  if table is None:continue
  table.attrib['id']=new.attrib['id'];columns=table.find('m:tableColumns',NS)
  is_log=any(c.attrib.get('name')=='本次联系结果' for c in columns)
  if is_log:
   names=[c.attrib['name'] for c in columns]
   for title in ['发送状态','消息编号']:
    if title not in names:ET.SubElement(columns,'{'+main+'}tableColumn',{'id':str(len(columns)+1),'name':title})
   columns.attrib['count']=str(len(columns));table.attrib['ref']=f'A8:N{capacity}'
  else:table.attrib['ref']=extend(table.attrib['ref'])
  auto=table.find('m:autoFilter',NS)
  if auto is not None:auto.attrib['ref']=table.attrib['ref']
  for elem in table.iter():
   if 'ref' in elem.attrib:elem.attrib['ref']=extend(elem.attrib['ref'])
  files[n]=ET.tostring(table,encoding='utf-8',xml_declaration=True)
 # Preserve validation definitions, especially the user's four owner choices and customer status choices.
 book=ET.fromstring(files['xl/workbook.xml']);rels={x.attrib['Id']:x.attrib['Target'] for x in ET.fromstring(files['xl/_rels/workbook.xml.rels'])}
 for sh in book.findall('m:sheets/m:sheet',NS):
  target=rels[sh.attrib['{'+relationship+'}id']];part=target.lstrip('/') if target.startswith('/') else 'xl/'+target
  if part not in original:continue
  root=ET.fromstring(files[part]);old=ET.fromstring(original[part]);dv=old.find('m:dataValidations',NS)
  if dv is not None:
   existing=root.find('m:dataValidations',NS)
   if existing is not None:root.remove(existing)
   for child in dv:child.attrib['sqref']=extend(child.attrib['sqref'])
   following={'hyperlinks','printOptions','pageMargins','pageSetup','headerFooter','drawing','legacyDrawing','tableParts','extLst'}
   idx=next((i for i,x in enumerate(root) if x.tag.split('}')[-1] in following),len(root));root.insert(idx,dv)
  links=[x for x in writes if x['sheet']==sh.attrib['name'] and x['cell'].startswith('L') and sh.attrib['name']=='跟进记录' and x['value']]
  if links:
   hp=root.find('m:hyperlinks',NS)
   if hp is None:
    hp=ET.Element('{'+main+'}hyperlinks');following={'printOptions','pageMargins','pageSetup','headerFooter','drawing','legacyDrawing','tableParts','extLst'}
    idx=next((i for i,x in enumerate(root) if x.tag.split('}')[-1] in following),len(root));root.insert(idx,hp)
   rp=str(Path(part).parent).replace('\\','/')+'/_rels/'+Path(part).name+'.rels'
   relationships=ET.fromstring(files[rp]) if rp in files else ET.Element('{'+package+'}Relationships')
   for link in links:
    for oldlink in list(hp):
     if oldlink.attrib.get('ref')==link['cell']:hp.remove(oldlink)
    rid='rIdFG'+uuid.uuid4().hex
    ET.SubElement(hp,'{'+main+'}hyperlink',{'ref':link['cell'],'{'+relationship+'}id':rid})
    ET.SubElement(relationships,'{'+package+'}Relationship',{'Id':rid,'Type':relationship+'/hyperlink','Target':link['value'],'TargetMode':'External'})
   files[rp]=ET.tostring(relationships,encoding='utf-8',xml_declaration=True)
  files[part]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in files.items():z.writestr(n,v)

class ExcelSync:
 def __init__(self,app):self.app=app;self.lock=threading.Lock()
 def flush(self):
  if not self.lock.acquire(blocking=False):return {'synced':0,'busy':True}
  pending=[];temp=None;guard=None;guard_fd=None;plan_path=None
  try:
   app=self.app;pending=app.store.rows("SELECT * FROM events WHERE sync_state='pending' ORDER BY created_at,rowid LIMIT 100")
   if not pending:return {'synced':0}
   target=Path(app.cfg['workbook']);guard=target.with_name(target.name+'.friesgo.lock')
   if getattr(target.stat(),'st_file_attributes',0)&1:raise ValueError('跟进表为只读，请选择可编辑的工作表副本。')
   if target.with_name('~$'+target.name).exists():raise ValueError('Excel正打开此文件，请关闭后补写。')
   try:guard_fd=os.open(guard,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
   except FileExistsError:raise ValueError('跟进表正在被其他写入任务使用。若程序曾异常中断，请检查 .friesgo.lock 文件。')
   os.write(guard_fd,str(os.getpid()).encode())
   before=hashlib.sha256(target.read_bytes()).hexdigest();snap=read_template(target);writes=[];code_updates={}
   rows=snap.rows;high=max(208,snap.capacity)
   def put(sheet,col,row,value,fmt=None):
    nonlocal high
    high=max(high,row);rows[sheet].setdefault(row,{})[col]=value if value is not None else ''
    writes.append({'sheet':sheet,'cell':addr(col,row),'value':value,'format':fmt})
   def empty(sheet,col=1):
    occupied=[r for r,d in rows[sheet].items() if r>=9 and d.get(col)]
    return max([8]+occupied)+1
   customer_cache={}
   for event in pending:
    d=json.loads(event['details']);cid=event['customer_id'];customer=customer_cache.get(cid)
    if not customer:
     matches=app.store.rows('SELECT * FROM customers WHERE id=?',(cid,))
     if not matches:raise ValueError('记录对应的客户不存在。')
     customer=matches[0];customer_cache[cid]=customer
    code=code_updates.get(cid,customer['code']);cr=snap.codes.get(code)
    if cr and str(rows['客户总表'][cr].get(2,'')).strip().casefold()!=customer['name'].strip().casefold():raise ValueError(f'客户编号{code}已属于其他公司，请先核对。')
    if not cr:
     matches=snap.names.get(customer['name'].strip().casefold(),[])
     if len(matches)>1:raise ValueError('Excel有多个同名客户，请先核对编号：'+customer['name'])
     if matches:cr=matches[0];code=str(rows['客户总表'][cr][1]);code_updates[cid]=code
     else:
      cr=empty('客户总表');snap.codes[code]=cr;snap.names[customer['name'].strip().casefold()]=[cr]
      for col,value in [(1,code),(2,customer['name']),(3,customer['country']),(4,'工程承包商'),(5,d.get('owner') or app.cfg['owner']),(8,'平衡阀／压差控制阀／流量控制阀'),(9,'待开发'),(11,customer['website'])]:put('客户总表',col,cr,value)
      put('客户总表',12,cr,local_serial(event['created_at'],True),'yyyy-mm-dd')
    kind=event['kind'];stage=rows['客户总表'][cr].get(9,'')
    if kind=='state':
     new={'paused':'暂停跟进','stopped':'停止联系','replied':'已回复','bounced':'暂停跟进','active':'已联系'}[d['state']]
     put('客户总表',9,cr,new);continue
    is_wa=d.get('channel')=='whatsapp';channel='WhatsApp' if is_wa else '邮箱'
    recipient=d.get('recipient','') or customer['email']
    if recipient:
     exists=any(r>=9 and str(c.get(1,''))==code and str(c.get(7 if is_wa else 6,'')).lower()==recipient.lower() for r,c in rows['联系人'].items())
     if not exists:
      rr=empty('联系人')
      for col,value in [(1,code),(3,customer['name']+'团队'),(5,'待确认'),(7 if is_wa else 6,recipient),(8,customer['phone']),(10,channel),(11,app.cfg['timezone'])]:put('联系人',col,rr,value)
    is_reply=kind in ('reply','auto_reply','bounce')
    key=('回复:'+d.get('inbound_key',event['id'])) if is_reply else '发送:'+str(d.get('message_id') or event['id'])
    matches=[r for r,c in rows['跟进记录'].items() if r>=9 and c.get(14)==key]
    lr=matches[0] if matches else empty('跟进记录')
    states={'submitted':'已提交发送服务','failed':'发送失败','uncertain':'发送结果待确认','reply':'收到回复','auto_reply':'收到自动回复','bounce':'退信'}
    if is_wa:states['submitted']={'submitted':'WhatsApp已提交（待回执）','sent':'WhatsApp服务器已接受','delivered':'WhatsApp已送达','read':'WhatsApp已读','failed_delivery':'WhatsApp投递失败'}.get(d.get('delivery'),'WhatsApp已提交（待回执）')
    title=d.get('reply_subject') if is_reply else d.get('subject');body=d.get('reply_body') if is_reply else d.get('body')
    content=f"收件地址：{recipient}\n主题：{(title or '')[:100]}\n摘要：{' '.join((body or '').split())[:120]}"
    if d.get('error'):content+='\n发送说明：'+' '.join(d['error'].split())[:100]
    result={'submitted':'未回复','reply':'已人工回复','auto_reply':'自动回复'}.get(kind,'')
    action={'submitted':'等待回复，按安排跟进','failed':'检查失败原因后人工处理','uncertain':'核查邮箱记录后确认结果；不自动重发','reply':'阅读回复并人工跟进','auto_reply':'查看自动回复内容','bounce':'核对收件地址，暂停自动联系'}.get(kind,'')
    if is_wa and kind=='uncertain':action='核查WhatsApp聊天记录后确认；不自动重发'
    if is_wa and kind=='submitted' and matches and d.get('receipt'):
     # Receipts update the existing send row without changing its original send date/result.
     put('跟进记录',13,lr,states[kind]);continue
    next_date=None
    if kind=='submitted' and d.get('followup_days'):next_date=local_serial((datetime.fromisoformat(d.get('submitted_at') or event['created_at'])+timedelta(days=int(d['followup_days']))).isoformat(),True)
    for col,value in [(1,code),(4,d.get('owner') or app.cfg['owner']),(5,d.get('reply_from') if is_reply else recipient),(6,channel),(8,content[:32000]),(9,result),(11,action),
      (12,f"http://127.0.0.1:{app.port}/message?id={event.get('message_id') or ''}"),(13,states.get(kind,kind)),(14,key)]:put('跟进记录',col,lr,value)
    put('跟进记录',3,lr,local_serial(event['created_at']),'yyyy-mm-dd hh:mm:ss');put('跟进记录',10,lr,next_date,'yyyy-mm-dd')
    if kind in ('submitted','reply','auto_reply'):
     old_date=rows['客户总表'][cr].get(13,'');new_date=local_serial(event['created_at'],True)
     try:old_date=float(old_date)
     except (TypeError,ValueError):old_date=0
     if new_date>=old_date:
      put('客户总表',13,cr,new_date,'yyyy-mm-dd');put('客户总表',16,cr,(states[kind]+'：'+(title or ''))[:600])
     if stage not in ('暂停跟进','停止联系'):
      if kind=='reply' and stage in ('待开发','已联系','已回复',''):put('客户总表',9,cr,'已回复')
      elif kind=='submitted' and stage in ('待开发',''):put('客户总表',9,cr,'已联系')
      if kind=='reply':put('客户总表',14,cr,None);put('客户总表',15,cr,action)
      elif kind=='submitted' and stage in ('待开发','已联系',''):
       if next_date is not None:put('客户总表',14,cr,next_date,'yyyy-mm-dd')
       put('客户总表',15,cr,action)
    elif kind=='bounce' and stage!='停止联系':put('客户总表',9,cr,'暂停跟进');put('客户总表',17,cr,'邮件退信，需核对地址')
   capacity=max(snap.capacity,((high-9)//200+1)*200+8)
   temp=target.with_name('.'+target.stem+'.'+uuid.uuid4().hex+'.tmp.xlsx')
   plan_path=app.data/('sync-'+uuid.uuid4().hex+'.json')
   plan={'source':str(target),'target':str(temp),'writes':writes,'capacity':capacity,'old_capacity':snap.capacity}
   plan_path.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
   run=subprocess.run([str(NODE),str(ROOT/'xlsx_writer.mjs'),str(plan_path)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=180)
   if run.returncode:raise ValueError('Excel写入失败：'+(run.stderr or run.stdout)[-1200:])
   preserve_native_features(target,temp,snap.capacity,capacity,writes)
   check=read_template(temp)
   for item in writes:
    # Check durable message identity and row values before replacing the user's workbook.
    if item['sheet']=='跟进记录' and item['cell'].startswith('N'):
     rr=int(item['cell'][1:])
     if check.rows['跟进记录'].get(rr,{}).get(14)!=item['value']:raise ValueError('写入校验失败，原表未替换。')
   if hashlib.sha256(target.read_bytes()).hexdigest()!=before:raise ValueError('写入期间表格被其他程序修改，已保留原表，稍后重试。')
   backup=app.data/'backups';backup.mkdir(exist_ok=True)
   (backup/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.xlsx')).write_bytes(target.read_bytes())
   os.replace(temp,target);temp=None
   with app.store.conn() as db:
    for cid,code in code_updates.items():db.execute('UPDATE customers SET code=? WHERE id=?',(code,cid))
    for e in pending:db.execute("UPDATE events SET sync_state='synced',sync_error='' WHERE id=?",(e['id'],))
   return {'synced':len(pending)}
  except Exception as e:
   if pending:
    with self.app.store.conn() as db:
     for p in pending:db.execute('UPDATE events SET sync_error=? WHERE id=?',(str(e)[:800],p['id']))
   raise
  finally:
   if guard_fd is not None:
    os.close(guard_fd)
    try:guard.unlink()
    except OSError:pass
   for p in (temp,plan_path):
    if p:
     try:p.unlink(missing_ok=True)
     except OSError:pass
   self.lock.release()
