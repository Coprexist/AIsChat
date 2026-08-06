# 文件式 skill/tool 机制（world skill runtime）

> 2026-08-06 落地。珑哥确认方向：世界能力走"skill/tools 放文件夹让实例识别"，
> **不平台硬编码**。world_command 将是该机制的第一个真实 skill。

## 一、两个作用域（造物主 ≠ 居民）

世界设计 AI（群视界机器人）是**设计世界的造物主**，在世界**之外**；
世界内的居民/管理者/物品是世界的**内容**。两者能力分开放：

| 作用域 | 位置 | 谁可用 | 例子 |
|---|---|---|---|
| 设计侧（造物主工具） | `data/world_ai_skills/<name>/` | 所有世界的设计 AI（全局共享库） | `world_stats` |
| 世界侧（居民能力） | `data/worlds/{id}/skills/<name>/` | 该世界的 AI / 居民 / 群 AI | `world_command`（下一步） |

同一套运行时，区别只在 ctx 能力集。

## 二、skill 目录约定

每个 skill 一个目录，含两个文件：

```
data/world_ai_skills/world_stats/
├── manifest.json    # 声明：名字/描述/参数 schema/所需能力清单
└── code.py          # 逻辑：async def run(args, ctx) -> dict
```

### manifest.json

```json
{
  "name": "world_stats",
  "description": "统计世界文件夹的文件数量与总大小。",
  "arguments": { "type": "object", "properties": {} },
  "permissions": ["file:list"]
}
```

### code.py

```python
async def run(args: dict, ctx) -> dict:
    files = ctx.file.list()          # 只能通过 ctx 做事
    return {"success": True, "file_count": len(files)}
```

## 三、ctx 能力注入（capability-based）

ctx 只包含 `manifest.permissions` **声明过**的能力——没声明的根本不注入
（代码里 `ctx.file` 会直接报错，不存在"越权调用"）。

| 权限 | ctx 能力 | 说明 |
|---|---|---|
| `file:list` / `file:read` / `file:write` / `file:delete` | `ctx.file.*` | 只限本世界文件夹（隔离目录+扩展名白名单，复用 world_file_service） |
| `data:read` / `data:write` | `ctx.data.*` | **世界数据（world_data 表）**：`await ctx.data.get(key)` / `set(key, value)` / `delete(key)`——结构化/操作数据只经 API/skill 读写 |
| `world:read` / `world:update` | `ctx.world.*` | 世界信息读取/更新（以世界主人身份） |
| `group:send` | `ctx.group.send()` | 发消息到绑定群（以世界创建者身份） |
| （无） | `ctx.log()` | 平台日志（无需声明） |

## 三·五、代码/数据分离（世界发布打包）

世界文件夹约定（2026-08-06 珑哥定）：

```
data/worlds/{id}/
├── index.html / skills/ / main.py ...   ← 代码区（发布世界时打包）
└── content/                             ← 内容产物区（静态文字类，自由层级）
```

- **content/ 不属于代码**：世界创作者在自己世界的 content/ 里自由建层级（设定文本/文档/素材文字）
- **发布世界不打包 content/**；下载数据**可选是否包含**（export `?include_content=false` 只打包代码，默认 true 包含）
- **结构化数据不进 content/**：一律走 world_data 表（API/skill ctx.data 读写）
- 现有世界（星野镇）暂不迁移，新约定对新世界生效

## 四、安全模型（v1 进程内 harness）

信任边界：**世界创作者（或其 AI）编写的代码**——防"AI 生成代码越权乱来"，
不防对抗性恶意代码。恶意场景需后置 subprocess/seccomp 沙箱（2.1 生产加固）。

- **import 白名单**：ast 扫描 code.py 的 import，仅标准库安全子集
  （`os/sys/subprocess/socket/pathlib/shutil/importlib/ctypes/sqlite3/http/...` 全拒）
- **builtins 收紧**：禁 `open/eval/exec/compile/input/breakpoint/__import__` 等
- **ctx 唯一出口**：代码无任何宿主对象/模块引用
- **超时强杀**：单次执行 30s（`asyncio.wait_for`），超时返回错误

⚠️ 已知边界：Python 内省逃逸（`().__class__.__bases__[0].__subclasses__()`）理论上
可绕过 builtins 限制——v1 接受该风险（AI 生成代码不会主动逃逸），
对抗性安全留给沙箱层。

## 五、接入点

- `world_chat_service.py`：`tools_for_world = [*WORLD_TOOLS, *build_skill_tools(world_id)]`
  → LLM function calling 定义动态合并（首轮 + 工具循环都带）
- `world_tools.py` `_do_execute`：未知平台工具 → `execute_skill()` 分发（找不到返回 None 走兜底）

## 六、路线图

1. ✅ 运行时骨架 + 两个作用域 + 安全加载 + ctx 注入 + 示例 `world_stats`
2. ⏳ 用户移动命令（`我去 2,3` → 世界程序解析 → 玩家传送）——语法先定
3. ⏳ `world_command`：世界侧第一个真实 skill——群 AI 发命令操作世界，
   命令统一交给世界程序解析（与用户共用语法，零重复逻辑）
4. ⏳ 群 AI 上下文注入：「本群绑定世界 X，可用世界颁布的能力行动」
5. ⏳ 沙箱加固（subprocess/rlimit/seccomp，对抗性安全）
