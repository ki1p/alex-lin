# 中亚五国文化与日常沟通知识数据库

研究整理日期：2026-10-31。覆盖哈萨克斯坦、乌兹别克斯坦、吉尔吉斯斯坦、塔吉克斯坦、土库曼斯坦，兼顾日常生活、地方语言及阀门销售交流。

**301条记录、23个主题、52个来源。** 内容包括143条文化或实践卡片、29条地方语言与文字差异、86条短语或自编示例、17条节庆及人生场景、20条实践规则、6项复盘指标。

## 先阅读

|入口|内容|
|---|---|
|[五国完整手册](HANDBOOK.md)|全部条目、使用范围、原文与来源|
|[哈萨克斯坦](KZ.md)|39条，含礼貌哈萨克语、地方词例、家庭仪式|
|[乌兹别克斯坦](UZ.md)|42条，含mahalla、茶与palov、乌兹别克语及方言|
|[吉尔吉斯斯坦](KG.md)|37条，含北南词例、问候、史诗与毡艺|
|[塔吉克斯坦](TJ.md)|42条，含地区语言、帕米尔诸语言、餐布与节庆|
|[土库曼斯坦](TM.md)|37条，含土库曼语、文字差异、地毯与dutar|
|[共同生活场景与俄语](COMMON.md)|104条，含36条自编俄语示例和沟通框架|
|[SQLite数据库](central_asia.sqlite3)|下载后用SQLite工具直接查询|
|[JSON维护数据](data.json)|可维护、可导入的原始结构化记录|

## 如何理解证据

- `cultural_reference`：来源支持所列文化、地区、时间或语言事实，不代表每位居民。
- `source_attested_phrase`：来源中可见的简短表达，未声称已经母语者专项审核。
- `authored_example`：为本任务编写的俄语生活和商务示例，不是客户真实消息。
- `practice_hypothesis`：自拟沟通方法、阈值与指标，尚未用用户客户数据验证。

所有数值规则均标记为实践假设。熟悉度R、正式度F、私密度P、请求负担B是观察工具，不用于计算国籍性格、友谊深度或成交概率。本人明确偏好、拒绝、家庭安排和真实业务约定优先。

## 地方语言的处理

明确区分：标准语、地区方言、独立语言、口语语域、历史参考、文字差异。例如帕米尔诸语言、雅格诺比语、卡拉卡尔帕克语不被当成国家语言的随意方言标签；土库曼语的跨境文字差异也不被误标为另一种语言。

本地短语保留来源字形和语域提醒；罗马字仅为阅读辅助，没有统一官方转写或精确发音的声明。复杂技术内容仍需按双方共同熟悉语言核对。部分历史教材年代较早、使用旧字母，已在来源限制中注明。

## 检索

需要Python 3.10+及SQLite FTS5，无第三方依赖。在本目录运行：

```powershell
python kb.py stats
python kb.py search "婚礼" --country KZ
python kb.py search "目录" --country KZ --country-only
python kb.py search "челек" --country KG
python kb.py search "Bagyslan" --country TM
python kb.py search "帕米尔" --country TJ
python kb.py search "平衡阀" --kind phrase
python kb.py show KZ-P001
python kb.py verify
python -m unittest -v
```

搜索为字面子串匹配，支持中文、原文及条目中的罗马字，忽略部分拉丁字母附加符号，并统一部分撇号。它不是自然语言翻译或拼写纠错工具。`--country KZ`默认同时包含共同场景；加`--country-only`只看该国。`CA`是本库内部的“中亚共同场景”代码，不是加拿大记录。

## 更新与重建

编辑`data.json`，保留稳定ID和证据标签，然后运行：

```powershell
python kb.py build
python kb.py export
python kb.py verify
python -m unittest -v
```

`build`先校验引用、范围和类型，随后原子替换派生数据库。搜索与查看以只读模式连接。自定义数据库路径用全局参数，例如`python kb.py --db sample.sqlite3 build`。

## 数据结构

`countries`保存国家及共同场景；`categories`保存主题；`records`保存标题、正文、适用范围、证据类型、详情及标签；`sources`保存来源与访问层级；`citations`明确每个来源支持的具体范围；`search_index`是可重建的FTS5索引。

来源访问层级区分`full_text`、`partial_full_text`和`search_excerpt`，没有将检索摘要伪装为读过全文。来源链接不证明自编话术已通过母语审核。

```sql
SELECT id,title,summary FROM records WHERE country='UZ' AND kind='language_variety';
SELECT id,title,source_urls FROM records_with_sources WHERE evidence='cultural_reference';
SELECT record_id,title FROM search_index WHERE search_index MATCH '"каталог"';
```

## 范围和使用边界

本包作为`knowledge/central-asia-culture-db/`独立知识库保存，不修改既有FriesGo界面或消息队列。数据只含一般研究和自编示例，没有真实客户WhatsApp聊天、联系方式、凭据或发送任务。

覆盖常见场景，并非穷尽五国所有民族、地区和家庭。斋月、宗教节日、公共假期、企业作息、平台可达性和采购条件在实际使用时重新核对；不提供统一礼金金额、强制社交动作或医疗法律结论。外部内容以简短转述和链接为主，未收录完整文章。
