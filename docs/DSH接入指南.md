# AIsChat 接入 DeepSeek Harness（DSH）指南

> 面向：想用 DSH 直接操作 AIsChat 的开发者/用户
> 适用范围：dsh-aischat 插件（v0.3.10+），AIsChat 作为插件嵌入 DSH Web

---

## 1. 这是什么

**dsh-aischat** 把 AIsChat 以「一等公民」嵌入 DeepSeek Harness Web。接入后你可以：

| 能力 | 说明 |
|---|---|
| 💬 **聊天嵌入** | DSH 侧边栏点 AIsChat 直接聊（置顶私信 / 群聊 / 功能页），不必切换系统 |
| 🖼️ **沉浸式界面** | 群聊"沉浸式"按钮、AIC 功能页（群视界/好友/我的AI/管理/设置）以 iframe 全屏打开 |
| 🗂️ **世界工作区** | 每个 AIsChat 世界 = DSH 工作区一个文件夹 `AIC群视界-世界名`，**用 DSH 原生的 agent 和工具直接操作世界**（改代码、跑逻辑、读写群聊） |

核心设计一句话：**对话/工具/沙箱用 DSH 的，操作对象是 AIsChat 的（世界文件、数据、群聊）**。

---

## 2. 架构总览

插件是**双面 Cordis 插件**，同一 npm 包分 Host / Client 两半：

```
┌─ DSH Web 进程（Host 半边）──────────────────────────────────────┐
│  /aischat-api/*   HTTP 代理 → AIsChat 后端（默认 127.0.0.1:5228）│
│  /aischat-ws       WebSocket 升级代理 → 后端 /ws                  │
│  /aischat-ui/*     前端静态托管（SPA 回退 + 防穿越）               │
│  /aischat-worlds/* 世界工作区：dir / token / status / pull 端点   │
│  world_* 工具（11 个） 按会话所在世界目录自动路由                 │
│  systemPrompt 段    世界会话提示词（泛化引导）                    │
└──────────────────────────────────────────────────────────────────┘
        ▲ 同源（浏览器永不接触后端地址）
┌─ 浏览器（Client 半边）───────────────────────────────────────────┐
│  侧边栏 AIsChat 入口 → 全屏 board（rail + 对话列 + composer）      │
│  沉浸式覆盖层（iframe /aischat-ui/...）                           │
│  世界同步：登录/打开面板时建文件夹+会话+上报 token+温和拉取         │
└──────────────────────────────────────────────────────────────────┘
```

**安全边界**：所有流量同源（`/aischat-api` 等前缀由 DSH Web 服务），浏览器不持有后端地址；`backendUrl` 仅限本机回环，来自插件配置而非客户端输入。

---

## 3. 安装与部署

### 3.1 前置

- DSH Web 已运行（`dsh web`，如 `127.0.0.1:3080`）
- AIsChat 后端在**同一台机器**运行（默认 `127.0.0.1:5228`），其前端已按 `/aischat-ui/` base 构建

### 3.2 构建插件

```bash
cd dsh-aischat
pnpm install        # 或复用 node_modules
node scripts/build.mjs   # 产出 lib/index.js（Host）+ lib/client.js（Client）
```

插件自包含 `dist/`（AIsChat 前端 `BASE_URL=/aischat-ui/` 构建产物），无需单独部署前端。

### 3.3 装入 DSH

```bash
dsh plugin --profile web add file:/path/to/dsh-aischat
systemctl restart dsh-web   # 或重启 dsh web 进程
```

### 3.4 配置（可选）

`cordis.patch.yml` / profile 覆盖：

```yaml
- insert:
    - id: dsh-aischat
      name: dsh-aischat
      config:
        backendUrl: http://127.0.0.1:5228   # 仅回环/内网
```

> 开发态改动同步：改 `src/*.ts` 后重跑 build，把 `lib/` 与 `dist/` 复制到
> profile 的 `node_modules/dsh-aischat/`，Host 改动需重启 dsh-web，Client 改动刷新页面即可。

---

## 4. 世界工作区（核心特性）

### 4.1 概念

每个 AIsChat 世界对应 DSH 工作区一个**真实目录**：

```
$DSH_HOME/aischat-worlds/AIC群视界-<世界名>/
├── .aischat-world.json   # 世界身份（worldId/name，工具据此路由）
├── .aischat-sync.json    # 同步快照（本地/远端 mtime）
├── index.html / main.py / blocks/ ...   # 世界文件「本地镜像」
```

**本地镜像 = 世界文件的本地副本**。agent 用 **DSH 原生的 read / write / edit / glob / grep / bash** 直接读写镜像（bash 可直接跑世界 Python 代码测试），改完 `world_push` 同步回 AIsChat 世界。

### 4.2 同步机制（GitHub 式）

`.aischat-sync.json` 记录每个文件「上次同步时的本地 mtime / 远端 mtime」，每次同步做**三路对比**：

| 分类 | 含义 | 处理 |
|---|---|---|
| `added` | 世界上新增 | 自动拉取 |
| `changedRemote` | 世界改了、本地未改 | 自动拉取 |
| `changedLocal` | 本地改了、世界未改 | 推送 |
| `conflict` | 两边都改 | **不自动**，交 AI/用户裁决 |
| `removed` | 世界上删除 | 删除本地（本地未改时） |

**自动拉取（温和）**：打开 AIsChat 时自动执行，**仅当「本地无未推送修改且世界有改动」**才拉取，返回 `+N 新增 ~N 修改 -N 删除` 报告。本地脏/冲突一律拒绝，**绝不覆盖 agent 正在工作的文件**（对话进行中文件不会被自动改动）。

**实现要点（正确性保障）**：

