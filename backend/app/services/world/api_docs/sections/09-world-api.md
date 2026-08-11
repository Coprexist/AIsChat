# 09 受控数据 API（世界代码）

> 区介绍：沙箱/世界代码访问世界数据/对话状态/群聊的代理接口：WORLD_API_TOKEN 鉴权、端点、动态配额。

## 1. 这是什么

世界代码（`main.py` 的 `handle()` 或沙箱里跑的脚本）不能直连数据库，也不能碰后端密钥。
平台给每个世界一个**专属 API token**，世界代码用它经代理读写**自己世界**的数据：

- 世界信息（名字/描述/状态/世界时间/绑定入口）
- 对话历史（与群视界机器人的世界级会话）
- 记忆（读/写，与 AI 的 store_memory/recall_memory 同一份数据）
- LLM 用量（调用次数/token/缓存命中率）
- 群聊（读消息/发消息/成员/管理——仅限**本世界绑定**的群）

token 只对本世界数据有效——拿不到别的世界、碰不到用户表、没有 JWT。

## 2. 鉴权（沙箱自动注入，零配置）

沙箱启动时自动注入环境变量，**世界代码直接读，不用自己生成**：

| 变量 | 说明 |
|------|------|
| `WORLD_ID` | 世界编号 |
| `WORLD_API_TOKEN` | 本世界的受控 API token（保密，别打印/外发） |
| `WORLD_API_BASE` | 受控 API 基地址，如 `http://127.0.0.1:8000/world/3/api` |

请求时带 `Authorization: Bearer <WORLD_API_TOKEN>`（或 `X-World-Token` 头）。

## 3. 端点

### 数据（2.3）

| 方法 | 路径（相对 WORLD_API_BASE） | 说明 |
|------|------------------------------|------|
| GET | `/world` | 世界信息（含绑定入口、配额） |
| GET | `/chat?limit=30&before_id=` | 对话历史（limit ≤100；before_id 传最旧 id 翻更早） |
| GET | `/memories?query=关键词&top_k=5` | 记忆检索（向量语义 → 文本回退） |
| POST | `/memories` body `{title, content}` | 存记忆（title/content 必填非空） |
| GET | `/usage` | LLM 用量：total_calls / prompt / completion / cached / cache_hit_rate_pct |
| POST | `/state` body `任意 JSON` | **发布状态快照**（NPC 对话/移动/事件 → 页面实时收到；≤100KB；写限流） |

**世界数据库（world_data，2026-08-06）**——结构化/操作数据，key-value JSON，只经 API 读写：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/data/{key}` | 读世界数据（不存在 value=null） |
| PUT | `/data/{key}` body `{value: 任意JSON}` | 写世界数据（upsert，key ≤200 字符） |
| DELETE | `/data/{key}` | 删世界数据 |

建议 key 用命名空间组织（如 `player.lihua`、`poems`、`quest.1`）——数据形状由世界代码自由定义，平台只管存储。
静态文字类大文件（设定/文档）放世界文件夹 `content/` 子目录（自由层级，发布不打包）。

### 群聊（2.4，身份 = 世界自身，作用域 = 仅本世界绑定群）

| 方法 | 路径（相对 WORLD_API_BASE） | 说明 |
|------|------------------------------|------|
| GET | `/groups` | 绑定群列表 |
| GET | `/group/messages?group_id=&limit=` | 读群消息（group_id 缺省 = 绑定第一个群） |
| GET | `/group/members?group_id=` | 群成员列表 |
| POST | `/group/messages` body `{group_id?, content}` | 发群消息（≤2000 字） |
| POST | `/group/roles` body `{group_id?, member_type, member_id, role}` | 改角色 owner/admin/member（仅群主/管理员） |
| POST | `/group/kick` body `{group_id?, member_type, member_id}` | 移出成员（仅群主/管理员） |

## 4. Python 示例（标准库 urllib，零依赖）

> ⚠️ **中文参数必须 URL 编码**：query 等参数带中文时用 `urllib.parse.quote` 编码，
> 直接拼进 URL 会报 `UnicodeEncodeError`（urllib 只接受 ascii URL）。

```python
import json
import os
import urllib.parse
import urllib.request

BASE = os.environ["WORLD_API_BASE"]
TOKEN = os.environ["WORLD_API_TOKEN"]

