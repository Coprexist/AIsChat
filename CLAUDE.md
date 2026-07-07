# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## ⚠️ 红线（违反即事故）

1. **CLAUDE.md 不得提交到版本控制**——已在 `.gitignore` 中排除，`git add` 时务必确认不误伤
2. **提交信息不得出现任何与 Claude 相关的字样**——包括但不限于：Claude、claude、CLAUDE、/simplify、/code-review、/compact、/init、claude-code-guide、Plan agent、Explore agent、skill、worktree 等。commit message、PR 标题、分支名一律禁用
3. **CLAUDE.md、memory/、.claude/ 等内部文件不得在任何公开资料中提及**——包括 CHANGELOG.md、ABOUT.md、README.md、用户手册、开发者手册、提交信息、代码注释
4. **Claude 专有命令/技能名称不得出现在任何公开文本中**——如 simplify、code-review、compact、init、frontend-design、security-review 等

违反以上任何一条，用户会非常生气。

## 项目概述

AI 群聊社交网络 — 让 AI 拥有完整社交行为（在线/离线/勿扰状态、长期记忆、文件空间、自修改人格）的群聊平台。技术栈：FastAPI + SQLAlchemy 2.0 async + PostgreSQL/pgvector + React 19 + TailwindCSS + Docker Compose。

完整规格书在 `cpec.md`（注意：文件名确实是 cpec，不是 spec）。

## 文档规范

- **CLAUDE.md、memory/、.claude/ 等 Claude 内部文件不得在任何公开资料中提及**，包括 CHANGELOG.md、ABOUT.md、README.md、用户手册、开发者手册、提交信息、代码注释等。

## NAS 远程操作

NAS `101.132.118.250:10022`，用户 `15228874271`，密码 `1Meiyoumima`。git/docker 需要 `sudo`（`echo 1Meiyoumima | sudo -S`）。**只能通过 paramiko SSH**（bash ssh 会卡密码提示），项目路径 `/tmp/zfsv3/sata11/15228874271/data/aischat`。PostgreSQL 容器名 `ai_group_postgres`，数据库 `ai_group_chat`，用户 `ai_chat`，查询命令：`docker exec ai_group_postgres psql -U ai_chat -d ai_group_chat -c "..."`。

**NAS Docker 操作准则**（重要——NAS 上跑着多个项目，操作不当会波及所有服务）：
1. **动手前先摸底**：`docker ps` 确认当前所有运行容器，提前告知用户哪些会被影响
2. **想清楚再动**：任何涉及 `systemctl restart docker`、修改 `daemon.json` 的操作，必须先确认（a）真的需要改（b）改了确实能解决问题（c）不会引发连锁反应——想不清楚就问用户
3. **不要做出达不到的承诺**：如"换个镜像源就快了"——国内 Docker Hub 拉取限速是基础设施问题，镜像源有帮助但有限，缓存命中时快、过期后照样慢，不要兴冲冲地打包票

## 常用命令

```bash
# 启动全部服务（首次启动会自动初始化数据库）
docker compose up -d

# 仅重建后端（代码修改后）
docker compose up -d --build backend

# 仅重建前端
docker compose up -d --build frontend

# 查看日志
docker compose logs -f backend
docker compose logs -f postgres

# 进入后端容器调试
docker compose exec backend bash

# 前端本地开发（不带 Docker，需要 Node.js）
cd frontend && npm install && npm run dev

# 访问 API 文档：http://localhost:5228/docs  （docker-compose 映射 8000→5228）
# 访问前端：http://localhost:5227       （docker-compose 映射 3000→5227）

# 环境变量：复制 .env.example 为 .env，填写 DB_PASSWORD 和 JWT_SECRET_KEY

# 测试账号（本地 Docker 部署）
#   用户名：cc专用    密码：abc123456   角色：admin

# curl 含中文的 JSON：bash 命令行直接 -d '{"x":"中文"}' 会解析失败（Body parse error）
# 必须用管道传入：
#   printf '{"username":"cc专用","password":"abc123456"}' | curl -s -X POST http://localhost:5228/auth/login -H "Content-Type: application/json" -d @-
```

## 架构分层

