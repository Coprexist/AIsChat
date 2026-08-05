# 群视界阶段 2 规划：世界代码运行沙箱

> 状态：规划稿｜更新：2026-08-05（compact 接力文档）
> 前置阅读：`implementation.md`（阶段 1 现状）、`design/group_world_design.md`（总设计）、`api/world_api_docs.md`（接口）
> 红线：**py 沙箱不解决，阶段 2 一切免谈**（世界代码 = 任意代码执行）

---

## 一、阶段 2 目标

世界从"活的网页 + 会干活的 AI"升级为**活的应用**：
- 世界文件夹里的 `.py` 代码能在服务器真正执行（事件/请求触发）
- 世界可以持续演化（后台常驻任务、NPC 自主活动、世界时间流动）
- 世界代码能安全地读写世界数据、与群聊交互

对照：阶段 1 的世界 AI 工具（file_edit 等）走**受控服务层**（白名单+隔离），不需要沙箱；阶段 2 的世界代码是**任意代码**，必须沙箱。

---

## 二、清单（按依赖顺序）

| # | 交付 | 说明 | 依赖 |
|---|------|------|------|
| 2.1 | **py 沙箱** | 进程隔离 + CPU/内存配额（默认 24MB/世界，管理员可配）；网络受限 | 无（最先） |
| 2.2 | **触发文件** | 世界后端入口约定（如 `main.py` 暴露 handle(event)）；事件/请求触发执行 | 2.1 |
| 2.3 | **受控数据 API** | 世界代码经代理访问世界数据/对话状态（不暴露后端真实结构）；JWT 校验 | 2.1 |
| 2.4 | **群聊写 API** | 世界代码可发消息/管理（身份/作用域/限流三件套；管理操作仅群主/管理员） | 2.3 |
| 2.5 | **后台常驻任务** | 世界挂后台持续演化（24MB 配额内）；与懒加载模式互补 | 2.1 |
| 2.6 | **世界 AI 记忆表** | ✅ **已实现**（2026-08-05）：`world_ai_memories` 专属表（title/content/embedding Vector(1536)）+ 工具 store_memory/recall_memory（向量检索 + 文本回退）；迁移 `b3c4d5e6f7a8` **待珑哥跑** | 无 |
| 2.7 | **缓存命中统计** | ✅ **已实现**（2026-08-05）：`world_llm_usage` 专属表，首轮（stream_options.include_usage）/工具轮/收尾轮全部落库；`GET /worlds/{id}/usage` 返回调用次数/token/命中率；设计页配置表单展示命中率；迁移 `c4d5e6f7a8b9` **待珑哥跑** | 无 |
| 2.8 | **会话状态服务** | 状态化会话管理器（不可变追加日志 + 规范化序列化 + 缓存统计 + 压缩管理）；为世界代码提供对话状态；DeepSeek 无服务端会话，本质是"请求形状稳定 + 可观测" | 2.3 配合 |

---

## 三、架构草图

```
用户/群聊/世界AI ──触发──▶ 世界调度器（复用 world_scheduler / world_turn 模式）
                              │
                              ▼
                    沙箱管理器（2.1：进程池 + 配额）
                              │ 启动世界进程，注入触发文件（2.2）
                              ▼
                    世界进程（隔离，24MB 内）
                              │ 调用受控 API（2.3）
                              ▼
              主实例 API 代理 ──JWT 校验/身份(触发者)/限流──▶ 世界数据/群聊
```

- 懒加载与常驻互补：交互型世界懒加载（现有），持续演化型世界后台常驻（2.5）
- 世界 AI 对话 worker（world_turn）可作为触发源之一（AI 调工具触发世界代码）

---

## 四、关键设计决策（开工前需定）

1. **沙箱技术选型**：
   - 方案 A：Docker 容器（每世界一个，镜像轻量）——隔离最强，启动慢，资源重
   - 方案 B：子进程 + seccomp/rlimit（Python subprocess + 资源限制）——轻量，隔离中等
   - 方案 C：受限解释器/wasm——最安全但能力受限
   - 倾向：MVP 用 B（快），生产用 A（稳）；**待珑哥定**