def api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def handle(event):
    info = api("/world")
    chat = api("/chat?limit=10")
    api("/memories", "POST", {"title": "最近事件", "content": "用户来过了"})
    q = urllib.parse.quote("事件")
    memories = api(f"/memories?query={q}&top_k=3")
    groups = api("/groups")
    if groups["groups"]:
        api("/group/messages", "POST", {"content": "世界已更新"})
    return {"info": info["name"], "recent_chat": len(chat["messages"]),
            "memory_hits": len(memories["memories"]), "groups": len(groups["groups"])}
```

### 页面订阅（世界状态实时推送，零轮询）

游戏/页面用 **EventSource** 订阅世界事件流（公开端点，与静态资源同理）：

```js
// 页面侧：实时收到世界代码发布的状态（连接即发当前快照，断线自动重连）
var es = new EventSource('/world/' + window.WORLD_ID + '/events');
es.onmessage = function (e) {
  var state = JSON.parse(e.data);
  // 例：state.npc_say → NPC 弹出对话；state.npc_pos → NPC 移动
};
```

世界代码侧发布：

```python
def publish(state):
    req = urllib.request.Request(BASE + "/state", data=json.dumps(state).encode(),
        method="POST", headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)

# handle/on_tick 里：
publish({"npc_say": "你好呀", "pos": [3, 4]})
```

## 5. 配额（10 秒窗口，动态按活跃人数加成）

**实际配额 = 基础值 + 每人加成 × 活跃人数**（活跃 = 最近 10 分钟内在该世界对话/打开过设计页的不同用户数）。

| 配额 | 默认实际值 | 可配字段（worlds.config） |
|------|-----------|--------------------------|
| 读/总请求 | 120 次/10 秒 | `api_rate_limit`（基础，默认 120） |
| 每人加成（读） | +60 次/10 秒/人 | `api_rate_limit_per_user`（默认 60，0 = 不加成） |
| 写操作（发消息/管理） | 20 次/10 秒 | `api_group_msg_limit`（基础，默认 20） |
| 每人加成（写） | +10 次/10 秒/人 | `api_group_msg_limit_per_user`（默认 10，0 = 不加成） |

例：基础 120 + 3 人在线 × 60 = **300 次/10 秒**；写操作 20 + 3 × 10 = **50 次/10 秒**。
超限返回 429（`{"detail": "请求过于频繁（…：N 次/10 秒）"}`），稍等重试。

## 6. 安全约定

- **别外泄 token**：`WORLD_API_TOKEN` 只在本世界进程内用，不要打印、不要写进页面/聊天记录。
- **错误体**：统一 `{"detail": "..."}`；401 = token 缺失/无效，403 = 越权（非绑定群/无管理权限），404 = 世界不存在。
- **写操作身份**：发消息/管理以**世界自身**身份执行（与世界 AI 同身份，底层按群角色体系检查：管理操作仅群主/管理员）。
- **作用域**：群聊端点只能操作 `world_bindings` 里绑定的群，显式传未绑定群 id 会被拒（403）。

## 7. 与 AI 工具的区别

| 场景 | 用哪个 |
|------|--------|
| 世界代码（handle/沙箱脚本）读数据/发群消息 | 受控 API（本区） |
| 群视界 AI 在对话中操作 | AI 工具（file_* / store_memory 等，见 03/04/05 分区） |
| 群管理（改角色/踢人） | 两边都可，权限同源（群主/管理员） |

## 8. 运行环境（沙箱）

- **工作目录 = 世界文件夹本体**（`/app/data/worlds/{world_id}/`）——世界代码可直接读写世界文件夹里的文件（含 JSON 数据文件），相对路径即世界内路径
- **注入环境变量**：`WORLD_ID`、`WORLD_DIR`（世界目录）、`WORLD_API_TOKEN`、`WORLD_API_BASE`、`WORLD_TICK_INTERVAL`（常驻）
- **数据规范（代码/数据分离）**：
  - 结构化/操作数据 → 本区 `/data/{key}` 数据库（world_data 表）
  - 静态文字类（设定/文档）→ 世界文件夹 `content/` 子目录（自由层级；世界产物区，发布不打包，下载可选）
  - 代码（网页/脚本）→ 世界文件夹根目录或自有目录
- 页面读数据：经世界代码 `POST /state`（页面 SSE 实时收）或页面内嵌；页面不直连数据库
