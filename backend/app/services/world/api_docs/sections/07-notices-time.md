# 07 懒通知与世界时间
> 用户手动改代码的通知机制（对话时取通知）、世界时间流速与运行模式（懒加载/后台任务）。

## 1. 懒通知机制（为什么存在）

**用途**：用户在界面上手动改了世界代码 → 系统记录改动 → 群视界机器人下次与用户对话时收到这些改动，**不会信息断层**。

**流程**：
1. 用户/前端保存文件时，系统自动记录懒通知（**你无需轮询**，也无需手动写）。
2. 你与用户开始对话时，调用接口**取出并清空**通知。

### 1.1 取出通知（对话开始时必做）

```
GET /worlds/{world_id}/notices
→ { "notices": [
    { "file": "index.html", "location": "L10-20", "summary": "用户手动编辑了 index.html", "at": "2026-08-04T01:00:00" } ] }
```

- 群视界机器人是**默认收件人**，不需要传 `agent_id`。
- **取出后通知即清空**（不重复投递）；最多保留最近 50 条。

### 1.2 行为约定

- **对话开始时先取通知**；若通知非空，在回复中体现"我看到你改了 xxx"，并询问/确认意图。
- 这是你和用户之间的"同步点"，漏掉会导致你基于旧代码工作。

### 1.3 写入通知（一般由前端调用，你也可用）

```
POST /worlds/{world_id}/notices
{ "agent_id": 5, "file": "index.html", "location": "L10-20", "summary": "…" }
```

- `agent_id` 省略 = 发给群视界机器人（默认收件人）；指定 = 发给世界内其他居民 AI。

## 2. 世界时间

- 服务端提供**默认懒计算**：世界休眠时时间不流动；唤醒时按 `world_time = 上次活跃 + 真实时间差 × time_flow_rate` 补偿。
- 读取当前世界时间：`GET /worlds/{world_id}` 返回 `world_time` 字段。
- `time_flow_rate`：时间流速（0.1~100），可在创建/更新世界时设置。
- **世界代码可接管时间系统**：世界可在自己的页面/后端里自定义时间规则（季节、昼夜、流速变化等），服务端字段作为兜底。

## 3. 运行模式

### 3.1 手动唤醒（当前默认）

- **世界状态只由手动控制**：`POST /worlds/{world_id}/wake`（唤醒）、`POST /worlds/{world_id}/sleep`（休眠）。
- 手动唤醒后**保持活跃**，不会自动转回休眠（自动休眠/唤醒调度已停用，2026-08-05）。
- 唤醒时自动离线时间补偿（world_time = 上次活跃 + 真实时间差 × 流速）。
- 与群视界机器人对话也会唤醒（对话是活跃信号）。

### 3.2 群消息钩子（世界程序感知）

绑定群的**群消息 → 异步喂给世界入口 `handle(event)`**（世界程序感知；处理不处理由世界程序自己决定）：

```json
{
  "type": "group_message",
  "group_id": 5,
  "source": "group",
  "messages": [
    {"message_id": 1, "sender_id": 2, "sender_name": "张三",
     "sender_type": "human", "content": "hi", "created_at": "2026-08-05T12:00:00"}
  ]
}
```

- **节流合并**：同世界 2 秒窗口内的消息合并成一条 event（`worlds.config.group_trigger_interval` 可配，0 = 每条触发）。
- **防死循环**：世界程序自己发的消息（经受控 API/AI 工具）不会触发自己。
- 世界入口不存在或 handle 缺省时静默跳过，不影响群聊。

### 3.3 后台任务（可选，阶段 2 实现）

- 世界可挂后台常驻任务，由管理员设置占用上限（CPU、内存，**默认 48MB/世界**；解释器硬下限 32MB）。
- 适合需要持续演化的世界（时间流动、NPC 自主活动）。

**选择建议**：大多数世界用懒加载；确实需要"不被打扰也自己在演化"的世界才用后台任务。

## 4. 世界管理接口速览（管理员/开发者用）

```
POST   /worlds                     # 创建世界 { name, description, time_flow_rate, config }
GET    /worlds                     # 我的世界列表
GET    /worlds/{id}                # 详情（含 bindings 入口、creator 群视界机器人、world_time）
PUT    /worlds/{id}                # 更新 { name?, description?, time_flow_rate?, config? }
DELETE /worlds/{id}                # 删除
POST   /worlds/{id}/bind           # 绑定入口 { entity_type: group|dm|user, entity_id }
POST   /worlds/{id}/unbind         # 解绑
```

- 世界是**独立实体**，群聊只是入口：模式 A 世界 ⊃ 群聊（多群绑同一世界）；模式 B 世界 ⊂ 群聊（单个群承载世界）。