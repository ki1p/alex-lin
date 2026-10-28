const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
let S=null,token='',view='customers',draftAttachments=[],previewId='',settingsDirty=false;
const statusNames={draft:'草稿',queued:'待发送',sending:'发送中',submitted:'已提交发送服务',failed:'发送失败',uncertain:'结果待确认',cancelled:'已取消',reply:'收到回复',auto_reply:'自动回复',bounce:'退信',state:'客户状态变更'};
const customerNames={active:'可联系',replied:'已回复',paused:'暂停',stopped:'停止联系',bounced:'退信'};
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function date(s){return s?new Date(s).toLocaleString('zh-CN',{hour12:false}):'—';}
function badge(s,customer=false){const n=(customer?customerNames:statusNames)[s]||s;return `<span class="badge ${['submitted','reply','active','replied','服务器已接受','已送达','已读'].includes(s)?'green':['failed','uncertain','bounced','bounce','stopped'].includes(s)?'red':''}">${esc(n)}</span>`;}
function toast(s){$('#toast').textContent=s;$('#toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('show'),6500);}
async function api(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-FriesGo-Token':token},body:JSON.stringify(data||{})});const v=await r.json();if(!r.ok)throw Error(v.error||'操作失败');return v;}
async function act(fn){try{await fn();await refresh();}catch(e){toast(e.message);}}
async function refresh(){const r=await fetch('/api/state');S=await r.json();render();}
function switchView(name){view=name;$$('.view').forEach(e=>e.classList.toggle('hidden',e.id!==name));$$('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===name));$('#page-title').textContent={customers:'客户与开发信',queue:'发送队列',history:'沟通与写表记录',settings:'邮箱与设置',whatsapp:'WhatsApp 客户联系',website:'官网留言'}[name];render();}
function render(){
 if(!S)return;
 $('#stat-customers').textContent=S.customers.length;$('#stat-queued').textContent=S.counts.queued;$('#queue-count').textContent=S.counts.queued;
 $('#stat-submitted').textContent=S.counts.submitted;$('#stat-sync').textContent=S.pending_sync;
 $('#run-status').textContent=S.running||S.whatsapp?.running?'有队列运行中':'队列已暂停';$('#run-status').classList.toggle('green',S.running||S.whatsapp?.running);
 $('#alert').textContent=S.last_error;$('#alert').classList.toggle('hidden',!S.last_error);
 const needle=$('#search').value.trim().toLowerCase(),filter=$('#filter-state').value;
 const customers=S.customers.filter(c=>(!filter||c.state===filter)&&(!needle||[c.name,c.email,c.code].join(' ').toLowerCase().includes(needle)));
 $('#customer-rows').innerHTML=customers.map(c=>{const drafts=S.messages.filter(m=>m.customer_id===c.id&&m.status==='draft'&&m.channel!=='whatsapp');const last=S.messages.find(m=>m.customer_id===c.id&&m.channel!=='whatsapp');return `<tr><td><strong>${esc(c.name)}</strong><small>${esc(c.code)} · ${esc(c.country)}</small></td><td class="email">${esc(c.email||'尚未核实邮箱')}<small>${esc(c.phone)}</small></td><td>${badge(c.state,true)}</td><td>${drafts.length?`${drafts.length} 封草稿`:last?esc(statusNames[last.status]):'待准备'}<small>${c.note?'有资料备注':''}</small></td><td><div class="row-actions"><button data-compose="${c.id}">${drafts.length?'查看草稿':'写开发信'}</button><button class="secondary" data-edit="${c.id}">资料</button><button class="secondary" data-state="${c.id}" data-next="${c.state==='active'?'paused':'active'}">${c.state==='active'?'暂停':'恢复联系'}</button>${c.state!=='stopped'?`<button class="text-button" data-state="${c.id}" data-next="stopped">停止联系</button>`:''}</div></td></tr>`;}).join('');
 $$('#customer-rows tr').forEach((row,i)=>{const c=customers[i];if(c.state==='active'){const b=document.createElement('button');b.className='secondary';b.textContent='标记已回复';b.dataset.state=c.id;b.dataset.next='replied';row.querySelector('.row-actions').append(b);}});
 $('#empty-customers').classList.toggle('hidden',customers.length>0);
 const cfg=S.config;$('#queue-policy').textContent=`${cfg.timezone} · ${cfg.hour_start}:00–${cfg.hour_end}:00 · 每日最多${cfg.daily_limit}次 · 间隔${cfg.interval_seconds}秒`;
 $('#queue-reason').textContent=S.reason;$('#start').disabled=S.running;$('#pause').disabled=!S.running;
 const queue=S.messages.filter(m=>m.channel!=='whatsapp'&&m.status!=='draft').sort((a,b)=>a.scheduled_at.localeCompare(b.scheduled_at));
 $('#queue-rows').innerHTML=queue.map(m=>`<tr><td><strong>${esc(m.name)}</strong><small>${esc(m.recipient)}</small></td><td>${esc(m.subject)}${m.parent_id?'<small>自动跟进信</small>':''}<small>${esc(m.error)}</small></td><td>${esc(date(m.scheduled_at))}</td><td>${badge(m.status)}</td><td><div class="row-actions"><button class="secondary" data-detail="${m.id}">详情</button>${m.status==='queued'?`<button class="text-button" data-cancel="${m.id}">取消</button>`:''}${['failed','cancelled'].includes(m.status)?`<button class="secondary" data-copy="${m.id}">另建草稿</button>`:''}${m.status==='uncertain'?`<button class="secondary" data-resolve="${m.id}" data-outcome="submitted">核实已发出</button><button class="secondary" data-resolve="${m.id}" data-outcome="failed">核实未发出</button>`:''}</div></td></tr>`).join('')||'<tr><td colspan="5" class="empty">还没有发送任务。先选择客户并预览开发信。</td></tr>';
 $('#monitor-status').textContent=`回复检测：${S.monitoring?'运行中':'未启动'} · 最近完整检查：${date(S.last_poll)} · Excel待补写：${S.pending_sync}条`;
 const historyEvents=S.events.filter((e,i,events)=>e.details?.channel!=='whatsapp'||e.kind!=='submitted'||!events.slice(0,i).some(x=>x.message_id===e.message_id&&x.kind==='submitted'));
 $('#event-list').innerHTML=historyEvents.map(e=>`<article class="event"><div class="event-head"><strong>${esc(e.name)}</strong><span>${badge(e.details?.channel==='whatsapp'&&e.details.delivery?({submitted:'submitted',sent:'服务器已接受',delivered:'已送达',read:'已读',failed_delivery:'投递失败'}[e.details.delivery]||e.kind):e.kind)}　<span class="hint">${esc(date(e.created_at))}</span></span></div><p>${esc(e.details.reply_subject||e.details.subject||customerNames[e.details.state]||'')}</p><p>${esc(e.details.reply_body?.slice(0,700)||e.details.error||e.details.recipient||'')}</p><div class="hint">${e.sync_state==='synced'?'✓ 已写入Excel':'等待写入Excel'} ${e.sync_error?`<span class="error">${esc(e.sync_error)}</span>`:''}</div>${e.message_id?`<button class="text-button" data-detail="${e.message_id}">查看消息原文</button>`:''}</article>`).join('')||'<div class="empty"><strong>沟通记录会出现在这里</strong><p>仅生成草稿或加入队列，不会记作已发送。</p></div>';
 if(!settingsDirty)fillSettings();
 if(typeof renderWA==='function')renderWA();
 if(typeof renderWeb==='function')renderWeb();
}
function fillSettings(){const f=$('#settings-form');for(const[k,v]of Object.entries(S.config)){const e=f.elements.namedItem(k);if(!e)continue;if(e.type==='checkbox')e.checked=!!v;else e.value=v??'';}
 f.owner.innerHTML=S.owners.map(x=>`<option>${esc(x)}</option>`).join('');f.owner.value=S.config.owner;
 $('#weekday-options').innerHTML=['一','二','三','四','五','六','日'].map((n,i)=>`<label><input type="checkbox" value="${i}" ${S.config.weekdays.includes(i)?'checked':''}>周${n}</label>`).join('');
 $('#credential-status').textContent=S.config.password_saved?(S.config.remember_password?'已保存Windows加密凭据。':'凭据仅保存在本次运行内存中。'):'尚未填写授权密码。';
}
function ask(title,content,label='确认'){return new Promise(resolve=>{const d=$('#confirm-dialog');$('#confirm-title').textContent=title;$('#confirm-text').textContent=content;$('#confirm-yes').textContent=label;$('#confirm-yes').onclick=()=>{d.close();resolve(true);};$('#confirm-no').onclick=()=>{d.close();resolve(false);};d.oncancel=()=>resolve(false);d.showModal();});}
function openCustomer(c={}){const f=$('#customer-form');f.reset();for(const[k,v]of Object.entries(c)){const e=f.elements.namedItem(k);if(e)e.value=v??'';}f.code.readOnly=!!c.id;$('#customer-dialog').showModal();}
function toInputTime(s){const d=s?new Date(s):new Date();return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
function openCompose(cid,message=null,copy=false){const c=S.customers.find(x=>x.id===cid);if(!c)return;const f=$('#compose-form');f.reset();
 const m=message||S.messages.find(x=>x.customer_id===cid&&x.status==='draft'&&x.channel!=='whatsapp');
 $('#compose-company').textContent=c.name;f.owner.innerHTML=S.owners.map(x=>`<option>${esc(x)}</option>`).join('');
 f.customer_id.value=cid;f.elements.namedItem('id').value=copy?'':m?.id||'';f.recipient.value=m?.recipient||c.email;f.owner.value=m?.owner||S.config.owner;
 f.subject.value=m?.subject||'Balancing Valve Supply for '+c.name;
 f.body.value=m?.body||`Dear ${c.name} Team,\n\nI’m BaiJiang Lin from FriesGo Global.\n\nWe supply lockable manual balancing valves, self-operated differential pressure control valves, and self-operated flow control valves for suitable water circuits.\n\nMay I send your technical or purchasing team our product catalogue for review?\n\nBest regards,\nBaiJiang Lin | FriesGo Global\n${S.config.sender_email}`;
 f.cn.value=m?.cn||'';f.scheduled_at.value=toInputTime(copy?null:m?.scheduled_at);f.followup_days.value=copy?0:m?.followup_days||0;
 f.followup_body.value=m?.followup_body||`Dear ${c.name} Team,\n\nI’m following up on my earlier email about water-system balancing valves. Could you let me know whether these components fall within your purchasing scope?\n\nIf you prefer not to receive further messages, please let me know.\n\nBest regards,\nBaiJiang Lin | FriesGo Global`;
 draftAttachments=[...(m?.attachments||[])];renderAttachments();$('#compose-dialog').showModal();
}
function renderAttachments(){$('#attachment-list').innerHTML=draftAttachments.map(id=>{const a=S.attachments.find(x=>x.id===id);return `<div>${esc(a?.name||'附件')} <button type="button" data-remove-attachment="${id}">移除</button></div>`;}).join('');}
function composeData(){const f=$('#compose-form');if(!f.reportValidity())return null;const d=Object.fromEntries(new FormData(f));d.scheduled_at=new Date(f.scheduled_at.value).toISOString();d.followup_days=Number(d.followup_days);d.attachments=draftAttachments;return d;}
function showMessage(m,preview=false){$('#preview-to').textContent=`收件人：${m.recipient}　｜　计划：${date(m.scheduled_at)}`;$('#preview-subject').textContent=m.subject;$('#preview-body').textContent=m.body;
 $('#preview-followup').innerHTML=m.followup_days?`<h3>${m.followup_days}天后无回复时，发送以下跟进信</h3><pre>${esc(m.followup_body)}</pre>`:'';
 $('#approve-queue').classList.toggle('hidden',!preview);$('#preview-dialog').showModal();}
$$('.nav').forEach(b=>b.onclick=()=>switchView(b.dataset.view));
$$('[data-close]').forEach(b=>b.onclick=()=>document.getElementById(b.dataset.close).close());
$('#search').oninput=render;$('#filter-state').onchange=render;$('#refresh').onclick=()=>act(refresh);$('#new-customer').onclick=()=>openCustomer();
$('#customer-form').onsubmit=e=>{e.preventDefault();act(async()=>{await api('/api/customer',Object.fromEntries(new FormData(e.target)));$('#customer-dialog').close();toast('客户已保存。');});};
$('#compose-form').onsubmit=e=>{e.preventDefault();act(async()=>{const d=composeData();if(!d)return;await api('/api/draft',d);$('#compose-dialog').close();toast('草稿已保存，未加入发送队列。');});};
$('#preview').onclick=()=>act(async()=>{const d=composeData();if(!d)return;const r=await api('/api/draft',d);previewId=r.id;$('#compose-form').elements.namedItem('id').value=r.id;showMessage(d,true);});
$('#approve-queue').onclick=()=>act(async()=>{await api('/api/queue',{ids:[previewId]});$('#preview-dialog').close();$('#compose-dialog').close();toast('已加入队列。');switchView('queue');});
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
 if(b.dataset.compose)openCompose(b.dataset.compose);
 if(b.dataset.edit)openCustomer(S.customers.find(x=>x.id===b.dataset.edit));
 if(b.dataset.detail){const m=S.messages.find(x=>x.id===b.dataset.detail);if(m)showMessage(m);}
 if(b.dataset.copy){const m=S.messages.find(x=>x.id===b.dataset.copy);openCompose(m.customer_id,m,true);}
 if(b.dataset.cancel)act(async()=>{await api('/api/cancel',{id:b.dataset.cancel});toast('任务已取消。');});
 if(b.dataset.state)act(async()=>{const c=S.customers.find(x=>x.id===b.dataset.state),next=b.dataset.next;
  if(await ask(customerNames[next],`${c.name}：${next==='active'?'恢复后仍需重新预览并安排邮件。':'后续待发送邮件会取消，并同步客户状态到Excel。'}`)){await api('/api/customer-state',{id:c.id,state:next});toast('客户状态已更新。');}});
 if(b.dataset.resolve)act(async()=>{if(await ask('核对发送结果',`请先在邮箱中核实这封邮件。将标记为${b.dataset.outcome==='submitted'?'已提交发送服务':'发送失败'}，不会自动重发。`)){await api('/api/resolve',{id:b.dataset.resolve,outcome:b.dataset.outcome});toast('核对结果已记录。');}});
 if(b.dataset.removeAttachment){draftAttachments=draftAttachments.filter(x=>x!==b.dataset.removeAttachment);renderAttachments();}
});
$('#start').onclick=()=>act(async()=>{if(await ask('启动真实发送',`将使用 ${S.config.sender_email} 发送已确认的队列内容。当前有 ${S.counts.queued} 封待发送邮件，按设置的时段和间隔执行。`,'启动发送')){await api('/api/start');toast('队列已启动。');}});
$('#pause').onclick=()=>act(async()=>{await api('/api/pause');toast('已暂停后续发送。');});
$('#sync').onclick=()=>act(async()=>{const r=await api('/api/sync');toast(`已同步 ${r.synced||0} 条记录。`);});
$('#poll').onclick=()=>act(async()=>{const r=await api('/api/poll');toast(`检查完成，匹配 ${r.matched} 条回复。`);});
$('#settings-form').oninput=()=>{settingsDirty=true;};$('#settings-form').onchange=()=>{settingsDirty=true;};
function settingsData(){const f=$('#settings-form'),d=Object.fromEntries(new FormData(f));d.imap_enabled=f.imap_enabled.checked;d.remember_password=f.remember_password.checked;d.weekdays=$$('#weekday-options input:checked').map(x=>Number(x.value));return d;}
$('#settings-form').onsubmit=e=>{e.preventDefault();act(async()=>{await api('/api/config',settingsData());settingsDirty=false;e.target.smtp_password.value='';e.target.imap_password.value='';toast('设置已保存。');});};
$('#check-mail').onclick=()=>act(async()=>{const r=await api('/api/check-mail');toast(r.message);});
$('#inspect-book').onclick=()=>act(async()=>{const r=await api('/api/inspect-book');$('#book-info').textContent=`结构正确：${r.customers}家客户，${r.log_rows}条跟进记录，当前预留${r.capacity}行。`;});
$('#import-book').onclick=()=>act(async()=>{const r=await api('/api/import-workbook');toast(`已导入 ${r.imported} 家客户。`);});
$('#clear-password').onclick=()=>act(async()=>{if(await ask('清除邮箱凭据','清除本次运行及本机加密保存的邮箱密码。')){await api('/api/config',{...settingsData(),clear_password:true,remember_password:false});settingsDirty=false;toast('凭据已清除。');}});
$('#import-known').onclick=()=>act(async()=>{const r=await api('/api/import-known');toast(`已导入 ${r.imported} 家客户及可用草稿。\n${r.errors?.join('\n')||'所有邮件均未发送。'}`);});
$('#csv-input').onchange=e=>act(async()=>{const f=e.target.files[0];if(!f)return;const r=await api('/api/import',{csv:await f.text()});toast(`已导入 ${r.imported} 家客户。\n${r.errors?.join('\n')||''}`);e.target.value='';});
$('#attachment-input').onchange=e=>act(async()=>{for(const file of e.target.files){if(file.size>12*1024*1024)throw Error('单个附件不能超过12MB。');const encoded=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});const a=await api('/api/attachment',{name:file.name,base64:encoded});S.attachments.push(a);draftAttachments.push(a.id);}renderAttachments();e.target.value='';});
(async()=>{try{const r=await fetch('/api/bootstrap'),d=await r.json();token=d.token;S=d.state;render();const mid=new URLSearchParams(location.search).get('id');if(mid){const m=S.messages.find(x=>x.id===mid);if(m)showMessage(m);}}catch(e){toast('连接本地服务失败：'+e.message);}})();
setInterval(()=>{if(!$$('dialog[open]').length&&!settingsDirty)refresh().catch(()=>{});},5000);
