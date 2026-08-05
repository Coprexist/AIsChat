# 群视界（Group World）实现文档

> 状态：阶段 1 完成（MVP 闭环）｜更新：2026-08-05
> 定位：**实现现状与架构**（设计见 `design/group_world_design.md`，接口见 `api/world_api_docs.md`）

---

## 一、一句话

**世界 = 可编程的网页 + 一个专属世界 AI（群视界机器人）**。群聊绑定世界后，成员可从聊天页进入"沉浸界面"体验世界；世界 AI 能读档案、改世界信息、建文件、查/用积木，全程服务器端执行。

核心设计决策：
- **世界 AI 不是 agent**：无账号、无好友关系、不进 agents 表——独立实体表 `world_ais`
- **世界 AI 的表全部专属**：world_ais / world_chat_messages / 未来 world_ai_memories，不往主系统表塞类型
- **对话轮次服务器端全程执行**：不依赖网页连接存活；断开/刷新不丢，重连可"加入直播"

---

## 二、数据模型（迁移链 head = c4d5e6f7a8b9）

| 表 | 职责 | 关键字段 |
|----|------|---------|
| `worlds` | 世界实体 | name / description / owner_id / status(active\|sleeping) / time_flow_rate / world_time / last_active_at / config(JSONB：sleep_memory_mb、chat_summary、workflow_memory) |
| `world_bindings` | 入口绑定（群聊/私信/用户 ↔ 世界，多对多） | world_id / entity_type / entity_id |
| `world_agents` | 世界居民 AI（**真 agent 入驻**，阶段 3 用） | world_id / agent_id / role |
| `world_ais` | **世界 AI 实体（每世界一个）** | world_id(唯一) / name / system_prompt / model / temperature / top_p / thinking / max_tool_rounds |
| `world_chat_messages` | 世界 AI 对话 | world_id / user_id / role(user\|ai\|tool\|note) / content / reasoning（思考过程，展示用不进上下文） |
| `world_ai_memories` | **世界 AI 长期记忆（2.6）** | world_id / title / content / embedding(Vector 1536) / 时间戳 |
| `world_llm_usage` | **LLM 用量与缓存命中（2.7）** | world_id / turn_id / round_no(0\|N\|final) / model / prompt / completion / reasoning / cached_tokens |

迁移链：`c0c1c2c3c4c5 → ab0d1f883cee（world 配置+聊天表）→ c2d3e4f5a6b7（重建误删三表）→ d4e5f6a7b8c9（备份设置）→ e5f6a7b8c9d0（列注释对齐）→ f6a7b8c9d0e1（reasoning 列）→ a2b3c4d5e6f7（world_ais 实体表）→ b3c4d5e6f7a8（world_ai_memories）→ c4d5e6f7a8b9（world_llm_usage）`

---

## 三、世界 AI 对话架构（服务器端 worker）

```
POST /worlds/{id}/chat ──入队──▶ WorldTurnWorker（每世界一个，独立 DB 会话）
                                    │ 逐条处理消息队列（DM 同款并发排队）
                                    ▼
                            stream_world_chat（完整轮次）
                              ├─ 首轮流式（SSE 透传 + 思考 [REASONING]）
                              ├─ 多轮工具循环（最多 max_tool_rounds，默认 50，最后 3 轮提醒收尾）
                              ├─ 强制收尾轮（不带 tools，保证必有最终回复）
                              └─ finally + shield：中断/取消也落库（历史必有闭环）
                                    │ 事件广播给所有订阅者（发布/订阅）
GET /worlds/{id}/chat/stream?turn_id= ──订阅直播（30s 心跳；断开重连=重新订阅）
```