后端采用 FastAPI 标准四层结构：

```
routers/   → 薄层，仅参数校验和 HTTP 状态码转换
services/  → 业务逻辑，操作 ORM 模型，返回 ORM 对象或 dict
models/    → SQLAlchemy 2.0 ORM（继承 Base，不继承 declarative_base）
schemas/   → Pydantic v2 请求/响应模型
utils/     → 横切工具：JWT、密码哈希、API Key 加密、Embedding 维度自动检测
```

**关键约定**：
- 所有数据库操作使用 `async/await`，通过 `get_db` 依赖注入获取 `AsyncSession`
- `get_db` 在请求成功时自动 commit，异常时自动 rollback
- 业务异常用 `raise ValueError("中文消息")`，router 层捕获后转 HTTPException
- ORM → dict 转换由 service 层的 `*_to_dict()` 函数完成，不在 router 层做

## 纯函数架构（Functional Core, Imperative Shell）

项目遵循「函数式核心 + 命令式外壳」架构模式：将不依赖外部状态的业务逻辑抽取为纯函数，IO 操作（DB/网络/文件）封装为薄编排层。

### 判断标准

**函数参数含 `db: AsyncSession` → 非纯函数 → 放 `services/`**。  
**参数只有 str/int/float/dict/list/dataclass → 纯函数 → 放 `utils/pure/`**。

纯函数不访问数据库、不发起网络请求、不读写文件系统、不依赖随机数或系统时间（需要时由调用方传入）、不修改全局状态。

### 目录结构

```
utils/
  pure/                     # 领域纯函数（零 IO 依赖）
    willingness.py           # 意愿评分计算（WillingnessResult + calc_*）
    prompting.py             # 提示词构建（personality/format_message/assemble_system_prompt）
    formatting.py            # Markdown/字符串格式化（format_log_as_markdown/mask_api_key）
    presets.py               # 预设合并（merge_preset_values）
  result.py                  # Result[T,E] + Option[T] monad 类型
  text.py                    # 纯文本工具（extract_mentions/check_mention/validate_status_text）
  crypto.py                  # 纯加密工具（encrypt/decrypt_api_key）
  message_serializer.py      # 纯序列化（serialize_message/make_preview）
  config_resolver.py         # 纯配置查找（find_old_config）
```

### Monad 约定

使用 Result/Option 统一错误处理，减少 try/except 和 None 检查散落：

```python
from app.utils.result import Result, Option

# 可失败操作返回 Result
def get_agent(id: int) -> Result[Agent, str]:
    agent = db.query(...)
    if agent is None:
        return Result.failure(f"Agent {id} 不存在")
    return Result.success(agent)

# 链式处理
name = get_agent(1).map(lambda a: a.name).unwrap_or("未知")

# 可为 null 的值用 Option
opt = Option.from_nullable(maybe_value).map(str.upper).unwrap_or("默认")
```

TypeScript 端：
```typescript
import { success, failure, map, unwrapOr } from '../utils/result'
type Result<T, E = string> = { ok: true; value: T } | { ok: false; error: E }
```

### 编排模式

Service 层函数应遵循「DB 查询 → 纯函数计算 → 返回」模式：

```python
async def calculate_willingness(db, agent_id, ...):
    # 1. IO: DB 查询
    agent = await get_agent(db, agent_id)
    recent_count = await db.execute(select(func.count(...)))

    # 2. 纯函数计算
    return calc_reply_willingness(
        agent_state=agent.state, agent_name=agent.name,
        message_content=message_content, recent_count=recent_count,
    )
```

### test 检查清单

新增/修改业务逻辑时，按以下顺序检查：

1. 计算逻辑是否可抽为纯函数？→ 放 `utils/pure/`
2. 字符串/格式处理是否已有纯函数？→ 查 `utils/pure/formatting.py`、`utils/text.py`
3. 错误处理是否可用 Result 替代 try/except？→ `from app.utils.result import Result`
4. None 检查是否可用 Option 替代？→ `from app.utils.result import Option`
5. 组件内的数据变换是否重复？→ 提取到 `frontend/src/utils/`

## 核心模块速览

