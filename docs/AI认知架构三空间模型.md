# AI 认知架构：三空间模型 / AI Cognitive Architecture: Three-Space Model

> 本文档描述 AIsChat 中 AI 的认知架构设计——思考空间、对话空间、记忆空间三者分离，以及 JSON intent 轻量协议、双重记忆架构（向量+数据库结构记忆）。
> This document describes the cognitive architecture of AIs in AIsChat — the separation of thinking, conversation, and memory spaces, the lightweight JSON intent protocol, and the dual memory architecture (vector + structured database).
>
> **v0.9.0 更新**：文件系统记忆已迁移为数据库结构记忆（`structured_records`），新增统一上下文（immersive/digital_life 档），详见第 4-7 节。理论基础见 [`docs/记忆架构设计.md`](./记忆架构设计.md)。

---

## 1. 设计动机 / Motivation

### 1.1 旧架构的问题

| 问题 | 表现 | 根因 |
|------|------|------|
| **思考泄露** | AI 在 `content` 字段中写草稿、自言自语 | "思考"和"说话"没有区分 |
| **无效 API 消耗** | AI 返回文字但忘调 `send_message` → system_reminder → 额外 API 调用 | 缺少明确的意图声明协议 |
| **记忆盲区** | AI 不知道"自己有什么记忆"，新 AI 完全看不到记忆系统的存在 | `total_files > 0` 阈值导致空目录不注入索引 |

### 1.2 新架构目标

```mermaid
flowchart TB
    subgraph Input["📥 输入"]
        Msg[用户消息或闹钟触发]
    end

    subgraph Thinking["🧠 思考空间"]
        RC[reasoning_content<br/>🔒 完全私有]
    end

    subgraph Intent["📋 意图声明"]
        CT[content JSON]
    end

    subgraph Action["🎬 行动分发"]
        Conv[💬 对话空间<br/>send_message / send_dm]
        Mem[📂 记忆空间<br/>store_memory / recall_memory<br/>manage_records 🆕]
        Tool[🔧 工具空间<br/>execute_command / file_list / ...]
    end

    Input --> Thinking
    Thinking --> Intent
    Intent -->|tool_calls| Conv
    Intent -->|tool_calls| Mem
    Intent -->|tool_calls| Tool
    Intent -->|end_turn| Done[✅ 本轮结束]
    Intent -->|no_action| Done

    style Thinking fill:#7c3aed,stroke:#6d28d9,color:#fff
    style Intent fill:#2563eb,stroke:#1d4ed8,color:#fff
    style Conv fill:#059669,stroke:#047857,color:#fff
    style Mem fill:#d97706,stroke:#b45309,color:#fff
    style Tool fill:#dc2626,stroke:#b91c1c,color:#fff
```

---

## 2. 三空间认知模型 / Three-Space Cognitive Model

### 2.1 思考空间（reasoning_content）

```
位置：DeepSeek API 的 reasoning_content 字段
性质：完全私有，不存储、不广播、不注入对话日志
AI 可通过 toggle_thinking 工具自主开关
```

### 2.2 对话空间（send_message / send_dm）

```
AI 与外界交流的唯一通道。只有调用这两个工具，别人才会听到 AI 的话。
一次回复可并行调用多次 send_message，模拟人类连续表达。
```

### 2.3 记忆空间（双重记忆架构 v0.9.0）

```mermaid
flowchart TB
    subgraph LTM["长时记忆 (LTM)"]
        direction TB
        subgraph S1["System 1: 向量记忆 · 情节层 (Episodic)"]
            RM["rough_memories<br/>detail_memories<br/>pgvector cosine"]
            VU["模糊回忆<br/>'我好像记得...?'"]
        end
        subgraph S2["System 2: 结构记忆 · 语义层 (Semantic)"]
            SR["structured_records<br/>category/sub_key/field → value"]
            PU["精确存取<br/>'这个人的X属性?'"]
        end
    end

    Input[消息输入] --> S1
    Input --> S2
    S1 --> Merge[合并注入系统提示词]
    S2 --> Merge
    Merge --> AI[AI 看到完整记忆画像]

    style S1 fill:#d97706,stroke:#b45309,color:#fff
    style S2 fill:#2563eb,stroke:#1d4ed8,color:#fff
```

