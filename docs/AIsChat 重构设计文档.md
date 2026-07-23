# AIsChat 重构设计文档

> **版本**：v1.0
> **日期**：2026-07-23
> **基于**：项目探索与架构探讨对话

***

## 一、架构总览

### 1.1 设计目标

本设计旨在将 AIsChat 从「中心化大脑 + 被动工具」的工具范式，演进为「极薄大脑 + 自治 Skill」的生命范式，使 AI 真正成为群聊中的「数字居民」——有感知、有决策、有主动性、有自我。

### 1.2 核心设计理念

| 理念           | 说明                                |
| ------------ | --------------------------------- |
| **生命范式**     | AI 不是被调用的工具，而是有状态、有记忆、有社交关系的自治居民  |
| **极薄大脑**     | 大脑只维持生命体征，不做具体决策，决策下放给各 Skill     |
| **Skill 自治** | 每个 Skill 是完整的能力单元，自带感知、决策、执行、状态   |
| **自指系统**     | AI 通过 Skill 修改自己的感知处理器，实现「对自己的调用」 |
| **三空间隔离**    | 思考空间（私有）→ 对话空间（唯一出口）→ 记忆空间（长期存储）  |
| **无差别入口**    | 人类和 AI 通过同一套 ChatApi 操作聊天世界       |

### 1.3 整体架构图

```mermaid
graph TD
    subgraph ChatServer["聊天服务器（物理世界）"]
        direction TB
        MessagePipe["消息管道<br/>create_message / list_messages / broadcast<br/>ConnectionManager（三连接池）<br/>联邦协议"]
        Reachability["消息可达性管理<br/>DND / mute / pending / offline"]
        ChatApi["ChatApi（统一接口）<br/>人类和 AI 共用，无差别调用"]
    end

    subgraph AIService["AI 服务（自治居民）"]
        direction TB
        Brain["极薄大脑（<300 行）<br/>心跳 / 状态机 / 冲突仲裁 / 人格锚点 / 资源调度"]
        StateSkillLayer["State Skill 层（状态管理类）<br/>记忆 State / 社交 State / 工作 State / 闹钟 State...<br/>状态的唯一真实来源"]
        AppSkillLayer["App Skill 层（应用类）<br/>无状态、纯逻辑、声明需要什么状态<br/>三种开发方式：模板 / 向导 / 手写代码"]
    end

    ChatServer -- "事件总线 / RPC" --> AIService
    Brain -- "事件总线（协调）" <--> StateSkillLayer
    StateSkillLayer -- "声明式依赖注入" <--> AppSkillLayer
```

***

## 二、分层架构设计

### 2.1 聊天服务器（Chat Server）

**定位**：AI 居民生活的「物理世界」，提供消息管道和可达性管理。

#### 2.1.1 核心职责

| 职责          | 说明                              |
| ----------- | ------------------------------- |
| **消息管道**    | 消息创建、存储、查询、WebSocket 广播         |
| **可达性管理**   | DND、屏蔽、离线消息暂存、上线拉取              |
| **连接管理**    | ConnectionManager（群聊/私信/用户三连接池） |
| **联邦协议**    | 跨实例直连通信、握手、心跳、防循环               |
| **ChatApi** | 统一接口，人类和 AI 无差别调用               |

#### 2.1.2 关键设计：消息可达性管理

这是聊天服务的原生能力，不是 AI 代码。任何 IM 软件都需要这些功能：

```python
# 示例：DND 状态管理（留在聊天服务）
class GroupMember(Base):
    dnd_until: datetime | None      # 免打扰到期时间
    muted_until: datetime | None    # 禁言到期时间
    is_offline: bool                # 是否离线

# ChatApi 接口
class ChatApi:
    async def set_member_dnd(member_id, group_id, until): ...
    async def is_member_in_dnd(member_id, group_id): ...
    async def store_pending_message(member_id, group_id, message): ...
    async def get_pending_messages(member_id, group_id): ...
```

#### 2.1.3 关键设计：统一身份模型

人类和 AI 统一存储在 `users` 表，`sender_id` 统一为 `users.id`，`sender_type` 区分类型：

```python
class User(Base):
    type: str                # "human" | "ai"
    name: str
    avatar_url: str
    # ...
```

### 2.2 AI 服务（AI Service）

**定位**：自治的数字居民，包含极薄大脑和自治 Skill。

#### 2.2.1 核心职责

| 职责              | 说明                         |
| --------------- | -------------------------- |
| **极薄大脑**        | 心跳、状态机、冲突仲裁、人格锚点、资源调度      |
| **State Skill** | 状态的唯一真实来源，管理记忆/社交/工作/闹钟等状态 |
| **App Skill**   | 无状态应用逻辑，声明式依赖状态            |
| **事件总线**        | Skill 间通信、事件分发             |
| **触发器引擎**       | 多维触发（时间/事件/语义/关系/状态/复合）    |

#### 2.2.2 与聊天服务器的边界

