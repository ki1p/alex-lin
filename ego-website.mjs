import {readFile,writeFile,access} from 'node:fs/promises';
import {kindOf,fieldValue,chooseForm} from './website-rules.mjs';
import {submitOnce} from './website-receipt.mjs';

export async function run(requestPath){
 const req=JSON.parse(await readFile(requestPath,'utf8'));
 const output={status:'needs_attention',url:req.url,fields:[],issues:[]};let task,page,finished=false,submitting=false;
 const save=()=>writeFile(req.folder+'/result.json',JSON.stringify(output,null,2));
 const cancelled=async()=>{try{await access(req.folder+'/cancel');return true;}catch{return false;}};
 const check=async()=>{if(await cancelled()){output.status='cancelled';throw Error('任务已暂停或取消');}};
 // All browser operations use ego APIs; no OS keyboard/clipboard, no window restore, no screenshots.
 const inspect=async()=>page.evaluate(()=>{
  const visible=e=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
  const groups=[...document.querySelectorAll('form,[role="form"]')].filter(visible);
  return groups.map((f,fi)=>{f.setAttribute('data-fg-form',String(fi));return {index:fi,text:f.innerText.slice(0,2500),fields:[...f.querySelectorAll('input,textarea,select')].filter(e=>visible(e)&&!['submit','button','reset','hidden'].includes(e.type)).map((e,i)=>{
   e.setAttribute('data-fg-field',String(i));
   const label=e.labels?.length?[...e.labels].map(l=>l.innerText).join(' '):(e.getAttribute('aria-label')||e.parentElement.innerText.slice(0,130)||'');
   return {selector:'[data-fg-form="'+fi+'"] [data-fg-field="'+i+'"]',label,name:e.name||'',id:e.id||'',placeholder:e.getAttribute('placeholder')||'',tag:e.tagName,type:e.type,required:e.required||e.getAttribute('aria-required')==='true'||/\*|Required|必填/i.test(label),disabled:e.disabled,options:e.tagName==='SELECT'?[...e.options].map(o=>({text:o.text,value:o.value})):[]};
  })};});
 });
 try{
  await check();task=await taskSpace('FriesGO website '+req.id);output.spaceId=task.spaceId;page=task.page('p1');
  console.log(JSON.stringify({spaceId:task.spaceId}));await page.goto(req.url);await check();
  // Known GoDaddy contact-page overlay: close its welcome popup, not a submit control.
  if(new URL(await page.url()).hostname.replace(/^www\./,'')==='aladran.com'){
   await page.evaluate(()=>{
    const close=document.querySelector('#popup-widget14562-close-icon');
    if(close)close.dispatchEvent(new MouseEvent('click',{bubbles:true}));
    const decline=[...document.querySelectorAll('a')].find(a=>a.textContent.trim()==='DECLINE');
    if(decline)decline.click();
   });
  }
  let forms=await inspect();let selected=chooseForm(forms);
  if(!selected){
   const link=await page.evaluate(()=>[...document.querySelectorAll('a[href]')].map(a=>({text:a.innerText.trim(),url:a.href})).filter(a=>/contact|联系我们|联系我|contacto|liên hệ/i.test(a.text+' '+a.url)&&/^https?:/.test(a.url)&&new URL(a.url).hostname===location.hostname).sort((a,b)=>(/contact/i.test(b.text)?1:0)-(/contact/i.test(a.text)?1:0))[0]);
   if(link&&link.url!==await page.url()){await page.goto(link.url);await check();forms=await inspect();selected=chooseForm(forms);}
  }
  if(!selected){
   const opener=await page.evaluate(()=>{const b=[...document.querySelectorAll('button[type="button"],button:not([type])')].filter(b=>!b.closest('form')&&/^(contact us|contactar un asesor|contact an advisor|send (us )?a message|联系我们)$/i.test(b.innerText.trim()));if(b.length===1){b[0].setAttribute('data-fg-open','1');return true;}return false;});
   if(opener){await check();await page.click('[data-fg-open="1"]',{label:'Open company contact form'});forms=await inspect();selected=chooseForm(forms);}
  }
  output.url=await page.url();
  if(!selected){output.issues.push('未找到可识别的联系表单；动态弹窗或嵌入表单需要适配。');}
  else{
   for(const f of selected.fields){
    await check();if(f.disabled)continue;
    const kind=kindOf(f),value=fieldValue(f,req.profile,req.body,req.subject);
    if(!value){if(f.required)output.issues.push('缺少或无法确定必填字段：'+(f.label||f.name||f.id));continue;}
    if(f.tag==='SELECT'){
     const o=f.options.find(o=>o.text.trim().toLowerCase()===value.toLowerCase()||o.value.toLowerCase()===value.toLowerCase());
     if(!o){if(f.required)output.issues.push('没有匹配的选项：'+f.label);continue;}
     await page.selectOption(f.selector,{label:o.text});
    }else await page.fill(f.selector,value);
    const actual=await page.evaluate(s=>{const x=document.querySelector(s);return x?.tagName==='SELECT'?x.selectedOptions[0]?.text:x?.value;},f.selector);
    if(actual!==value)output.issues.push('字段回读不一致：'+(f.label||kind));
    output.fields.push({label:f.label||f.name||kind,kind,value:actual});
   }
   if(!output.fields.some(f=>f.kind==='body'&&f.value===req.body))output.issues.push('留言正文未完整填入。');
   const visibleCaptcha=await page.evaluate(()=>[...document.querySelectorAll('iframe[title*="reCAPTCHA"],iframe[src*="hcaptcha"],input[name*="captcha"]')].some(e=>{const r=e.getBoundingClientRect();return r.width>40&&r.height>30;}));
   if(visibleCaptcha)output.issues.push('页面有交互式验证码，需要接管处理。');
   output.status=output.issues.length?'needs_attention':'filled';
   if(req.mode==='submit'&&output.status==='filled'){
    // Wait after form discovery/typing, so client-side minimum-age guards have elapsed.
    const readyAt=Date.now()+4000;
    while(Date.now()<readyAt){await check();await new Promise(resolve=>setTimeout(resolve,250));}
    if(new URL(output.url).hostname.replace(/^www\./,'')==='aladran.com'){
     const end=Date.now()+35000;let ready=false;
     while(Date.now()<end){await check();ready=await page.evaluate(()=>!!window.wsb?.recaptcha?.siteKey&&typeof window.grecaptcha?.execute==='function');if(ready)break;await new Promise(resolve=>setTimeout(resolve,750));}
     output.providerReady=ready;
     if(!ready){output.status='needs_attention';output.issues.push('验证码官方配置/脚本未就绪；未点击提交，也未发送留言请求。');await save();return;}
    }
    const buttons=await page.evaluate(fi=>[...document.querySelector('[data-fg-form="'+fi+'"]').querySelectorAll('button,input[type="submit"]')].filter(b=>{const r=b.getBoundingClientRect();return r.width>0&&r.height>0&&!b.disabled&&/^(send|send message|submit|submit enquiry|submit inquiry|发送|提交|enviar)$/i.test((b.innerText||b.value).trim());}).map((b,i)=>{b.setAttribute('data-fg-submit',String(i));return '[data-fg-submit="'+i+'"]';}),selected.index);
    if(buttons.length!==1){output.status='needs_attention';output.issues.push('提交按钮或多步骤预览无法唯一确定，已保留填写结果。');}
    else{
     const invalid=await page.evaluate(fi=>[...document.querySelector('[data-fg-form="'+fi+'"]').querySelectorAll('input,textarea,select')].filter(e=>!e.disabled&&e.willValidate&&!e.validity.valid).map(e=>e.name||e.id||e.type),selected.index);
     if(invalid.length){output.status='needs_attention';output.issues.push('表单校验未通过：'+invalid.join(', '));}
     else{
      const before=await page.evaluate(()=>document.body.innerText);
      const result=await submitOnce(page,buttons[0],{before,check,checkpoint:async()=>{await check();await writeFile(req.folder+'/submit-attempted',new Date().toISOString());submitting=true;},persist:async evidence=>{output.receipt=evidence;await save();}});
      output.receipt=result;output.url=result.url||output.url;output.status=result.status;if(result.status!=='submitted')output.issues.push(result.reason);
     }
    }
   }
  }
 }catch(e){output.error=String(e.message||e);output.status=submitting?'uncertain':output.status==='cancelled'?'cancelled':'needs_attention';}
 finally{
  await save();
  if(task&&page&&!finished){
   // Errors caused by user takeover must remain untouched.
   if(!/control|inactive|unassigned|用户.*接管/i.test(output.error||'')){
    try{await task.finish({keep:['p1']});finished=true;}catch(e){output.issues.push('任务空间保留：'+String(e.message||e));await save();}
   }
  }
  console.log(JSON.stringify(output));
 }
}
