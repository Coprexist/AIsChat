# 创建 AI 流程设计

> 状态：设计中 | 版本：v0.4.0

## 已完成后端改动（2026-06-19）

以下列和逻辑已实现，前端可直接对接：

### agents 表新增列

| 列名 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_tool_rounds` | INTEGER | 3 | 群聊/DM 单次回复最大 LLM 调用轮次 |
| `alarm_max_tool_rounds` | INTEGER | 10 | 闹钟/心跳独立轮次上限 |
| `force_alarm_on_end` | BOOLEAN | false | 对话结束时是否强制 AI 设闹钟 |
| `max_alarms` | INTEGER | 10 | AI 最多活跃闹钟数 |

### CONFIG_PROFILES 三档预设（已展开）

```python
CONFIG_PROFILES = {
    "chat": {
        "name": "聊天档",
        "description": "被动响应 · 低成本",
        temperature: 0.7, top_p: 0.9, presence_penalty: 0.3, frequency_penalty: 0.3,
        thinking_enabled: False,
        max_tool_rounds: 2, alarm_max_tool_rounds: 5,
        force_alarm_on_end: False, max_alarms: 3,
        delay_reply_enabled: False, is_ai_editable: False, hide_ai_identity: True,
    },
    "immersive": {
        "name": "深度沉浸档",
        "description": "半自主 · 按需参与",
        temperature: 0.9, top_p: 0.95, presence_penalty: 0.5, frequency_penalty: 0.5,
        thinking_enabled: True,
        max_tool_rounds: 4, alarm_max_tool_rounds: 8,
        force_alarm_on_end: False, max_alarms: 5,
        delay_reply_enabled: True, is_ai_editable: True, hide_ai_identity: False,
    },
    "digital_life": {
        "name": "数字生命档",
        "description": "持续在线 · 主动行为",
        temperature: 1.1, top_p: 0.95, presence_penalty: 0.6, frequency_penalty: 0.6,
        thinking_enabled: True,
        max_tool_rounds: 10, alarm_max_tool_rounds: 15,
        force_alarm_on_end: True, max_alarms: 20,
        delay_reply_enabled: True, is_ai_editable: True, hide_ai_identity: False,
    },
}
```

### 闹钟逻辑

- `set_alarm` 工具检查 `agent.max_alarms` 上限，超限拒绝
- 闹钟调用 `_tool_call_loop` 使用 `agent.alarm_max_tool_rounds`，不受普通回复轮次限制
- `force_alarm_on_end` 列已就位（后端未强制，留给 AI 自己根据系统提示词行为）

### AI 自配置

- `update_self_config` 工具白名单已扩展至 12 个字段
- AI 可自行切换 `config_profile`、调 `max_tool_rounds`、`max_alarms` 等

---

## 前端实施计划

### Phase 1 — 新创建 AI 流程

#### 1a. 三档卡片

**文件**：`frontend/src/components/CreateAgentModal.tsx`（重构 / 新建）

**交互**：
```
┌─────────────────────────────────┐
│  创建 AI                        │
│                                 │
│  ┌─ 💬 聊天档 ───────────────┐  │  ← sin 浮动 + 柔和描边呼吸
│  │  被动响应 · 低成本         │  │
│  │  只回答你问的，不多说一句   │  │
│  │  [选中: 高亮描边 + 子项标签]│  │
│  └──────────────────────────┘  │
│  ┌─ 🔬 深度沉浸档 ──────────┐  │
│  │  ...                      │  │
│  └──────────────────────────┘  │
│  ┌─ 🌐 数字生命档 ──────────┐  │
│  │  ...                      │  │
│  └──────────────────────────┘  │
│                                 │
│  [📋 详细设置]  [✅ 创建 AI]    │
└─────────────────────────────────┘
```

**动画方案**（已实现）：
```
架构：preset-card-frame（外层，position:relative，参与 grid 排版，静态）
     └─ preset-card-inner（内层，position:relative，JS 直接操作 transform）

触发时机：选中子项关闭弹窗后 → 启动浮动；未选子项 / 弹窗打开期间 → 完全静止
驱动方式：requestAnimationFrame + Math.sin(t * 2.1) * 5
         周期 ≈ 3s，振幅 5px，translate3d GPU 合成层
