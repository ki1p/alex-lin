'use strict';
let waPreviewId='';
const waDelivery={submitted:'已提交（待回执）',sent:'服务器已接受',delivered:'已送达',read:'已读',failed_delivery:'投递失败'};
const waNav=document.createElement('button');waNav.className='nav';waNav.dataset.view='whatsapp';waNav.textContent='◉　WhatsApp';waNav.onclick=()=>switchView('whatsapp');$('nav').append(waNav);
const waSection=document.createElement('section');waSection.id='whatsapp';waSection.className='view hidden';
waSection.innerHTML=`<div class="section-head"><div><h2>WhatsApp 客户联系</h2><p>先连接账号，再准备消息。每次发送后写入同一份跟进表。</p></div><div class="actions"><button id="wa-connect" class="secondary">连接 WhatsApp</button><button id="wa-new">＋ 准备消息</button></div></div>
<div class="settings-grid"><div class="panel"><h3 id="wa-status">尚未连接</h3><p id="wa-account"></p><p id="wa-connection-error" class="error"></p><img id="wa-qr" class="hidden" width="280" height="280" alt="WhatsApp关联设备二维码"><p class="hint">首次连接会打开专用 Chrome 窗口。手机 WhatsApp → 设置／菜单 → 已关联设备 → 关联设备，用现在的账号扫码。关联登录会保存在本机，可从手机取消关联。</p><p class="hint">使用非官方 WhatsApp Web 接入，可能失效或导致账号受限。连接成功不代表可以无限量发送。</p></div>
<form id="wa-settings" class="panel"><h3>WhatsApp 发送节奏</h3><div class="two"><label>每天最多尝试（UTC）<input name="daily_limit" type="number" min="1" max="100" value="20" required></label><label>两次尝试间隔（秒）<input name="interval_seconds" type="number" min="30" max="86400" value="120" required></label></div><p class="hint">独立于邮件队列。只发送已加入队列且到达计划时间的消息，程序重启后暂停。</p><button class="secondary" type="submit">保存发送节奏</button></form></div>
<div class="section-head wa-spacing"><div><h3>WhatsApp 发送队列</h3><p id="wa-reason"></p></div><div class="actions"><button id="wa-pause" class="secondary">暂停 WhatsApp</button><button id="wa-start">启动 WhatsApp 队列</button></div></div><div class="table-wrap"><table><thead><tr><th>客户／号码</th><th>内容／计划时间</th><th>状态</th><th>操作</th></tr></thead><tbody id="wa-rows"></tbody></table></div>`;
$('main footer').before(waSection);
const waDialog=document.createElement('dialog');waDialog.id='wa-dialog';waDialog.className='wide';
const waChecks=document.createElement('div');waChecks.className='panel wa-spacing';waChecks.innerHTML='<h3>号码检查（不发送消息）</h3><p class="hint">仅发送24小时内检查通过的号码。检查失败不等于未开通。</p><button id="wa-check-all" class="secondary">检查全部客户号码</button><div id="wa-check-results"></div>';$('#wa-rows').closest('.table-wrap').before(waChecks);
waDialog.innerHTML=`<form id="wa-form"><div class="dialog-head"><h2>准备 WhatsApp 消息</h2><button type="button" id="wa-close" class="close">×</button></div><input name="id" type="hidden"><label>客户<select name="customer_id" required></select></label><div class="two"><label>WhatsApp 国际号码<input name="recipient" placeholder="+84…（一个号码）" required></label><label>业务员<select name="owner"></select></label></div><div class="two"><label>实际发送文字<textarea name="body" rows="10" maxlength="12000" required></textarea></label><label>中文参考，不发送<textarea name="cn" rows="10" maxlength="12000"></textarea></label></div><label>计划发送时间（电脑本地时间）<input name="scheduled_at" type="datetime-local" required></label><p class="hint">号码不一定开通了 WhatsApp。发送前会检查；无效号码会记录失败并暂停。首版支持文字消息。</p><div class="dialog-foot"><button type="submit" class="secondary">保存 WhatsApp 草稿</button><button type="button" id="wa-preview">预览并加入 WhatsApp 队列</button></div></form>`;
document.body.append(waDialog);
function renderWA(){
 if(!S?.whatsapp)return;
 const w=S.whatsapp,names={disconnected:'尚未连接',connecting:'正在打开 WhatsApp',qr:'请用手机扫码关联',loading:'已授权，正在加载',ready:'WhatsApp 已连接',error:'连接异常'};
 $('#wa-status').textContent=names[w.status]||w.status;$('#wa-account').textContent=w.account?'当前发件号码：+'+w.account:'等待关联账号';$('#wa-connection-error').textContent=w.error||'';
 $('#wa-qr').classList.toggle('hidden',!w.qr);if(w.qr&&$('#wa-qr').getAttribute('src')!==w.qr)$('#wa-qr').src=w.qr;
 $('#wa-connect').disabled=['connecting','loading','qr','ready'].includes(w.status);$('#wa-start').disabled=w.running||w.status!=='ready';$('#wa-pause').disabled=!w.running;
 $('#wa-reason').textContent=(w.running?'运行中 · ':'已暂停 · ')+w.reason;
 if(!$('#wa-settings').contains(document.activeElement))for(const [k,v]of Object.entries(w.settings))$('#wa-settings').elements.namedItem(k).value=v;
 const messages=S.messages.filter(m=>m.channel==='whatsapp');
 const checks=w.number_checks||[];
 $('#wa-check-results').innerHTML=checks.filter(c=>c.account===w.account).map(c=>`<p><strong>${esc(S.customers.find(x=>x.id===c.customer_id)?.name||'')}</strong> · ${esc(c.number)} · ${esc({registered:'已开通，可发送',not_registered:'未开通，不发送',error:'检查失败，待重新检查'}[c.registration])}<small>${esc(date(c.checked_at))} ${esc(c.error)}</small></p>`).join('');
 $('#wa-rows').innerHTML=messages.map(m=>`<tr><td><strong>${esc(m.name)}</strong><small>${esc(m.recipient)}</small>${m.wa_account?`<small>发件：+${esc(m.wa_account)}</small>`:''}</td><td>${esc(m.body.slice(0,100))}<small>${esc(date(m.scheduled_at))}</small><small class="error">${esc(m.error)}</small></td><td>${badge(m.status)}<small>${esc(waDelivery[m.wa_delivery]||'')}</small></td><td><div class="row-actions"><button class="secondary" data-wa-detail="${m.id}">查看全文</button>${m.status==='draft'?`<button data-wa-edit="${m.id}">编辑／预览</button>`:''}${['draft','queued'].includes(m.status)?`<button class="text-button" data-wa-cancel="${m.id}">取消</button>`:''}${m.status==='uncertain'?`<button class="secondary" data-wa-resolve="${m.id}" data-outcome="submitted">核实已发出</button><button class="secondary" data-wa-resolve="${m.id}" data-outcome="failed">核实未发出</button>`:''}</div></td></tr>`).join('')||'<tr><td colspan="4" class="empty">还没有 WhatsApp 消息。先连接账号，再选择客户准备内容。</td></tr>';
 $$('#customer-rows tr').forEach((row,i)=>{const cid=row.querySelector('[data-edit]')?.dataset.edit;if(!cid)return;const b=document.createElement('button');b.className='secondary';b.textContent='WhatsApp';b.onclick=()=>openWA(cid);row.querySelector('.row-actions').append(b);});
}
function waBody(c){return `Hello ${c.name} Team,\n\nI'm BaiJiang Lin from FriesGo Global. We supply manual balancing valves, differential pressure control valves and flow control valves for water circulation systems.\n\nMay I send your engineering or purchasing team our catalogue for review?\n\nIf this is not relevant, please let me know and I will stop contacting you.`;}
function openWA(cid=null,m=null){const f=$('#wa-form');f.reset();f.customer_id.innerHTML=S.customers.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');f.owner.innerHTML=S.owners.map(x=>`<option>${esc(x)}</option>`).join('');f.owner.value=S.config.owner;if(cid)f.customer_id.value=cid;
 const c=S.customers.find(c=>c.id===f.customer_id.value);if(!c){toast('请先添加客户');return;}
 f.elements.namedItem('id').value=m?.id||'';f.recipient.value=m?.recipient||c.phone||'';f.body.value=m?.body||waBody(c);f.cn.value=m?.cn||'您好，我们供应水循环系统使用的平衡阀、压差控制阀和流量控制阀。能否向贵公司的工程或采购团队发送产品目录？如不相关，请告知，我们会停止联系。';f.scheduled_at.value=toInputTime(m?.scheduled_at);if(m)f.owner.value=m.owner;
 f.customer_id.disabled=!!m;$('#wa-dialog').showModal();}