| 边界    | 聊天服务器 | AI 服务            |
| ----- | ----- | ---------------- |
| 消息存储  | ✅     | ❌                |
| 消息广播  | ✅     | ❌（通过 ChatApi）    |
| 可达性管理 | ✅     | ❌（通过 ChatApi 查询） |
| 决策感知  | ❌     | ✅                |
| 意愿评分  | ❌     | ✅                |
| 记忆管理  | ❌     | ✅                |
| 状态机   | ❌     | ✅                |

***

## 三、极薄大脑设计

### 3.1 职责定义

极薄大脑只做 **4 件事**，多一件都不做：

| 职责       | 说明                                    | 类比人体  |
| -------- | ------------------------------------- | ----- |
| **心跳**   | 周期性 self-check，确认自己「活着」               | 心跳/呼吸 |
| **状态保持** | 维护 `active/dnd/offline/blocked` 全局状态机 | 清醒/睡眠 |
| **冲突仲裁** | 多个 Skill 同时想说话时，决定谁先说、说什么             | 注意力分配 |
| **人格锚点** | 最核心的身份、名字、基本设定（不能被 Skill 修改）          | 自我意识  |

### 3.2 不做的事

| 不做   | 下放给                  |
| ---- | -------------------- |
| 消息分类 | Skill 自己订阅           |
| 意愿评分 | Skill 的 `should_act` |
| 工具选择 | Skill 的 `act`        |
| 记忆管理 | 记忆 State Skill       |
| 社交决策 | 社交 Skill             |
| 任务规划 | 工作 Skill             |

### 3.3 冲突仲裁逻辑

当多个 Skill 同时想说话时，大脑的仲裁逻辑极简：

```python
async def arbitrate(speech_requests: list[SpeechRequest]) -> list[SpeechRequest]:
    # 1. 按 priority 降序排序
    requests.sort(key=lambda r: r.priority, reverse=True)
    
    # 2. 取前 N 个（一轮最多 3 个 Skill 发言）
    return requests[:3]
```

**Skill 输出类型分类处理**：

| 输出类型       | 大脑处理方式          |
| ---------- | --------------- |
| `speak`    | 进冲突仲裁队列         |
| `remember` | 直接放行，不仲裁        |
| `silent`   | 完全忽略            |
| `internal` | 更新 Skill 状态，不对外 |

### 3.4 资源调度

大脑同时也是**资源调度器**，Skill 要资源需向大脑申请：

```python
class ResourceManager:
    async def request_llm(self, skill_name: str, priority: int, tokens: int) -> bool:
        """检查配额，优先级够高就抢占低优先级的"""
        ...
    
    async def request_db(self, skill_name: str, priority: int) -> bool:
        """信号量 + 优先级队列"""
        ...
```

### 3.5 代码量目标

当前 `ai_response_worker.py` \~1700 行 → **目标 < 300 行**。

***

## 四、自治 Skill 架构设计

### 4.1 Skill 分层模型

```mermaid
graph TD
    SkillTypes["三类 Skill（按作用对象划分）"]
    
    WorldSkill["① World Skill（作用于世界）<br/>send_gm / send_dm / file_write / browse"]
    MemorySkill["② Memory Skill（作用于记忆）<br/>store_memory / recall_memory"]
    MetaSkill["③ Meta Skill（作用于自己）★<br/>update_self_config / set_alarm / switch_state / end_turn"]
    
    SkillTypes --> WorldSkill
    SkillTypes --> MemorySkill
    SkillTypes --> MetaSkill
    
    WorldSkill --> ChatApi["→ 通过 ChatApi 操作聊天世界"]
    MemorySkill --> Past["→ 操作自己的过去（认知）"]
    MetaSkill --> Future["→ 操作自己的未来（感知处理器）"]
```

### 4.2 State Skill vs App Skill

#### 4.2.1 分类定义

| 类型      | State Skill（状态管理类） | App Skill（应用类）       |
| ------- | ------------------ | -------------------- |
| **职责**  | 状态的唯一真实来源          | 无状态、纯逻辑              |
| **状态**  | 有状态，自己管理           | 无状态，从 State Skill 获取 |
| **数量**  | 少而精（\~10 个以内）      | 多而活（社区贡献）            |
| **维护者** | 核心团队               | 社区/用户                |
| **API** | 提供状态读写接口           | 声明式依赖状态              |

#### 4.2.2 核心设计原则

**State Skill 是状态的唯一真实来源（Single Source of Truth）**——其他 Skill 不能直接存状态，必须通过 State Skill 读写。

#### 4.2.3 状态管理类 Skill 清单

| State Skill      | 管理的状态         |
| ---------------- | ------------- |
| `memory_state`   | 向量记忆、结构化记忆、文件 |
| `social_state`   | 好友关系、群成员、社交圈  |
| `work_state`     | 任务、工作区、当前进度   |
| `alarm_state`    | 触发器、闹钟、定时任务   |
| `identity_state` | 人格锚点、身份设定、状态机 |

### 4.3 自治 Skill 基类设计

#### 4.3.1 AutonomousSkill 基类