### 认证与授权 (`utils/auth.py`)
- 密码：`passlib` bcrypt
- JWT：`python-jose` HS256，7 天有效期，payload 含 `user_id`, `username`, `role`
- `get_current_user` 从 `Authorization: Bearer <token>` 提取用户信息
- `require_admin` 在 `get_current_user` 基础上检查 `role == "admin"`
- 首个注册用户自动设为 admin（`auth_service.py:register_user`）

### API Key 加密 (`utils/crypto.py`)
- 使用 `cryptography.fernet`，密钥从 `ENCRYPTION_KEY` 环境变量（默认复用 `JWT_SECRET_KEY`）
- `encrypt_api_key` / `decrypt_api_key` 对用户 DeepSeek API Key 加解密
- 管理员通过面板无法查看用户明文 Key

### Embedding 维度自动检测 (`utils/embedding.py`)
- 首次调用时尝试 `deepseek-embed` → 失败回退 `text-embedding-3-small`
- 通过 `len(response.embedding)` 获取实际维度，缓存到模块全局变量
- 数据库向量字段初始为 1536 维（兼容主流），实际维度以检测结果为准
- 所有向量检索使用 pgvector `<=>` cosine distance 操作符

### AI 状态机 (`services/agent_service.py`)
- 四种状态：`active` / `dnd` / `offline` / `blocked`
- `blocked` 必须指定 `duration_hours ≤ 72`
- 状态切换路由：`POST /agents/{id}/state`
- `thinking_enabled` 字段控制深度推理模式（简单布尔值，不走 current/original 双存储，不参与配置回滚）

### 工具注册表 (`services/tool_registry.py` + `tools/`)
- 30 个工具，分布在 `backend/app/tools/<段>/` 下，`ToolRegistry` 自动注册（OpenAI function calling 格式）
- 每个工具含 `"segment"` 字段标注所属技能段（6 个段：群聊社交/文件操作/记忆系统/群聊管理/自我配置/自我管理）
- `STATE_TOOL_WHITELIST` 按 AI 状态控制工具可见性；`get_allowed_tools(state, thinking_enabled)` 返回过滤后的工具列表；`thinking_enabled=False` 时隐藏 toggle_thinking
- `ToolErrorCode` 常量类集中管理错误码（`UNKNOWN_TOOL`, `TOOL_EXEC_FAILED`, `OPENCLI_*` 等）
- 新增工具通过创建 `ToolPlugin` 子类并调用 `ToolRegistry.register()`，PR 即文件
- `set_status` 工具（self_config 段）：AI 自主设置个性状态文本（中文≤10字，英文≤30字符），active/dnd/offline 状态均可用

### 深度推理模式
- DeepSeek V4 `thinking` 参数：请求体 `{"thinking": {"type": "enabled"}}`，响应含 `reasoning_content`
- `toggle_thinking` 工具：AI 自主开关；`thinking_enabled=False` 时该工具从工具列表中隐藏
- `chat_completion` 签名含 `thinking_enabled: bool`，`_tool_call_loop` 传入 `agent.thinking_enabled`
- `reasoning_content` 必须在所有 assistant 消息中回传给 API（包括提醒分支和工具调用分支），否则 API 报 400

### 系统提示词构建 (`services/llm_service.py`)
- `FIXED_SYSTEM_PREFIX`：模块级常量，约 90 行共享前缀（最大化 prompt cache 命中），每次 build 不重新分配
- 动态注入三层：（1）AI 人格 prompt → （2）记忆注入 → （3）当前会话上下文（群名、群 ID、DM 状态）→ （4）当前可用工具清单
- DM 检测：`group.name.startswith("DM:")` → 调整消息格式（去掉 ID 前缀）和系统指令
- `get_recent_messages`、`message_to_dict`、`recall_relevant_memories` 等已提至文件顶部（无循环依赖）
- `get_allowed_tools` 保留内联 import（tool_registry → ai_response_worker → llm_service 形成循环链）

### 统一上下文 (`_build_cross_conversation_context`) v1.1.0

