// Pure rules shared by the ego executor and tests. Page text is data, never code.
export function kindOf(f) {
 const s=(f.label+' '+f.name+' '+f.id+' '+f.placeholder).toLowerCase().replace(/[_-]/g,' ');
 if (f.type==='password'||/credit.?card|passport|social.?security/.test(s))return 'restricted';
 if (f.type==='checkbox'||f.type==='radio'||f.type==='file')return 'unsupported';
 if (f.type==='email'||/e.?mail|邮箱|correo/.test(s))return 'email';
 if (/first.?name|given.?name|nombre\(s\)|名（|^名$/.test(s))return 'first_name';
 if (/last.?name|surname|family.?name|apellido|姓/.test(s))return 'last_name';
 if (/company|organisation|organization|empresa|公司/.test(s))return 'company';
 if (/designation|job.?title|position|职位/.test(s))return 'title';
 if (f.type==='tel'||/phone|mobile|telephone|teléfono|电话/.test(s))return 'phone';
 if (/country|país|国家/.test(s))return 'country';
 if (/postal|postcode|zip.?code|邮编/.test(s))return 'postcode';
 if (/province|state|省/.test(s))return 'province';
 if (/city|城市/.test(s))return 'city';
 if (/website|web.?site|官网/.test(s))return 'website';
 if (/address|地址/.test(s))return 'address';
 if (/subject|主题/.test(s))return 'subject';
 if (/message|remark|comment|enquiry|inquiry|mensaje|留言|内容/.test(s))return 'body';
 if (/category|department|industry|分类|部门|行业/.test(s))return 'category';
 if (/name|姓名|联系人/.test(s))return 'full_name';
 return 'unknown';
}
export function fieldValue(field,profile,body,subject){
 const k=kindOf(field);
 if(k==='phone')return String(profile.phone||'').replace(/[\s().-]/g,'').replace(/^00/,'+');
 if(k==='full_name')return [profile.first_name,profile.last_name].filter(Boolean).join(' ');
 if(k==='body')return body;
 if(k==='subject')return subject;
 if(k==='address')return [profile.street,profile.city,profile.province,profile.country,profile.postcode].filter(Boolean).join(', ');
 if(k==='category'){
  const options=field.options||[];
  // Only unambiguous general/business categories; never pretend to be a buyer or select a machine at random.
  const general=options.find(o=>/^(general( inquiry| enquiry)?|business( cooperation| partnership)?|supplier(s| registration)?|partnership|other)$/i.test(o.text.trim()));
  if(general)return general.text;
  if(/PE pipes|valves/i.test(body))return options.find(o=>/water.*waste.*water/i.test(o.text))?.text||'';
  return '';
 }
 return ['unknown','unsupported','restricted'].includes(k)?'':profile[k]||'';
}
export function receiptOutcome({dialogs=[],requests=[],text='',before='',validationResult}={}){
 const failure=/error|invalid|required|must contain|not sent|failed|失败|错误|必填/i;
 const success=/message (?:has been )?(?:sent|submitted)|thank you for (?:contacting|your (?:message|enquiry|inquiry))|successfully (?:sent|submitted)|(?:sent|submitted) successfully|发送成功|提交成功/i;
 const error=dialogs.find(d=>failure.test(d.message||''));
 if(error||validationResult===false)return {status:'needs_attention',reason:error?.message||'网站自定义表单校验未通过，未发出。'};
 const lines=text.split('\n').filter(line=>!before.includes(line));
 const confirmedDialog=dialogs.some(d=>d.type==='alert'&&success.test(d.message||''));
 if(confirmedDialog||lines.some(line=>success.test(line)))return {status:'submitted',reason:'网站返回成功提示。'};
 const failed=requests.find(r=>r.kind==='response'&&r.status>=400);
 if(failed)return {status:'uncertain',reason:'网站提交接口返回 HTTP '+failed.status+'；未确认接收，不自动重发。'};
 return {status:'uncertain',reason:'提交后未取得明确成功回执；不会自动重发。'};
}
export function chooseForm(forms){
 return forms.filter(f=>!f.fields.some(x=>kindOf(x)==='restricted')).map(f=>{
  const kinds=f.fields.map(kindOf);
  return {f,score:(kinds.includes('body')?12:0)+(kinds.includes('email')?3:0)+(kinds.some(x=>/name/.test(x))?2:0)-(/newsletter|subscribe|login|sign.?in|search/i.test(f.text)&&!kinds.includes('body')?25:0)};
 }).filter(x=>x.score>=15).sort((a,b)=>b.score-a.score)[0]?.f;
}
