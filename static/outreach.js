'use strict';
// Kept inside the existing composer: drafting and review never queue messages.
const writingPanel=document.createElement('details');
writingPanel.id='writing-panel';
writingPanel.innerHTML=`<summary>开发信助手 · 他 → 痛 → 证 → 轻</summary><p class="hint">先确认合作阶段与可交付价值，再写客户相关的标题。数字和交期有依据才用，正文兑现标题承诺；试单先明确条件。</p><div class="two">${Object.entries(OutreachRules.fields).map(([key,label])=>`<label>${esc(label)}<textarea data-brief="${key}" rows="2" maxlength="3000"></textarea></label>`).join('')}</div><div class="actions"><button type="button" id="writing-prompt">整理 GPT 提示词</button><button type="button" id="writing-check" class="secondary">检查当前开发信</button></div><label id="writing-output-label" class="hidden">定制提示词 · 复制到 GPT 后生成，再将确认过的主题、英文正文和中文回译填回编辑器<textarea id="writing-output" rows="10" readonly></textarea></label><button type="button" id="writing-copy" class="secondary hidden">复制提示词</button><p class="hint">资料随“保存草稿”保存于本机。整理提示词和检查均在本机完成；复制给 GPT 时才由你分享其中资料。</p>`;
$('#compose-form label:has(input[name="subject"])').before(writingPanel);
const writingReview=document.createElement('div');writingReview.id='writing-review';writingReview.setAttribute('aria-live','polite');
$('#compose-form .dialog-foot').before(writingReview);
function writingBrief(){return Object.fromEntries($$('[data-brief]').map(e=>[e.dataset.brief,e.value.trim()]));}
function checkWriting(){const f=$('#compose-form'),r=OutreachRules.review(f.subject.value,f.body.value,writingBrief());
 writingReview.innerHTML=`<h3>发信前自查 · 约${r.count}词</h3><p class="hint">规则检查只作提示；事实准确性和客户相关性需要人工判断。</p>${r.issues.length?`<ul>${r.issues.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'<p>未发现所检查的格式问题，请继续核对以下内容。</p>'}<ul>${r.manual.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
}
const composeWithWriting=openCompose;
openCompose=function(cid,message=null,copy=false){
 composeWithWriting(cid,message,copy);
 const m=message||S.messages.find(x=>x.customer_id===cid&&x.status==='draft'&&x.channel!=='whatsapp');
 const brief=m?.writing_brief||{};
 $$('[data-brief]').forEach(e=>e.value=brief[e.dataset.brief]||'');
 writingPanel.open=!m;writingReview.replaceChildren();$('#writing-output').value='';$('#writing-output-label').classList.add('hidden');$('#writing-copy').classList.add('hidden');
};
const composeWithBrief=composeData;
composeData=function(){const d=composeWithBrief();if(d)d.writing_brief=writingBrief();return d;};
$('#writing-check').onclick=checkWriting;
$('#writing-prompt').onclick=()=>{const c=S.customers.find(x=>x.id===$('#compose-form').customer_id.value);if(!c)return;
 $('#writing-output').value=OutreachRules.prompt(c,writingBrief());$('#writing-output-label').classList.remove('hidden');$('#writing-copy').classList.remove('hidden');
};
$('#writing-copy').onclick=async()=>{try{await navigator.clipboard.writeText($('#writing-output').value);toast('提示词已复制。');}catch{const e=$('#writing-output');e.focus();e.select();toast('请手动复制已选中的提示词。');}};
// Both single-address and company-wide previews run the same advisory check.
const previewWithWriting=$('#preview').onclick;
$('#preview').onclick=()=>{checkWriting();return previewWithWriting();};
const messageWithWriting=showMessage;
showMessage=function(m,preview=false){messageWithWriting(m,preview);if(!preview)return;
 const r=OutreachRules.review(m.subject,m.body,writingBrief()),note=document.createElement('div');
 note.className='notice';note.textContent=`开发信自查：约${r.count}词。${r.issues.join(' ')||'格式检查未发现问题。'} 请人工核对客户事实、结果来源及下一步。`;
 $('#preview-followup').prepend(note);
};