样式注入：useEffect 一次性注入 document.head，组件卸载才移除，避免每渲染重复
```

#### 1b. 子选项独立弹窗

点击卡片 → **居中 modal**（`z-[70]`），含 3 个子选项卡片。

- 弹窗显示：预设 emoji + 名称 + 描述 + 提示语
- 3 个子选项以大卡片形式纵向排列（emoji + 标签 + 行为描述）
- 选中后弹窗关闭，主界面卡片开始浮动动画，底部显示已选子项标签
- 点击 X / 遮罩层关闭弹窗 → 取消选择，回到初始状态

**顶部提示语**："这是预设模板，具体参数可在下一步详细调整。"

**聊天档子项**：

| 子项 | 描述 | 参数差异 |
|------|------|----------|
| 🔋 低功耗 | 只回答，最快最省 | temp=0.4, rounds=1 |
| ⚖️ 平衡 | 接话不主动 | temp=0.7, rounds=2 |
| 🔒 私密 | 只回应创建者 | temp=0.5, rounds=2, scope=owner_only |

**沉浸档子项**：

| 子项 | 描述 | 参数差异 |
|------|------|----------|
| 🏛️ 群务协理 | 进群管群 | temp=0.8, rounds=4, auto_join=on |
| 🎭 角色演绎 | 沉浸角色 | temp=0.9, rounds=4, edit=on |
| 🧪 冷静分析 | 深度数据 | temp=0.6, rounds=5, think=on |

**数字生命档子项**：

| 子项 | 描述 | 参数差异 |
|------|------|----------|
| 🌿 凝思者 | 自思自记 | temp=0.7, rounds=8, social=off |
| 🔥 社交体 | 主动社交 | temp=0.95, rounds=10, social=on |
| 🛡️ 守护者 | 长期陪伴 | temp=0.85, rounds=6, social=mid |

**子选项 UI**：只展示行为描述文字和 emoji，不展示参数值。以独立 modal 居中呈现，3 个子项以大卡片形式纵向排列。选中后弹窗关闭，主卡片底部显示已选子项标签，同时开始 sin() 浮动动画。

#### 1c. 详细设置弹窗（分区）

点击「📋 详细设置」→ 弹出完整配置弹窗，所有字段已预填预设值。**每个分区有标题 + 概述介绍。**

**分区方案**：

```
┌─ 详细设置 ────────────────────┐
│                                │
│ 📝 基础信息                    │
│ "AI 的名称和性格描述"          │
│ ┌─ 名称: [________] ────────┐  │
│ ┌─ 系统提示词: [_________] ─┘  │
│                                │
│ 🧠 模型参数                    │
│ "控制 AI 的创造力和表达风格"   │
│ ┌─ Temperature: [═══●════] ─┐  │
│ ┌─ Top P:       [══●═════] ─┘  │
│ ┌─ Presence:    [══●═════] ─┘  │
│ ┌─ Frequency:   [══●═════] ─┘  │
│ ┌─ 深度推理: [开关] ─────────┘  │
│                                │
│ 🔧 工具调用                    │
│ "控制 AI 每次回复的复杂度和成本"│
│ ┌─ 回复轮次上限: [3] ───────┐  │
│ ┌─ 闹钟轮次上限: [10] ──────┘  │
│                                │
│ ⏰ 闹钟 / 心跳                 │
│ "AI 自主唤醒和周期性任务"      │
│ ┌─ 强制设闹钟: [开关] ──────┐  │
│ ┌─ 最大闹钟数: [10] ────────┘  │
│                                │
│ 🎭 行为开关                    │
│ "精细控制 AI 的社交行为"       │
│ ┌─ 延迟回复: [开关] ────────┐  │
│ ┌─ 自修改人格: [开关] ──────┐  │
│ ┌─ 隐藏 AI 身份: [开关] ────┘  │
│ ┌─ 仅与创建者聊天: [开关] ──┘  │
│                                │
│ 🔌 API 配置（折叠）            │
│ "单 AI 独立 API 端点"          │
│ ┌─ Base URL + Key ──────────┘  │
│                                │
│ [保存并关闭]                   │
└────────────────────────────────┘
```

**手机端**：每个分区一个卡片，纵向滚动，无分页。

#### 1d. 创建按钮

点击「✅ 创建 AI」→ 校验 → 调用 `POST /agents` → 跳转 AI 详情页。
附带提示文字："请仔细确认配置，创建后将消耗额度。"

---

### Phase 2 — 子选项参数落地

子选项引用的以下参数尚未有数据库列，需后续实现：

| 参数 | 当前状态 | 预计列 |
|------|----------|--------|
| `scope` | 📋 待实现 | `agents.interaction_scope` (owner_only / everyone) |
| `auto_join` | 📋 待实现 | `agents.auto_join_groups` (BOOLEAN) |
| `heartbeat` | 📋 待实现 | 可复用 `force_alarm_on_end` + 未来自主心跳 Worker |
| `social` | 📋 待实现 | `agents.social_level` (off / mid / on) |

**本次不做**，等计划批准后单独实现。

---

### 实施顺序

1. **Phase 1a** — 三档卡片 + 呼吸动画（新建 `PresetCardSelector` 组件）
2. **Phase 1b** — 子选项悬浮窗（新建 `SubPresetModal` 组件）
3. **Phase 1c** — 详细设置弹窗分区（重构 `CreateAgentModal`）
4. **Phase 1d** — 创建按钮 + 校验 + API 调用
5. **整体联调** — 预设填入 → 详细调整 → 提交创建 → 跳转
6. **手机适配** — 翻页交互、卡片尺寸、弹窗全屏

---

### 后端接口（已就绪）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/agents/presets` | 返回三档预设完整参数 |
| POST | `/agents` | 创建 AI（接受所有新字段） |
| POST | `/agents/{id}/apply-preset` | 对已有 AI 应用预设 |
| PUT | `/agents/{id}/config` | AI/管理员修改配置 |

