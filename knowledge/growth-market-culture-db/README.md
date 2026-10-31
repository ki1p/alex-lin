# 增长与城建市场：文化、日常和阀门销售数据库

版本1.0.0 · 2026-10-31 · **431条记录／29类主题／79个来源**。12国新增完整画像，关联越南及中亚五国旧库；联系工具支持18个市场。

[市场比较与选择理由](MARKETS.md) · [通用生活和沟通](COMMON.md) · [联系时间](CONTACT_POLICY.md) · [来源](SOURCES.md) · [验证](VALIDATION.json)

## 新增完整国别资料

- [沙特阿拉伯](SA.md)：城市建设和制冷水系统机会
- [阿联酋](AE.md)：成熟城市持续投资与区域供冷
- [印度](IN.md)：城市服务建设与大规模分散市场
- [印度尼西亚](ID.md)：增长与城市治理投资
- [菲律宾](PH.md)：城市水务融资与建筑系统调研
- [孟加拉国](BD.md)：城市水务、污染治理和工业配套需求
- [埃及](EG.md)：新城建设及建筑系统配套
- [摩洛哥](MA.md)：基础设施投资加速与选择性建筑机会
- [肯尼亚](KE.md)：城市治理及建筑配套需求
- [坦桑尼亚](TZ.md)：都市基础设施与服务建设
- [卢旺达](RW.md)：增长信号与小规模试点验证
- [埃塞俄比亚](ET.md)：历史城市扩容及服务缺口，机会需重新验证

## 每国覆盖什么

入选依据、工程资料阶段、候选城市、产品适配、语言及地区差异、基础日常表达、称呼与关系、美食、音乐舞蹈话题、节庆、办公参考、个人作息提问，以及英文寒暄和阀门跟进示例。
通用手册补充家庭隐私、做客、鞋子座位、礼物、用餐、休闲、电话、WhatsApp、会议、议价、规格、质量、交付与投诉。阅读国别条目时同时看[通用手册](COMMON.md)。

## 怎样量化

可量化联系窗口、跟进间隔、消息长度、问题数、会议时长和承诺兑现率。参数全部标为自拟未验证实践；不编造“某国人90%喜欢什么”或民族成交概率。
文化参考、来源短语、自编话术和实践参数在数据中分别标注；地方语言不是一概称为方言。短语未做母语专项复核，不替代关键技术／合同翻译。

## 产品边界

适用于调研手动平衡阀、自力式压差控制阀、自力式流量控制阀的楼宇水系统应用。市政水务、污水、消防、蒸汽或工艺需求须重新验证；城市有工程不表示这三类阀一定适用。
所有project_signal均标记当前采购未核实。规划、融资批准、实施报告和历史成果不可冒充实时采购线索。

## 查询和导出

标准库即可查询SQLite；时区需要系统IANA数据或tzdata。中文用字串检索；英文支持大小写／重音归一化。FTS5索引保留给SQL使用，中文默认不依赖分词。

```powershell
python kb.py stats
python kb.py search "美食" --country SA
python kb.py search "谢谢" --country ID --kind phrase --country-only
python kb.py search "压差" --country AE
python kb.py show SA-001
python contact_planner.py --country ID --timezone Asia/Jakarta
python kb.py build
python kb.py export
python kb.py verify
python -m unittest discover -p "test_*.py" -v
```

按国家搜索默认包含GLOBAL通用建议；用--country-only仅查国别记录。JSON是维护源，SQLite和国别手册从同一JSON生成。不要直接修改SQLite后遗失JSON变更。

```sql
SELECT id, title, body, source_urls
FROM records_with_sources WHERE country = 'SA';
```

## 文件和维护

- data.json：结构化记录、来源支持范围与国家画像。
- growth_markets.sqlite3／schema.sql：只读查询库与模式。
- kb.py／export_guides.py：构建、检索与可读文档导出。
- contact_planner.py／contact_policy.json：调用时判断当地联系时间。
- customer_schedule.example.json：虚构空白模板；真实客户信息不进仓库。
- test_*.py／VALIDATION.json／MANIFEST.json：验证与交付清单。

更新经济或项目条目时保留发布日期、预测／实绩性质与阶段；未找到最新证据保持unknown。更新作息只改受控私人档案；不把个人资料写进公共data.json。

## 已有市场

- [越南](../vietnam-communication-db/HANDBOOK.md)（既有资料；本轮仅关联）
- [哈萨克斯坦](../central-asia-culture-db/KZ.md)（既有资料；本轮仅关联）
- [乌兹别克斯坦](../central-asia-culture-db/UZ.md)（既有资料；本轮仅关联）
- [吉尔吉斯斯坦](../central-asia-culture-db/KG.md)（既有资料；本轮仅关联）
- [塔吉克斯坦](../central-asia-culture-db/TJ.md)（既有资料；本轮仅关联）
- [土库曼斯坦](../central-asia-culture-db/TM.md)（既有资料；本轮仅关联）

本库覆盖常见场景，未声称穷尽所有地区、族群、地方语言或各国全部习俗。实际个人与企业偏好优先。
