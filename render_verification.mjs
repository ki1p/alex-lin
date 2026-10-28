import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load('data/qa/验证用跟进表.xlsx'));
for(const [sheetName,range,file] of [['客户总表','A7:F11','customer-after'],['跟进记录','A7:F11','log-left'],['跟进记录','H7:N11','log-right'],['跟进记录','A207:F210','extended-row']]){
 const im=await wb.render({sheetName,range,scale:1,format:'png'});await fs.writeFile(`data/qa/${file}.png`,new Uint8Array(await im.arrayBuffer()));
}
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:10},summary:'QA formula scan',maxChars:1800})).ndjson);
