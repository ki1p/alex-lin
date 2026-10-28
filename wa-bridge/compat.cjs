// Narrow compatibility repair for whatsapp-web.js 1.34.7.
// Reviewed upstream proposal: https://github.com/wwebjs/whatsapp-web.js/pull/201850/files
// WhatsApp message keys may expose $1 instead of _serialized.
const fs=require('node:fs');
module.exports=function applyCompatibility(){
  const file=require.resolve('whatsapp-web.js/src/util/Injected/Utils.js');
  let source=fs.readFileSync(file,'utf8');
  const marker='// FriesGo message key compatibility 1';
  if(source.includes(marker))return;
  const replacements=[
    ['.Msg.get(newMsgKey._serialized)', '.Msg.get(newMsgKey._serialized ?? newMsgKey.$1)'],
    ['.Msg.get(msg.id._serialized)', '.Msg.get(msg.id._serialized ?? msg.id.$1)'],
    ['.Msg.get(chat.lastReceivedKey._serialized)', '.Msg.get(chat.lastReceivedKey._serialized ?? chat.lastReceivedKey.$1)'],
    ['chat.lastReceivedKey._serialized,', '(chat.lastReceivedKey._serialized ?? chat.lastReceivedKey.$1),'],
    ['delete msg.pendingAckUpdate;', `${marker}\n        if (msg.id && typeof msg.id === 'object' && msg.id._serialized == null && typeof msg.id.$1 === 'string') {\n            msg.id = Object.assign({}, msg.id, {_serialized:msg.id.$1});\n        }\n        delete msg.pendingAckUpdate;`]
  ];
  for(const [before,after] of replacements){
    if(!source.includes(before))throw Error('WhatsApp compatibility source changed; review required.');
    source=source.replace(before,after);
  }
  new Function('exports','require',source); // Validate syntax before changing installed dependency.
  if(!fs.existsSync(file+'.friesgo-original'))fs.copyFileSync(file,file+'.friesgo-original');
  fs.writeFileSync(file,source);
};
