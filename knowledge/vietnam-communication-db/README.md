# 越南生活与阀门销售沟通知识数据库

第一版：2026-10-31。面向与越南各地客户及朋友以英文为主的交流，包含常见生活场景、少量越南语、地方用词、节庆与可校准的沟通参数。

## 直接阅读

- [完整分类手册](HANDBOOK.md)：按场景阅读全部条目、话术、规则和来源。
- [机器可维护的数据](data/database.json)：260条记录、23个分类、25个来源。
- [SQLite数据库](vietnam_communication.sqlite3)：下载后用SQLite客户端打开。
- [数据库表结构](schema.sql)：可用于其他系统接入。

## 三种证据标签

|标签|含义|
|---|---|
|`cultural_reference`|有明确来源范围的文化或采购案例参考；不是对每个人的预测。|
|`practice_hypothesis`|为本任务编写的沟通建议、指标和起始阈值，尚未用客户数据验证。|
|`authored_example`|按场景编写的话术示例；不伪装成真实客户原话。|

所有40条数值沟通规则均为`practice_hypothesis`。熟悉度R、正式度F、话题私密度P、请求负担B用于帮助观察场景；不用于计算国籍性格、友谊深度或成交概率。客户本人偏好、明确拒绝、停止联系要求和既定业务约定优先。

越南语话术未完成母语者专项审核；出现anh/em时需确认辈分和称呼关系。部分复杂话术只提供英文及中文，越南语字段留空，不声称全部完成三语翻译。

## 使用方法

需要Python 3.10+、SQLite FTS5支持，无第三方依赖。从本目录执行：

```powershell
python database.py stats
python database.py search "婚礼"
python database.py search "ket xe"
python database.py search "阀门" --category valves
python database.py search "message" --kind rule
python database.py show P001
python database.py verify
python -m unittest -v
```

搜索支持中文子串和忽略越南语声调的字面匹配，如`kẹt xe`可以搜`ket xe`，`đ`按`d`归一化。一次查询按完整字面子串匹配，不支持自然语言推理或拼写纠错。另有FTS5索引供SQL查询；中文检索优先使用CLI子串查询。

修改`data/database.json`后重建：

```powershell
python database.py build
python export_handbook.py
python database.py verify
python -m unittest -v
```

`build`会验证输入并原子替换指定的派生数据库。`--db`是全局参数，应放在子命令前，例如`python database.py --db copy.sqlite3 build`。搜索与查看以只读模式打开数据库。

## 数据结构

- `records`：稳定ID、类型、分类、标题、摘要、正文、证据标签、适用范围、关系与话题等级、标签、更新日期。
- `sources`及`record_sources`：来源URL、出版方、检查日期、适用限制和每条引用支持的范围。
- `phrase_details`：英文、越南语、中文、语域提醒、称呼假设。
- `rule_details`：数值区间、单位、触发条件、动作、优先覆盖条件。
- `term_details`：南北中常见用词与使用范围。
- `event_details`：公历／农历／家庭特定／可变日期与沟通动作。
- `search_index`：可重建的FTS5索引。
- `knowledge_with_sources`：带来源URL的只读查询视图。

```sql
SELECT id,title,summary,evidence_type
FROM records WHERE category_id='valves';

SELECT r.id,r.title,d.min_value,d.max_value,d.unit,d.override_condition
FROM records r JOIN rule_details d ON d.record_id=r.id;

SELECT id,title,source_urls FROM knowledge_with_sources
WHERE evidence_type='cultural_reference';
```

## 接入alex-lin

此目录作为`knowledge/vietnam-communication-db/`独立知识数据包存放，可供人工检索或由现有应用只读查询。不会自动接入邮件或WhatsApp发送队列，不会启动联系、修改真实客户档案、改变原有发送规则。当前版本未修改FriesGo应用界面或MCP工具。

数据库只包含通用研究资料和自编示例，不含真实客户联系方式、私密聊天、凭据或会话数据。后续如记录客户观察，应另设受控的本地文件，不将其自动加入公共知识仓库。

## 维护与边界

新增文化条目必须附限定范围的来源；新增数值参数必须保留实践假设标签。避免把部分地区、代际或研究样本推广为所有越南人的行为标准。节庆公历日期、企业假期、热门赛事和采购条件在实际使用时重新核对；本库不做农历换算，不提供医疗或法律判断。

更新时保留稳定ID，注明修订原因，运行验证及测试，并同步更新手册。参考资料以转述和链接为主，未复制完整文章；外部文章版权归原作者所有。