| 维度 | System 1: 向量记忆 | System 2: 结构记忆 |
|------|-------------------|-------------------|
| 理论基础 | 情节记忆 (Tulving Episodic) | 语义记忆 (Tulving Semantic) |
| 存储 | PostgreSQL pgvector | PostgreSQL 键值表 |
| 组织 | 扁平（靠 embedding 聚类） | 层级目录 (category/sub_key/field) |
| 规模 | 千级 | 百万级 |
| 注入 | 语义召回 top-k | 目录索引始终注入（空时展示推荐目录） |
| 工具 | `store_memory` / `recall_memory` | `manage_records` |

**设计思想**：等同人脑。向量记忆 = 海马体（快速编码、模糊回忆）；结构记忆 = 大脑皮层（稳定存储、精确提取）。二者互不依赖（Tulving SPI 独立提取原则），协同工作：向量发现话题 → 结构读取细节。

---

## 3. JSON Intent 轻量协议

AI 的 `content` 字段为 JSON：

```json
{"intent": "tool_calls" | "end_turn" | "no_action"}
```

```mermaid
flowchart TD
    LLM[LLM 返回] --> Parse{解析 intent}
    Parse -->|end_turn / no_action| Exit[✅ 直接退出]
    Parse -->|tool_calls| Execute[执行工具调用]
    Parse -->|解析失败 + 有content无tool_calls| Remind[system_reminder 兜底]
    Execute --> Continue[继续循环]
    Remind --> Continue
```

---

## 4. 结构记忆（数据库版 v0.9.0）

> 理论基础：Tulving SPI 模型语义记忆层 + 2026 AI 记忆综述 Agentic Memory pattern。
> 详细设计见 [`docs/记忆架构设计.md`](./记忆架构设计.md)。

### 4.1 数据模型

```sql
CREATE TABLE structured_records (
    id SERIAL PRIMARY KEY,
    agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL,    -- 顶层目录
    sub_key VARCHAR(200) NOT NULL,     -- 子目录
    field VARCHAR(200) NOT NULL,       -- 字段名
    value TEXT NOT NULL,               -- 内容
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, category, sub_key, field)  -- upsert
);
```

**目录语义**（通用，不预设职业）：

| 目录 | 含义 | 示例 |
|------|------|------|
| `people/` | 人：信息、偏好、关系 | `people/张三/偏好: 喜欢简洁` |
| `topics/` | 事：知识、观点 | `topics/物理/力学: 已掌握F=ma` |
| `tasks/` | 任务：进度、待办 | `tasks/项目A/进度: 80%` |
| `journal/` | 日志：反思、事件 | `journal/2026-07/01: ...` |

### 4.2 索引注入

```mermaid
flowchart TD
    Start([对话开始]) --> Query[查询 structured_records]
    Query --> Check{有数据?}
    Check -->|是| Show[展示目录树 + 字段摘要]
    Check -->|否| Guide["展示推荐目录 + 用法引导<br/>people/ · topics/ · tasks/ · journal/"]
    Show --> Inject[注入系统提示词]
    Guide --> Inject
```

**核心原则**：始终展示（空时引导），像人脑先天分区等待经验填充。

### 4.3 工具接口

| action | 说明 |
|--------|------|
| `set` | 写入字段（upsert） |
| `get` | 读取字段/全部 |
| `list` | 列出子目录 |
| `summary` | 生成快照摘要 |
| `categories` | 列出所有顶层目录 |
| `delete` | 删除（精确到 field） |

---

## 5. 配置体系 / Configuration Matrix

### 5.1 三层配置模型

```mermaid
flowchart TB
    subgraph Profile["config_profile"]
        Chat["chat 聊天档 · 被动"]
        Imm["immersive 沉浸档 · 主动"]
        DL["digital_life 数字生命档 · 自主"]
    end

    subgraph Type["ai_type"]
        Gen["general 通用 · 用户隔离"]
        Semi["semi_general 半通用"]
        Res["resonance 共鸣 · 全共享"]
    end

    subgraph Feature["影响"]
        Ctx["统一上下文"]
        Mem["记忆过滤"]
    end

    Chat -->|❌| Ctx
    Imm -->|✅| Ctx
    DL -->|✅| Ctx

    Gen -->|filter trigger_user_id| Mem
    Semi -->|filter trigger_user_id| Mem
    Res -->|无过滤| Mem
```

### 5.2 统一上下文（v1.1.0）

