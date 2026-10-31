"""Export readable guides from the same versioned JSON used by SQLite."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
LABELS={'cultural_reference':'来源事实／文化参考','source_attested_phrase':'来源短语；未做母语专项复核','authored_example':'自编示例','practice_hypothesis':'自拟实践建议；未验证'}

def main():
    d=json.loads((ROOT/'data.json').read_text(encoding='utf-8'))
    sources={s['id']:s for s in d['sources']}
    cats={c['id']:c['name_zh'] for c in d['categories']}
    full=[c for c in d['countries'] if c['coverage']=='new_full_profile']
    linked=[c for c in d['countries'] if c['coverage']=='linked_existing']
    for c in d['countries']:
        code=c['code']; filename='COMMON.md' if code=='GLOBAL' else code+'.md'
        lines=[f'# {c["name_zh"]}：市场、文化与日常沟通','','2026-10-31 · [总入口](README.md) · [通用生活与沟通](COMMON.md) · [联系时间](CONTACT_POLICY.md)','',c['overview'],'']
        if c['coverage']=='linked_existing':
            lines.extend(['本轮仅建立关联索引，不表示重新筛查了该市场。','',f'[阅读既有完整资料]({c["profile_link"]})',''])
        elif code!='GLOBAL':
            lines.extend(['**市场入选理由：** '+c['selection_reason'],'','**调研次序：** '+c['research_priority']+'（自拟；不是成交概率）','','**语言：** '+c['languages'],'','**区域差异：** '+c['regions'],'','个人偏好、起床／入睡、午睡、爱好均为未知；文化话题供礼貌提问，不代表客户本人。',''])
        for cat,label in cats.items():
            rows=[r for r in d['records'] if r['country']==code and r['category']==cat]
            if not rows:continue
            lines.extend(['## '+label,''])
            for r in rows:
                lines.extend([f'### {r["id"]} · {r["title"]}','',f'**{LABELS[r["evidence"]]}**','',r['summary'],'',r['body'],'',f'适用范围：{r["scope"]}',''])
                x=r['details']
                if r['kind']=='phrase':
                    lines.extend([f'- 原文：{x["text"]}',f'- 中文：{x["meaning_zh"]}',f'- 英文：{x["meaning_en"]}',f'- 语气：{x["register"]}',f'- 适合：{x["when_to_use"]}',f'- 避免：{x["when_not_to_use"]}',''])
                    if x.get('transliteration'):lines.extend(['阅读辅助：'+x['transliteration'],''])
                elif r['kind']=='project_signal':lines.extend([f'资料阶段：`{x["stage"]}`；当前采购已核实：**否**。','',x['next_check'],''])
                elif r['kind']=='language_variety':lines.extend(['分类：`'+x['variety_type']+'`；'+x['classification_limit'],''])
                elif r['kind']=='rule':lines.extend([f'初始范围：{x["min"]}—{x["max"]} {x["unit"]}；覆盖条件：{x["override"]}。',''])
                for ref in r['sources']:
                    s=sources[ref['source']]
                    lines.extend([f'来源 [{s["id"]} · {s["title"]}]({s["url"]})：{ref["supports"]}',''])
        if code!='GLOBAL':lines.extend(['## 也要阅读通用场景','','[称呼／倾听／作息／家庭隐私／做客送礼／用餐／运动／唱歌跳舞／邮件／谈判／技术／售后](COMMON.md)',''])
        (ROOT/filename).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    source_lines=['# 来源与使用边界','','2026-10-31；每条记录在data.json和国别手册注明支持范围。','',
      '来源事实不覆盖自拟城市短名单、个人作息或成交概率。检索摘要／页面摘录不等于整份报告逐页复核；access_level按检索证据保守记录。',
      '预测数值保留预测标记；规划、融资、实施和历史成果分开。没有把任何资料宣称为已核实的当前阀门采购。','']
    for s in d['sources']:source_lines.extend([f'## {s["id"]} · {s["title"]}','',f'[{s["publisher"]}]({s["url"]})；检索日期：{s["checked_on"]}；访问层级：`{s["access_level"]}`。','',s['limitations'],''])
    (ROOT/'SOURCES.md').write_text('\n'.join(source_lines)+'\n',encoding='utf-8')
    matrix=['# 增长、城建需求与产品适配：分开判断','','2026-10-31。调研顺序是自拟判断，不是统计排名；本轮没有确认任何实时采购线索。','',
      '|新增完整市场|为什么入选|优先核实方向|调研次序|','|---|---|---|---|']
    for c in full:matrix.append(f'|[{c["name_zh"]}]({c["code"]}.md)|{c["selection_reason"]}|{c["cities"][0]}及工程顾问／MEP渠道|{c["research_priority"]}|')
    matrix.extend(['','## 怎样理解“迅速发展”','',
      '- 增长预测：仅对已经找到清晰数值、年份和预测性质的来源记录数值；预测不可写成全年已实现增长。',
      '- 城建投入：规划、融资和建设可提供长期调研方向，但不能推断预算已变成采购订单。',
      '- 服务缺口：供水、排水和城市韧性需求不必然使用楼宇暖通水力控制阀。',
      '- 市场可进入性：确认实际应用、设计规范、渠道服务、回款和进口责任后，再投入样品和备货。','',
      '## 经济数字快照','',
      '|国家|已核实快照|解释边界|','|---|---|---|',
      '|沙特|IMF页面2026预测1.7%，July 2026 WEO update|入选主要基于城市投资和制冷方向，不能称为本表增长最快|',
      '|阿联酋|IMF页面2026预测3.1%|版本口径未单独确认，不用于跨国排名|',
      '|印尼|世界银行2026年6月预测2026增长5.0%|预测，不是全年实绩|',
      '|卢旺达|世界银行Annual Meetings 2026预测2026增长7.5%|增长快不证明楼宇市场容量大或回款好|',
      '|摩洛哥|2024—2030投资增量约为2024GDP的12%|这是多年投资规模，不是GDP年增速|','',
      '其余国家本轮不编造精确增长数字；没有同口径全体比较，不能据此做国家增长排名。来源见[完整索引](SOURCES.md)。','',
      '## 从城市新闻走到可跟进项目','',
      '1. 保存官方项目页、资料日期和阶段。',
      '2. 找到实际建筑或水回路，区分楼宇暖通、市政、污水、消防和工艺用途。',
      '3. 核对项目主体、设计顾问、MEP承包商、招标包件和采购时间。',
      '4. 收集流量、可用压差、介质、温度压力、接口及性能证据要求。',
      '5. 确认品牌批准、试样、供货、安装调试和售后角色。',
      '6. 只有实际采购状态已核实，才将project_signal升级为真实商机；本版没有此类记录。','',
      '## 与原市场关联','',
      '已有越南和中亚五国资料保留；本轮只链接，不假称重新完成增长与城建筛查。',''])
    for c in linked:matrix.append(f'- [{c["name_zh"]}]({c["profile_link"]})')
    (ROOT/'MARKETS.md').write_text('\n'.join(matrix)+'\n',encoding='utf-8')
    policy=json.loads((ROOT/'contact_policy.json').read_text(encoding='utf-8'))
    names={c['code']:c['name_zh'] for c in d['countries']}
    lines=['# 联系时间、生活作息和日历边界','','默认22:00—08:30免打扰为用户联系偏好，**不是任何国家的统一睡眠时间**。当地23:00提示不要打扰，给下一个候选时间。','',
      '本工具每次调用时判断；不会后台监控，不会发送、建队列或创建定时任务。用户明确约定和客户确认的时间优先。','',
      '|市场|时区|默认候选工作日|候选当地时间|','|---|---|---|---|']
    weekdays=['一','二','三','四','五','六','日']
    for c,p in policy['countries'].items():
        days='／'.join('周'+weekdays[n] for n in p['working_days'])
        windows='、'.join(a+'—'+b for a,b in p['contact_windows'])
        if c=='AE':windows+='；周五仅09:30—11:30'
        zone=p['timezone'] if c!='ID' else 'Jakarta／Makassar／Jayapura（必须确认）'
        lines.append(f'|[{names[c]}]({c}.md)|{zone}|{days}|{windows}|')
    lines.extend(['','上述是候选联系窗口，不等于办公室开关门；各国办公参考见国别手册和contact_policy.json。','',
      '## 必须区别的情况','',
      '- 阿联酋：联邦政府周五部分办公、沙迦政府四天工作制，私企另问。周五上午窗口是保守选择。',
      '- 沙特与孟加拉：周日—周四为参考；企业可不同。孟加拉商务指南PM笔误未被采用。',
      '- 印尼：三时区；缺少已确认城市／时区时工具拒绝给默认时间。',
      '- 印度：UTC+5:30；工具保留半小时，不四舍五入到整点。',
      '- 摩洛哥：斋月相关调钟；埃及：夏令时。使用IANA动态计算；无时区数据时报错，不能全年固定偏移。',
      '- 埃塞俄比亚：会议明确公历日期与24小时国际钟点，避免当地历法／钟点习惯造成歧义。',
      '- 新增12国和越南本轮未做完整逐年假日核验；中亚引用原库参考快照，也未声明完整。输出会提示再次核验。','',
      '## 命令','',
      '```powershell',
      'python contact_planner.py --country SA --channel email',
      'python contact_planner.py --country IN --at "2026-10-31T23:00:00+05:30"',
      'python contact_planner.py --country ID --timezone Asia/Makassar --channel whatsapp',
      'python contact_planner.py --country MA --channel call',
      'python contact_planner.py --country AE --profile customer-profile.local.json',
      '```','',
      'Windows若缺IANA数据库，可安装tzdata：`python -m pip install tzdata`；它仅提供时区数据，不建立发送服务。','',
      '## 个人档案字段','',
      '|字段|未知时|','|---|---|',
      '|当前所在地、时区|先确认，不凭号码和国籍推断|',
      '|工作日、联系窗口、免打扰|用默认候选并标明未确认|',
      '|起床、入睡、午睡、用餐|保持null；通常只需要联系窗口|',
      '|周末、轮班、休假、特殊工作日|按本人提供的具体日期和确认时间保存|',
      '|音乐、唱歌、舞蹈、运动、美食|保持null，文化传统不代填|',
      '|确认日期、来源|保留，地点／工作变动后复核|','',
      '示例文件不含真实客户资料。真实档案留在受控本地，不能提交公共GitHub。','',
      '## 文案示例','',
      '“客户当地现在23:00，可能正在休息，建议不要打扰。先准备邮件，按工具给出的下一个候选工作窗口再联系；该日企业和节假日仍待核验。”',''])
    (ROOT/'CONTACT_POLICY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # One template: values are examples, unknown lifestyle fields remain null.
    profile=dict(example_only=True,country='AE',timezone='Asia/Dubai',schedule_confirmed=False,working_days=[0,1,2,3,4],contact_windows=[['09:30','12:00'],['14:00','16:30']],weekday_contact_windows={'4':[['09:30','11:30']]},quiet_hours=['22:00','08:30'],unavailable_dates=[],confirmed_working_dates=[],confirmed_on=None,source_type=None,personal_routine=dict(wake_time=None,sleep_time=None,nap=None,meal_times=None),interests=dict(food=None,music=None,singing=None,dancing=None,sports=None))
    (ROOT/'customer_schedule.example.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    n=len(d['records']);ns=len(d['sources'])
    readme=['# 增长与城建市场：文化、日常和阀门销售数据库','',
      f'版本1.0.0 · 2026-10-31 · **{n}条记录／{len(cats)}类主题／{ns}个来源**。12国新增完整画像，关联越南及中亚五国旧库；联系工具支持18个市场。','',
      '[市场比较与选择理由](MARKETS.md) · [通用生活和沟通](COMMON.md) · [联系时间](CONTACT_POLICY.md) · [来源](SOURCES.md) · [验证](VALIDATION.json)','',
      '## 新增完整国别资料','']
    for c in full:readme.append(f'- [{c["name_zh"]}]({c["code"]}.md)：{c["selection_reason"]}')
    readme.extend(['','## 每国覆盖什么','',
      '入选依据、工程资料阶段、候选城市、产品适配、语言及地区差异、基础日常表达、称呼与关系、美食、音乐舞蹈话题、节庆、办公参考、个人作息提问，以及英文寒暄和阀门跟进示例。',
      '通用手册补充家庭隐私、做客、鞋子座位、礼物、用餐、休闲、电话、WhatsApp、会议、议价、规格、质量、交付与投诉。阅读国别条目时同时看[通用手册](COMMON.md)。','',
      '## 怎样量化','',
      '可量化联系窗口、跟进间隔、消息长度、问题数、会议时长和承诺兑现率。参数全部标为自拟未验证实践；不编造“某国人90%喜欢什么”或民族成交概率。',
      '文化参考、来源短语、自编话术和实践参数在数据中分别标注；地方语言不是一概称为方言。短语未做母语专项复核，不替代关键技术／合同翻译。','',
      '## 产品边界','',
      '适用于调研手动平衡阀、自力式压差控制阀、自力式流量控制阀的楼宇水系统应用。市政水务、污水、消防、蒸汽或工艺需求须重新验证；城市有工程不表示这三类阀一定适用。',
      '所有project_signal均标记当前采购未核实。规划、融资批准、实施报告和历史成果不可冒充实时采购线索。','',
      '## 查询和导出','',
      '标准库即可查询SQLite；时区需要系统IANA数据或tzdata。中文用字串检索；英文支持大小写／重音归一化。FTS5索引保留给SQL使用，中文默认不依赖分词。','',
      '```powershell',
      'python kb.py stats',
      'python kb.py search "美食" --country SA',
      'python kb.py search "谢谢" --country ID --kind phrase --country-only',
      'python kb.py search "压差" --country AE',
      'python kb.py show SA-001',
      'python contact_planner.py --country ID --timezone Asia/Jakarta',
      'python kb.py build',
      'python kb.py export',
      'python kb.py verify',
      'python -m unittest discover -p "test_*.py" -v',
      '```','',
      '按国家搜索默认包含GLOBAL通用建议；用--country-only仅查国别记录。JSON是维护源，SQLite和国别手册从同一JSON生成。不要直接修改SQLite后遗失JSON变更。','',
      '```sql',
      'SELECT id, title, body, source_urls',
      'FROM records_with_sources WHERE country = \'SA\';',
      '```','',
      '## 文件和维护','',
      '- data.json：结构化记录、来源支持范围与国家画像。',
      '- growth_markets.sqlite3／schema.sql：只读查询库与模式。',
      '- kb.py／export_guides.py：构建、检索与可读文档导出。',
      '- contact_planner.py／contact_policy.json：调用时判断当地联系时间。',
      '- customer_schedule.example.json：虚构空白模板；真实客户信息不进仓库。',
      '- test_*.py／VALIDATION.json／MANIFEST.json：验证与交付清单。','',
      '更新经济或项目条目时保留发布日期、预测／实绩性质与阶段；未找到最新证据保持unknown。更新作息只改受控私人档案；不把个人资料写进公共data.json。','',
      '## 已有市场',''])
    for c in linked:readme.append(f'- [{c["name_zh"]}]({c["profile_link"]})（既有资料；本轮仅关联）')
    readme.extend(['','本库覆盖常见场景，未声称穷尽所有地区、族群、地方语言或各国全部习俗。实际个人与企业偏好优先。'])
    (ROOT/'README.md').write_text('\n'.join(readme)+'\n',encoding='utf-8')
    (ROOT/'HANDBOOK.md').write_text('# 手册入口\n\n[数据库说明和国别目录](README.md) · [市场比较](MARKETS.md) · [日常生活全场景](COMMON.md) · [时间规则](CONTACT_POLICY.md) · [来源](SOURCES.md)\n\n完整条目分国保存，避免单页过长。\n',encoding='utf-8')
    print(f'Exported {len(d["countries"])} scope guides and 5 entry/reference guides')

if __name__=='__main__':main()
