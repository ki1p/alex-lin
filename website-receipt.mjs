import {receiptOutcome} from './website-rules.mjs';

// Records dialogs and network evidence before looking at DOM text; no automatic re-clicks.
export async function submitOnce(page,selector,{before,check,checkpoint,persist,timeout=45000}){
 const dialogs=[],requests=[],seen=new Set();let receipt,clicked=false;
 await page.cdp('Page.enable');await page.cdp('Network.enable');await page.events();
 const base=await page.evaluate(()=>({url:location.href,formActions:[...document.forms].filter(f=>f.method.toLowerCase()==='post').map(f=>f.action)}));
 const relevant=(url,method)=>method==='POST'&&(base.formActions.includes(url)||/\/v3\/messages(?:\?|$)/.test(url));
 const requestIds=new Set();
 async function collect(){
  for(const e of await page.events()){
   const p=e.params||{};
   if(e.method==='Page.javascriptDialogOpening'){
    const key=p.type+'|'+p.message;if(!seen.has(key)){seen.add(key);dialogs.push({type:p.type,message:p.message});}
   }
   if(e.method==='Network.requestWillBeSent'&&relevant(p.request?.url||'',p.request?.method)){
    requestIds.add(p.requestId);requests.push({kind:'request',requestId:p.requestId,url:p.request.url.split('?')[0],method:p.request.method});
   }
   if(e.method==='Network.responseReceived'&&requestIds.has(p.requestId))requests.push({kind:'response',requestId:p.requestId,status:p.response.status,url:p.response.url.split('?')[0]});
   if(e.method==='Network.loadingFailed'&&requestIds.has(p.requestId))requests.push({kind:'failure',requestId:p.requestId,error:p.errorText});
  }
  return {dialogs,requests};
 }
 await check();await checkpoint();
 receipt=await page.click(selector,{label:'Submit company supply inquiry'});clicked=true;
 await persist({clickReceipt:receipt,dialogs,requests});
 if(receipt?.dialog){const d=receipt.dialog;dialogs.push({type:d.type||'alert',message:d.message||d.text||''});}
 const end=Date.now()+timeout;
 let text='',validationResult,handledDialogs=0;
 while(Date.now()<end){
  await collect();
  if(dialogs.length>handledDialogs){
   // Dismiss alerts (including validation errors); never approve a confirm/prompt.
   try{await page.dismissDialog();}catch{}
   handledDialogs=dialogs.length;
   if(dialogs.some(d=>d.type!=='alert'))return {status:'needs_attention',reason:'网站要求额外确认，已取消该提示。',clickReceipt:receipt,dialogs,requests};
  }
  try{const s=await page.cdp('Runtime.evaluate',{expression:'({text:document.body.innerText,validationResult:document.MM_returnValue,url:location.href})',returnByValue:true,timeout:1500});const v=s.result?.value;if(v){text=v.text;validationResult=v.validationResult;}}catch{}
  const result=receiptOutcome({dialogs,requests,text,before,validationResult});
  await persist({...result,clickReceipt:receipt,dialogs,requests,url:await page.url().catch(()=>base.url)});
  if(result.status!=='uncertain'||requests.some(r=>r.kind==='response'&&r.status>=400))return {...result,clickReceipt:receipt,dialogs,requests,url:await page.url().catch(()=>base.url)};
  try{await check();}catch{return {status:'uncertain',reason:'提交后任务暂停，结果待核实；不会重发。',clickReceipt:receipt,dialogs,requests};}
  await new Promise(resolve=>setTimeout(resolve,500));
 }
 return {...receiptOutcome({dialogs,requests,text,before,validationResult}),clickReceipt:receipt,dialogs,requests,clicked};
}