要点：
- **并发排队**：上一轮还在跑时发新消息 → 入队，返回 `{turn_id, queued, position}`，前端显示排队位置
- **直播可重连**：SSE 断开不影响轮次（服务器照跑）；重连订阅即"加入直播"，缺口由历史（DB）补齐
- **中断恢复（工作流记忆）**：轮次无最终回复中断 → `worlds.config.workflow_memory` 记录已执行工具步骤；下次对话注入「【未完成工作流】…请继续完成，不要重复」，正常完成自动清除
- **出错闭环**：工具执行错误落「（对话中断：工具执行出错…）」；余额不足等错误友好提示（见 §八）

### 事件协议（SSE，`data: xxx\n\n`）
| 事件 | 含义 |
|------|------|
| `data: <增量>` | 正文逐 token（换行 `{NL}` 占位） |
| `data: [REASONING]<增量>` | 思考过程（工具轮也显示） |
| `data: [TOOL]{json}` | 工具执行结果 → 前端居中气泡（🔧） |
| `data: [ERROR]<友好信息>` | 错误 |
| `data: [DONE]` | 轮次结束 |

---

## 四、工具系统（与主站同名同义，执行限世界作用域）

| 工具 | 说明 |
|------|------|
| `file_read` / `file_write` / `file_edit` / `file_list` / `file_delete` | 世界文件夹读写（隔离目录+扩展名白名单+防越界）；**file_edit 与主站共用同一份编辑核心** `app/utils/pure/file_edit.py`（str_replace 唯一性校验 / insert 行语义 / delete_lines 边界） |
| `update_world_info` | 改世界名/简介（以世界主人身份） |
| `compact_context` | 压缩对话历史 → 存 `worlds.config.chat_summary`（复用主站 context_compression_service） |
| `list_world_blocks` / `view_world_block` / `apply_world_block` | 积木体系（§七） |
| `view_api_doc` | **接口文档分区查看（2026-08-05）**：工具描述只列区名+区介绍，AI 按需传区号（01~08）取详细 API（读 `data/world_api_docs/sections/`，注册表白名单防穿越） |
| `store_memory` / `recall_memory` | **世界 AI 长期记忆（2.6）**：store 存 title+content（向量化失败降级无向量）；recall 语义检索（embedding <=> 余弦距离）→ 失败文本包含回退；世界按 world_id 隔离 |
| `get_bound_groups` / `get_group_messages` / `list_group_members` / `send_group_message` / `set_group_member_role` / `kick_group_member` | **群聊 API（以世界创建者身份）**：默认作用本世界绑定群，无需传群号；管理操作仅群主/管理员（§十一） |
| `web_search` / `web_fetch` | **上网（2026-08-05）**：**复用主系统同一份实现**（WebSearch/WebFetch 类，无 opencli 依赖）；web_fetch 支持 `delay_ms` 延迟抓取（AI 可设定等待后再取，应对慢速/动态加载页面） |

**温和去重**（`_execute_world_tool` 包装）：
- 同工具同参数、**5 分钟内**重复且**结果完全一致** → 提示「⏭ 已跳过…」不硬拦
- 结果变化（如写完文件后 list 看到新文件=验证场景）→ 正常执行
- 超过 5 分钟（用户可能改了文件）→ 允许重跑

**安全**：文件走 `world_file_service`（`data/worlds/{id}/` 隔离、`..` 拒绝、白名单扩展名）；工具以世界主人身份执行写操作；所有设计页端点仅创建者可调（`_require_owner`）。

---

## 五、上下文与缓存

- **前缀稳定**：静态 system（档案+提示词+工具约定）→ 摘要 → 历史 → 用户消息；动态信息（懒通知/压缩提示/当前时间）全部放**末尾独立 system 消息**（与主对话同规则，不破坏 prefix cache）
- **当前时间**：`## 当前时间` 尾部注入（display_timezone，v4 思考默认开是正常行为）
- **compact**：接近上限（128K 的 60%）提示 AI 调 `compact_context` → 摘要存库 → 下次只发「摘要+最近 10 条」；一次压缩一次 miss，之后稳定命中
- **请求日志**：每次发往 DeepSeek 的完整请求落盘 `data/world_llm_requests/{world_id}.jsonl`（每世界最近 10 条，含 turn_id/round 标记），排查问题直接看模型收到了什么

