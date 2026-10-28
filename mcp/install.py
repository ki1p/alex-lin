"""Install only this MCP entry, preserving all other Codex settings byte-for-byte."""
import json,os,shutil,tomllib
from datetime import datetime
from pathlib import Path

root=Path(__file__).resolve().parent
config=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml'
config.parent.mkdir(exist_ok=True,parents=True)
original=config.read_text(encoding='utf-8') if config.exists() else ''
parsed=tomllib.loads(original)
entry={'command':str(root/'.venv/Scripts/python.exe').replace('\\','/'),
       'args':['-X','utf8',str(root/'server.py').replace('\\','/')],
       'cwd':str(root).replace('\\','/'),'startup_timeout_sec':20,'tool_timeout_sec':180,'enabled':True}
old=parsed.get('mcp_servers',{}).get('friesgo-whatsapp')
if old and old!=entry:raise SystemExit('Existing friesgo-whatsapp configuration differs; review before modifying.')
if not old:
    block='\n\n[mcp_servers.friesgo-whatsapp]\n'+'\n'.join(k+' = '+json.dumps(v,ensure_ascii=False) for k,v in entry.items())+'\n'
    updated=original+block;result=tomllib.loads(updated)
    check=dict(result);check['mcp_servers']=dict(check['mcp_servers']);check['mcp_servers'].pop('friesgo-whatsapp')
    baseline=dict(parsed);baseline.setdefault('mcp_servers',{})
    assert check==baseline
    if config.exists():shutil.copy2(config,config.with_name('config.toml.before-whatsapp-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.bak'))
    temp=config.with_name('config.toml.whatsapp.tmp');temp.write_text(updated,encoding='utf-8');os.replace(temp,config)
assert tomllib.loads(config.read_text(encoding='utf-8'))['mcp_servers']['friesgo-whatsapp']==entry
(root/'mcp.json').write_text(json.dumps({'mcpServers':{'friesgo-whatsapp':{k:entry[k] for k in ('command','args','cwd')}}},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'installed':True,'name':'friesgo-whatsapp','config':str(config),'other_servers_preserved':True},ensure_ascii=False))