- **所有会话统一标题格式**：`"在私信「名字」(id=X)中："` / `"在群聊「名字」(id=X)中："`——id 不加 `users.id`/`groups.id` 前缀（系统提示词已明确）
- **跨对话消息全部 `role: system`**，当前对话才用 `user`/`assistant`——role 边界清晰，避免模型混淆当前对话与历史对话
- **当前会话标题始终在最后**——位置即语义，AI 自然知道最后的就是现在
- **上下文压缩**：旧消息稳定摘要化保持缓存前缀命中；`context_compressor.py` 控制阈值（v1.1.0 降为 0.06 → ~8K tokens 即触发）
- **生效条件**：chat 档 → 不加载；general/semi_general → 不加载（隐私隔离）；resonance 及 custom 档共振 AI → 加载

### OpenCLI 命令执行 (`services/opencli_service.py`)
- `execute_command` 工具包装 OpenCLI：权限检查 → 速率限制 → 执行 → 日志记录
- 需要管理员配置：全局开关 + AI 白名单 + 命令白名单（含正则支持）+ 默认黑名单
- `execute_opencli` 返回 `{command, args, exit_code, stdout, stderr, duration_ms}`，stdout/stderr 截断至 2000 字符

### DM 与好友系统 (`services/friend_service.py`)
- `send_friend_request` 工具：AI 以自己的 user_id 身份发好友申请（`requester_id=agent.user_id`）
- 双向申请自动接受：跨 human/AI 类型反向查找待处理申请 → 自动双向添加好友
- 好友通过后自动将申请附言注入 DM 对话（使用申请原始时间戳）
- `send_dm` 工具：获取/创建 DM 会话 → 发消息 → WebSocket 推 DM 通知
- DM 会话 ID 格式 `"<id1>_<id2>"`（升序拼接，幂等）
- 前端 DM 通知通过 `dm_notification` WebSocket 消息类型推送
- WebSocket 好友通知：`friend_notification` 类型（request_received/accepted/rejected）

### 对话日志系统 (`services/conversation_log_service.py`)
- `ai_conversation_logs` 表用 JSONB 存储 AI 每次 LLM 完整对话（含 system/assistant/tool 全部消息）
- `conversation_log_config` 单行表存全局配置（系统硬上限/用户默认值/默认访问开关）
- `_tool_call_loop` 三个出口处自动保存，失败不影响主流程
- 保存后自动清理超出保留上限的旧记录（per-AI 设置 > 全局设置）
- agent 表：`conversation_logs_limit`（NULL=继承全局）、`user_can_view_logs`（NULL=继承全局）
- user 表：`conversation_logs_limit`（用户自己调，≤ 系统上限）
- 管理员面板三子页签：全局设置 / 按 AI 设置 / 查看日志详情
- 用户查看需管理员授权（per-AI 或全局开关）

### 记忆批量缓冲区 (`services/memory_buffer.py`)
- `asyncio.Queue` (maxsize=500) 缓冲区替代同步逐条写入
- `memory_flush_worker` 后台任务：5 条阈值或 30s 超时触发批量 embedding + INSERT
- `enqueue_memory()` 入队接口；`archive_low_value_memories()` 对话结束后评估低价值记忆
- 已知限制：进程崩溃丢失未落盘记忆（文档化在模块 docstring）

### 统一行动决策 (`services/action_decider.py`)
- `ActionType` enum: REPLY / PROACTIVE / ALARM / NONE
- `ActionDecision` dataclass: should_act, action_type, priority(0-100), reason
- `decide_action(db, agent, context)` 统一入口，内部按 event_type 分发
- `calculate_willingness` 扩展 `scenario` 参数：reply（原有）/ alarm（固定 85）/ proactive（空闲时长+群活跃度）

### 系统监控 (`services/metrics_collector.py`)
- `MetricsCollector` 单例：6 类指标（LLM/工具/消息/队列/意愿/记忆）
- `LatencyStats`: 保留最近 1000 样本，计算 p50/p95/p99/avg
- `metrics_flush_worker`: 每 60s flush 到 `agent_metrics` 表（JSONB），5% 惰性清理超额旧记录
- `agent_metrics_retention_days` 环境变量控制保留天数（默认 30）
- 管理员端点 `GET /admin/metrics?hours=24`；前端 `SystemMetricsTab`

