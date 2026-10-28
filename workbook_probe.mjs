import fs from 'node:fs/promises';
import {Workbook,FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const w=Workbook.create();w.worksheets.add('test');
console.log(w.help('table.resize',{include:'index,examples,notes',maxChars:2000}).ndjson);
const src='E:/Document/Tengxun/WeChat/Document/xwechat_files/wxid_9an6z3uh5fwy22_b428/msg/file/2026-10/FriesGo-海外客户开发跟进空白模板.xlsx';
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(src));
const im=await wb.render({sheetName:'跟进记录',range:'A7:L11',scale:1,format:'png'});
await fs.mkdir('data/qa',{recursive:true});await fs.writeFile('data/qa/template-before.png',new Uint8Array(await im.arrayBuffer()));
