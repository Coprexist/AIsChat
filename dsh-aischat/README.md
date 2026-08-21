# dsh-aischat

AIsChat 原生集成插件：把 AIsChat 聊天（置顶 / 私信 / 群聊）、沉浸式界面与
**群视界世界工作区**以原生方式嵌入 DeepSeek Harness Web。

> 完整接入说明见仓库根目录 `docs/DSH接入指南.md`。

## 架构

双面插件：

- **Host 半**（`lib/index.js`）：在 DSH Web 服务上注册同源网关 + 世界工作区
  - `GET/POST /aischat-api/*` → 代理到本机 AIsChat 后端（默认 `http://127.0.0.1:5228`，可配置）
  - `/aischat-ws?token=...` → WebSocket 升级代理到后端 `/ws`
  - `/aischat-ui/*` → AIsChat 前端静态托管（SPA 回退 + 路径穿越防护）
  - `/aischat-worlds/*` → 世界工作区端点（dir 建目录 / token 上报 / status 诊断 / pull 拉取）
  - **11 个 `world_*` 工具**（文件/API/群聊/生命周期/同步/沙箱运行），按会话 cwd 自动路由到所属世界
  - systemPrompt 注册世界会话引导段（镜像模式：用 DSH 原生工具 + world_push 同步）
- **Client 半**（`lib/client.js`）：原生界面 + 世界同步
  - 侧边栏底部入口（`sidebar.footer.action`）+ 全屏 board（联系人 + 对话 + composer）
  - 沉浸式覆盖层（`shell.overlay`）：群聊"沉浸式"、AIC 功能页（群视界/好友/我的AI/管理/设置）
  - 世界同步：登录/打开面板时建 `AIC群视界-*` 工作区文件夹 + 会话 + 上报 token（按 worldId）+
    温和自动拉取（仅本地干净且世界有改动才拉，绝不覆盖本地修改）
  - 设置页（`settings.section`）：登录 / 退出 / 状态说明

登录 token 仅保存在浏览器 localStorage（client 侧 `aisc.token`）；host 内存 `worldTokenMap`
按 worldId 存一份供 owner 鉴权写操作（不落盘、不打日志）。

## 安装

```bash
# 1. 构建
pnpm install   # 或复用已有 node_modules（frontend 下）
node scripts/build.mjs   # 产出 lib/index.js + lib/client.js

# 2. 装入 DSH web profile
dsh plugin --profile web add file:/path/to/dsh-aischat

# 3. 重启 DSH web 进程使插件生效
```

开发态改动：改 `src/*.ts` → build → 复制 `lib/` 与 `dist/` 到 profile 的
`node_modules/dsh-aischat/`；Host 改动需重启 dsh-web，Client 改动刷新页面即可。

## 配置

插件配置（`cordis.patch.yml` 或 profile 覆盖）：

```yaml
- insert:
    - id: dsh-aischat
      name: dsh-aischat
      config:
        backendUrl: http://127.0.0.1:5228
```

`backendUrl` 仅限本机回环/内网地址，不参与公网。

## 世界工作区（GitHub 式双向同步）

每个 AIsChat 世界 = DSH 工作区文件夹 `AIC群视界-世界名`，目录即世界文件的
**本地镜像**（`$DSH_HOME/aischat-worlds/`）。agent 用 **DSH 原生工具**
（read/write/edit/bash）操作镜像，`world_push` 同步回世界，`world_pull` 拉最新。

- `.aischat-sync.json` 快照 + 三路对比（added/changedRemote/changedLocal/conflict）
- 自动拉取仅当「本地无未推送修改且世界有改动」（温和，不覆盖 agent 工作文件）
- 冲突文件不盲目覆盖：push/pull 默认跳过并报告，`force:true` 强制；AI 读两边内容裁决
- 版本提示：world_* 工具结果附 `updateHint` / `conflictHint`

## 与 AIsChat 独立部署的关系

AIsChat 本体（docker-compose / 源码）保持独立可部署；本插件只是一个加装层，
不改动 AIsChat 的部署方式。后端世界文件仍在后端，DSH 侧只是镜像 + 同步。

## 安全要点

- 代理目标默认回环地址，且只来自插件配置，不接受客户端输入
- 转发前剥离 hop-by-hop 头（Connection / Transfer-Encoding 等），防请求走私
- 错误响应使用固定文案，不回显后端内部错误
- 浏览器与代理之间为同源请求，无 CORS 面
- token 仅内存（client localStorage / host worldTokenMap），不落盘、不打日志