---

## 六、世界变量注入 + UI 桥

后端在服务世界 HTML（`/world/{id}/files/*.html` 与 `/preview`）时自动注入：

```js
window.WORLD_ID = 2;            // 世界编号
window.WORLD_AI_ID = 'world-2'; // 世界 AI 身份
window.WORLD_AI_NAME = '群视界机器人';
window.GROUP_ID = null;         // 入口群聊（?group_id= 传入）
window.USER_ID = null;          // 宿主环境补
window.WorldUI = {              // UI 桥（postMessage → 宿主 Layout）
  toggleSidebar, showSidebar, hideSidebar,
  hideFloatingIcon, showFloatingIcon,
};
```

- `/world/{id}/preview` → **307 重定向**到 `/world/{id}/files/index.html`（单一规范挂载点，页面内相对路径永远有效，打包即插即用）
- **打包原则**：世界代码零硬编码，一切标识走变量；相对路径引用资源（支持跨文件夹 `../`）

---

## 七、积木体系（预制世界块）

- 积木包：`data/world_blocks/{block_id}/`（manifest.json + 自包含 css/js）
- 现有积木：
  - `platform-sidebar`（平台侧边栏——**内置平台基础菜单：首页/聊天/世界列表/设置，必保留**（可折叠「平台」组，跳主应用 window.parent），+ 世界自定义菜单 `SIDEBAR_ITEMS`，组名/项名可自定义 `SIDEBAR_PLATFORM_TITLE/LABELS`，应用后自动 `WorldUI.hideFloatingIcon()`）
  - `group-chat`（**群聊对话窗，2026-08-05**：消息列表+输入发送+轮询；**样式与主界面聊天一致**——渐变头像（自己紫/别人青/系统红，有头像用图）、左右布局、相对时间（刚刚/X分钟前/HH:MM）、Markdown 轻量渲染（标题/粗体/代码/列表/引用/链接，先转义防 XSS）、附件（图片缩略图/文件芯片）；发送人区分：`window.USER_ID` 优先 + localStorage `user_info` 回退，`sender_type === 'human'`；挂载点 `<div id="group-chat">` + `GROUP_CHAT_CONFIG{mountId,groupId,height,title,apiBase,pollMs}`）
- AI 工具：查（list）/ 看（view，完整代码）/ 应用（apply → 复制进世界 `blocks/{id}/`，随世界打包导出）
- 约定：任何世界侧边栏必须保留平台基础菜单（四目的地），否则用户回不了主应用
- ⚠️ 已应用过积木的世界不会自动更新（文件是复制的），平台侧升级需重新 apply

---

## 八、错误处理

`_friendly_llm_error(err)`：
| 错误 | 提示 |
|------|------|
| 402 余额不足 | 💰 充值引导 +「已记录工作流，充值后说继续」 |
| 401/403 Key 无效 | 🔑 检查更新 API Key |
| 429 限流 | ⏳ 稍等再试 |
| 5xx | 🔧 服务繁忙稍后再试 |
| 其他 | 原文前 200 字 |

---

## 九、懒加载调度（world_scheduler）

- 60s 扫描：活跃超 10 分钟 → 休眠（零占用）；休眠但有近期活动（对话/预览）→ 唤醒 + **离线时间补偿**（`world_time += 真实时间差 × time_flow_rate`）
- 对话/预览都是活跃信号；阶段 2 世界代码常驻时此机制是省资源+世界线不丢的骨架

---

## 十、前端

