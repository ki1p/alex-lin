import assert from 'node:assert/strict';
import {submitOnce} from '../website-receipt.mjs';
let clicks=0,dismissals=0,phase=0,checkpoints=0;
const page={cdp:async(method)=>method==='Runtime.evaluate'?{result:{value:{text:'Contact us',validationResult:false}}}:{},events:async()=>phase++===0?[]:[{method:'Page.javascriptDialogOpening',params:{type:'alert',message:'phone must contain a number'}}],evaluate:async()=>({url:'https://example.com/contact',formActions:['https://example.com/contact.php']}),click:async()=>{clicks++;return {};},dismissDialog:async()=>{dismissals++;},url:async()=>'https://example.com/contact'};
const result=await submitOnce(page,'button',{before:'Contact us',check:async()=>{},checkpoint:async()=>{checkpoints++;},persist:async()=>{},timeout:1000});
assert.equal(result.status,'needs_attention');assert.equal(clicks,1);assert.equal(checkpoints,1);assert.equal(dismissals,1);assert.equal(result.dialogs[0].message,'phone must contain a number');
console.log('website-receipt: validation dialog handled without re-click');
