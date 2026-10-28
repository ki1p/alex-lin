"""Initialize only the writable output workbook; never writes a communication record."""
import json,subprocess,os
from pathlib import Path
from app import ROOT,Store
from excel_sync import NODE,read_template,preserve_native_features
store=Store(ROOT/'data'/'friesgo.sqlite3');target=Path(store.setting('config')['workbook']);snap=read_template(target)
if snap.summary()['log_rows']:raise SystemExit('工作表已有沟通记录，跳过初始化。')
temp=target.with_name('.'+target.stem+'.init.xlsx');plan_path=ROOT/'data'/'qa'/'init-plan.json'
plan_path.parent.mkdir(parents=True,exist_ok=True)
plan={'source':str(target),'target':str(temp),'capacity':snap.capacity,'old_capacity':snap.capacity,'writes':[]}
plan_path.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
subprocess.run([str(NODE),str(ROOT/'xlsx_writer.mjs'),str(plan_path)],cwd=ROOT,check=True)
preserve_native_features(target,temp,snap.capacity,snap.capacity,[])
check=read_template(temp);assert check.summary()['log_rows']==0
os.replace(temp,target);plan_path.unlink()
print(json.dumps(check.summary(),ensure_ascii=False))
