"""Render the canonical JSON data as a GitHub-readable reference."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def main():
    data=json.loads((ROOT/'data'/'database.json').read_text(encoding='utf-8'))
    sources={s['id']:s for s in data['sources']}
    lines=['# 越南生活与阀门销售沟通：完整分类手册','',
        '更新时间：2026-10-31。由结构化数据生成；维护入口为 `data/database.json`。','',
        '**量化参数均为实践起点，尚无客户数据验证。本人偏好、明确拒绝及业务约定优先。**',
        '自编英文与越南语均为示例；越南语称呼须按双方关系调整，尚未完成母语专项审核。',
        '文化条目保留限定范围来源；不将地区或国籍当作个人性格预测。','',
        '## 目录','']
    for c in data['categories']:
        count=sum(r['category_id']==c['id'] for r in data['records'])
        lines.append(f'- [{c["name_zh"]}（{count}条）](#{c["id"]})')
    labels={'cultural_reference':'文化参考','practice_hypothesis':'实践建议／待验证参数','authored_example':'自编话术示例'}
    for c in data['categories']:
        lines.extend(['',f'<a id="{c["id"]}"></a>',f'## {c["name_zh"]}',''])
        for r in data['records']:
            lines.extend([f'### {r["id"]} · {r["title"]}','',f'证据类型：**{labels[r["evidence_type"]]}**','',r['summary'],''])
            if r['body']!=r['summary']:lines.extend([r['body'],''])
            if r['kind']=='phrase':
                p=r['phrase']
                lines.extend(['- 英文：'+p['english'],'- 中文：'+p['chinese']])
                if p['vietnamese']:lines.append('- 越南语：'+p['vietnamese'])
                lines.extend(['- 使用条件：'+p['assumptions'],''])
            if r['kind']=='rule':
                p=r['rule']; lines.extend([f'- 起始区间：{p["min_value"]}—{p["max_value"]} {p["unit"]}','- 触发条件：'+p['trigger_condition'],'- 优先条件：'+p['override_condition'],''])
            if r['kind']=='term':
                p=r['term']
                lines.extend(['- 北部常见：'+(p['northern'] or '本条未提供'),'- 中部部分地方：'+(p['central'] or '本条未提供'),'- 南部常见／口语形式：'+(p['southern'] or '本条未提供'),'- 使用提醒：'+p['usage_note'],''])
            if r['kind']=='event':
                p=r['event']; date=f'{p["month"]}月{p["day"]}日' if p['month'] else '按本人或家庭安排确认'
                lines.extend([f'- 历法：{p["calendar"]}；日期：{date}','- 沟通动作：'+p['action_note'],''])
            for ref in r['sources']:
                s=sources[ref['source_id']]
                lines.extend([f'来源：[{s["title"]}]({s["url"]})。支持范围：{ref["claim_scope"]}',''])
    lines.extend(['## 来源索引',''])
    for s in data['sources']:
        lines.extend([f'### {s["id"]} · {s["title"]}','',f'[{s["publisher"]}]({s["url"]})；检查日期：{s["checked_on"]}。','',s['scope'],'',s['limitations'],''])
    (ROOT/'HANDBOOK.md').write_text('\n'.join(lines),encoding='utf-8')
    print('HANDBOOK.md generated')


if __name__=='__main__':main()