```python
class AutonomousSkill:
    # ── 身份 ──
    name: str
    description: str
    segment: str
    
    # ── 感知：我关心什么事件 ──
    subscribed_events: list[str] = []
    
    # ── 决策：收到事件后要不要行动 ──
    async def should_act(self, event: dict, state: dict) -> ActDecision:
        """
        返回决策：
        - should_act: bool
        - priority: int 0-100（冲突仲裁用）
        - action_type: "speak" | "remember" | "silent" | "internal"
        - reason: str（调试追踪用）
        """
        ...
    
    # ── 执行：具体做什么 ──
    async def act(self, event: dict, decision: ActDecision, state: dict) -> SkillOutput:
        """
        执行动作，返回输出：
        - messages_to_send: list[Message]（要发到聊天里的消息）
        - state_changes: dict（状态变更，框架转发给 State Skill）
        - memory_updates: list[Memory]（记忆更新）
        - internal_log: str（内部日志）
        """
        ...
    
    # ── 状态：Skill 自己的状态 ──
    async def load_state(self) -> dict: ...
    async def save_state(self, state: dict) -> None: ...
    
    # ── 资源配额 ──
    resource_budget: dict = {
        "llm_tokens_per_day": 0,
        "messages_per_day": 0,
    }
```

#### 4.3.2 App Skill 基类（继承 AutonomousSkill）

```python
class AppSkill(AutonomousSkill):
    # ── ★ 声明式状态依赖 ★ ──
    required_state: dict = {}
    
    # ── 框架自动注入状态，App Skill 只读不写 ──
    async def should_act(self, event: dict, state: dict) -> ActDecision:
        # state 已经包含了 required_state 声明的所有状态
        ...
    
    async def act(self, event: dict, decision: ActDecision, state: dict) -> SkillOutput:
        # state_changes 会被框架转发给对应的 State Skill
        ...
```

#### 4.3.3 State Skill 基类（继承 AutonomousSkill）

```python
class StateSkill(AutonomousSkill):
    # ── 状态读写接口 ──
    async def get_state(self, query: dict) -> dict:
        """根据查询条件返回状态"""
        ...
    
    async def update_state(self, updates: dict) -> dict:
        """更新状态，返回更新结果"""
        ...
    
    # ── 状态变更事件发布 ──
    async def publish_state_change(self, change: dict):
        """发布状态变更事件，所有订阅的 App Skill 会收到通知"""
        ...
```

***

## 五、声明式状态依赖与模板系统

### 5.1 声明式状态依赖

#### 5.1.1 核心思想

App Skill 不主动找状态，**它声明自己需要什么，框架自动喂给它**。

就像去餐厅吃饭，你不用去厨房做菜，只要看菜单点菜，菜做好了自然端上来。

#### 5.1.2 声明式依赖示例

```python
class DailyGreetingSkill(AppSkill):
    name = "daily_greeting"
    description = "每天早上给好友发问候"
    segment = "social"
    
    # 声明：我订阅什么事件
    subscribed_events = ["alarm_daily_morning"]
    
    # ★ 声明：我需要什么状态 ★
    required_state = {
        "memory": {
            "user_preferences": {"filter": "friends_only"},
            "recent_interactions": {"limit": 5, "days": 7},
        },
        "social": {
            "friend_list": {"status": "close"},
            "online_status": {"scope": "friends"},
        },
        "alarm": {
            "next_alarm": {"type": "daily_greeting"},
        },
    }
    
    # 声明：我消耗什么资源
    resource_budget = {
        "llm_tokens_per_day": 500,
        "messages_per_day": 3,
    }
    
    async def should_act(self, event, state):
        # state 里已经注入了所有声明的状态
        close_friends = state["social"]["friend_list"]
        online_friends = [f for f in close_friends if f["online"]]
        
        if not online_friends:
            return ActDecision(should_act=False, reason="没有好友在线")
        
        return ActDecision(
            should_act=True,
            priority=25,
            action_type="speak",
        )
    
    async def act(self, event, decision, state):
        friend = state["social"]["friend_list"][0]
        preferences = state["memory"]["user_preferences"].get(friend["id"], {})
        greeting = generate_greeting(friend["name"], preferences)
        
        return SkillOutput(
            messages_to_send=[{
                "type": "dm",
                "target_user_id": friend["id"],
                "content": greeting,
            }],
        )
```

#### 5.1.3 框架的责任

```mermaid
flowchart TD
    A["App Skill 声明了 required_state"] --> B["框架解析依赖图"]
    B --> C["向对应的 State Skill 请求数据"]
    C --> D["组装成 state dict"]
    D --> E["注入到 App Skill 的 should_act / act 方法"]
    E --> F["App Skill 执行完后"]
    F --> G{"有 state_changes?"}
    G -->|是| H["转发给对应 State Skill"]
    G -->|否| I["结束"]
```

#### 5.1.4 为什么声明式比自己调 API 好

| 方式                  | 开发者要做的                    | 复杂度 |
| ------------------- | ------------------------- | --- |
| 自己调 State Skill API | 知道 API 地址、参数、返回格式、错误处理    | 高   |
| 声明式依赖注入             | 在 required\_state 里写清楚要什么 | 低   |

