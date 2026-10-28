import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const plan=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(plan.source));
const definitions=[['客户总表',18],['联系人',12],['跟进记录',14],['询盘报价',21],['样品记录',20],['订单记录',19]];
const log=wb.worksheets.getItem('跟进记录');
if(log.getRange('M8').values[0][0] && log.getRange('M8').values[0][0]!=='发送状态')throw new Error('跟进记录M列已有其他用途，未覆盖。');
if(log.getRange('N8').values[0][0] && log.getRange('N8').values[0][0]!=='消息编号')throw new Error('跟进记录N列已有其他用途，未覆盖。');
if(!log.getRange('M8').values[0][0]){
 log.getRange(`M8:N${plan.old_capacity}`).copyFrom(log.getRange(`K8:L${plan.old_capacity}`),'all');
 log.getRange(`M8:N${plan.old_capacity}`).clear({applyTo:'contents'});
 log.getRange('M8:N8').values=[['发送状态','消息编号']];
 log.getRange(`M8:M${plan.capacity}`).format.columnWidth=23;
 log.getRange(`N8:N${plan.capacity}`).format.columnWidth=46;
}
for(const [name,cols] of definitions){
 const sh=wb.worksheets.getItem(name);
 if(plan.capacity>plan.old_capacity){
  for(let row=plan.old_capacity+1;row<=plan.capacity;row++){
   sh.getRangeByIndexes(row-1,0,1,cols).copyFrom(sh.getRangeByIndexes(plan.old_capacity-1,0,1,cols),'all');
   sh.getRangeByIndexes(row-1,0,1,cols).clear({applyTo:'contents'});
  }
  const formulas=sh.getRangeByIndexes(8,0,plan.capacity-8,cols).formulas;
  for(let r=0;r<formulas.length;r++)for(let c=0;c<cols;c++)if(formulas[r][c] && formulas[r][c].includes("'客户总表'!"))sh.getCell(r+8,c).formulas=[[formulas[r][c].replaceAll('$'+plan.old_capacity,'$'+plan.capacity)]];
 }
 for(let row=plan.old_capacity+1;row<=plan.capacity;row++){
  if(name==='客户总表')sh.getRange(`R${row}`).formulas=[[`=IF(A${row}="","",IF(OR(I${row}="暂停跟进",I${row}="停止联系"),"已暂停",IF(N${row}="","待安排日期",IF(N${row}<TODAY(),"逾期",IF(N${row}=TODAY(),"今日跟进","待跟进")))))`]];
  else sh.getRange(`B${row}`).formulas=[[`=IF(A${row}="","",IF(COUNTIFS('客户总表'!$A$9:$A$${plan.capacity},A${row})=0,"客户编号未建档",IF(COUNTIFS('客户总表'!$A$9:$A$${plan.capacity},A${row})>1,"客户编号重复",IF(VLOOKUP(A${row},'客户总表'!$A$9:$B$${plan.capacity},2,FALSE)="","公司名称未填写",VLOOKUP(A${row},'客户总表'!$A$9:$B$${plan.capacity},2,FALSE)))))`]];
  if(name==='询盘报价')sh.getRange(`M${row}`).formulas=[[`=IF(OR(I${row}="",L${row}=""),"",I${row}*L${row})`]];
  if(name==='订单记录')sh.getRange(`K${row}`).formulas=[[`=IF(OR(I${row}="",J${row}=""),"",I${row}-J${row})`]];
 }
}
for(const w of plan.writes){
 const sh=wb.worksheets.getItem(w.sheet),cell=sh.getRange(w.cell);
 cell.values=[[(typeof w.value==='string' && w.value.startsWith('='))?"'"+w.value:w.value]];
 if(w.format)cell.setNumberFormat(w.format);
}
log.getRange(`C8:C${plan.capacity}`).format.columnWidth=25;
log.getRange(`C9:C${plan.capacity}`).format.horizontalAlignment='center';
log.getRange(`H8:H${plan.capacity}`).format.columnWidth=60;
for(const w of plan.writes.filter(w=>w.sheet==='跟进记录'&&/^H\d+$/.test(w.cell))){
 const row=Number(w.cell.slice(1));const width=s=>[...s].reduce((n,c)=>n+(c.charCodeAt(0)>255?2:1),0);
 const lines=String(w.value||'').split('\n').reduce((n,s)=>n+Math.max(1,Math.ceil(width(s)/58)),0);
 log.getRange(`A${row}:N${row}`).format.rowHeight=Math.min(260,Math.max(76,lines*14+12));
}
wb.recalculate();
const result=await SpreadsheetFile.exportXlsx(wb);await result.save(plan.target);
if(plan.preview){
 for(const [name,range,label] of [['客户总表','A7:F11','customer'],['跟进记录','A7:N11','log']]){
  const im=await wb.render({sheetName:name,range,scale:1,format:'png'});
  await fs.writeFile(plan.preview+'-'+label+'.png',new Uint8Array(await im.arrayBuffer()));
 }
}
console.log(JSON.stringify({written:plan.writes.length,capacity:plan.capacity}));
