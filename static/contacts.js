'use strict';
// Default company-wide planning is explicit in previews; queue endpoints still accept exact message IDs only.
const contactFields=document.createElement('div');contactFields.innerHTML=`<p class="hint">联系策略：本公司全部联系方式分别尝试；已发、待发或结果待确认的地址跳过，收到回复后停止后续任务。</p><label>全部邮箱（每行一个，含主要邮箱）<textarea name="emails" rows="4" placeholder="sales@example.com&#10;purchase@example.com"></textarea></label><label>全部 WhatsApp 候选号码（含国家区号，每行一个）<textarea name="whatsapp_numbers" rows="4" placeholder="+84…&#10;+84…"></textarea></label>`;
$('#customer-form button[type="submit"]').before(contactFields);
const originalOpenCustomer=openCustomer;
openCustomer=function(c={}){originalOpenCustomer(c);const f=$('#customer-form');f.elements.namedItem('emails').value=(c.emails||[c.email]).filter(Boolean).join('\n');f.elements.namedItem('whatsapp_numbers').value=(c.whatsapp_numbers||[]).join('\n');};
function allContactToggle(form,id,label){const e=document.createElement('label');e.className='check';e.innerHTML=`<input type="checkbox" id="${id}" checked> ${label}`;form.querySelector('.dialog-foot').before(e);}
allContactToggle($('#compose-form'),'email-all-contacts','默认向本公司全部邮箱分别准备邮件（每封仅一个收件人）');
allContactToggle($('#wa-form'),'wa-all-contacts','默认检查本公司全部 WhatsApp 号码，向已开通的号码分别准备消息');
let contactPreviewIds=[];
function skippedText(batch){return batch.skipped.map(x=>`${x.recipient}：${x.reason}`).join('\n');}
const originalEmailPreview=$('#preview').onclick;
$('#preview').onclick=()=>{if(!$('#email-all-contacts').checked){contactPreviewIds=[];return originalEmailPreview();}return act(async()=>{
 const d=composeData();if(!d)return;const saved=await api('/api/draft',d);$('#compose-form').elements.namedItem('id').value=saved.id;
 const batch=await api('/api/contacts/prepare',{message_id:saved.id});contactPreviewIds=batch.ids;
 showMessage({...d,recipient:batch.messages.map(m=>m.recipient).join('；')||'无可新联系的邮箱'},batch.ids.length>0);
 const note=document.createElement('pre');note.textContent=`逐一准备 ${batch.ids.length} 个邮箱。\n${skippedText(batch)}`;$('#preview-followup').append(note);
});};
const originalApproveQueue=$('#approve-queue').onclick;
$('#approve-queue').onclick=()=>{if(!contactPreviewIds.length)return originalApproveQueue();return act(async()=>{await api('/api/queue',{ids:contactPreviewIds});contactPreviewIds=[];$('#preview-dialog').close();$('#compose-dialog').close();toast('已按邮箱分别加入队列；未启动发送');switchView('queue');});};
const originalWAPreview=$('#wa-preview').onclick;
$('#wa-preview').onclick=()=>{if(!$('#wa-all-contacts').checked)return originalWAPreview();return act(async()=>{
 const d=waData();if(!d)return;const saved=await api('/api/wa/draft',d);$('#wa-form').elements.namedItem('id').value=saved.id;
 const batch=await api('/api/contacts/prepare',{message_id:saved.id});
 if(!batch.ids.length){toast('本公司号码已全部检查，没有可新发送的号码。\n'+skippedText(batch));return;}
 const preview=`将分别联系：\n${batch.messages.map(m=>m.recipient).join('\n')}\n\n${d.body}\n\n跳过：\n${skippedText(batch)||'无'}\n\n加入队列不会启动发送。`;
 if(await ask('全部 WhatsApp 联系方式预览',preview,'加入已检查号码的队列')){await api('/api/wa/queue',{ids:batch.ids});$('#wa-dialog').close();switchView('whatsapp');toast(`已为 ${batch.ids.length} 个号码分别加入队列`);}
});};
$('#wa-check-all').onclick=()=>act(async()=>{const b=$('#wa-check-all');b.disabled=true;try{let companies=0,numbers=0;for(const c of S.customers.filter(c=>c.state==='active'&&(c.whatsapp_numbers||[]).length)){
 b.textContent=`检查 ${++companies}：${c.name}`;const r=await api('/api/contacts/check-whatsapp',{customer_id:c.id});numbers+=r.checks.length;await refresh();
 }toast(`已逐一检查 ${companies} 家公司的 ${numbers} 个号码，未发送消息。`);}finally{b.disabled=false;b.textContent='检查全部客户的全部号码';}});