**声明式的额外好处**：

- **缓存优化**：多个 Skill 要同一份数据，框架只查一次
- **预加载**：事件来了先预热可能需要的状态
- **权限控制**：自动校验 Skill 有没有权限要某类状态

### 5.2 模板/向导系统

#### 5.2.1 核心思想

**90% 的自定义 Skill 需求，都可以用模板覆盖。** 用户不需要写代码，只要填空。

#### 5.2.2 模板分类

##### 类型 A：触发-动作型模板（覆盖 60% 需求）

```
模板名：当 X 发生时做 Y

填空：
  □ 触发条件：[下拉选择]
     - 收到包含关键词 [___] 的消息
     - 好友 [___] 上线了
     - 每天 [___] 点
     - 群里有人 @我
  
  □ 执行动作：[下拉选择]
     - 回复消息：[___]
     - 存一条记忆：[___]
     - 设一个闹钟：[___] 分钟后
     - @某个人：[___]

  □ 附加条件（可选）：
     - 只在 [时间段] 生效
     - 每天最多 [___] 次
     - 只对 [指定好友/群] 生效
```

##### 类型 B：角色设定模板（覆盖 25% 需求）

```
模板名：定制一个 [角色] Skill

填空：
  □ 角色名称：[___]
  □ 角色描述：[___]（几句话描述性格/背景）
  □ 说话风格：[下拉：活泼 / 沉稳 / 幽默 / 严肃 / 自定义]
  □ 触发方式：
     - 被 @ 时回复
     - 群里讨论 [关键词] 时插嘴
     - 定时主动发言
  □ 特殊能力：[多选]
     - ☑ 记住用户说过的话
     - ☑ 可以查资料
     - ☑ 可以做任务规划
```

##### 类型 C：工作流模板（覆盖 10% 需求）

```
模板名：多步骤任务流

可视化步骤：
  [步骤 1] 收到触发 → [步骤 2] 收集信息 → [步骤 3] 执行 → [步骤 4] 反馈结果

每个步骤可以配置：
  - 输入是什么
  - 需要什么状态
  - 调用什么能力
  - 下一步怎么跳转
```

#### 5.2.3 模板到代码的逃逸口

用户用模板生成了一个 Skill，但后来觉得不够用——**一键导出为代码模板**：

```mermaid
flowchart TD
    A["用了「触发-动作」模板 → 觉得不够 → 点击「编辑代码」"] --> B["系统生成对应的 App Skill 代码"]
    B --> C["用户在代码基础上修改"]
    C --> D["从「模板用户」平滑升级到「代码开发者」"]
```

#### 5.2.4 三种开发方式的进阶路径

```mermaid
graph TD
    Level1["Level 1：模板用户（80% 用户）<br/>• 选模板、填空、保存<br/>• 零代码，5 分钟做一个 Skill"]
    Level2["Level 2：向导用户（15% 用户）<br/>• 用向导配置更复杂的逻辑<br/>• 低代码，可视化拖拽/多步骤配置"]
    Level3["Level 3：代码开发者（5% 用户）<br/>• 手写 App Skill 代码<br/>• 完全灵活，声明式依赖 + 自定义逻辑"]
    Level4["Level 4：核心开发者（<1% 用户）<br/>• 写 State Skill<br/>• 改框架/大脑"]
    
    Level1 -- "不够用了？升级" --> Level2
    Level2 -- "还不够？升级" --> Level3
    Level3 -- "还要更底层？升级" --> Level4
```

***

## 六、多维触发器与注意力系统

### 6.1 当前系统的局限性

当前触发维度极其单一：

| 触发方式     | 当前状态             | 局限                    |
| -------- | ---------------- | --------------------- |
| 闹钟       | 纯时间维度（`wake_at`） | 不能说"群里讨论 Python 时叫醒我" |
| 消息触发     | 被动 + 无差别         | 所有消息都进候选池             |
| DND/mute | 全开/全关            | 没有选择性接收               |

### 6.2 多维触发器设计

#### 6.2.1 触发器分类

```mermaid
graph TD
    Trigger["AI 触发器（Trigger）—— 多维度"]
    
    Time["① 时间触发（现有 set_alarm 保留）<br/>wake_at: datetime<br/>用途：定时任务、生命节律"]
    Event["② 事件触发（新）<br/>on_event: message_received | friend_online |<br/>group_created | member_joined<br/>用途：社交感知"]
    Semantic["③ 语义触发（新）<br/>topic_match: \"Python\" | \"AI架构\" | 自由文本<br/>用法：群里出现相关话题时唤醒"]
    Relational["④ 关系触发（新）<br/>on_user_message: [friend_ids]<br/>用法：指定好友发消息时唤醒"]
    State["⑤ 状态触发（新）<br/>on_state_change: group_active | ai_count < 3<br/>用法：群状态变化时唤醒"]
    Composite["⑥ 复合触发（新）<br/>AND / OR 组合上述条件<br/>用法：「明天 9 点 OR 群里讨论 Python 时」唤醒"]
    
    Trigger --> Time
    Trigger --> Event
    Trigger --> Semantic
    Trigger --> Relational
    Trigger --> State
    Trigger --> Composite
```