> v1.1.0 重新设计：所有会话采用统一的 `"在XX「名字」(id=X)中："` 标题格式，当前会话放最后。详见 [`AI对话链机制.md §2.4`](./AI对话链机制.md#24-统一上下文--unified-context)。

```mermaid
flowchart LR
    subgraph UC["AI 统一上下文（所有会话统一格式）"]
        Sys["[system] 核心身份 + 人格 + 工具"]
        G1["[system] 在群聊「化学研讨」(id=42)中："]
        M1["[assistant] 张三: 上次说的催化剂..."]
        G2["[system] 在私信「李四」(id=3)中："]
        M2["[user] 李四: 你好，我是新来的"]
        Cur["[system] 在私信「ShuAICFR」(id=1)中： ← 当前，最后一个！"]
        CurM["[user] ShuAICFR: 你记得..."]
    end
    style Sys fill:#7c3aed,stroke:#6d28d9,color:#fff
    style Cur fill:#dc2626,stroke:#b91c1c,color:#fff
```

| config_profile | ai_type | 统一上下文 | 隐私过滤 |
|---------------|---------|:--------:|:------:|
| chat | 任意 | ❌ | - |
| custom / immersive / digital_life | resonance | ✅ | 无过滤（共鸣 AI 全共享） |
| custom / immersive / digital_life | general / semi_general | ❌ | - |
| custom / immersive / digital_life | 其他 | ✅ | 按 trigger_user_id |

---

## 6. 系统提示词段布局

七段结构（v1.1.0），固定段在前最大化 cache 命中：

```mermaid
flowchart TB
    subgraph Fixed["固定段 · Cache 命中"]
        S1["1. core_identity"]
        S2["2. personality"]
        S3["3. protocol"]
        S4["4. tools"]
    end
    subgraph Dynamic["动态段"]
        S5["5. current_context"]
        S6["6. cross_context 🆕 v1.1.0<br/>统一上下文（统一标题格式）"]
        S7["7. injected_skills<br/>向量记忆 + Skill 引擎<br/>+ 结构记忆索引"]
    end
    S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7

    style S1 fill:#2563eb,stroke:#1d4ed8,color:#fff
    style S6 fill:#dc2626,stroke:#b91c1c,color:#fff

    style S7 fill:#0891b2,stroke:#0e7490,color:#fff
```

> v1.1.0: 跨对话上下文从独立消息注入改为统一标题格式，配合上下文压缩保缓存命中。详见 [`AI对话链机制.md §2.4`](./AI对话链机制.md#24-统一上下文--unified-context)。

---

## 7. v0.9.0 变更汇总

### 7.1 新增工具

| 工具 | 文件 | 说明 |
|------|------|------|
| `manage_records` | `tools/memory/manage_records.py` | 数据库版目录级记忆 |
| `search_users` | `tools/chat_social/search_users.py` | 按用户名搜索 ID |
| `send_friend_request` | `tools/chat_social/send_friend_request.py` | AI 主动加好友 |

### 7.2 新增文件

| 文件 | 说明 |
|------|------|
| `models/structured_record.py` | 结构记忆 ORM |
| `services/structured_memory_service.py` | CRUD + 提示词格式化 |
| `docs/记忆架构设计.md` | 双重记忆架构设计（含 Tulving SPI 理论基础） |
| 前端 `utils/platform.ts` | `isDesktop()` / `getInstanceUrl()` |
| 前端 `pages/InstanceSetupPage.tsx` | 桌面端实例配置 |
| 前端 `pages/LocalModelPage.tsx` | Ollama 本地模型管理 |

### 7.3 BUG 修复

| 文件 | 内容 |
|------|------|
| `Toggle.tsx` | 加 `border-2 border-border` 描边 |
| `AdminPage.tsx` | 分页按钮加 `text-textSecondary` 日夜适配 |
| `llm_service.py` | 空目录不注入索引 → 始终注入 |
| `llm_service.py` | 新增 `_build_cross_conversation_context` 统一上下文（v1.1.0 统一标题格式） |
| `api/client.ts` | API_BASE 可配置（桌面端 localStorage） |
| `hooks/useWebSocket.ts` | WS URL 从配置读取 |

### 7.4 系统关系

| 组件 | 变更 |
|------|------|
| `memory_index.py` | **废弃**（不再调用 `init_memory_directories`，索引注入改为数据库版） |
| `structured_records` 表 | **新增**（数据库版语义记忆） |
| `agent_service.py` | 移除 `init_memory_directories` 调用 |