function waData(){const f=$('#wa-form');if(!f.reportValidity())return null;return {...Object.fromEntries(new FormData(f)),customer_id:f.customer_id.value,scheduled_at:new Date(f.scheduled_at.value).toISOString()};}
$('#wa-close').onclick=()=>$('#wa-dialog').close();$('#wa-new').onclick=()=>openWA();
$('#wa-check-all').onclick=()=>act(async()=>{const b=$('#wa-check-all');b.disabled=true;try{let n=0;for(const c of S.customers.filter(c=>c.phone&&c.state==='active')){b.textContent=`正在检查 ${++n}：${c.name}`;const r=await api('/api/wa/check-number',{customer_id:c.id});await refresh();if(r.check.registration==='error')throw Error('号码检查连接失败，已停止检查：'+r.check.error);await new Promise(resolve=>setTimeout(resolve,2000));}toast('号码检查完成，未发送消息。');}finally{b.disabled=false;b.textContent='检查全部客户号码';}});
$('#wa-form').customer_id.onchange=()=>{const f=$('#wa-form'),c=S.customers.find(c=>c.id===f.customer_id.value);f.recipient.value=c.phone||'';f.body.value=waBody(c);};
$('#wa-connect').onclick=()=>act(async()=>{await api('/api/wa/connect');toast('已启动连接。请在新窗口或工作台二维码处完成手机关联。');});
const waReconnect=document.createElement('button');waReconnect.textContent='重新连接';waReconnect.className='secondary';waReconnect.onclick=()=>act(async()=>{await api('/api/wa/reconnect');toast('正在重新连接，队列保持暂停。');});$('#wa-connect').after(waReconnect);
$('#wa-settings').onsubmit=e=>{e.preventDefault();act(async()=>{await api('/api/wa/config',Object.fromEntries(new FormData(e.target)));toast('WhatsApp发送节奏已保存');});};
$('#wa-form').onsubmit=e=>{e.preventDefault();act(async()=>{const d=waData();if(!d)return;await api('/api/wa/draft',d);$('#wa-dialog').close();switchView('whatsapp');toast('已保存草稿，未发送');});};
$('#wa-preview').onclick=()=>act(async()=>{const d=waData();if(!d)return;const r=await api('/api/wa/draft',d);$('#wa-form').elements.namedItem('id').value=r.id;waPreviewId=r.id;
 if(await ask('确认 WhatsApp 内容',`发件账号：+${S.whatsapp.account||'尚未连接'}\n客户号码：${d.recipient}\n\n${d.body}\n\n先检查号码，加入队列后仍需点击启动。`,'检查号码并加入队列')){const c=await api('/api/wa/check-number',{customer_id:d.customer_id,recipient:d.recipient});if(c.check.registration!=='registered')throw Error(c.check.registration==='not_registered'?'该号码未开通WhatsApp，草稿已保留。':'检查失败：'+c.check.error);await api('/api/wa/queue',{ids:[r.id]});$('#wa-dialog').close();switchView('whatsapp');toast('号码检查通过，已加入WhatsApp队列，未启动发送');}});
$('#wa-start').onclick=()=>act(async()=>{const n=S.messages.filter(m=>m.channel==='whatsapp'&&m.status==='queued').length;
 if(await ask('启动 WhatsApp 真实发送',`将使用 +${S.whatsapp.account} 向已预览的 ${n} 位收件人发送队列中的内容，并逐条记录到Excel。`,'启动发送'))await api('/api/wa/start',{account:S.whatsapp.account});});
$('#wa-pause').onclick=()=>act(async()=>{await api('/api/wa/pause');toast('WhatsApp队列已暂停');});
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
 if(b.dataset.waEdit){const m=S.messages.find(x=>x.id===b.dataset.waEdit);openWA(m.customer_id,m);}
 if(b.dataset.waDetail){const m=S.messages.find(x=>x.id===b.dataset.waDetail);showMessage(m);}
 if(b.dataset.waCancel)act(async()=>{await api('/api/cancel',{id:b.dataset.waCancel});});
 if(b.dataset.waResolve)act(async()=>{if(await ask('核对WhatsApp发送结果','请先在WhatsApp聊天记录中核实。此次仅记录结果，不会重发。'))await api('/api/wa/resolve',{id:b.dataset.waResolve,outcome:b.dataset.outcome});});
});