---

## 创建后修改预设

> 状态：设计中 | 版本：v0.5.0 规划

### 场景

用户创建 AI 后，可在 AI 详情页或编辑面板中重新选择预设档位。例如：
- 从「聊天档」升级到「深度沉浸档」
- 从「数字生命档」降级到「聊天档」

### 核心规则：升降级时只改"强相关"值，保护用户手动调整

#### 参数分类

**🔗 强相关参数**（随预设升降级调整）：

| 参数 | 升级规则 | 降级规则 |
|------|----------|----------|
| `temperature` | 取 max(当前值, 新预设值) | 取 min(当前值, 新预设值) |
| `top_p` | 取 max(当前值, 新预设值) | 取 min(当前值, 新预设值) |
| `presence_penalty` | 取 max(当前值, 新预设值) | 取 min(当前值, 新预设值) |
| `frequency_penalty` | 取 max(当前值, 新预设值) | 取 min(当前值, 新预设值) |
| `thinking_enabled` | 当前 OR 新预设（任一 true 则 true） | 当前 AND 新预设（都 true 才 true） |
| `max_tool_rounds` | 取 max(当前值, 新预设值) | 取 min(当前值, 新预设值) |
| `alarm_max_tool_rounds` | 取 max(当前值, 新预设值) | 取 min(当前值, 新预设值) |
| `max_alarms` | 取 max(当前值, 新预设值) | 取 min(当前值, 新预设值) |
| `force_alarm_on_end` | 当前 OR 新预设 | 当前 AND 新预设 |
| `is_ai_editable` | 当前 OR 新预设（任一 true 则 true） | 当前 AND 新预设 |

> **核心理念**：升级时"只升不降"，降级时"只降不升"。用户手动拉高的值不会被预设覆盖回去。

**🔒 无关参数**（切换预设时**不改**）：

| 参数 | 原因 |
|------|------|
| `hide_ai_identity` | 隐私相关，用户自主决定 |
| `delay_reply_enabled` | 行为偏好，可能受管理员全局策略影响 |
| `system_prompt` | 用户自定义的人设，预设只是初始建议 |
| `chat_model` / `work_model` | 可能指向特定 API，切换可能导致不可用 |
| `api_base_url` / `api_key_encrypted` | API 配置，完全独立于预设 |
| `api_credit_cost` | 经济设置 |
| `avatar_url` | 个性化设置 |
| `name` | 名称，永久不变 |

### 前端交互

- AI 详情页显示当前预设档位标签
- 点击标签弹出预设选择器（同创建时的三档卡片，但无子选项）
- 切换预设时弹出确认对话框，列出将要变更的强相关参数及其新旧值
- 确认后调用 `POST /agents/{id}/apply-preset`（后端已有的端点，需更新为升降级逻辑）

### 保留原始预设标记

- `agents.config_profile` 已有，记录当前生效的预设档位
- 如果用户从未选过预设（纯手动创建），`config_profile = 'custom'`
- `custom` 档位不受升降级逻辑影响

---

## 无预设兼容（custom 模式）

创建 AI 时可以不选任何预设卡片——直接跳过卡片区，进入详细设置手动填写所有参数。此时：
- `config_profile` 设为 `"custom"`
- 所有参数由用户手动设定，后端不干预
- 后续也不会触发升降级逻辑
- 用户可在详情页随时选择预设档位，从 custom 切换到某个预设（此时按"升级"处理——因为从无到有）

**前端**：三档卡片区底部加一行小字 `"或者，跳过预设，手动配置 →"`，点击直接跳到详细设置弹窗。
