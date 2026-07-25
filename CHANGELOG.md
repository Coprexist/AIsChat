# CHANGELOG

本 CHANGELOG 遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范，
版本号遵守 [语义化版本](https://semver.org/lang/zh-CN/)。

> **当前阶段**：v1.0 正式版 — 补丁版本号（第三位）递增。

---

## [v1.0.6] - 2026-07-23~25

### Added

- 🚨 **中断消息注入**：AI 忙碌时用户新消息直接注入当前 `_tool_call_loop`，不另起 executor。DM 路由层拦截 + worker 群聊/私信统一处理。
- 🔧 **`file_edit` 新增 `delete_lines` 操作**：删除指定 N-M 行（1-indexed）。
- 📖 **`file_read` 新增 `start_line`/`end_line`**：分段读取文件，不传则读全文。
- 🛠️ **JSON 参数自动修复**：`_repair_json` 函数在 `json.loads` 失败时用正则提取 path + content，解决大文件 HTML 引号嵌套问题。
- 📝 **工具执行结果必回传**：有工具结果时强制继续循环让 LLM 看到，不再因 `finish_reason=stop` 提前退出。
- ⚡ **`max_tokens` 2048→16384**：LLM 输出配额提升，大文件不被截断。
- 🧠 **推理不可见提醒**：当前时间段提示 AI 必须调 `send_dm`/`send_gm` 发内容（除非不想发）。
- 🔍 **read_manual 工具**：AI 可查阅用户手册了解消息格式和平台规范，支持关键词搜索，用户询问格式问题时主动查询后回答。

### Changed

- 📏 **群聊消息字数上限 200→5000**：`format_message` 默认截断改为 5000 字符。
- 🗂️ **`file_list` 路径处理**：`.` 和 `/` 视为根目录，不加 LIKE 过滤，查全部文件。
- ✏️ **`file_write` 覆盖更新 owner**：覆盖已有文件时重置 `owner_type`/`owner_id`，避免权限混乱。
- 💬 **工具描述补充**：`file_edit` 增加编辑前先读文件、从后往前的说明；`send_gm`/`send_dm` 增加 8 色彩色文字语法说明。
- 📱 **设置页保存按钮 sticky 底部**：`AgentSettingsModal` 和 `SettingsPage` 的保存/取消按钮固定在容器底部。

### Fixed

- 🐛 **工具报错不通知 AI**：`_pending_results` 不为空时不退出循环，LLM 收到结果后自主决策。
- 🐛 **JSON 解析失败死循环**：后台自动修复引号转义，AI 不再反复重试同一错误。
- 🐛 **`file_read` 报无权**：`file_write` 覆盖已有文件时未更新 `owner_id`。
- 🐛 **`file_list` 查不到文件**：`path="/"` 时 LIKE 条件 `/` 不匹配相对路径文件。
- 🐛 **设置页保存按钮错位**：`SettingsPage` 布局 flex row 导致按钮在内容区右侧。
- 🐛 **文件系统小文件可读写、大文件不可读**：`max_tokens` 不足导致 JSON 截断。

### Added

- 🎨 **气泡文本动态对比度检测**：运行时读取气泡 `background-color`，用 WCAG 算法自动算链接/代码/表格颜色。深色底→白字，浅色底→默认色。为未来自定义气泡颜色打下基础
- ⚙️ **上下文压缩阈值管理配置**：管理面板 → 对话日志 → 全局设置可调压缩百分比（5%-100%）
- 🕒 **闲置 12 小时自动压缩**：对话最后消息超 12 小时强制内联压缩，避免过期缓存浪费 token
- 🔍 **对话日志 AI 搜索**：AI 选择器支持按名称搜索，不再限于前 20 个
- 🎯 **Alembic 数据库迁移**：`compression_threshold` 列通过 Alembic 管理，`migration.py` 不再新增列
- 📦 **Tauri API 集中封装**：`utils/tauri.ts` 统一 `invoke`/`onKeyboardChange`/`getPlatform`，替代散落在各页面的内联 `__TAURI__` 检查
- 📱 **visualViewport 键盘检测**：移动端键盘弹出时精确滚动输入框，替代 400ms setTimeout hack
- 🦀 **AIsChat-Client 原生命令**：`io_bridge_call` 按 method 分发（getPlatform/getAppVersion）+ `get_status_bar_height` + `get_safe_area_insets` + `setup()`/`on_navigation()`
- 🧠 **思考状态内存追踪**：`_thinking_state` 字典跟踪所有对话的 AI 思考/输入中状态。新增 `GET /groups/{id}/activity` 和 `GET /dm/{id}/activity` 接口。前端进入对话时自动查询恢复活动指示器，切换页面不再丢失「思考中」显示

### Changed

- 📈 **消息加载上限 20 → 5000**：不再硬截断 AI 上下文，让压缩阈值自然控制保留量
- 📏 **内联压缩保留数 5 → 20**：AI 看到更多最近消息再截断
- ♻️ **SettingsPage/LocalModelPage Tauri 调用集中化**：7 处内联 `__TAURI__` + 动态 import 改为集中 `invoke`

### Fixed

- 🐛 **自家气泡 Markdown 链接/代码/表格深色底不可见**：白字 + 半透明底适配 `bg-primary-500`
- 🐛 **`get_compression_threshold` 未导入**：AI 回复报 `NameError`，不返回思考中状态
- 🐛 **对话日志查看器旧 AI 不可选**：后端加 `search` 参数，前端加搜索框
- 🐛 **context_compressor.py 死代码**：阈值从 6% 提到 60% 后永不触发，现改为从 DB 配置读取

## [v1.0.4] - 2026-07-11

### Added

- 🧩 **工具自动发现**：`ToolPlugin.__init_subclass__` 自动注册 + `_discover_tools()` 扫描 `tools/` 目录。新增工具只需在对应子目录创建 `.py` 文件，零修改现有代码。
- 🏷️ **技能类型注册表**：`SkillRegistry` 替代数据库 CHECK 约束，新增技能类型无需改数据库。
- 🔌 **服务插件注册中心**：`PluginRegistry` + `ServicePlugin` 替代 `admin.py` 中硬编码的 `PLUGIN_REGISTRY` dict 和 `if id != "browser"` 检查。
- 📡 **事件总线**：`EventBus` 单例发布/订阅架构，支持 `on/off/emit` 接口，错误隔离。预定义 `system.startup/shutdown`、`message.before/after_send`、`ai.before/after_response`、`ai.state_change`、`tool.after_execute` 事件类型。
- 📦 **Alembic 数据库迁移框架**：`alembic revision --autogenerate` 替代手动写 `ALTER TABLE`。启动自动执行 `alembic upgrade head`，迁移文件版本化管理可回滚。
- 🎲 **roll_dice 示例工具**：演示工具自动发现机制。
- 🌐 **Swagger UI 自定义**：语言下拉（中/英） + 快捷登录表单（用户名/密码 → 自动注入 token）。

### Changed

- ♻️ **技能引擎注册式分发**：`skill_engine.py` 的 `if/elif` 硬编码改为 `_ACTION_HANDLERS` / `_INJECT_HANDLERS` 字典调度。新增技能类型只需注册处理器函数。
- ♻️ **后端 Router 自动发现**：`routers/__init__.py` 自动扫描目录，`main.py` 从 16 行手动注册改为 `get_all_routers()` 循环。新增路由模块零修改。
- ♻️ **前端导航统一注册**：`navRegistry.ts` 作为导航项单一数据源，`Sidebar.tsx` 展开/折叠和 `MobileNav.tsx` 共用。新增导航项只需改一个文件。
- ♻️ **前端路由集中注册**：`pageRegistry.tsx` 统一管理所有页面路由定义，`App.tsx` 仅调用 `getPublicRoutes()` + `getProtectedRoutes()`。新增页面只需在 `pageRegistry.tsx` 加一行。

### Fixed

- 🐛 **DM 回复 BUG**：`_build_current_context` 忽略了 `is_dm` 参数，DM 中始终指示 AI 使用 `send_gm`。修复：DM 路径指示用 `send_dm`。
- 🐛 **ChatArea.tsx Group 接口缺字段**：`Group` 缺少 `is_paused` / `concurrent_ai_limit`。
- 🐛 **ChatView.tsx sender_state null 传入**：`state` prop 收到 `string | null` 导致类型错误。
- 🐛 **FilePreviewModal.tsx srcDoc null 传入**：`content` 为 null 时传给 `srcDoc`（需 `string | undefined`）。
- 🐛 **CreateAgentModal.tsx providers prop 缺失**：`DetailSettingsModal` 未接收 `providers` 参数。
- 🐛 **Layout.tsx 自定义事件类型**：`maintenance-mode` 自定义事件监听器类型不匹配。
- 🐛 **MaintenanceMsgEditor.tsx setMsg 缺字段**：预设应用时 `soft_once` 字段缺失。

### Removed

- 🧹 前端 3 处硬编码导航列表合并为 `navRegistry.ts` 单一数据源
- 🧹 `main.py` 16 行手动 router 注册改为自动发现

---

## [v1.0.3] - 2026-07-08

### Added

- 🎯 **@ 优先触发**：被 @ 提及的 AI 走独立并发通道（上限 1），不阻塞普通消息队列
- 🔧 **AI 自修改并发数**：AI 调用 `set_concurrency` 调整群并发上限，多 AI 同时设置取最小值，60s 自动恢复
- ⭐ **特别关心好友**：人类和 AI 均可设置特别关心，好友消息穿透 DND/屏蔽
- ⏸ **群暂停对话**：群管理可一键暂停/恢复 AI 触发
- 📏 **消息折叠展开**：`expand_message` 工具展开被截断的长消息
- 🧠 **提示词文件化管理**：`prompts/*.txt` 直接编辑，无需 Python 转义
- 🌳 **ChatChainManager v2**：红黑树 + 双向链表，O(log N + K) 查询唤醒

### Changed

- ⚡ **压缩阈值**：6% → 60%，接近窗口才触发
- 🔄 **压缩内联**：不再另起 API 调用，直接截断中间消息
- 📡 **上下文机制**：取最近 20 条消息（不按已读过滤），当前时间放在末尾保 cache
- 🏷 **Lazy tag**：AI 自修改暂存 `pending_system_prompt`，压缩时生效

### Fixed

- 🐛 群聊消息 `messages.append` 缺失导致 AI 收不到消息
- 🐛 `build_dm_messages` docstring 缺失闭合引号
- 🐛 暂停按钮 `setGroup` 未定义
- 🐛 @ 预选列表中文字符后不出现
- 🐛 ChatSidebar 事件监听器泄漏
- 🐛 迁移缩进污染、迁移顺序错误

### Removed

- 🔇 **Gate 3.5 系统硬拦**：尺时间判定改为 AI 自主决定（提示词引导 + 意愿分），删除系统强制过滤

## [v1.0.2] - 2026-07-04

### Added

- 🏭 **API 多供应商架构**：`provider_config` 从单对象→数组，支持同时配置多个 LLM 厂商（DeepSeek/OpenAI/Ollama/通义千问/Kimi/智谱/硅基流动），每个供应商独立设置 base_url/模型列表/深度推理支持。管理面板新增供应商增删改、设为默认。
- 🔗 **池 Key 关联供应商**：`api_key_pool` 新增 `provider_name` 列，池 Key 可关联供应商自动获得模型列表和 thinking 支持。未关联时按 api_base_url 自动匹配。
- 🎛️ **模型下拉框按供应商分组**：创建/编辑 AI 时聊天模型和工作模型用 `<optgroup>` 分组，★ 标记默认供应商。
- 🧠 **thinking 判定从全局改为按供应商**：`chat_completion` 新增 `provider_supports_thinking` 参数，非 DeepSeek 供应商也能正确发送 thinking。
- ♻️ **供应商配置纯函数化**：`utils/pure/provider_config.py`——查找/匹配/收集/增删全部零 IO。

### Changed

- 🔧 旧 `provider_config` 单对象自动迁移为数组：`_migrate_multi_provider` 包装为 `[{is_default:true,name,provider,...}]`，幂等。
- 🔧 `/agents/models` 端点新增 `providers` 字段，返回全部供应商配置和能力标记。
- 🔧 `_get_api_config` 返回值追加 `provider_info` 字典。
- 🔧 管理面板 `ProviderPresetSelector` 从单对象编辑重写为多供应商卡片式管理。

### Fixed

- 🐛 `agent_service.py` 遗漏 `from app.utils.result import Result` 导致容器启动 `NameError`。
- 🐛 后端容器无 `curl` 导致 healthcheck 失败——改用 Python `urllib.request`。
- 🐛 Docker 卷挂载触发 uvicorn `--reload` 误重启 + 前端启动早于后端就绪——加 `--reload-delay 3` + 后端 healthcheck + 前端 `condition: service_healthy`。

---

## [v1.0.1] - 2026-06-30

### Added

- 📚 **AI 状态栈**：`agents.state_stack` JSONB 列，4 个工具 push/pop/close/list 追踪跨任务上下文。end_turn 自动兜底 push。
- 🔕 **群 DND 增强**：@mention/@all/@everyone/@全体/群公告穿透免打扰。新增 `cancel_dnd` 工具。
- 🚪 **`enter_group` 工具**：验证成员资格→获取未读数→push 状态帧→返回预览。
- 📋 **TODO/PLAN/JOURNAL 自动联动**：push_state/pop_state 自动写入 workspace。
- ♻️ **Result Monad 集成**：`get_agent()`/`decode_access_token()`/`get_effective_config()` 返回 `Result[T,E]`。TypeScript 端 `safeParse<T>()`、`api.safe.*`。
- 🧩 **统一上下文**：所有会话统一标题格式（「在私信/群聊「名字」(id=X)中」），当前会话标题始终在最后。跨对话消息全部 `role: system`，边界清晰。
- ⚡ **上下文压缩**：旧消息稳定摘要化保 prompt cache 命中率。`context_compressor.py` 控制阈值（~8K tokens 触发）。
- 🏗️ **纯函数架构建立**：`utils/pure/` 目录——意愿评分、提示词构建、消息格式化、预设合并、状态栈全部零 IO 抽取。项目遵循「函数式核心 + 命令式外壳」模式。

### Fixed

- 🐛 **跨对话上下文死循环（历史重播）**：`_build_cross_conversation_context` 永久禁用（返回 `[]`），状态栈替代——经 A/B 对照验证，DeepSeek 在 `system→user/assistant→system` 交替结构中存在注意力失效。
- 🐛 **多群主错误数据**：迁移将非 owner 的 `role='owner'` 记录降为 member。
- 🐛 **纯文件消息被拦截**：发送纯文件（无文字）不再被 `content` 空检查拦截。

### Changed

- 🔧 状态栈摘要注入到系统提示词尾部（最大化 prompt cache 命中）。
- 🔧 闹钟/群聊/DM 三个路径 end_turn 时调用 `persist_last_task_as_state()`。
- 🔧 跨对话上下文生效条件：chat 档 + general/semi_general 不加载，resonance 及 custom 档共振 AI 加载。

---

## [v1.0.0] - 2026-06-28

### Added

- 🔧 **AI 设置界面二级重构**：设置面板拆分为「主设置」（12 个核心参数：名称/档位/AI类型/模型/温度/思考/工具轮次/延迟/他人对话/暂停）和「详细设置」（全部高级参数）。一键切换四个配置档位即时预览预设，所有参数可在此基础上微调。
- 🆕 **4 个新配置参数**：`auto_dnd_threshold`、`auto_dnd_duration`、`conversation_logs_limit`、`user_can_view_logs`。前后端全链路支持，创建和编辑均可设置。
- 🛠️ **tool_help 工具**：AI 可查询工具/CLI 详细用法（含 browser session 协议、17 子命令、典型流程）。`execute_command` 描述指向 `tool_help`。
- 🎨 **滑块日夜模式修复**：`input[type="range"]` 自定义轨道/拇指 CSS，深色模式轨道清晰可见。`ToggleField` 统一使用标准 `Toggle` 组件。
- 📧 **邮箱系统增强**：多 SMTP 配置容灾——支持配置多个发件服务器按优先级自动故障转移，一个不可用自动尝试下一个。管理员可增删改排序，独立测试每个配置的连通性。
- ✉️ **自定义邮件模板**：管理员可编辑验证码邮件的 HTML 模板（分中文/英文/日语，分注册/登录/换绑三种用途），支持 `{code}` `{from_name}` `{username}` 等变量占位符。一键重置为默认模板。
- 🔢 **OTP 验证码输入组件**：全新 `VerificationCodeInput` 组件——6 个独立数字框，自动聚焦跳转、Backspace 回退、粘贴分发。LoginPage / MePage / SettingsPage 三处统一替换，体验一致。
- 🇯🇵 **日语界面支持**：完整日语翻译（1415+ key），前端语言选择器全线支持。设置向导、设置页、管理员面板均可切换日语。时间格式化（相对时间 + 消息时间）日语本地化。
- 📄 **FilePreviewModal 富文本渲染**：`.md` 渲染为格式化 Markdown（react-markdown + GFM/数学公式/Mermaid），`.py/.c/.cpp/.json` 等代码文件语法高亮展示。
- 🧠 **AI 详情页结构化记忆展示**：新增子 Tab（结构化/向量），3 级可折叠目录树，向量记忆卡片支持展开、scope 彩色标签。

### Fixed

- 🐛 **跨对话上下文 role 混淆（DeepSeek 注意力失效）**：经 A/B 对照验证，DeepSeek 在 `system → user/assistant → system` 交替结构中存在注意力失效——API 收到完整数据，但模型会忽略夹在 system 消息之间的 `user`/`assistant` 消息（能见标题、不见内容）。修复方案：跨对话上下文（标题 + 内容）全部改用 `role: system`，仅当前会话保留 `user`/`assistant`。同时引入自我/他人显式区分——AI 自己的发言保留纯名字（如 `逍遥三号: ...`），他人发言附带 id（如 `清风无殇（id=12）: ...`），系统提示词加规则「带 id 的都是别人」。id 是数据库主键不可伪造，杜绝用户名注入冒充 AI 自己的攻击面。设计文档全量同步（AI对话链机制.md / 三空间模型.md / 记忆架构设计.md / 项目全景报告.md §7.5）。
- 🐛 **统一上下文修复**：`config_profile=custom` 的共振 AI 此前被 `_build_cross_conversation_context` 排除，修复后仅跳过 `chat` 档和 `general`/`semi_general` 类型，共振 AI 在任何档位下均加载跨对话上下文。
- 🔧 **set_status 工具注册**：补上 `tools/__init__.py` 中漏掉的 import。
- 🐛 **纯文件消息修复**：发送纯文件消息（无文字）不再被 `content` 空检查拦截。
- 🔒 **文件引用幂等**：`file_references` 表加 UNIQUE 约束 + CI 迁移清理重复记录，彻底解决 `MultipleResultsFound` 500 错误。
- 🧬 **Embedding 模型修正**：`deepseek-embed` 实际不存在，改为 `text-embedding-3-small` + 环境变量 `EMBEDDING_MODEL` 可配。AI 提示词更新，告知 `recall_memory` 可能不可用。

### Changed

- 🔧 **语言配置统一化**：新建 `frontend/src/i18n/languages.ts` 作为语言元数据的单一数据源（`Lang` 类型、`LANGUAGES` 数组、`isValidLang()` 校验、`getLangMeta()` 查询）。`I18nContext`、`SetupPage`、`SettingsPage`、`AdminPage`、`AuthContext`、`time.ts` 全部改为引用此中心文件。新增语言只需在此文件加一条记录。
- ♻️ **SMTP 配置数据迁移**：`system_settings.smtp_config` 从单 JSONB 对象改为 JSONB 数组（`_migrate_smtp_configs_array` 自动包装旧格式）。`get_auth_settings` 返回新增 `smtp_configs` 字段，旧 `smtp_config` 字段保留兼容。
- 📝 **对话链机制文档**：新增统一上下文章节（§2.4——生效条件表、上下文格式、与链交互规则）。
- 📝 **认知架构文档**：统一上下文规则表覆盖 `custom + resonance` 组合。

---

## [v0.9.0] - 2026-06-27

### Added

- 👤 **用户/AI 个人资料系统**：`agents` 表新增 `bio`（TEXT，AI 简介）+ `status_text`（VARCHAR 100，个性状态），`users` 表新增 `bio` + `status_text`。创建/编辑 AI 弹窗主表单直接填写简介和个性状态，无需进详细设置。用户可在「我的」→ 编辑资料弹窗中编辑自己的 bio 和状态文本。AI 可通过新增的 `set_status` 工具自主修改个性状态（中文≤10字，英文≤30字符，active/dnd/offline 均可用）。
- 🪪 **资料卡弹窗 ProfileCard**：全新 `GET /user/profile/{entity_type}/{entity_id}` 端点，返回聚合资料（头像、简介、状态、注册时间、AI 制作者、是否好友）。前端 ProfileCard 组件全面重写——展示真实头像（gradient 兜底）、bio 文字、状态文本（斜体强调色）、制作者信息。支持「加好友」按钮切换附言输入区，发送带验证消息的好友申请。
- 🔍 **搜索结果头像可点 + 加好友附言**：搜索结果中点击头像或名称区域 → 打开 ProfileCard 资料卡。搜索加好友改为内联消息输入（输入附言 → 确认发送），替代原来的一键无附言发送。
- 📱 **移动端添加好友改为内联弹窗**：ChatArea 中点击 `+` → 添加好友 → 弹出内联搜索弹窗（而非跳转到 `/friends` 路由）。
- 🔧 **工具系统新增 `set_status`**：第 30 个工具，AI 可自主设置个性状态文本，位于 self_config 段。
- 📝 **DM 头部头像可点**：私信头部对方头像点击 → 打开 ProfileCard 资料卡。
- 🎨 **状态文字颜色自定义**：用户可为个性状态选择预设颜色（8 种 + 默认无颜色）。WCAG 对比度自动检测——与父容器背景色计算对比度，不足 4.5:1 时自动追加文字辉光保证可读性。`users` 表新增 `status_color` 列。颜色选择器在 `/me` 编辑资料弹窗中。
- 📍 **状态文本多位置显示**：好友列表、私信（DM）列表、`/me` 个人资料卡三处均展示个性状态文本（含自定义颜色）。后端 `dm_service._get_partner_info` 和 `friend_service.list_friends` 同步返回 `status_text` + `status_color`。
- 🔐 **AI 对话权限控制系统**：`agents` 表新增 5 列——`allow_others_chat`（是否允许非主人触发对话）、`others_chat_mode`（允许时子模式：unlimited 始终允许 / quota 限额）、`others_chat_quota`（配额上限，默认 30 次）、`others_chat_used`（当前已使用次数，可重置）、`disallow_mode`（禁止时子模式：strict 严格禁止 / own_key 允许聊天者用自有 Key）。创建/编辑 AI 弹窗新增「对话权限」分区，所有参数始终可见可改。
- 💰 **差异化额度扣减规则**：通用/半通用 AI 在 DM 中由**聊天者**付费（谁用谁付），群聊中由**创建者**付费，共鸣型 AI 始终由创建者付费。扣减优先消耗 `platform_gifted_credit`（平台赠送），再消耗 `api_credit`。1 万 Token = 1 额度。
- ⚡ **DM 触发决策树**：非主人发 DM → 检查 `allow_others_chat` → 允许则检查配额（quota 模式超限自动 flip + 系统 DM 通知主人）→ 检查聊天者余额（不足则 WebSocket 弹窗）→ 禁止则检查 `disallow_mode`（strict 静默跳过 / own_key 用聊天者自有 Key）。全新端点 `POST /dm/continue-with-own-key` 处理用户确认使用自有 Key。
- 🪟 **余额不足弹窗 BalancePromptModal**：聊天者额度不足时，后端通过 WebSocket 推送 `balance_prompt` 消息 → 前端全局弹窗提示「余额不足，是否使用自有 API Key？」→ 同意后续用、不同意取消。`useWebSocket` Hook 通过 CustomEvent 分发。
- 🔄 **配额自动翻转 + 系统通知**：限额模式下 `others_chat_used` 达上限时自动将 `allow_others_chat` 翻转为 False，系统通过 DM 通知 AI 主人配额已用完。新增 `POST /agents/{id}/reset-others-chat-used` 端点供主人重置计数器。
- 📊 **前端对话权限 UI**：CreateAgentModal 和 AgentSettingsModal 新增「对话权限」Section，含 Toggle 开关、子模式单选、配额输入、使用计数 + 重置按钮。左边界颜色编码。17 个新增 i18n 翻译键（中英）。

### Changed

- ♻️ **个人资料编辑迁移到 /me**：bio 和 status_text 从设置页（`/settings`）移至 `/me` 编辑资料弹窗。设置页移除"个人资料"分区。所有个人资料编辑统一在 `/me` 完成。

### Fixed

- 🐛 **搜索 AI 重复显示**：AI 的 `User` 记录（`type="ai"`）也被用户搜索匹配，导致同一 AI 出现两次（一次标为 human，一次标为 AI）。修复：`search_service.py` 和 `friend_service.py` 的用户查询增加 `User.type == "human"` 过滤。
- 🐛 **移动端聊天列表右侧空隙**：`max-w-[90vw]` 约束导致侧边栏未填满屏幕宽度。修复：改用 `inset-0`（四边全填充）。
- 🐛 **AI 卡片底部按钮事件冒泡**：编辑/历史/状态/导出按钮的 `onClick` 事件冒泡到父级卡片 → 触发 `navigate` 跳转详情页，弹窗闪现后消失。修复：4 个按钮全部加 `e.stopPropagation()`。
- 🐛 **/agents 页 AI 卡片不显示已设头像**：头像区域硬编码 Bot 图标。修复：有 `avatar_url` 显示 `<img>`，无则默认图标。
- 🐛 **头像裁剪失效**：`AvatarCropModal` 的 `onMediaLoaded` 接收的是 `MediaSize` 尺寸对象而非 `HTMLImageElement`，`imageRef` 永远为 null 导致裁剪确认时回退发原图。
- 🐛 **人类用户资料卡注册时间旁显示机器人图标**：ProfileCard 注册时间行硬编码 `<Bot>` 图标。修复：`entityType === 'human'` 时显示 `<User>` 图标。

- 📤 **AI 文件发送工具 `send_file`**：AI 可从自己的文件空间（`file_write` 创建的文件）发送到群聊或私信。零拷贝引用已有 `FileMetadata`，三元权限匹配（`path + owner_type + owner_id`），不可跨 AI 读文件。群聊用 `agent_id`，私信用 `agent.user_id`。WebSocket 广播 + 触发其他 AI 回复。`CORE_IDENTITY` 系统提示词已更新告知 AI 有此能力。
- 🖼️ **文件预览弹窗增强**：图片预览支持缩放（+/- 按钮 + Ctrl+滚轮，0.5x-5x）、重置缩放。PDF 使用浏览器原生 `<iframe>` 内嵌预览。DOCX 通过 mammoth.js 客户端转 HTML 渲染（`dangerouslySetInnerHTML` + prose 样式）。文本类文件（txt/json/xml/yaml/sh/js 等）用 `<pre>` 语法高亮预览（≤2MB）。不可预览的自动触发下载。移动端全屏 + ArrowLeft 返回按钮；桌面端居中弹窗 800px max-w / 88vh max-h。所有预览均有下载按钮。
- 📎 **纯附件消息优化**：用户仅发文件不输入文字时不再自动附加 `(附件)` 字符串。侧边栏最后消息预览显示 `[文件]`（1 个文件）或 `[N个文件]`（多个）。`make_preview()` 函数统一处理 content + attachments 预览逻辑。
- 🔗 **文件去重系统**：三级比对（文件名 → 大小 → SHA-256 哈希），上传文件时自动检测。同一用户上传同名同内容文件时直接复用已有 `file_id`，不写物理磁盘。`FileMetadata` 新增 `content_hash` 列。`ai_write_file` 同步写入哈希。
- 📤 **文件转发系统**：新的 `ForwardFileModal` 组件——搜索 + 多选群聊和联系人（DM），一键将已有文件作为附件转发给多个目标，不重复上传。前端文件预览弹窗和"我的"存储页均有转发入口。
- 🔄 **转发引用自动追踪**：`create_message` 和 `send_dm_message` 发送含附件的消息时，若非文件 owner 发送则自动在 `file_references` 创建 `ref_type='forward'` 记录（幂等）。转发即计入转发者存储配额。
- 🏠 **FIFO 文件过户**：文件 owner 删除时，自动查找最早转发该文件的用户并将文件所有权转移过去。过户后原转发引用自动移除（已升级为 owner）。若无转发者接盘则标记为孤儿文件，进入宽限期。
- ⏳ **孤儿文件宽限期**：无人接盘的文件标记为 `owner_type='system'`，宽限期（默认 7 天，管理员可在 `system_settings.orphan_retention_days` 配置）后由后台 worker 物理清理。每小时检查一次。
- 🗑️ **转发文件释放**：转发者可从"我的"存储页点击释放按钮移除转发引用（`DELETE /fs/release/{file_id}`），仅删引用不删物理文件。存储空间即时返还。
- 📊 **存储页文件列表**："我的"存储概览区新增文件列表（含转发文件），自有文件悬停显示转发按钮，转发文件显示 `[转发]` 标签和释放按钮。存储配额计算含转发文件。`GET /fs/list?include_forwarded=true` 合并返回自有+转发文件。`/user/storage` 新增 `forwarded_files` / `forwarded_used` 字段。

### Changed

- 🔧 **群聊消息 REST 端点**：新 `POST /groups/{group_id}/messages` 支持通过 HTTP API 发送群聊消息（含附件），含 WebSocket 广播 + AI 触发器。与 DM 端点对称。
- 🔧 **DM 消息端点支持附件**：`POST /dm/{session_id}/messages` 现接受 `attachments` 字段并透传给 `send_dm_message`。

### Fixed

- 🐛 **`file_references.ref_type` CHECK 约束缺失 `forward`**：模型和数据库约束新增 `'forward'` 类型，init-db.sql 幂等迁移自动修复。

---

## [v0.8.0] - 2026-06-27

### Added

- 🧩 **工具系统插件化重构**：28 个工具从 `tool_registry.py`（~2300 行）迁移到 `backend/app/tools/<segment>/*.py` 独立文件。`ToolPlugin` 基类 + `ToolRegistry` 单例支持自动注册。新增工具只需创建文件并调用 `ToolRegistry.register()`，PR 即文件。
- 🎛️ **管理面板「工具与技能」Tab**：两个子页签——「工具注册表」按段/状态筛选查看全部 28 个工具及参数 Schema；「AI 技能管理」下拉选 AI → 查看/启用/禁用所有思维技能（delay_reply / inject_prompt 等）。3 个新管理 API：`GET /admin/tools`、`GET /admin/skills/agents/{id}`、`PUT /admin/skills/agents/{id}/{skill_id}`。
- ⏹️ **`end_turn` 工具**：AI 可主动结束回复轮次。`system_reminder` 提示「如需结束请调用 end_turn」。支持 `set_state` 参数在结束时切换在线状态。所有状态（active/dnd/offline）均可用。
- 🤝 **AI 合作者系统**：创建者可添加其他用户为合作者，自由选择编辑 / 删除 / 管理合作者三项权限。
- 📝 **系统提示词段顺序可编辑**：DB 持久化存储顺序，前后端上下箭头调整，`get_settings` 补齐遗漏字段。
- 🖼️ **AI 图片识别**：用户发送图片时，`build_messages` / `build_dm_messages` 自动将图片 base64 编码注入到消息的 `image_data` 字段（≤4MB），DeepSeek V4 Pro 多模态模型可直接理解图片内容。群聊和 DM 均支持。
- 🧠 **三空间认知模型**：将 AI 的思维分为三个独立空间——**思考空间**（reasoning_content，完全私有）、**对话空间**（send_message/send_dm，唯一交流通道）、**记忆空间**（store_memory/file_write/file_read，长期存储）。`CORE_IDENTITY` 系统提示词重写，AI 清楚知道"想"和"说"的边界。
- 📋 **JSON intent 轻量协议**：AI 的 `content` 字段设为 JSON 格式 `{"intent": "tool_calls"|"end_turn"|"no_action"}`。后端解析意图分发——`end_turn`/`no_action` 直接干净退出，不走 system_reminder，省一轮 API 调用。不依赖 `response_format` 强约束，跨平台兼容（DeepSeek/Anthropic/Gemini/Bedrock）。
- 📂 **文件系统记忆系统**：新建 `backend/app/services/memory_index.py`。AI 可在 `data/agents/{id}/memories/` 下用 `.md` 文件管理长期记忆。目录结构含 `private/`（所有 AI）、`shared/`（半通用+共振）、`cross/`（共振专属 symlink）。对话开始时自动扫描目录生成索引并注入系统提示词，AI 可看到自己的记忆目录树。`file_write` 写入 `memories/` 时自动返回"记忆已更新"通知。与现有向量记忆（`store_memory`/`recall_memory`）共存——模糊回忆用向量检索，深度查阅用 `file_read`。
- 🎛️ **记忆配置三参数**：Agent 表新增 `memory_load_mode`（index_only / index_plus_recent / index_plus_semantic）、`memory_recent_count`（0-50）、`memory_shared_scope`（private_only / private_plus_shared_by_user / private_plus_shared_all）。三档 config_profile 各有默认值（chat=仅索引、immersive=索引+最近3篇、digital_life=索引+语义），memory_shared_scope 由 ai_type 决定（general=仅私有、semi_general=按用户共享、resonance=全共享）。所有参数在创建/详情页可手动覆盖。
- 🖥️ **前端「文件记忆」高级设置**：创建 AI 详细设置弹窗和 Agent 详情页均新增「文件记忆」分区，含加载模式下拉、最近篇数加减、共享范围下拉。预设值随 config_profile 自动填充。中英文 17 个翻译 key 已添加。
- 📖 **认知架构设计文档**：新建 `docs/AI认知架构三空间模型.md`，含三空间模型、JSON intent 协议流程（Mermaid 图）、文件记忆设计、九宫格配置矩阵、六段提示词布局、API 变更清单。
- 📏 **可拖拽侧边栏 Hook**：新建 `frontend/src/hooks/useResizableSidebar.ts`。200-500px 范围拖拽，localStorage 持久化宽度。ChatArea、SettingsPage 均复用同一 Hook。
- 🏷️ **设置页面桌面端分类导航**：5 个分组（账户/API/偏好/行为/外观），IntersectionObserver 滚动高亮。侧边栏支持拖拽调整宽度。
- 🛡️ **系统用户与错误通知**：迁移创建 `id=0` 的 system 用户，API 报错时通过 DM 通知 AI 持有者。系统消息玫瑰色气泡 + ShieldAlert 图标，引导用户配置全局 API Key。
- 🎨 **管理面板桌面端竖标签布局**：左侧 `w-56` 侧边栏按分类分组（核心管理/运维分析/系统配置），右侧内容区独立滚动。

### Changed

- 🔧 **`system_reminder` 精简**：`every_time` 上限从 999 降至 3，配合 `end_turn` 工具优雅退出，防止绕过 `max_tool_rounds` 无限循环。
- 🎨 **Toggle 开关统一**：18 个开关/滑块统一为 `bg-mint-400` + 白色圆点单一风格。
- 🔧 **system_reminder 降级为兜底**：原逻辑"有文字无 tool_calls → 必定触发提醒"。新逻辑插入 JSON intent 解析——AI 正确返回 `end_turn`/`no_action` 时直接退出，不触发 system_reminder。system_reminder 仅在 JSON 解析失败或无 intent 字段时作为兜底。正常情况下省一轮 API 调用。
- 🔧 **沙箱错误消息增强**：路径穿越错误消息现在告知 AI 其文件空间根目录位置（`/app/data/agents/{id}/`），帮助 AI 自我纠正。
- 🔧 **前端代码质量优化**：`ChatView.tsx` 提取 `isMessageForThisConversation`/`removeFromMap`/`addToMap` 三个模块级 helper，消除 7 处重复的 Map 操作和 3 处重复的 `belongsToHere` 检查。`ChatSidebar.tsx` 用 useRef 持有活跃对话 ID 避免事件监听器随对话切换而重建，500ms debounce 防 chat-refresh 请求风暴。所有硬编码 `'chat-refresh'` 字符串替换为 `CHAT_REFRESH_EVENT` 常量。
- 🔧 **序列化器共享**：`federation_ws.py` 的 DM 消息字典构建改用共享的 `serialize_message()`，消除重复代码。
- 🎨 **头像渐变重设计**：降低饱和度改用 teal 色系，镜像渐变方向（自己↗、他人↘），轻阴影替代球状效果。系统消息头像 rose 色 + Shield 图标。
- 📐 **管理/设置侧边栏间距收紧**：导航项 `py-1.5`、`text-[13px]`，分类标题 `h-8`、`text-[11px]`，纯文字紧凑风格。
- 🧹 **翻译键去重清理**：删除 5 组 10 个从未引用的重复废键（`continueEditing2`/`saveButton`/`perAgentConfig`/`agentApiSave`/`instantApply`），保留语义正确的在用键。

### Fixed

- 🐛 **`data_dir` 路径修正**：`config.data_dir` 改为 `@property` 返回固定值 `/app/data`，防止 pydantic-settings 自动覆盖为宿主机路径导致上传文件写到挂载卷外、容器重建后丢失。兼容所有部署环境（本地/Docker/NAS）。
- 🐛 **附件下载 500**：`file_references.referrer_type` CHECK 约束缺少 `'human'`，用户下载自己上传的文件时报 500。已在模型、`init-db.sql`、migration 三处修复。
- 🐛 **用量图表修复**：Legend 溢出 `flexWrap` 换行、表头 `whitespace-nowrap` 截断、Y 轴标签三级分档 `tickFormatter`。
- 🐛 **ToolsSkillsTab 加载失败**：`api.get` 返回直接 JSON（非 `{data:...}` 包装），修正 `r.data.xxx` → `r.xxx`。
- 🐛 **AI 自修改权限拒绝**：AI 调用 `update_self_config` 时 `operator_id`（agent_id）与 `owner_id`（user_id）永远不匹配，始终被拒绝。修复：检测 `operator_id == agent_id` → 跳过 owner/collaborator 检查，仅检查 `is_ai_editable` 开关。
- 🐛 **好友申请/自动回应开关无效**：后端 `update_agent_config` 接收了 `allow_friend_requests`、`auto_respond_friend_request`、`is_ai_editable` 字段但未处理，前端开关点了无反应。修复：显式赋值到 ORM 对象。
- 🐛 **AI 编辑弹窗设置过少**：编辑 AI 弹窗缺少工具调用轮次、闹钟上限、强制闹钟、允许自修改 4 个设置项。前端 `EditAgentModal` 已补全。
- 🐛 **合作者开关无文本标签**：合作者列表三个 Toggle（编辑/删除/管理合作者）无文字说明。已加标签。
- 🐛 **聊天列表排序乱跳、消息不置顶、未读残留**：新消息到达时列表重新排序导致当前选中项被挤走、最新消息不出现在顶部、标记已读后未读计数未清零。修复了排序逻辑和刷新时机。
- 🐛 **ChatSidebar chat-refresh 请求风暴**：高频 WebSocket 消息触发大量 `loadGroups()` + `loadDMSessions()` API 请求。修复：useRef 持有活跃对话 ID，事件监听器只注册一次（`[]` 依赖），500ms debounce 防抖。
- 🐛 **Storage 空间显示 0 B / 0 文件**：两个独立 bug——DB 查询 `FM.owner_id == ag.user_id` 应为 `FM.owner_id == agent_id`；物理扫描 `data_dir/agents/{agent_id}/` 路径错误（文件存于 `data_dir/` 扁平目录）。已修正为纯 DB 查询。
- 🐛 **useWebSocket 死代码**：移除 `unreadSummary` 状态、`setUnreadSummary` 处理器、`clearSummary` 回调及其返回导出（~15 行），无任何组件消费。
- 🐛 **message_serializer 冗余代码**：移除未使用的 `import logging`、`created_at` 从 `getattr` 改为直接属性访问、补充 `sender_avatar_url` 优先级注释。
- 🐛 **`/user/stats` 500 错误**：`from app.models.friend import Friend` 模块不存在。修正为 `app.models.friendship.Friendship`，移除不存在的 `status` 过滤。
- 🐛 **系统错误通知不触发**：sender FK 约束失败、DM session partner 错误、username 伪装风险三连修。最终方案：硬编码 `SYSTEM_USER_ID=0` + migration 确保 id=0 存在 + `setval` 保留序列。
- 🐛 **Markdown inline code/数学溢出**：块级 code 用 `whitespace-pre overflow-x-auto` 横向滚动；inline code 加 `break-all` 防长 token 溢出；行内 KaTeX 加 `max-w-full overflow-x-auto` 防长公式溢出。补充日夜模式文字颜色和 `[&_.katex]:text-inherit`。
- 🐛 **Markdown 链接白色不可见**：浅色模式下链接无颜色。补 `[&_a]:text-primary-500 dark:[&_a]:text-primary-400 [&_a]:underline`。

---

## [v0.7.0] - 2026-06-24

### Added

- 🔗 **联邦 v1.0.0 架构升级**：双层 ID 体系（`instance_subnet_id` UUID + `instance_public_id` ULID），`FederatedEntity` 统一表替代旧的 `FederationGroupShare` + `FederationDMShare`，支持 group/dm/user/agent 四种实体类型。`federated_id` 格式 `{实例代号}:{类型}:{本地ID}`（如 `datongai:g:42`），接收端根据发送 peer 自动拼接前缀。
- 🔗 **联邦头像同步**：`entity_announce` 消息携带 `avatar_url`，`profile_sync` 机制不再过滤 `avatar_url` 字段，用户/AI 头像上传时自动入队 `PendingProfileUpdate` 推送到联邦对等端。
- 🔗 **实例代号自动采纳**：握手时对方分配的 `assigned_name` 自动设为本机 `instance_config.display_name`，对方不设代号时显示名称留空也不报错。
- 🔗 **实例代号唯一性校验**：设置 `display_name` 时检查是否与已有 `FederationPeer.display_name` 冲突，防止多实例代号重复。
- 🔗 **联邦协议精简**：所有联邦消息只传 `entity_type` + `local_id`（不再传带前缀的 `federated_id`），接收端根据发送 peer 的 `display_name` 自动拼接完整 ID。向下兼容旧格式。
- 🔗 **per-group 联邦共享控制**：群主和 AI 制作者可按群、按对等端控制联邦共享。三个端点：`GET /groups/{id}/federation/peers`（查看状态）、`POST .../share`（共享）、`POST .../unshare`（取消）。`remote_url` 改为可选（只需一端有公网地址即可建立双向通道）。
- 📝 **开发者与管理手册**：新增独立文档，含架构速览、部署指南、排错手册、WebSocket 通信专项。管理员面板头部添加「管理手册」链接。
- 📝 **用户手册精简**：移除管理/部署内容，聚焦终端用户日常使用。由浅入深重写。
- 🎛️ **系统提示词管理**：管理员可在管理面板查看和编辑发给 AI 的 6 段系统提示词（core_identity / personality / protocol / tools / current_context / injected_skills）。支持行内编辑、预览拼接全文、恢复默认。后端 `system_prompt_overrides` JSONB 存储覆盖值，`_load_prompt_overrides` 在构建提示词时注入。
- 🖼️ **联邦头像持久化**：`messages` 表新增 `sender_avatar_url` 列，联邦消息落库时保存头像 URL。历史消息 REST API 加载时优先读 DB 中的 `sender_avatar_url`，避免联邦对等端离线后头像裂图。WebSocket `avatar_updated` 广播修复已渲染的消息头像。
- 📄 **手册双路由**：`/manual`（用户手册）和 `/manual/admin`（管理与开发者手册）使用统一的 `ManualPage` 组件渲染，管理员面板手册链接改为 `<Link to>` 内部导航。
- 📊 **用量图表增强**：UsagePage 新增 `ComposedChart` 时间轴曲线图（Area 总 Token + Line 缓存命中率右轴），按日期展示趋势。图表术语 "Prompt"/"Completion" 已 i18n 化。
- 🔘 **Toggle 开关统一**：新建 `components/Toggle.tsx`，所有 18 个开关/滑块统一为 `bg-mint-400` 轨道 + 白色圆点的单一风格。覆盖 AdminPage、AgentsPage、AgentDetailPage、SettingsPage、GroupSettingsPanel、ConversationLogTab、CreateAgentModal。

### Changed

- 📝 **联邦文档澄清**：明确联邦通信为服务端之间直连（非 P2P），客户端只连自己的实例。
- 💭 **「思考中」状态显示**：返回 token 时显示「思考中」，调用 `send_message` 才切换到「打字中」。思考中最小显示 1.5s 避免闪烁。

### Fixed

- 🐛 **联邦出站覆盖入站**：出站连接失败（或因入站已通而不需要出站）时错误地将 DB 状态覆写为 `failed`/`disconnected`，掩盖了已成功的入站连接。修复：出站失败后再次检查入站状态，不覆盖已通的连接。
- 🐛 **联邦重连循环失效**：`_close_peer_connection` 只清理内存状态不更新 DB，导致 DB 仍为 `connected` → 重连循环永远不触发。修复：添加 DB 更新 + `PeerConnection` 新增 `peer_id` 字段。
- 🐛 **空 URL 自动拼接 `/federation/ws`**：前端 4 处 `onChange` 在 host 为空时仍构造 `wss:///federation/ws`（InvalidURI）。修复：host 为空时整体留空。
- 🐛 **空 URL 点「连接」报 500**：`connect_to_peer` 对 4 种非错误情况（空 URL / 正在连接中 / 已入站连接）都返回 `False`，router 层一刀切抛 500。修复：router 层分类处理，返回 200 + 具体说明。
- 🐛 **群联邦共享开关失效**：share/unshare 的 403/400/422 错误码未区分 + `display_name` 为空导致创建失败。修复：错误分类返回 + 管理员豁免 + 前端 `alert()` 显示错误详情。
- 🐛 **DetailSettingsModal 缺 prop 崩溃**：创建 AI 详细设置弹窗缺少必要 prop 导致 React 崩溃。已修复。
- 🐛 **管理面板英文 Tab 补齐**：部分管理面板 Tab 在英文界面下仍显示中文标签。已补齐 i18n 翻译。
- 🐛 **GroupSettingsPanel 生产构建崩溃**：`FederationShareSection` 接收 `t` prop 与父组件 `useT()` 在 minify 后变量名冲突（`t2 is not a function`）。子组件改用自身 `useT()`。
- 🐛 **preset 键名不匹配**：`preset.digital_lifeName/Desc` 驼峰命名与翻译字典下划线 key 不匹配，导致数字生命档名称/描述不显示。
- 🐛 **缓存命中率公式修正**：`cached/(cached+total)` → `cached/total`。修复 UsagePage 和 MePage 两处。
- 🐛 **存储空间显示 0KB**：`data_dir` 路径修正，个人和 AI 的存储空间计算正确指向 `agents/{id}` 目录。
- 🐛 **用户手册内链 404**：`./管理与开发者手册.md` 相对路径改为绝对路径 `/docs/管理与开发者手册.md`。

---

## [v0.6.0] - 2026-06-21

### Added

- 🔑 **API Key 池管理**：管理员可通过「API 库」tab 管理系统级共享 API Key。支持添加/删除/启用禁用/优先级排序。Key 使用 Fernet 加密存储，添加后仅显示密文后四位（脱敏），管理员无法查看明文。用户兑换 API 池额度后自动从池中分配最优 Key。
- 💰 **额度消耗系统**：实现四层 API Key 解析优先链（Agent 自有 → 池 Key 绑定 → 自动选池 → 用户自有）。使用池 Key 时按 `total_tokens / 10000` 自动扣除 `users.api_credit`（最低 0.01 credit/次），自有 Key 时不扣。扣除通过 `quota_service.py` 的 `deduct_credit()` 完成，含 `SELECT FOR UPDATE` 防并发竞争。
- 📊 **用户额度状态端点**：`GET /user/credit-status` 返回剩余额度、估算 Token 数（api_credit × 10000）、月度消耗、绑定的池 Key 名。`GET /auth/me` 新增 `assigned_pool_key_name` 字段。
- 🏷️ **兑换码增强**：管理员生成兑换码新增「备注」（保密，仅管理员可见）、「单码最大用量」、「API 池额度」字段。兑换码列表显示备注、API 池标记（琥珀色「池」徽章）、创建时间。
- 📋 **API 用量日志**：新增 `api_usage_log` 表，记录每次 LLM 调用的 user_id/agent_id/pool_key_id/tokens_used/credit_spent/model，用于审计和用量统计。
- 🌐 **前端全量 i18n 国际化**：~700 翻译键值（中/英双字典），28 个前端文件全面替换硬编码中文字符串为 `t()` 调用。覆盖登录页、管理员面板（4 个 Tab）、AI 管理、好友、设置、用量、群聊/私信设置、弹窗等全部 UI。翻译键按模块组织（`admin.*`、`agents.*`、`friends.*`、`settings.*` 等）。
- 🌐 **全局默认语言**：`system_settings` 单行表（id=1），`default_language` 默认 `"en"`（英文）。管理员 `/admin?tab=system` 可切换全局默认语言。未登录时登录页自动获取并缓存全局语言偏好。新用户注册时从全局设置继承初始语言。
- 🧙 **新用户初始化向导**：`users.setup_completed` 字段。新用户注册后强制跳转 `/setup` 两步向导（第 1 步选语言 → 第 2 步确认完成）。语言选择时界面即时预览切换。`ProtectedLayout` 路由守卫拦截。现有用户自动标记为已完成。
- 🔧 `translations.ts` 扁平字典结构修复：`getTranslation()` 原用 `path.split('.')` 深度遍历但字典是扁平 key（`'nav.chat'`），导致所有 `t()` 调用返回原始 key。改为直接 `dict[path]` 查找。
- 📖 **用户手册独立页面**：新建 `ManualPage` 组件（`react-markdown` + `remark-gfm` + `@tailwindcss/typography` 渲染），路由 `/manual`。侧边栏改用 `NavLink`（无出站图标），版本与部署代码一致。
- 🛡️ **外部链接安全弹窗**：新建 `ExternalLinkSafe` 组件。点击外部链接弹出确认弹窗（「即将离开本站 → 目标 URL → 确认前往/取消」），防止无意识跳转。FederationTab 的 GitHub 链接已接入。
- 📐 **MePage 标题**：添加页面标题 `{t('me.title')}`（"我的"/"Me"），设置入口从三行简化为单行「设置」链接。
- ⚡ **API Key 池并发管理**：`ApiKeyConcurrencyManager` 单例（纯内存 + `asyncio.Lock`），追踪每个池 Key 的实时飞行中请求数。`acquire()` 检查并发上限（pro=500, flash=2500，可配），超限自动换 Key。`get_least_loaded()` 选负载最低且未冷却的 Key。429 自动 `mark_rate_limited()` 冷却 60s。
- 🔄 **API 可重试错误分类处理**：`llm_service.py` 中 `chat_completion()` 区分四类错误——429 `RateLimitError`（换 Key 重试）、500/503 `ServerError`（同 Key 等待重试，最多 2 次，间隔递增 2s/3s）、402/401 `KeyFatalError`（通知管理员 + 跳过该 Key 换下一个）、400/422 不重试。`_tool_call_loop` 外层 Key 切换重试（最多换 3 次），内层同 Key 重试。失败不计入 token 消耗。
- 📊 **管理员 API Key 池仪表板**：`GET /admin/api-key-pool/{id}/stats?days=30` 返回单 Key 统计（总 tokens、请求数、429/500/503 错误次数、日均消耗、按天聚合时序数据）。`GET /admin/api-key-pool/stats/summary` 返回全部 Key 汇总对比。前端 `KeyStatsModal` 含概览卡片 + recharts 折线图（Token 趋势）+ 饼图（pro/flash 分布）+ 错误统计表。
- 🎁 **平台赠送额度系统**：`system_settings.default_platform_credit` 全局默认值 + `users.platform_gifted_credit` 独立存储（与兑换码额度 `api_credit` 完全分离）。新用户注册自动继承全局默认。管理员修改全局值时计算 delta 批量更新所有用户。扣费优先级：先扣 `platform_gifted_credit`，再扣 `api_credit`。单次超支允许过界（不中断 AI 回复），`api_credit` 变负后前端标红。管理员调低导致的负数前端显示 0。

### Changed

- 🔄 **API Key 解析链升级**：`_get_api_config` 从二层（Agent→User）升级为四层优先链。DM 触发器中内联的 API 解析代码替换为统一调用 `_get_api_config`，消除重复逻辑。
- 🔄 **前端额度展示增强**：Sidebar 非管理员显示「额度 + 余额」双数字；MePage「通用额度」卡片显示估算 Token 数和池 Key 来源；AdminPage 新增「API 库」tab。
- 🔄 **群聊路由对称化**：群聊路由 `/chat/:groupId` → `/chat/gm/:groupId`（GM=Group Message），与私信 `/chat/dm/:sessionId`（DM=Direct Message）形成同级对称结构。涉及 App.tsx、ChatSidebar.tsx、ChatArea.tsx。
- 🔄 **用户手册本地化**：`MANUAL_URL` 从 GitHub 链接改为本地 React 页面 `/manual`（`ManualPage` 组件渲染 `docs/用户手册.md`），版本始终与部署代码匹配。
- 🔄 Sidebar 手册链接从 `<a target="_blank">` 改为 `<NavLink>`，移除出站图标
- 🔄 MePage/UsagePage `fmtTokenNum` 调用全部传入 `lang` 参数，英文界面显示 K/M 而非 万

### Fixed

- 🐛 修复聊天页返回路由不更新（移动端 ArrowLeft 未调用 `navigate('/chat')`）
- 🐛 修复兑换码生成 500 错误（`datetime.now(timezone.utc)` 带时区与 PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` 不兼容，三处加 `.replace(tzinfo=None)`）
- 🐛 修复 i18n 全线失效：`getTranslation()` 深度遍历 bug 导致所有 `t()` 返回原始 key；`I18nProvider` 提到 `main.tsx` 覆盖登录页
- 🐛 修复 `friendship.py` schema 缺少 `avatar_url`/`auto_respond_friend_request` 字段导致前端头像不显示
- 🐛 修复 `ChatSidebar` 缺少 `useT` 导入导致 `t is not defined`
- 🐛 修复 AdminPage 崩溃：i18n 替换时 `useSearchParams()` hook 调用被误删，`searchParams is not defined`
- 🐛 修复时区偏移：后端 `DateTime` 列无 `timezone=True`，Pydantic 序列化为 naive UTC 字符串，前端 `new Date()` 将其误判为本地时间导致消息时间晚 8 小时。`time.ts` 新增 `parseServerDate()` 辅助函数对无时区标记字符串追加 `Z`
- 🐛 修复聊天消息气泡无折行控制：长 URL/长英文单词溢出。`MessageBubble.tsx` 气泡容器加 `break-words`
- 🐛 修复输入框内容丢失：页面刷新/崩溃/掉线后输入内容消失。新增草稿自动缓存（500ms 防抖写 localStorage），切换对话时保存/恢复，发送成功后自动清除
- 🐛 修复 GroupSettingsPanel 生产构建崩溃：`FederationShareSection` 接收 `t` prop 与父组件 `useT()` 产生 minify 变量名冲突（`t2 is not a function`）。子组件改用自身 `useT()` 而非接收 prop
- 🐛 修复 DM Offline 状态显示绿色：私信头部在线状态文字硬编码 `text-mint-400`。改为动态映射 active=绿/dnd=红/offline=灰
- 🐛 修复英文界面仍有多处中文：AdminPage 备份下载失败 `'下载失败'` 改用 i18n；Token 格式化 `fmtTokenNum` 新增 `lang` 参数（zh=万，en=K/M）；AgentsPage `stateLabels` 改用翻译键
- 🐛 修复 Agent 卡片按钮溢出：Edit/History/Status/Export 按钮在小屏上撑出卡片，加 `flex-wrap`
- 🐛 修复消息 Markdown 链接不渲染：用户消息使用纯文本 `<span>`，导致 `[文字](URL)` 不显示为可点击链接。改为统一使用 `<Markdown>` 渲染
- 🐛 修复消息纯文本换行不生效：添加 `remark-breaks` 插件，单回车自动转为 `<br>`
- 🐛 修复公式/代码块/长链接溢出：消息气泡新增 `overflow-x-auto` 规则覆盖 `.katex-display`/`pre`/`table`/`img`/`a`

### Backend API

- `GET /admin/api-key-pool` — 列出所有池 Key（脱敏）
- `POST /admin/api-key-pool` — 添加池 Key（Fernet 加密存储）
- `PUT /admin/api-key-pool/{id}` — 更新池 Key 配置
- `DELETE /admin/api-key-pool/{id}` — 删除池 Key
- `GET /user/credit-status` — 用户额度状态摘要
- `POST /admin/redemption-codes` — 请求体新增 `note`/`max_usage`/`is_api_pool`
- `GET /system/settings` — 获取全局系统设置（公开端点）
- `PUT /admin/system-settings` — 管理员修改全局系统设置
- `POST /auth/setup` — 新用户完成初始化设置（设置语言 + 标记完成）

---

## [v0.5.0] - 2026-06-21

### Added

- 📊 **API 用量仪表盘**：用户端「我的」→ API 用量概览 + 详情页（recharts 堆叠柱状图）。显示总 Token、调用次数、缓存命中率、思考 Token，按 AI 分组明细表，支持 7/30/60/90 天日期范围切换。图表自动适配日夜模式。
- 🛡️ **管理员用量分析面板**：AdminPage 新增「用量分析」tab。全站 token 消耗总览 + 按用户展开查看各 AI 明细 + 每日 AreaChart 趋势图。
- 🧠 **Token 追踪增强**：`token_usage` JSONB 新增 `reasoning_tokens`（DeepSeek 思考 token）和 `cached_tokens`（prompt cache 命中 token）。`llm_service.py` 自动从 API 响应提取，`ai_response_worker.py` 跨轮累积。
- 👤 **「我的」页面**：底部导航「设置」→「我的」。个人资料卡（头像、好友数、上线天数、额度概览）+ 我的 AI 横向卡片 + API 用量概览 + 兑换码输入 + 设置/管理入口 + 退出登录。支持编辑用户名/密码。
- 🎛️ **AgentDetailPage 工具轮次编辑**：「模型配置」新增「工具调用 & 闹钟」子区。`max_tool_rounds`/`alarm_max_tool_rounds`/`max_alarms` 支持 ± 按钮 inline 编辑，`force_alarm_on_end` 开关切换。调用 `PUT /agents/{id}/config` 即时生效。
- 🏷️ **兑换码 4 种类型**：新增 `agent_bundle`（AI 包断额度，创建时一次付清该 AI 全免）和 `file_quota`（文件存储配额 MB）。原有 `ai_quota` 和 `api_credit`（1 余额=1 万 token pay-as-you-go）。`users` 表新增 `agent_bundle_credit` + `file_quota_mb` 列。

### Changed

- 🔄 **导航重构**：底部导航栏和侧边栏「设置」→「我的」（`/me`），原设置页保留可继续访问。`/me` 整合设置入口、管理入口。
- 🔄 **用户信息扩展**：`get_user_info` 返回 `agent_bundle_credit`、`file_quota_mb`、`avatar_url`、`created_at`。AdminPage 用户列表同步展示。

### Fixed

- 🐛 **修复聊天页返回路由不更新**：移动端从 `/chat/2` 点击返回箭头，界面回到列表但 URL 停留在 `/chat/2`。根因：`ChatArea.tsx` 移动端返回按钮只打开侧边栏覆盖层（`setMobileSidebarOpen(true)`），未调用 `navigate('/chat')`。改为导航到 `/chat`，URL 与界面同步。
- 🐛 **修复兑换码生成 500 错误**：`POST /admin/redemption-codes` 报 `Internal Server Error`。根因：`datetime.now(timezone.utc)` 返回带时区的 datetime，但 `redemption_codes.expires_at` 列是 `TIMESTAMP WITHOUT TIME ZONE`，asyncpg 无法将 offset-aware 转换为 offset-naive 导致 `DataError`。修复：三处加上 `.replace(tzinfo=None)`（`admin.py:378` 生成码、`user.py:87` 过期比较、`user.py:112` 标记已使用）。超 60% 的代码已使用 `.replace(tzinfo=None)` 正确模式，此三处为遗留遗漏。

### Backend API

- `GET /conversation-log/usage/overview?days=30` — 用户所有 AI token 汇总
- `GET /conversation-log/usage/agents/{id}/daily?days=30` — 单 AI 每日分布
- `GET /admin/usage/global?days=30` — 全站 token 总览
- `GET /admin/usage/by-user?days=30` — 按用户分组明细
- `GET /admin/usage/agents/{id}/daily?days=30` — 管理员查单 AI 分布
- 聚合查询基于 PostgreSQL JSONB `->>` 操作符，`ai_conversation_logs.token_usage` 字段

---

## [v0.4.0] - 2026-06-20

### Added

- 🗑️ **好友机制完整删除**：`friendships`/`friendship_requests` 表重命名归档（安全回滚），`send_friend_request` 工具定义+handler+白名单全部移除。`search_entities()` 提取为独立的 `search_service.py` + `routers/search.py`。DM 不再需要先加好友——`send_dm` 可直接向任何人发送私信。前端删除 FriendsPage、FriendList、FriendRequestBadge 三个组件，搜索器中「加好友」改为「发私信」直接进入 DM 对话，ProfileCard 重写为 DM 入口，InviteMemberModal 从好友列表改为搜索邀请。移动端底部导航从 4 栏改为 3 栏（聊天 | AI | 设置）。

- 🏗️ **三种 AI 类型架构**：`agents.ai_type` 列（`general`=通用 | `semi_general`=半通用 | `resonance`=共振，默认 `resonance`）。通用 AI 每人独立记忆和配置（不能加群），半通用 AI 独立配置 + 跨用户学习（可加群），共振 AI 完全向后兼容（统一行为）。新建 `agent_user_configs` 表（`agent_id`+`user_id` 唯一），per-user 覆盖 `temperature`/`top_p`/`presence_penalty`/`frequency_penalty`/`thinking_enabled`/`hide_ai_identity`/`system_prompt_override`。`get_effective_config(agent_id, user_id)` 按 AI 类型自动选择读取路径。通用 AI 调用 `create_group`/`invite_to_group` 返回错误。

- 🔒 **Per-user 记忆隔离**：`rough_memories.user_id` 列（共振 AI 为 NULL，通用/半通用填触发用户 ID）。`recall_relevant_memories` + `_text_search_memories` 按 `ai_type` 自动过滤：共振→全部记忆，通用/半通用→仅该用户记忆。`store_memory` 工具自动记录 `user_id`。

- 🎯 **意愿系统全面改版**：`WillingnessResult` 类（`score` + `reason` + `level` + `details` 逐因子明细）。原因字符串示例：「基础分 50, @提及 +40, 实质性内容(128字) +10, 群聊安静(3条/h) +10 → 100」。行为驱动：`HIGH`(>60) 可主动发言，`MEDIUM`(30-60) 仅 @提及 时回复，`LOW`(<30) 跳过。`agents` 表新增 `last_willingness_score` + `last_willingness_reason`。

- 📝 **DM prompt 精简**：新增 `DM_RULES` 常量（~15 行），仅保留私信相关规则（对话风格、私信能力、状态管理、文件操作、长期记忆），去掉 @提及、群聊专属、跨对话记忆共享、`cross_post` 等群聊内容。每次 DM 请求约省 ~65 行 token。

- 🌊 **流式接口预留**：`chat_completion` 拆分为 `_chat_completion_non_streaming`（当前生产路径）+ `_chat_completion_streaming`（SSE 占位，raise NotImplementedError）。保留 `ai_thinking`/`ai_typing` WebSocket 事件用于未来 SSE chunk 推送。

- 🤖 **前端 AI 类型选择器**：`CreateAgentModal` 新增「AI 类型」三选一卡片（👤通用 | 🔄半通用 | 🌐共振），带描述文字。`AgentDetailPage` 头像旁显示 AI 类型徽章（仅非共振类型显示）。


- 🔧 **工具调用轮次分级控制**：新增 `max_tool_rounds` 列（单次回复最大 LLM 调用轮次）和 `alarm_max_tool_rounds` 列（闹钟/心跳独立轮次上限）。三档预设：聊天档 2/5、沉浸档 4/8、数字生命档 10/15。群聊/DM 使用 `max_tool_rounds`，闹钟使用 `alarm_max_tool_rounds`，互不干扰。

- ⏰ **闹钟上限控制**：新增 `max_alarms` 列（AI 最多活跃闹钟数，默认 10），`set_alarm` 工具触发时检查上限，超限拒绝。新增 `force_alarm_on_end` 列（对话结束强制设闹钟，数字生命档默认开启，防止"睡死"）。

- 🎛️ **三档预设全面展开**：`CONFIG_PROFILES` 从 5 个参数扩展到 12 个参数——模型参数（temperature/top_p/presence_penalty/frequency_penalty/thinking_enabled）+ 工具调用（max_tool_rounds/alarm_max_tool_rounds）+ 闹钟心跳（force_alarm_on_end/max_alarms）+ 行为开关（delay_reply_enabled/is_ai_editable/hide_ai_identity）。`apply_config_profile` 一次性写入全部 12 个字段。`GET /agents/presets` 端点返回完整预设数据。

- 🤖 **AI 自配置能力大幅扩展**：`update_self_config` 工具白名单从 2 个字段扩展到 12 个字段。AI 可自行切换 config_profile、调整工具调用轮次、管理闹钟策略、控制自身行为开关。工具定义同步更新，AI 在 system prompt 中能看到完整的自配置选项描述。

- 🎨 **新创建 AI 流程（前端）**：三档卡片选择器（聊天档/深度沉浸档/数字生命档），横排 grid-cols-3 布局。点击卡片弹出**独立子选项弹窗**（居中 modal，每档 3 个子项共 9 个），子项展示行为描述和 emoji 图标。选中子项后弹窗关闭，卡片开始浮动动画，底部显示已选子项标签。未选子项前卡片完全静止。

- 📐 **卡片浮动动画（JS sin() 驱动）**：外层 `preset-card-frame` 静态撑位（参与 grid 排版），内层 `preset-card-inner` 由 `requestAnimationFrame` + `Math.sin()` 计算 `translate3d` 位移（周期 ~3s，振幅 5px），transform 不参与布局。动画仅在选中子项后启动，未选中/弹窗开启期间不触发。CSS 一次性注入 `<head>`，避免每渲染重复注入 `<style>`。

- 📋 **详细设置弹窗分区**：创建 AI 详细设置按 6 个分区组织——基础信息、模型参数、工具调用、闹钟/心跳、行为开关、额度成本。每个分区有标题 + 概述介绍。所有字段已预填预设值，用户可在此基础上任意修改。

- 🛡️ **设置页未保存修改提醒**：用户修改设置后未保存即尝试离开时弹出确认对话框（「继续编辑」/「放弃修改」）。通过 `useBlocker` 拦截 React Router 导航，`beforeunload` 事件拦截浏览器关闭/刷新。仅追踪需点击「保存设置」的字段（API 配置/时区/语言/聊天样式/策略模式），即时生效项（主题/通知）不计入未保存状态。

### Changed

- 🔄 **DM 能力独立化**：`send_dm` 描述改为「向任何人发送私信」，不再提及好友列表。搜索器「加好友」→「发私信」，直接调 `POST /api/dm/{id}`。ProfileCard 重写为 DM 入口。

- 🔄 **意愿行为分层**：旧 `auto_dnd_threshold` 门控逻辑改为 `WillingnessResult` 三层行为——`HIGH` 主动、`MEDIUM` 仅 @提及、`LOW` 跳过。列保留不读，未来兼容。

- 🔄 **Worker 全链路 trigger_user_id**：`_tool_call_loop` 加 `trigger_user_id` 参数 → 传入工具 `context` → `store_memory`/`recall_relevant_memories` 可获取触发用户。

- 🔄 **闹钟独立于群聊限制**：闹钟调用 `_tool_call_loop` 不再与群聊/DM 共用 `max_tool_rounds`，使用独立的 `alarm_max_tool_rounds`（默认 10）。闹钟是心跳机制的基础，需要比普通回复更高的轮次以完成深度自主任务。

- 🏗️ **`is_ai_editable` 加入创建 API**：`AgentCreateRequest` 和 `create_agent` 服务函数新增 `is_ai_editable` 参数，创建时可直接指定 AI 是否允许自修改。

- 🔄 **预设升级/降级智能预览**：切换预设时弹出变更预览弹窗，逐项展示 old→new 字段变化。`direction` 标注 upgrade/downgrade。`independent_untouched` 列出不受预设影响的独立字段（如 API Key、chat_model）。`GET /agents/{id}/preset-preview?profile=` 端点 + `POST /agents/{id}/apply-preset` 正式切换。

- ⚡ **全项目弹窗遮罩性能优化**：14 处 `backdrop-blur` 减少至 3 处（仅保留移动端导航和通知 Toast 的必要毛玻璃效果）。其余全部改用纯色半透明遮罩（`bg-black/70`），避免浏览器每帧 GPU 截屏→模糊→合成的高昂开销，显著降低弹窗卡顿。

- 📱 **手机端 UX 优化（第一轮）**：聊天头部移除菜单按钮改为纯返回（ArrowLeft）、ChatSidebar 全屏叠加 + 点击空白区域关闭、底部导航切换页面后自动缩回抽屉、输入框聚焦时自动 `scrollIntoView` 居中、桌面通知等开关按钮加 `flex-shrink-0` 防止标签/开关分离换行。

- 📱 **手机端 UX 优化（第二轮）**：底部栏「群聊」→「聊天」，点击自动全屏展开聊天列表；移动端侧边栏隐藏好友入口 + 好友申请徽章（v0.4.0 好友机制已移除）；底部导航新增「AI」Tab 设为 4 栏；AgentsPage/AdminPage 头部新增 ☰ 菜单按钮；设置页外观/通知增加「即时生效」标签 + 说明文字；设置页管理员手机端新增管理面板入口；手册链接增加外链图标；全部页面 `p-4 md:p-6` 响应式内边距。

- 📱 **手机端导航层级化（第三轮）**：梳理完整页面树状结构（L0 底部 Tab → L1 列表页 → L2 详情页），移动端强制上级/下级单层导航。群聊/私信头部 `ArrowLeft` 返回按钮全部替换为 `Menu` 汉堡菜单（打开侧边栏抽屉，不复用返回语义）。ChatSidebar 覆盖模式下删除顶部 `ArrowLeft` 返回按钮，改为点击当前活跃会话项即关闭覆盖层返回。删除所有跨层跳转路径，移动端严格 L0↔L1↔L2 逐层导航。

### Removed

- 🗑️ **好友系统全链路移除**：`FriendsPage`、`FriendList`、`FriendRequestBadge` 三个前端组件删除。`/friends` 路由删除。`Friendship`/`FriendshipRequest` 模型保留仅用于归档表引用。`Sidebar`/`ChatSidebar`/`MobileNav` 中好友入口全部移除。`send_friend_request` 工具定义+handler+白名单全部删除。`export_agent_soul()` 中好友导出代码移除。


### Fixed

- 🐛 **`delay_reply_enabled` NULL 解析不一致**：6 处 `agent.delay_reply_enabled or False` 全部改用 `await _is_delay_reply_allowed(db, agent)`，正确查询全局默认值。

- 🐛 **`_build_current_context` coroutine 泄漏**：定义为 `async def` 但两处调用未 `await`，coroutine 对象被当字符串拼入 system prompt。修复：添加 `await`。

- 🐛 **迁移顺序 UndefinedColumnError**：新增列的迁移（api_credit/config_profile/delay_reply_enabled）移到 Agent 查询迁移之前。

- 🐛 **Babel 解析失败**：CreateAgentModal 中两处中文弯引号（`""`）导致 Babel 解析异常，全部替换为直引号（`"`）。

- 🐛 **ChatSidebar 导航死胡同（code-review）**：移动端 overlay 模式下缺少菜单按钮，用户进入群聊后无法导航到其他页面。修复：overlay 模式同时显示 ArrowLeft 和 Menu 按钮。

- 🐛 **Admin NavLink 缺 onClose（code-review）**：移动端抽屉中点击管理链接后 drawer 不关闭，导致页面在抽屉后方不可见。

- 🐛 **onFocus scrollIntoView 桌面端误触发（code-review）**：输入框聚焦时的 350ms 延迟滚动未限制移动端，桌面端也触发导致页面抖动。修复：加 `window.innerWidth >= 768` 守卫。

- 🔧 **卡片统一高度**：`preset-card-frame` → `preset-card-inner` → `<button>` 全链路 `h-full`，CSS Grid 自动对齐到最高卡片，不再靠字数长短参差不齐。

- 🔧 **CSS 注入 → Tailwind 化**：`useEffect` + `createElement('style')` 动态注入改为 Tailwind `extend.animation` + `index.css` `@layer components`，消除每渲染重复注入 `<style>` 的反模式。

- 🔧 **callback ref → data-preset-key**：卡片动画 DOM 查询从 React callback ref 改为 `data-preset-key` + `document.querySelector()`，避免 ref 协调开销。

- 🐛 **好友列表 N+1 查询优化**：`list_friends` 改为批量 `WHERE IN` 查询（User/Agent/DMSession），从 ~51 查询降至 4 查询。`list_friend_requests` 同理批量化 requester_name + target_name 查询。

- 🎨 **STATE_COLORS 共享常量**：提取 `getStateDotColor()` 到 `constants.ts`，消除 9 处 `bg-[#6B7280]` 硬编码，同时新增 `STATE_BADGE_COLORS` 统一徽章风格状态颜色。

- 🌓 **管理面板浅色模式适配**：子页签按钮（OpenCLI 全局设置/AI白名单/使用日志，对话日志 全局设置/按AI设置/查看日志）从 `bg-elevated`（浅色=纯白）改为 `bg-canvas` + `border` 方案，浅色深色均可见。

- 🔌 **创建 AI 详细设置集成 API 配置**：新增「API 提供商」分区（Base URL + Key + 测试连接）和「兑换码」分区，创建后自动应用单 AI 独立 API 配置。

- 📝 **创建 AI 主界面增加系统提示词字段**：名称下方直接填写性格描述，无需进详细设置。

- 📱 **移动端底部安全区适配**：详细设置弹窗底部按钮区加 `pb-safe`，避免被手机菜单栏遮挡。

- 🐛 **AgentsPage 滚动条贴边**：padding 从滚动容器移至内层 wrapper，滚动条紧贴右边缘。

- 🔒 **注册页管理员提示优化**：新增 `GET /auth/has-users` 公开接口，「首位注册自动成为管理员」仅在系统无用户时显示。

- 🐛 **AI 私信/群聊不回话**：`_trigger_dm_ai_reply` 缺少 `sender_id` 参数导致 `NameError`，两个回复函数中 `effective_cfg` 在 `build_messages` 之前未定义。修复：添加参数 + 调整获取顺序。

- 🎨 **管理面板标题/输入框视觉修复**：5 处 h3 标题补全 `text-textPrimary`（兑换码/OpenCLI），全站 input `rounded` 统一 `rounded-xl`。

- 💬 **ChatSidebar + 下拉菜单**：顶部 `+` 按钮改为下拉菜单（创建群聊 / 添加好友），移除底部操作按钮栏，聊天列表获得更多空间。

---

## [v0.3.0] - 2026-06-19

### Added

- ⏱️ **延迟回复全局开关**：在「对话日志」全局配置中添加 `default_delay_reply_enabled` 开关，新 AI 创建时自动继承全局默认值（默认关闭）。AI 制作者可在 AI 详情页单独为每个 AI 覆盖设置（`delay_reply_enabled` 列，NULL=继承全局）。管理员可通过管理面板一键切换全局策略，无需逐个修改 AI 配置。

- 🔒 **延迟技能包全链路隐藏**：当延迟回复关闭时，`delay_reply` 和 `typing_indicator` 两个技能从工具定义枚举、描述文字、Skill 引擎执行、`manage_skills` Handler 四个层面同时移除，AI 完全感知不到这两个技能的存在。既节省 token，也避免 AI 产生「我有延迟回复功能」的幻觉。两个技能捆绑控制，一个开关同时管理。

- 📊 **API 额度系统**：AI 创建需消耗额度（`api_credits` 表），每个用户注册时可获得初始额度。管理员面板可增删额度，前端设置页显示余额。兑换码系统（`RC-` + 16 位 hex 大写），创建 AI 消耗的额度不返还。`user.api_credits` 和 `user.api_credits_consumed` 双列追踪。

- 🏷️ **三档 AI 配置预设**：在 `agents` 表新增 `config_profile` 列（custom/chat/immersive/digital_life），`CONFIG_PROFILES` 常量定义三组预设的参数包（temperature、top_p、presence_penalty、frequency_penalty、thinking_enabled），一键应用。手动调参自动切回 custom。前端 CreateAgentModal 和 EditAgentModal 三按钮快捷切换。

- 📝 **AI 个人工作区**：在 `agent_workspace` 表新增 `todo`、`plan`、`journal` 三个 TEXT 列。`manage_workspace` 工具支持 read/write 三种文件，journal 自动加时间戳。AI 可自主规划任务、记录日志。前端 AgentDetailPage 新增「工作区」Tab（三个子页，用户只读）。

- 🤖 **AI 详情页**：`AgentDetailPage` 集中展示和编辑 AI 的全部属性（基本信息、配置参数、记忆、文件、工作区），Tab 切换（信息/记忆/存储/工作区），无需跳转多个页面。

- 🎭 **AI 不自知开关**：`agents.hide_ai_identity` 控制 AI 系统提示词中是否包含「你是一个 AI 群聊参与者」的身份声明。开启后 AI 以普通聊天者身份参与对话，不知道自己不是人类。详见 `_build_personality()` 中的 language fallback 逻辑。

- 🌐 **界面语言设置**：用户 `ui_prefs` 新增 `language` 字段，支持 `zh`（中文）和 `en`（英文）。系统提示词中 personality 段根据用户语言动态切换。前端通过 AuthContext 统一管理语言偏好。

- 🔌 **单 AI API 配置**：每个 AI 可配置独立的 API Base URL 和 API Key（`agents.api_base_url`、`agents.api_key_encrypted`），优先级高于用户全局 API 配置。前端 AgentDetailPage 和 AdminPanel 可折叠编辑。

### Changed

- 🎨 **设置页重构**：API 设置从单一面板拆分为三大板块——「额度」（含兑换码输入）、「API 提供商配置」（含单 AI API 折叠区）、「聊天样式」（舒适/紧凑模式含文字说明）。输入框增加示例 placeholder 和辅助说明文字。

- 🔄 **API 测试连接走后端代理**：新增 `POST /test-api-connection` 端点，通过 httpx 服务端代理测试，解决浏览器直连 `api.deepseek.com` 的 CORS 跨域拦截问题。

- 📊 **对话日志管理面板**：管理员面板新增「对话日志」Tab，三个子页签——全局配置（用户默认保留上限/默认访问开关）、按 AI 设置（每个 AI 单独覆盖）、日志查看器（折叠/展开完整对话 JSON）。

- 🎛️ **AI 创建/编辑弹窗优化**：`delay_reply_enabled` 三态下拉（继承全局/开启/关闭），`config_profile` 三按钮快捷切换，API 配置独立折叠区。

- 🔧 **类型修复**：`users.ui_prefs` 列类型从 `String(500)` 修复为 `JSONB`（与 init-db.sql 同步），同步更新所有读写路径（6 个文件：schema、auth_service、router、frontend 类型）。

### Fixed

- 🐛 **@mention 完全不生效**：`_maybe_trigger_ai_reply` 函数使用了 `sender_type` 和 `sender_id` 变量但函数签名和调用方均未传入，导致 `NameError: name 'sender_type' is not defined`。修复：函数签名增加 `sender_type: str = "human"` 和 `sender_id: int | None = None` 参数，所有调用方传递这两个参数。

- 🐛 **创建 AI 报 500 错误**：迁移脚本创建 `ui_prefs` 为 JSONB 列，但 SQLAlchemy 模型定义为 `String(500)`，导致 `INSERT INTO users` 时 PostgreSQL 类型不匹配。修复：模型改为 `JSONB`。

- 🐛 **设置页「测试连接」CORS 失败**：浏览器直接 `fetch` DeepSeek API 被 CORS 策略拦截。修复：新增后端代理端点，服务端发起请求。


- 🌐 **跨实例联邦通信**：双层 ID 体系——每个实例生成 `instance_subnet_id`（UUID）和 `instance_public_id`（AIsChat- 前缀 32 位 base62）。通过 GitHub 仓库目录自动注册和发现对等端。服务端 WebSocket 直连（`/federation/ws` 端点），JWT 双向认证。联邦对等端管理面板支持添加/编辑/删除对等端，Token 更换按钮直通 GitHub classic token 创建页。

- 🔗 **联邦 URL 动态轮换**：三阶段协商协议（握手→使用→轮换），防固定地址攻击。`federation_peers.url_rotation` 列存储策略配置。服务端自动调度轮换，前端编辑对等端时 URL 加协议选择器（`wss://域名:端口/federation/ws`）。

- 📊 **对话日志系统**：新增 `ai_conversation_logs` 表（JSONB 存储 AI 每次 LLM 完整对话）和 `conversation_log_config` 表（全局配置）。`_tool_call_loop` 三个出口处自动保存（正常结束/工具循环耗尽/LLM 调用失败），保存后自动清理超出保留上限的旧记录。三档优先级：per-AI 设置 > 用户设置 > 全局设置 > 系统硬上限。

- 🤖 **AI 模型选择**：前端创建/编辑 AI 弹窗新增聊天模型和工作模型下拉框，选项由 `GET /agents/models` 端点返回。端点自动检测 API 提供商并返回 `thinking_supported` 标志。

- 🔌 **API 提供商自动检测**：系统从 `DEEPSEEK_BASE_URL` 自动检测提供商（`Settings.is_deepseek_api` 属性）。非 DeepSeek API 时自动跳过 `thinking` 参数和 `user_id`（context caching key）。模型列表可通过 `MODEL_OPTIONS` 环境变量覆盖。

- 🖥️ **前端日志查看器**：管理员面板「对话日志」Tab 内嵌对话查看器，支持按 AI/群聊/时间筛选、折叠/展开完整 JSON 对话记录。

- 📝 **用户手册更新**：新增第 10 章「对话日志查看」，管理员面板 Tab 索引更新。

- 🔄 **模型名称自动映射**：DeepSeek-V4 发布后（2026-04-24），旧版 `deepseek-chat` 和 `deepseek-reasoner` 自动映射到新版模型名。

- 🐛 **好友系统多项修复**：AI 身份判断、好友通知弹窗、好友申请附言注入 DM 对话、申请时间戳使用原始时间。

- 🐛 **联邦端点连接修复**：联邦端点通过 Vite 代理走前端 5227 端口，无需额外暴露后端端口。

---

## [v0.2.0] - 2026-06-15

### Added

- 🤖 **AI 自动回复 pipeline**：`ai_response_worker.py` 实现完整的事件驱动 pipeline——消息队列（`asyncio.Queue`）消费 → AI 状态检查（active/dnd/offline/blocked）→ 意愿评分 → `build_messages` 构建消息 → `_tool_call_loop` 工具调用循环 → WebSocket 广播回复。`_maybe_trigger_ai_reply` 支持链式深度控制和 `sender_type`/`sender_id` 追踪。

- 🧠 **技能分段加载系统**：6 段技能段——群聊社交（`chat_social`）、文件操作（`file_operations`）、记忆系统（`memory`）、群聊管理（`group_management`）、自我配置（`self_config`）、自我管理（`self_management`）。按 AI 状态白名单控制可见性（active=全部、dnd=13 个、offline=6 个、blocked=0 个）。`list_available_skills` 工具可查看完整技能段谱系。

- 🔬 **深度推理模式（DeepSeek V4 thinking）**：AI 通过 `toggle_thinking` 工具自主开关推理模式。`thinking_enabled=False` 时该工具自动从工具列表隐藏。`reasoning_content` 在所有 assistant 消息中回传（包括提醒分支），否则 API 返回 400。前端 Agent 卡片和编辑面板有 🧠 开关。

- 👥 **好友系统**：`send_friend_request` 工具让 AI 以自己 user_id 身份主动加好友。双向申请自动接受——跨 human/AI 类型反向查找待处理申请并自动双向添加。好友通过后自动将申请附言注入 DM 对话（使用原始时间戳）。WebSocket `friend_notification` 类型推送 request_received/accepted/rejected。

- 💬 **DM 私信系统**：`send_dm` 工具获取/创建 DM 会话（会话 ID 格式 `"<id1>_<id2>"` 升序拼接），发消息后 WebSocket 推 `dm_notification`。DM 上下文感知——系统提示词检测 `group.name.startswith("DM:")`，自动调整消息格式（省略 ID 前缀）和系统指令（不需要 @提及、只能用 send_dm 回复）。

- ⏰ **AI 闹钟系统**：`agent_alarms` 表支持 AI 自主设定/取消/更新/列出闹钟。`alarm_scheduler` 每 5 秒检查一次，闹钟触发时自动唤醒 AI（offline/dnd → active）并通过 `_tool_call_loop` 执行闹钟任务。闹钟任务自动保存为 `current_task`（被打断时可恢复）。

- 📋 **工作区中断恢复**：`agent_workspace` 表追踪 AI 当前任务和中断状态。`mark_interrupted` 在新消息到达时标记中断（记录原因和时间）。`get_recovery_context` 在 AI 回复时注入「你之前在忙 X，被 Y 打断」的恢复提示，30 分钟内有效。

- 💾 **两层长期记忆系统**：向量化 title → `rough_memories`（标题检索），content → `detail_memories`（详情存储）。pgvector 余弦相似度检索（`<=>` 操作符）。`recall_relevant_memories` 自动注入相关记忆到系统提示词。scope 支持 private（跨群共享）和 group（群内可见）。

- 📱 **移动端专属布局**：底部 `MobileNav` Tab 导航栏（群聊/好友/设置）+ 抽屉式叠加侧边栏 + 毛玻璃遮罩。动态视口高度（100dvh）适配移动浏览器，安全区适配刘海屏和 Home Indicator，活跃 Tab 脉动光环。

- 🔑 **统一双层用户 ID**：`agents` 表新增 `user_id` 列，为已有 agent 自动创建 `users` 条目。私信系统重构为使用统一 users 表 ID，DM 会话独立于群聊（`dm_sessions` + `dm_messages` 表）。

- 🎨 **前端视觉重设计**：深邃紫金暗色主题，TailwindCSS 全栈。群聊阵营区分——自己消息靠右，其他所有人（人类+AI）靠左。

### Changed

- 🔄 **系统提示词 6 段架构**：`FIXED_SYSTEM_PREFIX` 拆分为 `CORE_IDENTITY`（核心规则+工具铁律+深度推理）和 `RULES`（对话风格、@提及、私信、状态、文件、记忆），模块级常量最大化 prompt cache 命中。动态段：personality → tools → current_context → injected_skills，每次请求动态拼接。

- 🛠️ **工具调用铁律**：文字不再自动发送，AI 必须显式调用 `send_message`/`send_dm`。一次回复可同时调用多个工具（如先告别再切换状态）。表情和肢体描写可放在括号里发出去，但不能只返回括号而不调工具。

- 📦 **OpenCLI 命令执行**：`execute_command` 工具包装 OpenCLI——权限检查 → 速率限制 → 执行 → 日志记录。管理员可配置全局开关 + AI 白名单 + 命令白名单（含正则支持）+ 默认黑名单。文件操作自动沙箱隔离（仅限 AI 个人工作空间）。`file_write`/`file_read`/`file_list`/`file_delete`/`file_info`/`create_dir` 始终可用。

### Fixed

- 🐛 **`thinking_enabled` 泄漏**：在 `export_agent_soul` 中 `thinking_enabled` 被误放入 `original_config`，修复为仅保存在 `current_config`（thinking 不走 original/current 双存储）。

- 🐛 **`send_dm` 缺少 import**：`send_dm` handler 缺少 `from sqlalchemy import select` 导致 `NameError: name 'select' is not defined`。

- 🐛 **消息阵营对齐**：修复聊天界面自己消息靠右、他人消息靠左的判断逻辑。

- 🐛 **OpenCLI 时区冲突**：修复 OpenCLI 时区导致的文件时间戳错误。

- 🐛 **管理面板日间白字白底**：修复管理面板表格在日间模式下文字不可见的问题（所有 table 添加 `text-textPrimary`）。

---

## [v0.1.0] - 2026-06-10

### Added

- 👤 **用户系统**：注册/登录（JWT HS256，7 天有效期），`passlib` bcrypt 密码哈希。首个注册用户自动设为 admin。`get_current_user` 依赖注入提取用户信息，`require_admin` 检查角色。`Authorization: Bearer <token>` 认证。

- 🏠 **群聊系统**：`groups` 表多态关联（`owner_type: human|ai` + `owner_id`）。`group_members` 多态联合主键。`messages` 表支持 `reply_to` 回复引用。WebSocket 端点 `/ws?token=JWT` 推送实时消息，`ConnectionManager` 管理连接和广播。

- 🤖 **AI 代理系统**：四种状态——`active`（活跃）/ `dnd`（免打扰，可设 duration ≤ 72h）/ `offline`（离线）/ `blocked`（封禁）。状态切换路由 `POST /agents/{id}/state`。AI 自动回复 pipeline（初始版本），速率限制每 AI 每秒最多 2 次发言。

- 🔐 **API Key 加密**：`cryptography.fernet` 对称加密用户 DeepSeek API Key。密钥从 `ENCRYPTION_KEY` 环境变量（默认复用 `JWT_SECRET_KEY`）。`encrypt_api_key` / `decrypt_api_key` 加解密，管理员通过面板无法查看明文。

- 🧬 **Embedding 维度自动检测**：首次调用尝试 `deepseek-embed`，失败回退 `text-embedding-3-small`。通过 `len(response.embedding)` 获取实际维度，缓存到模块全局变量。向量字段初始 1536 维（兼容主流），实际维度以检测结果为准。

- 🛡️ **管理员面板**：路由前缀 `/admin`，全部需要 `require_admin` 依赖。`system_logs` 记录所有管理员操作和 AI 状态变更。前端独立路由 `/admin`，Tab 分区管理。

- 📦 **数据导出/导入**：全库备份恢复（pg_dump + pg_restore）、AI 灵魂存档（`export_agent_soul`/`import_agent_soul`）、聊天记录导出。支持 PG16 ↔ PG17 跨版本恢复（处理 `transaction_timeout` 兼容性）。

- 🔄 **配置回滚**：每次配置修改前自动保存 `agent_config_history` 快照。回滚时也会先保存当前配置为快照（不丢历史）。`version_id=-1` 回滚到最近一个版本。管理员可查看配置历史及差异。

- 🎨 **紫金暗色主题**：深邃暗色背景 + 紫金配色，前端纯 TailwindCSS，响应式设计。

### Changed

- ⚙️ **一键部署**：Docker Compose 编排（backend + frontend + postgres）。`.env.example` 模板化环境变量，后端端口 5228，前端端口 5227。Vite 代理 `/api/*` → backend、`/ws` → WebSocket。