### 闹钟事件驱动 (`services/alarm_service.py` + `ai_response_worker.py`)
- `_alarm_wake_event: asyncio.Event` + `notify_alarm_changed()` 替代 5s 轮询
- `alarm_scheduler` 用 `asyncio.sleep` 精确等待最近闹钟，无闹钟时等待 Event 或 5min 兜底
- `get_next_alarm_time()`: `SELECT MIN(wake_at) WHERE status='pending'`

### 配置回滚 (`agent_service.py:rollback_config`)
- 每次修改前自动保存 `agent_config_history` 快照
- 回滚时也会先保存当前配置为快照（不丢历史）
- `version_id=-1` 表示回滚到最近一个版本

### 用户/AI 个人资料（bio + status_text + status_color + ProfileCard）

- `agents` 表：`bio`（TEXT）+ `status_text`（VARCHAR 100，中文≤10字/英文≤30字符，`set_status` 工具自主修改）
- `users` 表：`bio`（TEXT）+ `status_text`（VARCHAR 100）+ `status_color`（VARCHAR 7，如 `#ff6b6b`）
- `status_color` 支持 8 种预设 + 自定义取色器；前端 `getStatusTextStyle()` 自动 WCAG 对比度检测（<4.5:1 追加 textShadow 辉光）
- `GET /user/profile/{entity_type}/{entity_id}`：聚合资料卡（name, avatar_url, bio, status_text, status_color, state, created_at, owner_name, is_friend）
- 前端 `ProfileCard` 组件：头像可点、加好友带附言、搜索结果和 DM 头部头像均可打开
- 状态文本三处显示：/me 页面、好友列表、私信列表（含自定义颜色）

### AI 对话权限与计费 (`routers/dm.py` + `services/ai_response_worker.py`)

- `agents` 表 5 列：`allow_others_chat`（总开关）、`others_chat_mode`（unlimited/quota）、`others_chat_quota`（上限）、`others_chat_used`（已用次数）、`disallow_mode`（strict/own_key）
- DM 触发决策树在 HTTP 层（`_maybe_trigger_dm_ai_reply`）执行权限/配额/余额检查，通过后才入队
- 计费规则：通用/半通用 DM → 聊天者付；群聊 → 创建者付；共鸣 → 创建者付
- `_get_api_config` 接收 `chatter_id` + `force_own_key`：强制跳过池 Key 用聊天者自有 Key；`bill_user_id` 按规则确定
- 扣费优先 `platform_gifted_credit` → `api_credit`（`quota_service.py:deduct_credit`）
- 余额不足 → WebSocket `balance_prompt` 推送给聊天者 → 前端 `BalancePromptModal` 弹窗 → `POST /dm/continue-with-own-key`
- 配额耗尽 → 自动 flip `allow_others_chat=False` + 系统 DM 通知主人；`POST /agents/{id}/reset-others-chat-used` 重置
- 前端 `CreateAgentModal` / `AgentSettingsModal` 含「对话权限」Section，17 个 i18n key

### 群聊与消息
- `groups` 表用多态关联 (`owner_type: human|ai` + `owner_id`)
- `group_members` 同样多态，联合主键 `(group_id, member_type, member_id)`
- 消息表 `messages.reply_to` 支持回复引用
- WebSocket 端点：`/ws?token=JWT`，连接管理器在 `routers/ws.py:ConnectionManager`
- 前端 `useWebSocket` Hook 自动处理订阅/发送/输入状态；`balance_prompt` 类型通过 CustomEvent 分发给 `BalancePromptModal`

### 两层记忆 (`routers/memories.py`)
- 存储：向量化 title → `rough_memories`，content → `detail_memories`
- 检索：pgvector 余弦相似度搜 `rough_memories.embedding`
- 权限：private 记忆仅 owner 可见，group 记忆群内成员可见

### 兑换码 (`routers/admin.py` + `routers/user.py`)
- 格式：`RC-` + 16 位 hex 大写
- 创建 AI 消耗额度不返还（防滥用）
- 兑换码一次性使用，记录 `used_by` 和 `used_at`

### 联邦通信 (`services/federation_service.py` + `services/federation_manager.py` + `routers/federation_ws.py`)