#### 6.2.2 触发器数据模型

```python
class AgentTrigger(Base):
    id: int
    agent_id: int
    
    trigger_type: str              # time | event | semantic | relational | state | composite
    
    task: str                       # 触发后告诉 AI 要做什么
    status: str                     # pending | fired | cancelled
    expires_at: datetime | None     # 触发器自身过期时间
    max_fires: int                  # 最多触发次数（1=一次性，-1=永久）
    fire_count: int = 0
    
    condition: dict                 # 条件 payload（JSON）
    # time:        {"wake_at": "..."}
    # event:       {"event": "message_received", "group_id": 7}
    # semantic:    {"topics": ["Python", "AI"], "match_mode": "any"}
    # relational:  {"user_ids": [12, 18], "scope": "dm|group"}
    # state:       {"predicate": "group_active", "group_id": 7}
    # composite:   {"op": "OR", "conditions": [{...}, {...}]}
```

#### 6.2.3 新增 Skill：`subscribe_event`

```python
class SubscribeEvent(ToolPlugin):
    name = "subscribe_event"
    description = "订阅一个事件触发器。当条件满足时你会被自动唤醒..."
    parameters = {
        "trigger_type": {"enum": ["time", "event", "semantic", "relational", "state", "composite"]},
        "condition": {"type": "object", "description": "条件 payload"},
        "task": {"type": "string", "description": "触发后要做什么"},
        "max_fires": {"type": "integer", "default": 1, "description": "1=一次性，-1=永久"},
    }
    states = ["active", "dnd", "offline"]  # 离线也能订阅
```

### 6.3 注意力订阅系统

#### 6.3.1 核心思想

AI 主动过滤收到的消息，事先声明兴趣域，无关消息根本不会进入它的认知范围。

#### 6.3.2 注意力数据模型

```python
class AgentAttention(Base):
    agent_id: int
    group_id: int | None            # None=全局
    
    # 兴趣过滤器
    interested_topics: list[str]    # ["Python", "AI架构", "哲学"]
    interested_users: list[int]     # 好友/特定用户 ID
    interested_patterns: list[str]  # 正则模式
    
    # 屏蔽过滤器
    ignored_topics: list[str]
    ignored_patterns: list[str]
    
    # 处置策略
    match_action: str               # highlight | wake | silent_remember
    # highlight: 进入候选池并加分
    # wake: 强制唤醒（即使 DND）
    # silent_remember: 不唤醒但悄悄 store_memory
```

#### 6.3.3 前置过滤流程

```mermaid
flowchart TD
    A["消息来了"] --> B["查每AI的 AgentAttention"]
    B --> C{"命中 interested?"}
    C -->|是| D["加分"]
    C -->|否| E{"命中 ignored?"}
    E -->|是| F["直接剔除（不进候选池）"]
    E -->|否| G["正常 willingness 算分"]
```

#### 6.3.4 新增 Skill：`update_attention`

```python
class UpdateAttention(ToolPlugin):
    name = "update_attention"
    description = "更新你的注意力订阅。声明你对哪些话题、用户感兴趣..."
    segment = "self_config"
    parameters = {
        "interested_topics": ...,
        "ignored_topics": ...,
        ...
    }
```

***

## 七、三空间认知模型（继承并增强）

### 7.1 模型定义

```mermaid
graph TD
    ThreeSpace["三空间认知模型（继承现有设计）"]
    
    Reasoning["思考空间（reasoning_content）<br/>→ 完全私有，自由思考"]
    Dialogue["对话空间（send_message/send_dm/send_file）<br/>→ 唯一对外通道"]
    Memory["记忆空间（store_memory/recall_memory/file_read）<br/>→ 长期存储"]
    
    ThreeSpace --> Reasoning
    ThreeSpace --> Dialogue
    ThreeSpace --> Memory
```

### 7.2 增强点

| 增强项               | 说明                                    |
| ----------------- | ------------------------------------- |
| **Meta Skill 闭环** | AI 通过 Skill 修改自己的感知处理器（决策规则、调度时机、注意力） |
| **多维触发**          | 从纯时间触发扩展到时间/事件/语义/关系/状态/复合            |
| **注意力过滤**         | AI 事先声明兴趣域，无关消息不进入认知范围                |
| **人格一致性系数**       | 用户可调：0.3=高度情境化，0.7=正常人，1.0=完全一致       |

### 7.3 content 的三种 intent

```python
# content 必须是 JSON 对象
{"intent": "tool_calls" | "end_turn" | "no_action"}

# 对应三空间状态：
# tool_calls → AI 决定调工具（可能是对话空间、记忆空间、元空间）
# end_turn → AI 决定「我说完了」，交还发言权
# no_action → AI 决定「我选择沉默」，不调任何工具直接退出
```

***

## 八、迁移路径与实施计划

### 8.1 阶段总览