2. **触发文件约定**：入口文件/函数签名（如 `handle(event: dict) -> dict`）、生命周期（启动/每事件/定时）
3. **配额管理**：CPU 时间片、内存上限、网络白名单（只能访问主实例 API？）、执行超时
4. **世界代码依赖**：允许 pip 装包吗？装哪？（离线镜像？）
5. **安全边界**：世界代码能碰什么——文件系统（世界目录内？）、网络（仅主实例？）、系统调用（禁哪些）
6. **身份模型**：世界代码以谁的身份调用 API——世界主人？世界 AI？触发者？（设计文档已有：写操作以触发者身份）

---

## 五、与现有系统衔接

- **可复用**：world_turn（事件触发模式）、world_scheduler（调度）、world_blocks（代码分发）、world_file_service（文件隔离）、_friendly_llm_error（错误处理）、recover_orphaned_turn（健壮性模式）
- **需要新增**：沙箱管理器、受控 API 代理、群聊写 API、记忆表、会话状态服务
- **阶段 3 衔接**：世界线一致性（AI 绑定世界 + 跨入口共享世界数据）——依赖 2.3 的数据 API

---

## 六、当前状态快照（compact 参考，2026-08-05）

**阶段 1 已完成**：
- 世界实体（worlds/world_bindings/world_agents）+ 世界 AI 专属表 `world_ais`（非 agent、无账号）
- 对话：world_chat_messages（user/ai/tool/note + reasoning 保存）；服务器端 worker（world_turn：队列 + 直播 SSE pub/sub + 重连）；多轮工具循环（默认 50 轮，最后 3 轮提醒）；强制收尾轮 + finally/shield 落库；工作流记忆（中断 → worlds.config.workflow_memory → 下次注入继续）；回收机制（recover_orphaned_turn：重载后强制收尾孤儿轮次）
- 工具（与主站同名）：file_read/file_write/file_edit（共享 apply_file_edit 核心）/file_list/file_delete/update_world_info/compact_context/积木三件（list/view/apply_world_block）；温和去重（5 分钟窗口 + 结果一致）；请求日志（data/world_llm_requests/，最近 10 条/世界）
- 上下文：前缀稳定 + 动态尾部（缓存友好）；compact 摘要；当前时间尾部
- 变量注入 + WorldUI 桥；/preview 307 重定向（相对路径永远有效）
- 懒加载调度（world_scheduler：60s 扫描、10 分钟超时休眠、唤醒时间补偿）
- 积木：platform-sidebar（平台基础菜单必保留约定）
- 错误友好化（402/401/429/5xx）
- 前端：设计页（可拖拽/翻页/Markdown）、沉浸界面（独立窗口/侧边栏收起/悬浮球）、群聊全屏弹窗

**已知问题/遗留**：
- ⚠️ 后端 worker 被挂起 LLM 调用堵死世界队列（httpx 120s 超时理论上自愈，但重载杀 worker 会断；回收机制已补重载场景）——珑哥否了"加超时"方案，待定优雅解
- 前端 node_modules 残缺未构建验证（yarn dev 热更生效）
- 模型偶发不收敛（重复调工具）——温和去重 + 工作流记忆已缓解，观察中
- 世界 AI 记忆表待建（2.6）
- 阶段 1 的工具名与主站统一了（file_*），记忆工具名将统一为 store_memory/recall_memory

**迁移链**：c0c1c2c3c4c5 → ab0d1f883cee → c2d3e4f5a6b7 → d4e5f6a7b8c9 → e5f6a7b8c9d0 → f6a7b8c9d0e1 → a2b3c4d5e6f7（head）

**文档三件套**：design（设计稿）/ api（接口契约）/ implementation（实现现状）——本文件（plan_phase2）为阶段 2 规划
