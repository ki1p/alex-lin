# 增长与城建市场：文化、日常和阀门销售数据库

版本1.1.0 · 2026-10-31 · **468条记录／29类主题／92个来源**。已整理12国资料，按最新偏好默认只保留3国为重点调研候选；另关联既有越南和中亚五国资料。

[先看市场筛选](SCREENING.md) · [市场背景](MARKETS.md) · [日常沟通](COMMON.md) · [联系时间](CONTACT_POLICY.md) · [来源](SOURCES.md) · [验证](VALIDATION.json)

**用户最新范围：极低收入或明显不安稳地区不继续深度开发。旧资料保留并标记，不再全部当作推荐。候选也不表示已核实客户付款和采购。**

## 当前重点调研候选

- [印度](IN.md)：城市服务建设与大规模分散市场；在避开受限地区、确认客户资金及应用的前提下，优先研究已有候选商业城市。
- [印度尼西亚](ID.md)：增长与城市治理投资；优先研究已列候选城市，另确认三时区、自然灾害及实际客户回款条件。
- [摩洛哥](MA.md)：基础设施投资加速与选择性建筑机会；先研究卡萨布兰卡、拉巴特等已有候选城市；收入类别不能替代付款和履约核查。

## 暂不优先／暂停／退出的旧资料

- [沙特阿拉伯](SA.md)：局势原因暂停新开发
- [阿联酋](AE.md)：暂不优先，条件待核验
- [菲律宾](PH.md)：暂不优先，条件待核验
- [孟加拉国](BD.md)：暂不优先，条件待核验
- [埃及](EG.md)：暂不优先，条件待核验
- [肯尼亚](KE.md)：暂不优先，条件待核验
- [坦桑尼亚](TZ.md)：暂不优先，条件待核验
- [卢旺达](RW.md)：按低收入规则退出新开发
- [埃塞俄比亚](ET.md)：按低收入规则退出新开发

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
python kb.py markets
python kb.py search "Tajine" --country MA
python kb.py search "Kabsa" --country SA --include-inactive
python kb.py search "谢谢" --country ID --kind phrase --country-only
python kb.py search "压差" --country AE
python kb.py show SA-001
python contact_planner.py --country ID --timezone Asia/Jakarta
python kb.py build
python kb.py export
python kb.py verify
python -m unittest discover -p "test_*.py" -v
```

默认搜索只含重点候选、GLOBAL通用建议和既有资料索引；暂停／退出／待核验国家不混入默认结果。查看旧资料需--include-inactive；直接show会显示记录中的market_screen_status。按国家搜索默认包含GLOBAL；--country-only仅查该国。JSON是维护源，SQLite和手册从同一JSON生成。

```sql
SELECT id, title, body, source_urls
FROM records_with_sources WHERE country = 'SA';
```

## 文件和维护

- data.json：结构化记录、来源支持范围与国家画像。
- growth_markets.sqlite3／schema.sql：只读查询库与模式。
- kb.py／export_guides.py：构建、检索与可读文档导出。
- contact_planner.py／contact_policy.json：调用时判断当地联系时间。
- market_screen.json／SCREENING.md：最新开发筛选与理由；收入、安全和客户资金分别判断。
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