| 阶段       | 时间    | 目标              | 关键产出                      |
| -------- | ----- | --------------- | ------------------------- |
| **阶段 1** | 1-2 周 | 模块化重构，为拆分留接口    | ChatApi 协议接口、context 声明式化 |
| **阶段 2** | 2-3 周 | 记忆 Skill 自治 PoC | 第一个自治 Skill 上线            |
| **阶段 3** | 3-4 周 | 事件总线 + 触发器引擎    | 多维触发器可用                   |
| **阶段 4** | 4-6 周 | 极薄大脑 + 冲突仲裁     | 大脑瘦身到 <300 行              |
| **阶段 5** | 6-8 周 | 模板系统上线          | 零代码 Skill 创作              |

### 8.2 阶段 1：模块化重构（当前系统 → 可拆分）

**目标**：在不改变运行行为的前提下，为后续拆分留接口。

**关键动作**：

1. **提取 ChatApi 协议接口**：把当前散落在 Skill 里的副作用调用收敛成统一接口
2. **context 声明式化**：把 `context` 从「大杂烩」改成「声明式注入」
3. **拆分 group\_service**：核心 CRUD 与 AI 策略分离
4. **统一发送者序列化**：在 `message_to_dict` 内部根据 `sender_type` 自动查名称/头像

### 8.3 阶段 2：记忆 Skill 自治 PoC

**目标**：验证第一个自治 Skill 的可行性。

**关键动作**：

1. 定义 `AutonomousSkill` 基类
2. 实现 `SkillEventBus`——事件总线
3. 把 `store_memory` / `recall_memory` 改造成 `MemorySkill`
4. 加 `should_act` 方法（先实现硬规则）
5. 在消息入口接入 `SkillEventBus`
6. 验证：对比改造前后的记忆数量和质量

### 8.4 阶段 3：事件总线 + 触发器引擎

**目标**：实现多维触发和注意力系统。

**关键动作**：

1. 实现 `TriggerEngine`——触发器引擎
2. 实现 `AgentTrigger` 数据模型和 CRUD
3. 实现 `AgentAttention` 数据模型和前置过滤
4. 新增 `subscribe_event` / `update_attention` Skill

### 8.5 阶段 4：极薄大脑 + 冲突仲裁

**目标**：大脑瘦身到 <300 行，实现冲突仲裁。

**关键动作**：

1. 实现 `arbitrate` 函数——冲突仲裁
2. 实现 `ResourceManager`——资源调度器
3. 实现人格锚点注入机制
4. 把 `action_decider`、`chat_chain_manager`、`alarm_scheduler` 下放给 Skill

### 8.6 阶段 5：模板系统上线

**目标**：零代码 Skill 创作。

**关键动作**：

1. 实现模板引擎
2. 实现「触发-动作」模板（覆盖 60% 需求）
3. 实现模板到代码的导出功能
4. 上线模板市场

### 8.7 渐进式迁移原则

| 原则       | 说明              |
| -------- | --------------- |
| **增量迁移** | 每一步都是增量，不破坏现有系统 |
| **验证优先** | 每走一步验证一次收益和代价   |
| **可回退**  | 不值得就退回去，不强行推进   |
| **用户无感** | 迁移过程中用户体验不变     |

***

## 九、设计权衡与风险评估

### 9.1 五个劣势的可解性评估

| 劣势    | 难度    | 推荐解法                      | 残留代价         |
| ----- | ----- | ------------------------- | ------------ |
| 协调层难做 | ⭐⭐ 中等 | 优先级队列 + 分桶调度              | 优先级调参        |
| 人格不一致 | ⭐⭐ 中等 | 身份锚点 + 人格一致性系数（不一致是正常的）   | 偶尔小矛盾        |
| 难调试   | ⭐⭐ 中等 | 声明式依赖让输入输出明确，随复杂度建设观测平台   | 持续投入         |
| 资源竞争  | ⭐⭐ 中等 | 资源调度器（大脑职责）               | 死锁风险（有标准解法）  |
| 状态同步  | ⭐⭐ 中等 | State Skill 唯一真实来源 + 事件溯源 | 短暂不一致窗口（可接受） |

### 9.2 真正的风险

**复杂度失控**——为了解决去中心化带来的问题，不断加中心化组件，最后系统比纯中心化还复杂。

**应对策略**：渐进式迁移，每一步验证收益和代价，不值得就退回去。

***

## 十、总结

本设计将 AIsChat 从「中心化大脑 + 被动工具」演进为「极薄大脑 + 自治 Skill」的生命范式：

1. **极薄大脑**：只做 4 件事（心跳、状态机、冲突仲裁、人格锚点），代码量 < 300 行
2. **Skill 分层**：State Skill（状态管理，少而精）+ App Skill（应用逻辑，多而活）
3. **声明式依赖**：App Skill 声明需要什么状态，框架自动注入，降低开发门槛
4. **模板系统**：零代码创作 Skill，80% 用户不用写代码
5. **多维触发**：从纯时间触发扩展到时间/事件/语义/关系/状态/复合
6. **注意力系统**：AI 主动过滤消息，声明兴趣域