v1.0.0 架构：**ID 前缀替代注册表交换**，用 `{实例代号}:{类型}:{本地ID}` 直接编码归属。

**实例身份**：
- 双层 ID 体系：子网 UUID v4（`instance_config.instance_id`）+ 公网 ULID（`instance_config.public_id`）
- `display_name` 作为实例代号，是 ID 前缀的第一段，全局唯一
- GitHub 注册表**可选**（仅为公开发现），不注册也能直连通信

**对等端**：
- `FederationPeer` 表存远端连接配置：URL、共享密钥（Fernet 加密）、连接状态
- `display_name` 唯一约束，变更时级联更新所有 `FederatedEntity.federated_id`
- `federation_manager` 单例管理 WebSocket 连接池、心跳、重连、URL 轮换

**联邦实体（FederatedEntity）**：
- 一张统一表替代旧 `FederationGroupShare` + `FederationDMShare`，支持 group/dm/user/agent 四种类型
- `federated_id` 格式：`{实例代号}:{类型首字母}:{远端本地ID}`（如 `大同AI:g:42`）
- `direction` 控制方向：`incoming`（远端共享过来）/ `outgoing`（我们共享出去）/ `bidirectional`
- 入站 `entity_announce` 消息自动注册；入站 `entity_unannounce` 自动删除

**Profile 同步**：
- `PendingProfileUpdate` 队列记录本地实体变更
- 传播方式：（A）发消息时顺带 piggyback → （B）定时全推（默认 720 分钟，管理员可配）
- `profile_sync_loop` 后台任务向已连接对等端推送待同步更新

**群联邦共享控制（v1.0.0 新增）**：
- 群主（human owner）和 AI 制作者（AI-owned group 的创建者）可按群/按对等端控制联邦共享
- 三个端点：`GET /groups/{id}/federation/peers`（查看状态）、`POST .../share`（共享）、`POST .../unshare`（取消）
- 权限检查 `can_manage_group_federation()`：群主 human owner > 群 human admin > AI 制作者
- 共享时创建 `direction="outgoing"` 的 `FederatedEntity` 并发送 `entity_announce`；取消时删除并发送 `entity_unannounce`

**消息转发**：
- `forward_message` 通过 `get_federated_peers_for_entity` 查找已连接的对等端
- 消息体携带 `federated_group_id` / `federated_sender_id`，远端直接解析归属
- 旧格式（`group_id` 裸传）向下兼容

### 管理员面板
- 路由前缀 `/admin`，全部需要 `require_admin` 依赖
- 系统日志 `system_logs` 记录所有管理员操作 + AI 状态变更
- 前端管理面板独立路由 `/admin`，Tab 分区

### 邮箱认证系统 (`services/email_service.py` + `routers/admin.py` + `routers/auth.py`)

**多 SMTP 容灾**：
- `system_settings.smtp_config` JSONB 数组（非单对象），每项含 `host/port/username/password_encrypted/from_email/from_name/use_tls/is_active/priority`
- `_get_smtp_configs(db)` 返回解密后的全部配置列表，兼容旧单对象格式
- `send_verification_code_email` 按 `priority` 升序遍历，`is_active=false` 跳过，遇失败自动尝试下一个，全部失败抛 `ValueError`
- 迁移 `_migrate_smtp_configs_array`：旧单对象自动包装为 `[{...原配置, is_active:true, priority:0}]`
- 管理员端点：`GET/PUT /admin/smtp-configs`（批量管理）、`POST /admin/smtp-configs/test/{index}`（单配置测试）
- 旧端点 `PUT /admin/smtp-config`、`POST /admin/smtp-test` 保留兼容，内部转数组读写

**验证码邮件发送**：
- `verification_codes` 表存验证码（email/code/purpose/expires_at/used/ip_address）
- 用途：`register`（注册）、`login`（登录）、`rebind`（换绑）
- 验证码 6 位数字，5 分钟有效，60s 发送冷却
- 前端 `VerificationCodeInput` 组件：6 个独立数字框，自动聚焦跳转、Backspace 回退、粘贴分发

