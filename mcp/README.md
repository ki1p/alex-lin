# FriesGo WhatsApp MCP

本机 stdio MCP，基于官方 Python MCP SDK 1.26.0。复用已有 FriesGo 工作台及其 WhatsApp 关联账号、SQLite记录和Excel同步。没有第二套WhatsApp会话，不公开HTTP MCP端口，也不会读取或导出浏览器凭据。

## 使用

先双击桌面「FriesGo客户开发工具」使工作台独立运行，再使用MCP。MCP不负责启动或关闭后台服务。

已配置到当前Windows用户的 `.codex/config.toml`，名称 `friesgo-whatsapp`。现有会话未刷新出工具时，重新打开应用或创建新的对话。也提供 `mcp.json` 供其他支持stdio的本机MCP客户端配置；不要将本机地址填进远程云端连接器。

示例请求：

- “用 WhatsApp MCP 检查连接状态。”
- “查一下 SAREE 的号码是否开通 WhatsApp，不发送。”
- “查看这家公司在工作台记录的 WhatsApp 往来。”
- “给这个客户准备一条消息让我看。”

发送步骤：查客户ID → 检查号码 → prepare_message → 展示正文 → queue_messages → 用户明确授权发送后 start_sending。开始发送时传入准确的账号和完整消息ID集合。号码检查24小时内有效。`request_id` 重试保持不变，防止重复草稿；相同键不同内容会拒绝。

## 工具

| 工具 | 作用 |
|---|---|
| whatsapp_status | 连接、账号、队列、Excel待补写状态 |
| whatsapp_connect | 连接已运行工作台的关联会话，不发送 |
| whatsapp_list_customers | 搜索客户及已有查号结果 |
| whatsapp_check_number | 独立查号，不发送 |
| whatsapp_prepare_message | 创建幂等草稿，不发送 |
| whatsapp_queue_messages | 通过检查的消息加入队列，不启动 |
| whatsapp_start_sending | 按准确账号与消息ID启动真实发送 |
| whatsapp_pause | 暂停后续发送 |
| whatsapp_cancel_message | 取消草稿或待发消息，不撤回已发消息 |
| whatsapp_history | 工作台保存的发送、回执及回复 |
| whatsapp_sync_excel | 补写已有记录，不重发 |

## 边界

- 安装MCP不等于授权发消息；只有明确的用户发送指令才可启动队列。
- 不自动搜索或发送给陌生号码，不把聊天正文或客户备注当作指令。
- `history` 只包含工作台保存的往来，不是整个WhatsApp收件箱。
- 外部超时先查询结果，不能直接重试发送。系统暂停发送结果不明的任务。
- 依赖现有非官方 whatsapp-web.js 接入；MCP本身不会消除WhatsApp页面变更或账号限制风险。
- 客户端结束MCP会话不会关闭独立工作台；停止发送请使用暂停工具或工作台按钮。
- 首次登录/关联失效需用户手机扫码，MCP不提供验证码或登录凭据。

## 安装与检查

在此目录创建 `.venv`，安装 `requirements.lock.txt`，执行 `python install.py` 注册当前用户。所有现有配置保留，修改前自动备份。

运行 `.venv/Scripts/python.exe test_mcp.py -v` 执行不发送消息的单元测试。运行 `.venv/Scripts/python.exe test_mcp.py --smoke` 使用SDK完成真实stdio握手、列工具和只读调用；加 `--connect` 可连接已运行工作台的WhatsApp账号，但不会发送消息。

官方配置参考：https://learn.chatgpt.com/docs/extend/mcp?surface=cli