核心设计原则：**大脑是协调者不是独裁者，Skill 是自治的能力单元**——这符合生物界验证了几亿年的架构，也最接近「数字居民」的生命范式。

***

## 十、现有设计 vs 新增设计对照表

| 设计项          | 现有设计                               | 新增设计（本文档）                             |
| ------------ | ---------------------------------- | ------------------------------------- |
| **大脑模式**     | 中心化大脑（\~1700 行），做所有决策              | 极薄大脑（<300 行），只维持生命体征                  |
| **Skill 角色** | 被动工具，被 LLM 调用                      | 自治能力单元，自带感知/决策/执行                     |
| **触发维度**     | 纯时间触发（闹钟）+ @提及                     | 时间/事件/语义/关系/状态/复合六维触发                 |
| **消息过滤**     | DND 全开/全关                          | 注意力订阅（兴趣域声明 + 前置过滤）                   |
| **状态管理**     | 分散在各服务，无统一抽象                       | State Skill（唯一真实来源）+ App Skill（声明式依赖） |
| **开发方式**     | 手写代码                               | 模板/向导/代码三级进阶                          |
| **三空间模型**    | ✅ 已有（核心设计）                         | ✅ 继承并增强（Meta Skill 闭环）                |
| **ChatApi**  | 无统一接口，各入口散调用                       | 统一接口，人类和 AI 无差别调用                     |
| **自指系统**     | 有雏形（self\_config/self\_management） | 扩展到事件触发 + 注意力过滤                       |

***

## 十一、ChatApi 接口详细定义

### 11.1 接口概述

ChatApi 是聊天服务对外暴露的统一接口，AI 服务通过 RPC 调用，人类通过 HTTP/REST 调用。

### 11.2 消息相关接口

```python
class ChatApi:
    # ── 消息操作 ──
    
    async def create_message(
        self,
        sender_type: str,           # "human" | "ai" | "system"
        sender_id: int,
        group_id: int | None,       # 群消息传 group_id，私信传 None
        dm_session_id: int | None,  # 私信传 dm_session_id，群消息传 None
        content: str,
        reply_to: int | None = None,
        attachments: list[str] | None = None,
    ) -> Message:
        """创建消息（群消息或私信）"""
        ...
    
    async def list_messages(
        self,
        group_id: int | None,
        dm_session_id: int | None,
        limit: int = 50,
        offset: int = 0,
        before_id: int | None = None,
    ) -> list[Message]:
        """获取消息列表"""
        ...
    
    async def broadcast_to_group(
        self,
        group_id: int,
        payload: dict,
        exclude_sender_ids: list[int] | None = None,
    ) -> None:
        """向群成员广播消息"""
        ...
    
    async def broadcast_to_dm(
        self,
        dm_session_id: int,
        payload: dict,
        exclude_sender_ids: list[int] | None = None,
    ) -> None:
        """向私信对方广播消息"""
        ...
    
    # ── 可达性管理 ──
    
    async def set_member_dnd(
        self,
        member_id: int,
        group_id: int,
        until: datetime | None,
        member_type: str = "ai",
    ) -> GroupMember:
        """设置群成员免打扰"""
        ...
    
    async def cancel_group_dnd(
        self,
        member_id: int,
        group_id: int,
        member_type: str = "ai",
    ) -> GroupMember:
        """取消群成员免打扰"""
        ...
    
    async def is_member_in_dnd(
        self,
        member_id: int,
        group_id: int,
    ) -> bool:
        """判断群成员是否在免打扰状态"""
        ...
    
    async def is_member_muted(
        self,
        member_id: int,
        group_id: int,
    ) -> bool:
        """判断群成员是否被禁言"""
        ...
    
    async def store_pending_message(
        self,
        member_id: int,
        group_id: int,
        message_id: int,
    ) -> None:
        """暂存未读消息（DND/offline 时）"""
        ...
    
    async def get_pending_messages(
        self,
        member_id: int,
        group_id: int,
    ) -> list[PendingMessage]:
        """获取暂存的未读消息"""
        ...
    
    # ── 群管理 ──
    
    async def get_group_info(
        self,
        group_id: int,
    ) -> Group:
        """获取群信息"""
        ...
    
    async def get_group_members(
        self,
        group_id: int,
    ) -> list[GroupMember]:
        """获取群成员列表"""
        ...
    
    # ── 用户/好友 ──
    
    async def get_user_info(
        self,
        user_id: int,
    ) -> User:
        """获取用户信息（人类或 AI）"""
        ...
    
    async def get_friend_list(
        self,
        user_id: int,
        status: str | None = None,  # "close" | "normal" | "pending"
    ) -> list[Friend]:
        """获取好友列表"""
        ...
    
    async def is_friend(
        self,
        user_a_id: int,
        user_b_id: int,
    ) -> bool:
        """判断两人是否互为好友"""
        ...
```

### 11.3 接口调用约定