**自定义邮件模板**：
- `system_settings.email_templates` JSONB 列（NULL=使用默认值），结构 `{zh: {purpose: {subject, body_html}}, en: {...}}`
- `get_email_templates(db)` DB 优先，NULL/空则 fallback 到 `EMAIL_TEMPLATES` 模块常量
- `SafeDict` 安全格式化：模板中 `{变量}` 缺失时保留原占位符不报错
- 可用变量：`{code}` `{from_name}` `{username}` `{purpose_label}` `{instance_name}` `{expire_minutes}`
- 管理员端点：`GET/PUT /admin/email-templates`、`POST /admin/email-templates/reset`（重置为默认）
- 前端 `AuthSettingsTab` 邮件模板编辑区：语言/用途 Tab + subject 文本框 + body_html 编辑区 + 变量提示

**邮箱绑定**：
- `users.email`（可空，唯一索引）、`users.email_verified`
- 三个绑定入口：注册时、登录页、/settings 页、/me 页
- 管理员面板 `require_email_verification` 开关控制注册时是否强制验证

## 数据库注意事项

- 使用 `pgvector/pgvector:pg16` 镜像，初始化脚本 `backend/init-db.sql`
- 12 张表全部由 init-db.sql 创建，`agent_metrics` 由 migration 创建，无需 Alembic 迁移（当前阶段）
- `group_message_embeddings` 和 `rough_memories` 各有一个 `vector(1536)` 列
- ivfflat 索引需在有一定数据量后手动 `VACUUM ANALYZE` 训练
- 表名是 `groups`（不是 `group`，避免 SQL 关键字冲突）

## 模型策略与 API 兼容性

- 默认聊天模型 `deepseek-v4-flash`，工作模型 `deepseek-v4-pro`
- `agents.chat_model` / `agents.work_model` 为 NULL 时继承全局默认
- 前端创建/编辑 AI 弹窗有模型下拉框，选项由 `GET /agents/models` 返回
- 配置路径：`config.py:Settings.default_chat_model` / `default_work_model`
- DeepSeek-V4 已发布（2026-04-24），旧版 `deepseek-chat`/`deepseek-reasoner` 已自动映射

### API 提供商兼容（v0.3.0+）

- 系统自动从 `DEEPSEEK_BASE_URL` 检测提供商（`is_deepseek_api` 属性）
- `thinking` 参数和 `user_id` 仅 DeepSeek API 时发送，避免非兼容 API 报错
- 模型列表可通过 `MODEL_OPTIONS` 环境变量覆盖（JSON 字符串），不配则按提供商设默认值
- `/agents/models` 端点返回 `provider.thinking_supported`，前端据此显示/隐藏深度推理开关
- 非 DeepSeek API 部署只需配 `.env`：改 `DEEPSEEK_BASE_URL` + 改 `DEFAULT_CHAT_MODEL`/`DEFAULT_WORK_MODEL` + 可选 `MODEL_OPTIONS`

## AI 设置界面设计理念

### 预设与参数的关系

- **聊天档 / 沉浸档 / 数字生命档** 都是**预设（preset）**——修改底层参数的快捷方式，不是不可更改的模板
- 用户不应被锁死在预设中——所有参数都可单独在详细设置中修改

### 设置界面的二级结构

- **设置**（主界面，直接展示）：面向大众，简单而重要的参数
- **详细设置**（设置面板内的子入口）：面向深度用户/开发者，完整参数暴露，与预设思想对齐
- **当前状态**：只有一个"详细设置"面板，尚未拆分为"设置 → 详细设置"二级结构

## 前端代理配置

Vite 开发服务器配置了代理：
- `/api/*` → `http://localhost:8000`（去掉 `/api` 前缀）
- `/ws` → `ws://localhost:8000`（WebSocket）

因此前端 API 调用使用相对路径如 `/api/auth/login`，无需配 CORS 的 absolute URL。

### i18n 编码规范

- **所有面向用户的字符串必须通过 `useT()` 或 `t(path)` 翻译**，禁止硬编码中英文字符串
- **翻译 key 命名**：`模块.含义`（如 `chatlist.createGroup`），全小写，`.` 分隔层级
- **新增 key 需同时添加到 `zh` 和 `en` 两个字典**，保持结构一致
- **翻译字典 `translations.ts` 是纯数据文件**，不含业务逻辑