| 界面 | 说明 |
|------|------|
| 世界列表 `WorldsPage` | 我的世界（创建者） |
| **设计页** `WorldDesignPage` | 左文件树/编辑器/预览 + 右世界 AI 对话（⚙️ 配置表单：名字/提示词/模型/温度/思考开关/工具轮上限）；可拖拽面板（复用 useResizableSidebar）；Markdown 渲染（共享 MarkdownContent）；历史滚到顶翻页 |
| **沉浸界面** `WorldViewPage` | 全屏渲染世界；网页端命名 `window.open` 独立窗口（复用+聚焦），桌面 Tauri 独立 WebviewWindow；侧边栏默认收起 + 悬浮球开关（世界代码可经 WorldUI 控制）；独立窗口里"返回"= 关窗口 |
| **群聊入口** | 绑定世界的群聊进对话页 → **全屏弹窗**「这个群聊绑定了群视界」→ 🎮 沉浸（独立窗口）/ ⚙️ 标准（关弹窗加载消息，门控先不加载） |

---

## 十一、已知边界 & 阶段 2 路线

**边界**：
- 前端 node_modules 残缺未构建验证（yarn dev 热更生效）
- 模型偶发不收敛（重复调工具）——温和去重 + 工作流记忆已缓解，观察中
- 记忆 MVP 无自动注入（AI 主动 store/recall）；后续可加：对话开始自动 recall 注入上下文

**阶段 2（沙箱先行，红线）**：
1. ✅ **2.6 世界 AI 记忆表**（2026-08-05 已完成：world_ai_memories + store_memory/recall_memory）
2. ✅ **2.7 缓存命中统计**（2026-08-05 已完成：world_llm_usage 三处落库 + GET /worlds/{id}/usage + 设计页命中率展示）
3. **2.1 py 沙箱**（决策已定：MVP=subprocess + resource.rlimit + 超时强制杀；生产加固=加严配额或 seccomp+Landlock（参考 evalbox）或容器）——世界代码真正能跑
4. 触发文件（世界后端入口）
5. 受控数据 API（世界代码访问世界数据）
6. 群聊写 API（身份/作用域/限流三件套）
7. 后台常驻任务（世界自主演化）
8. 世界线一致性（阶段 3）

---

## 附：模块清单

```
backend/app/
├── models/world.py              # worlds / world_bindings / world_agents / world_ais / world_chat_messages
├── routers/worlds.py            # 世界 CRUD/绑定/唤醒/creator 配置/对话/文件（owner 校验）
├── routers/world_proxy.py       # /world/{id}/files/* + /preview（307）+ 变量/WorldUI 注入
├── services/world/
│   ├── world_service.py         # CRUD/绑定/唤醒/懒通知/世界 AI 实体（再导出拆分模块）
│   ├── world_chat_service.py    # 世界档案/历史/凭证/流式对话/多轮工具/收尾/工作流记忆/请求日志
│   ├── world_tools.py           # 工具定义 + 执行 + 温和去重（5min 窗口）+ 摘要
│   ├── world_turn.py            # 轮次 worker（队列 + 直播广播 pub/sub）
│   ├── world_scheduler.py       # 懒加载调度（休眠/唤醒/时间补偿）
│   ├── world_blocks.py          # 积木注册表（查/看/应用）
│   └── world_file_service.py    # 世界文件隔离读写（安全）
├── utils/pure/file_edit.py      # 增量编辑核心（主站 file_edit 与世界共用）
frontend/src/
├── pages/WorldsPage.tsx / WorldDesignPage.tsx / WorldViewPage.tsx
├── components/ChatView.tsx      # 群聊世界入口全屏弹窗 + 沉浸独立窗口
├── components/Layout.tsx        # 沉浸界面侧边栏收起 + 悬浮球 + WorldUI 桥监听
├── components/shared/MarkdownContent.tsx  # 共享 Markdown 渲染
└── hooks/useResizableSidebar.ts # 可拖拽面板（left/right）
data/
├── worlds/{id}/                 # 世界文件（隔离）
├── world_blocks/                # 积木包
└── world_llm_requests/{id}.jsonl  # 实际 LLM 请求日志（最近 10 条/世界）
```