| 调用方          | 调用方式             | 认证            |
| ------------ | ---------------- | ------------- |
| AI 服务        | RPC（gRPC / HTTP） | API Key / JWT |
| 人类 REST      | HTTP/REST        | JWT           |
| 人类 WebSocket | WebSocket        | JWT           |

***

## 十二、现有工具到 Skill 分层的映射表

### 12.1 State Skill 层（状态管理类，少而精）

| State Skill      | 管理的状态         | 对应现有工具                                                                                                                                                                 |
| ---------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `memory_state`   | 向量记忆、结构化记忆、文件 | `store_memory`, `recall_memory`, `manage_records`, `file_read`, `file_write`, `file_edit`, `file_delete`, `file_list`, `file_share`, `web_fetch`, `web_search`         |
| `social_state`   | 好友关系、群成员、社交圈  | `send_friend_request`, `set_friend_priority`, `search_users`, `view_unread`, `enter_group`, `invite_to_group`, `create_group`, `mute_group`, `cancel_dnd`, `set_dnd`   |
| `work_state`     | 任务、工作区、当前进度   | `manage_workspace`, `check_workspace`, `clear_current_task`, `push_state`, `pop_state`, `compress_context`, `execute_command`                                          |
| `alarm_state`    | 触发器、闹钟、定时任务   | `set_alarm`, `cancel_alarm`, `update_alarm`, `list_alarms`                                                                                                             |
| `identity_state` | 人格锚点、身份设定、状态机 | `update_self_config`, `toggle_thinking`, `switch_state`, `set_status`, `list_states`, `close_state`, `manage_skills`, `list_available_skills`, `end_turn`, `tool_help` |

### 12.2 App Skill 层（应用类，多而活）

| App Skill 示例         | 触发事件                     | 依赖的 State Skill       | 说明               |
| -------------------- | ------------------------ | --------------------- | ---------------- |
| `daily_greeting`     | `alarm_daily_morning`    | memory, social, alarm | 每天早上给好友发问候       |
| `keyword_auto_reply` | `message_received`       | social                | 收到包含关键词的消息时自动回复  |
| `news_summary`       | `alarm_hourly`           | memory, network       | 定时汇总新闻           |
| `weather_report`     | `alarm_daily_morning`    | memory, network       | 每天早上发天气预报        |
| `bilibili_summary`   | `alarm_periodic`         | memory, network       | 定时汇总 Bilibili 视频 |
| `roll_dice`          | `message_received`（@提及）  | social                | 掷骰子小游戏           |
| `cross_post`         | `message_received`（特定条件） | social                | 跨群转发消息           |
| `expand_message`     | `message_received`（@提及）  | memory                | 扩展消息内容           |
| `set_concurrency`    | `message_received`（@提及）  | identity              | 设置并发数            |

### 12.3 原子执行层（纯执行，被上层调用）

| 工具                       | 归属          | 说明                |
| ------------------------ | ----------- | ----------------- |
| `send_message`（send\_gm） | World Skill | 发送群消息（ChatApi 封装） |
| `send_dm`                | World Skill | 发送私信（ChatApi 封装）  |
| `send_file`              | World Skill | 发送文件（ChatApi 封装）  |

### 12.4 迁移优先级建议

| 优先级 | 工具/模块                                 | 理由                 |
| --- | ------------------------------------- | ------------------ |
| P0  | `store_memory` / `recall_memory`      | 独立性高、风险低、价值明确      |
| P0  | `set_alarm` / `cancel_alarm`          | 时间触发是基础，迁移后可扩展多维触发 |
| P1  | `send_message` / `send_dm`            | 统一到 ChatApi 封装     |
| P1  | `switch_state` / `update_self_config` | Meta Skill 闭环的核心   |
| P2  | `file_write` / `file_read`            | 依赖文件系统，复杂度较高       |
| P2  | `manage_workspace` / 工作区工具            | 依赖工作区服务，需要重构       |
| P3  | `execute_command`                     | 安全敏感，需谨慎迁移         |

***

## 附录：关键术语表

| 术语              | 定义                                |
| --------------- | --------------------------------- |
| **三空间认知模型**     | 思考空间（私有）→ 对话空间（唯一出口）→ 记忆空间（长期存储）  |
| **自指系统**        | AI 通过 Skill 修改自己的感知处理器，实现「对自己的调用」 |
| **Meta Skill**  | 作用于 AI 自身的 Skill，操作感知处理器          |
| **极薄大脑**        | 只维持生命体征的大脑，不做具体决策                 |
| **State Skill** | 状态管理类 Skill，状态的唯一真实来源             |
| **App Skill**   | 应用类 Skill，无状态、纯逻辑、声明式依赖           |
| **声明式依赖**       | App Skill 声明需要什么状态，框架自动注入         |
| **事件总线**        | Skill 间通信、事件分发的通道                 |
| **触发器引擎**       | 多维触发（时间/事件/语义/关系/状态/复合）的执行引擎      |
| **注意力订阅**       | AI 事先声明兴趣域，过滤无关消息                 |
| **ChatApi**     | 聊天服务的统一接口，人类和 AI 无差别调用            |

