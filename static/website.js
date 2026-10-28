'use strict';
const webNav=document.createElement('button');webNav.className='nav';webNav.textContent='◎　官网留言';webNav.dataset.view='website';webNav.onclick=()=>switchView('website');$('nav').append(webNav);
const webSection=document.createElement('section');webSection.id='website';webSection.className='view hidden';
webSection.innerHTML=`<div class="section-head"><div><h2>官网留言 · ego lite</h2><p>自动找联系入口、填写字段并回读结果。预览模式停在提交前；自动提交模式不逐条确认。</p></div><button id="web-new">＋ 准备官网留言</button></div>
<div class="notice" id="web-status"></div><details class="panel"><summary>我的对外联系资料</summary><form id="web-profile"><div class="settings-grid" id="web-profile-fields"></div><button type="submit" class="secondary">保存官网留言资料</button></form></details>
<div class="section-head"><div><h3>官网任务</h3><p>后台按网页元素填写，不使用桌面键盘、剪贴板或窗口截图。需要验证码和复杂表单时保留结果。</p></div><div class="actions"><button id="web-pause" class="secondary">暂停官网任务</button><button id="web-start">启动官网队列</button></div></div>
<div class="table-wrap"><table><thead><tr><th>公司 / 官网</th><th>内容 / 模式</th><th>状态 / 原因</th><th>操作</th></tr></thead><tbody id="web-rows"></tbody></table></div>`;
$('main footer').before(webSection);
const webDialog=document.createElement('dialog');webDialog.id='web-dialog';webDialog.className='wide';
webDialog.innerHTML=`<form id="web-form"><div class="dialog-head"><h2>准备官网留言</h2><button type="button" id="web-close" class="close">×</button></div><input type="hidden" name="id"><label>客户<select name="customer_id" required></select></label><label>官网 / 联系页面<input name="url" type="url" required></label><div class="two"><label>介绍产品<select name="focus"><option value="all">阀门、线缆、PE 管道</option value="valves">阀门</option><option value="cables">电缆与线缆</option><option value="pipes">PE 管道、阀门</option></select></label><label>执行模式<select name="mode"><option value="preview">自动填写和预览（停在提交前）</option><option value="submit">自动填写并提交（不逐条确认）</option></select></label></div><label>主题（表单有该字段时填写）<input name="subject" required maxlength="300"></label><label>英文留言<textarea name="body" rows="13" required maxlength="8000"></textarea></label><p class="hint">正文会根据所选产品生成基础版本，可按客户需求修改。已加入队列的资料和正文会固定保存。</p><div class="dialog-foot"><button type="button" id="web-generate" class="secondary">按产品重新生成</button><button type="submit" class="secondary">保存草稿</button><button type="button" id="web-enqueue">保存并加入官网队列</button></div></form>`;document.body.append(webDialog);
const webStatus={draft:'草稿',queued:'待执行',running:'执行中',filled:'已填写 · 未提交',needs_attention:'需要处理',submitted:'网站已确认提交',uncertain:'提交结果待核实',cancelled:'已取消'};
let webProfileDirty=false;
const webLabels={first_name:'名',last_name:'姓',title:'职位',company:'公司',email:'邮箱',phone:'电话（含区号）',website:'公司官网',country:'国家（英文）',province:'省 / 州（英文）',city:'城市（英文）',street:'街道地址（可选）',postcode:'邮编（可选）',products:'供应产品（英文）'};
$('#web-profile-fields').innerHTML=Object.entries(webLabels).map(([k,v])=>`<label>${esc(v)}<input name="${k}" ${['street','postcode'].includes(k)?'':'required'}></label>`).join('');
function renderWeb(){
 if(!S?.website)return;const w=S.website;
 if(w.running){$('#run-status').textContent='官网任务运行中';$('#run-status').classList.add('green');}
 $('#web-status').textContent=`ego lite ${w.ego_available?'已找到执行器':'执行器未找到'} · ${w.running?'队列运行中':'队列暂停'} · ${w.reason}`;
 $('#web-start').disabled=w.running;$('#web-pause').disabled=!w.running;
 if(!webProfileDirty&&!$('#web-profile').contains(document.activeElement))for(const [k,v]of Object.entries(w.profile))$('#web-profile').elements.namedItem(k).value=v;
 $('#web-rows').innerHTML=w.jobs.map(j=>`<tr><td><strong>${esc(j.name)}</strong><small>${esc(j.url)}</small></td><td>${esc(j.body.slice(0,110))}<small>${j.mode==='submit'?'自动提交':'填写预览'}</small></td><td><strong>${esc(webStatus[j.status]||j.status)}</strong><small>${esc(j.error||(j.result.issues||[]).join('；'))}</small></td><td><div class="row-actions">${j.status==='draft'?`<button data-web-edit="${j.id}">编辑 / 安排</button>`:''}${['filled','needs_attention','cancelled'].includes(j.status)?`<button class="secondary" data-web-copy="${j.id}">另建任务</button>`:''}<a class="button secondary" href="/api/web/preview?id=${encodeURIComponent(j.id)}" target="_blank" rel="noopener">预览记录</a>${['draft','queued','running'].includes(j.status)?`<button class="text-button" data-web-cancel="${j.id}">取消</button>`:''}</div></td></tr>`).join('')||'<tr><td colspan="4" class="empty">选择客户准备官网留言，再启动自动填写。</td></tr>';
 $$('#customer-rows tr').forEach(row=>{const cid=row.querySelector('[data-edit]')?.dataset.edit;if(!cid)return;const c=S.customers.find(c=>c.id===cid);if(c?.state!=='active')return;const b=document.createElement('button');b.className='secondary';b.textContent='官网留言';b.onclick=()=>openWeb(cid);row.querySelector('.row-actions').append(b);});
}
function generateWebBody(){const f=$('#web-form'),c=S.customers.find(x=>x.id===f.customer_id.value),p=S.website.profile;
 const products={all:p.products,valves:'valves',cables:'cables and wires',pipes:'PE pipes and valves'}[f.elements.namedItem('focus').value];
 f.subject.value=`Supply cooperation: ${products} | ${p.company}`;
 f.body.value=`Hello ${c?.name||''} team,\n\nI am ${p.first_name} ${p.last_name}, ${p.title} at ${p.company} in ${p.city}, ${p.province}, ${p.country}. We supply ${products}. I would like to explore potential supply cooperation with your company.\n\nCould you direct me to the purchasing team responsible for these products and share any relevant specifications or supplier registration requirements? We would review your needs and provide suitable product information for evaluation.\n\nBest regards,\n${p.first_name} ${p.last_name} | ${p.title}\n${p.company}\n${p.email}\n${p.phone}\n${p.website}`;
}
function openWeb(cid=null,j=null){const f=$('#web-form');f.reset();f.customer_id.innerHTML=S.customers.filter(c=>c.state==='active').map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');if(cid)f.customer_id.value=cid;
 const c=S.customers.find(c=>c.id===f.customer_id.value);if(!c){toast('请先添加可联系客户');return;}
 f.elements.namedItem('id').value=j?.id||'';f.url.value=j?.url||c.website||'';f.mode.value=j?.mode||'preview';generateWebBody();if(j){f.subject.value=j.subject;f.body.value=j.body;}f.customer_id.disabled=!!j;$('#web-dialog').showModal();
}
function webData(){const f=$('#web-form');if(!f.reportValidity())return null;return {...Object.fromEntries(new FormData(f)),customer_id:f.customer_id.value};}
$('#web-new').onclick=()=>openWeb();$('#web-close').onclick=()=>$('#web-dialog').close();$('#web-generate').onclick=generateWebBody;
$('#web-form').customer_id.onchange=()=>{const f=$('#web-form');f.url.value=S.customers.find(c=>c.id===f.customer_id.value)?.website||'';generateWebBody();};
$('#web-form').focus.onchange=generateWebBody;
$('#web-form').onsubmit=e=>{e.preventDefault();act(async()=>{const d=webData();if(!d)return;await api('/api/web/draft',d);$('#web-dialog').close();switchView('website');toast('官网草稿已保存');});};
$('#web-enqueue').onclick=()=>act(async()=>{const d=webData();if(!d)return;const r=await api('/api/web/draft',d);$('#web-form').elements.namedItem('id').value=r.id;await api('/api/web/queue',{ids:[r.id],mode:d.mode});$('#web-dialog').close();switchView('website');toast(d.mode==='submit'?'已安排自动提交，启动队列后执行':'已安排填写预览，不提交');});
$('#web-profile').onsubmit=e=>{e.preventDefault();act(async()=>{await api('/api/web/profile',Object.fromEntries(new FormData(e.target)));webProfileDirty=false;toast('资料已保存，后续安排的任务使用新资料');});};
$('#web-profile').oninput=()=>{webProfileDirty=true;};
$('#web-start').onclick=()=>act(async()=>{await api('/api/web/start');toast('官网队列已启动');});$('#web-pause').onclick=()=>act(async()=>{await api('/api/web/pause');toast('已暂停官网队列');});
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.webEdit){const j=S.website.jobs.find(j=>j.id===b.dataset.webEdit);openWeb(j.customer_id,j);}if(b.dataset.webCopy){const j=S.website.jobs.find(j=>j.id===b.dataset.webCopy);openWeb(j.customer_id,{...j,id:'',mode:'preview'});}if(b.dataset.webCancel)act(()=>api('/api/web/cancel',{id:b.dataset.webCancel}));});
if(location.hash==='#website')switchView('website');