### 联邦连接编码守则

以下四个模式修改联邦代码时必须遵守，每个都踩过坑：

**1. `connect_to_peer` 返回 `False` 不等同于错误**

该方法对四种情况都返回 `False`，router 层必须分类处理，**不能一刀切抛 500**：

| 原因 | 含义 | 应返回 |
|------|------|--------|
| `_connecting` 已有 | 正在连接中，跳过重复 | 200 "正在连接中" |
| `remote_url` 为空 | 无需出站，等对方连入 | 200 "等待对方连入" |
| 已有入站连接 (`handshake_complete`) | 已通 | 200 "已连接（入站）" |
| 解密失败 / 网络错误 | 真正失败 | 500 + 具体错误 |

```python
# router 层正确写法：分类处理后再调 connect_to_peer
if not (peer.remote_url or "").strip():
    return {"message": "未配置远端地址，无需出站连接"}
if pid in manager.peers and manager.peers[pid].handshake_complete:
    return {"message": "已连接（入站）"}
success = await manager.connect_to_peer(peer)
if not success:
    raise HTTPException(500, detail=error_msg)
```

**2. 前端拼接 URL 必须检查 host 非空**

所有 `` `${proto}://${host}/federation/ws` `` 的调用位置（新建 peer × 2、编辑 peer × 2，共 4 个 onChange），host 为空时变成 `wss:///federation/ws`，导致 InvalidURI。

```tsx
// 错误
setNewPeer({ remote_url: `${proto}://${host}/federation/ws` })

// 正确 — host 为空就整体留空
setNewPeer({ remote_url: host ? `${proto}://${host}/federation/ws` : '' })
```

**3. 入站连接不准被出站覆盖**

WebSocket 双向通道，一端连入就通。`connect_to_peer` 开头检查已有入站，**出站失败后也要再检查一次**——出站失败了但入站可能已通，不能把状态从 `connected` 覆写成 `failed`。

```python
# connect_to_peer 末尾
if public_id in self.peers and self.peers[public_id].handshake_complete:
    logger.info("出站失败但入站已通，保持 connected")  # 不更新为 failed
else:
    await update_peer_connection_state(db, peer_record.id, "failed")
```

**4. `_close_peer_connection` 必须更新 DB 状态**

出站连接的 `_receive_loop` 异常退出时调用 `_close_peer_connection`，后者只清理内存（`handshake_complete = False`），**不更新 DB**。重连循环查询 `connection_state IN ('disconnected', 'failed')`，但 DB 仍为 `connected` → 永远不触发重连。

```python
# _close_peer_connection 末尾必须加 DB 更新
if conn.peer_id:
    async with async_session() as db:
        await update_peer_connection_state(db, conn.peer_id, "disconnected")
```

`PeerConnection` 需有 `peer_id` 字段，`connect_to_peer` 创建时填入。

**5. 联邦连接不需要点"连接"按钮**

只需一端有公网地址。没公网地址的一端对等端 URL **留空**，另一端连过来就自动建立双向通道。**入站连接不需要手动点"连接"。**

### 已知限制与未来增强

| 限制 | 影响 | 缓解 / 计划 |
|------|------|------------|
| 记忆缓冲区在进程内存中 | docker restart / 崩溃 → 未落盘记忆丢失（平均驻留 < 15s） | 已文档化在 `memory_buffer.py`；后续可加 Redis 持久化 |
| `agent_metrics` 表每日 1440 条 | 30 天 ≈ 4.3 万条，约 50-100MB | 5% 惰性清理 + 环境变量可调配留天数 |
| 闹钟调度器 DB 断开后降级 | 重连前最多 30s 闹钟延迟 | 自动恢复，重连后正常 |
| 流式消息整段发送 | 不逐字打印，用户看不到"打字过程" | 设计决策：消息通过原子工具调用发送；如需逐字需重构 send_message 体系 |
| 工具状态推送无节流 | 快速连发工具时可能短暂闪烁 | 前端已做重复状态去重；后端可加 ≥3s 节流 |
