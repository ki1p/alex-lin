// Local child process; no listening TCP port, no exported cookies or credentials.
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
require('./compat.cjs')();
const {Client, LocalAuth} = require('whatsapp-web.js');
const QR = require('qrcode');
const data = process.env.FRIESGO_WA_DATA;
if (!data) throw Error('Missing local data directory');
fs.mkdirSync(data, {recursive:true});
const emit = obj => process.stdout.write(JSON.stringify(obj)+'\n');
console.log = (...args) => process.stderr.write(args.join(' ')+'\n');
let client, status='disconnected', account='', starting=false;
const outboxDir=path.join(data,'outbox');fs.mkdirSync(outboxDir,{recursive:true});
function save(id, value) {
  const file=path.join(outboxDir,id+'.json');
  fs.writeFileSync(file+'.tmp',JSON.stringify(value),{mode:0o600});
  fs.renameSync(file+'.tmp',file);
}
function state(extra={}) {console.log(new Date().toISOString(),status,extra.error||'');emit({event:'state',status,account,...extra});}
async function initialize() {
  if (starting || client) return;
  starting=true;status='connecting';state();
  client=new Client({authStrategy:new LocalAuth({clientId:'friesgo',dataPath:path.join(data,'session')}),
    webVersionCache:{type:'none'},
    puppeteer:{headless:false,executablePath:process.env.FRIESGO_CHROME,
      args:['--window-size=1100,800']}});
  const attachListeners=client.attachEventListeners.bind(client);
  client.attachEventListeners=async()=>{try{return await attachListeners();}catch(e){console.log('EVENT_SETUP_FAILED',String(e?.stack||e).slice(0,1200));throw e;}};
  client.on('qr', async qr=>{status='qr';account='';state({qr:await QR.toDataURL(qr,{width:280,margin:2})});});
  client.on('authenticated',()=>{status='loading';state({qr:''});});
  client.on('ready',()=>{const user=client.info?.wid?.user;if(!user){status='error';state({error:'WhatsApp未返回发件账号，请重新连接。'});return;}status='ready';account=user;starting=false;state({qr:''});});
  client.on('auth_failure',()=>{status='error';account='';state({error:'登录授权失败，请重新连接。',qr:''});});
  client.on('disconnected',()=>{status='disconnected';account='';state({qr:'',error:'WhatsApp已断开，发送队列已暂停。'});});
  client.on('message_ack',(msg,ack)=>emit({event:'ack',message_id:msg.id._serialized,ack,account}));
  client.on('message',async msg=>{
    if(msg.fromMe || msg.from.endsWith('@g.us') || msg.from==='status@broadcast')return;
    try {
      const contact=await msg.getContact();
      emit({event:'incoming',account,number:contact.number,id:msg.id._serialized,body:msg.body||'',timestamp:msg.timestamp});
    }catch(e){/* Never infer a phone number from an opaque LID. */}
  });
  try {await client.initialize();} catch(e) {status='error';starting=false;state({error:String(e.message).slice(0,500)});}
}
let busy=false;
async function command(c) {
  if(c.op==='connect'){initialize();return {ok:true};}
  if(c.op==='reconnect'){
    if(busy)throw Error('发送处理中，请先暂停并等待结果。');
    if(client){client.removeAllListeners();await client.destroy();client=null;}
    starting=false;account='';status='disconnected';initialize();return {ok:true};
  }
  if(c.op==='status')return {status,account};
  if(c.op==='diagnostics'){
    const d={status,hasClient:!!client,hasInfo:!!client?.info,hasAccount:!!client?.info?.wid?.user,account:client?.info?.wid?.user||''};
    if(client){try{d.connection=await Promise.race([client.getState(),new Promise((_,reject)=>setTimeout(()=>reject(Error('state query timed out')),6000))]);}catch(e){d.error=String(e.message).slice(0,400);}}
    return d;
  }
  if(c.op==='check'){
    if(!/^\+[1-9]\d{7,14}$/.test(c.number))throw Error('Invalid phone number');
    if(!client?.info?.wid?.user||client.info.wid.user!==c.account||await client.getState()!=='CONNECTED')throw Error('WhatsApp查询连接尚未就绪，未检查号码。');
    if(busy)throw Error('正在发送，请先暂停队列再检查号码。');
    try {
      const target=await client.getNumberId(c.number.slice(1));
      if(client.info.wid.user!==c.account||await client.getState()!=='CONNECTED')throw Error('号码检查期间账号连接变化。');
      return {number:c.number,account:c.account,registration:target?'registered':'not_registered'};
    }catch(e){status='error';state({error:'号码检查连接异常，请重新连接。'});throw e;}
  }
  if(c.op!=='send')throw Error('Unsupported command');
  if(!/^[a-f0-9]{32}$/.test(c.key)||!/^\+[1-9]\d{7,14}$/.test(c.number)||typeof c.body!=='string'||!c.body.trim()||c.body.length>12000)throw Error('Invalid message');
  const file=path.join(outboxDir,c.key+'.json');
  if(fs.existsSync(file))return JSON.parse(fs.readFileSync(file,'utf8'));
  if(status!=='ready'||account!==c.account)return {status:'failed',error:'WhatsApp连接或发件账号已变化；未调用发送。'};
  if(busy)return {status:'failed',error:'WhatsApp正在处理另一条消息；未调用发送。'};
  busy=true;
  try {
    let target;
    try {target=await client.getNumberId(c.number.slice(1));}
    catch(e){status='error';state({error:'WhatsApp页面连接失效，请重新连接。'});return {status:'failed',error:'号码检查失败，未调用发送：'+String(e.message).slice(0,300)};}
    if(!target)return {status:'failed',error:'该号码未查到WhatsApp账号；未发送。'};
    if(status!=='ready'||account!==c.account)return {status:'failed',error:'账号连接变化，未发送。'};
    save(c.key,{status:'uncertain',error:'已进入发送步骤，需核实聊天记录；禁止自动重发。'});
    try {
      const msg=await client.sendMessage(target._serialized,c.body,{sendSeen:false});
      const remoteId=msg?.id?._serialized ?? msg?.id?.$1;
      if(!remoteId)throw Error('WhatsApp没有返回消息编号，需要核实聊天记录。');
      const result={status:'submitted',remote_id:remoteId,ack:msg.ack};save(c.key,result);return result;
    }catch(e){const result={status:'uncertain',error:'发送调用未返回确定结果：'+String(e.message).slice(0,400)};save(c.key,result);return result;}
  }finally{busy=false;}
}
const input=readline.createInterface({input:process.stdin});
input.on('line',line=>{let c;try{c=JSON.parse(line);}catch{return;}
  command(c).then(result=>emit({id:c.id,result})).catch(e=>emit({id:c.id,error:String(e.message).slice(0,500)}));});
input.on('close',async()=>{try{if(client)await client.destroy();}finally{process.exit(0);}});
state();