- **快照只记录"实际同步成功"的文件**：`.aischat-sync.json` 更新时只写入本次真正拉取/推送成功的文件，其余保留旧记录——未同步的本地修改、被跳过的冲突、远端新改动**绝不会被"洗白"成已同步**，下次对比仍能识别
- **`force:true` 语义**：拉取 = 完全以远端为准（覆盖冲突 + 本地修改），推送 = 完全以本地为准（覆盖冲突）；温和模式 = 任何一边有未同步改动都拒绝
- 快照文件自身、`__pycache__`、`.pyc` 等运行产物不计入对比（不误报"本地新增"）

**版本提示**：任何 `world_*` 工具执行后，若世界有更新未拉取 → 结果附 `updateHint`；有冲突 → 附 `conflictHint`——AI 看到就知道该 `world_pull` 或处理冲突。

### 4.3 典型工作流

```
① 打开 AIsChat（自动：建文件夹+会话+上报 token+温和拉取）
② 工作区点开 AIC群视界-世界名 会话
③ 对 DSH agent 说：
   "看看我的世界有什么文件"      → world_list_files
   "读一下 main.py"             → 原生 read
   "把 style.css 背景改深"      → 原生 write/edit
   "跑一下 main.py 测试"        → 原生 bash
   "同步到世界"                 → world_push
④ 世界在别处改过？"拉取最新"    → world_pull
```

### 4.4 冲突裁决

冲突文件（本地与世界都改了同一文件）**不盲目覆盖**：

- `world_push` / `world_pull` 默认**跳过冲突文件**并报告
- AI 读两边内容决定：保留本地（`world_push force:true`）/ 采用世界（`world_pull force:true`）/ 手动合并

---

## 5. 工具参考（Host 注册，按会话所在世界目录自动路由）

| 工具 | 作用 | 鉴权 |
|---|---|---|
| `world_list_files` | 列世界文件树 | owner token |
| `world_read_file` | 读世界文件内容 | 免鉴权 |
| `world_write_file` | 写世界文件（覆盖/建目录） | owner token |
| `world_delete_file` | 删世界文件 | owner token |
| `world_api` | 调世界受控 API（world/chat/memories/usage/groups/group-messages/state/data） | 世界沙箱 `api_token` |
| `world_chat` | 读写世界绑定群聊消息（以世界身份发送） | 沙箱 token |
| `world_lifecycle` | 唤醒/休眠世界 | owner token |
| `world_push` | 镜像改动 → 世界（快照对比 + 冲突保护 + force） | owner token |
| `world_pull` | 世界 → 镜像（快照对比 + 冲突保护 + force） | owner token（列树） |
| `world_run` | 后端沙箱跑 Python（24MB/10s 配额） | owner token |
| `world_trigger` | 触发世界入口 `handle(event)` | owner token |

> 大部分文件/API 操作也可直接用 DSH 原生工具（read/write/edit/bash）完成，`world_*` 是精确操作与同步用。

---

## 6. 沉浸式界面与功能导航

- **群聊头部「沉浸式」按钮**：自动查 `/worlds/by-entity` 绑定世界 → 打开 `/aischat-ui/world-view/{id}?embed=1`
- **AIC 侧边栏「功能」分组**：群视界 / 好友 / 我的AI / 管理 / 设置，点击在覆盖层打开对应前端页面
- **嵌入模式**（`?embed=1`）：前端隐藏自身侧边栏，API 基址走 `/aischat-api`；401 通知宿主；`?token=` 注入复用登录态；router basename `/aischat-ui`
- **世界页内嵌群聊**：后端注入 `window.WORLD_API` / `WORLD_UI`（DSH 嵌入 = `/aischat-api` / `/aischat-ui`，独立部署默认不变），世界代码的群聊面板/平台菜单/SSE 正确走代理

---

## 7. 安全与隐私

- **零公网地址**：插件代码、UI、代理目标全部 loopback；`backendUrl` 来自配置不接受客户端输入
- **token 仅内存**：client 登录后把 token 按 worldId 上报 host（`worldTokenMap`），供 owner 鉴权写操作；**不落盘、不打日志**；dsh-web 重启后需重新打开 AIsChat 同步
- **同源代理**：无 CORS 面；剥离 hop-by-hop 头防请求走私；错误响应固定文案不回显内部
- **世界沙箱 token**（`api_token`）：仅内部调用用，绝不回传给模型

---

## 8. 排障

| 现象 | 处理 |
|---|---|
| 世界工具报"未连接登录态" | 打开一次 AIsChat（触发 token 上报）；查 `GET /aischat-worlds/status` 看 `tokenWorlds` 是否含该世界 |
| 工作区没有世界文件夹 | 确认登录 AIsChat；只同步**自己创建**的世界（`/worlds` 只返回 owner） |
| `world_push` 跳过冲突 | 冲突裁决：读两边内容，`force:true` 或手动合并 |
| 世界页打不开/显示宿主界面 | 世界无 index.html（提示"让群视界机器人生成"）；或路径未走 `/aischat-api` |
| token 丢了（重启后） | 重新打开 AIsChat 面板触发同步 |
| 工具报"不属于任何 AIsChat 世界" | 会话 cwd 需在 `aischat-worlds` 目录下（打开 AIC群视界-* 会话） |

---

## 9. 与 AIsChat 独立部署的关系

AIsChat 本体（docker-compose / 源码）保持独立可部署；插件是**加装层**，不改动 AIsChat 部署方式。后端世界文件仍在后端容器/数据目录，DSH 侧只是镜像 + 同步。

---

*相关：`docs/dev/TODO.md`（开发待办）、CHANGELOG v0.3.10（特性记录）、`dsh-aischat/README.md`（插件包内说明）*
