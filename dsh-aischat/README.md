# dsh-aischat

AIsChat 原生集成插件：把 AIsChat 聊天（置顶 / 私信 / 群聊）以原生界面嵌入 DeepSeek Harness Web。

## 架构

双面插件：

- **Host 半**（`lib/index.js`）：在 DSH Web 服务上注册同源网关
  - `GET/POST /aischat-api/*` → 代理到本机 AIsChat 后端（默认 `http://127.0.0.1:5228`，可通过配置修改）
  - `/aischat-ws?token=...` → WebSocket 升级代理到后端 `/ws`
  - 转发浏览器携带的 `Authorization` 头与 WS token，不落盘、不打印、不暴露任何公网地址
- **Client 半**（`lib/client.js`）：原生界面
  - 侧边栏底部入口按钮（`sidebar.footer.action`）
  - 聊天视图（`conversation.view`）：联系人面板（置顶私信 / 置顶群聊 / 私信 / 群聊）+ 消息历史 + 输入框 + WS 实时收发
  - 设置页（`settings.section`）：登录 / 退出 / 状态说明

登录 token 仅保存在浏览器 localStorage，通过同源代理访问服务。

## 安装

```bash
# 1. 构建
pnpm install   # 或复用已有 node_modules（frontend 下）
node scripts/build.mjs

# 2. 装入 DSH web profile
dsh plugin --profile web add file:/path/to/dsh-aischat

# 3. 重启 DSH web 进程使插件生效
```

安装后 profile 的 `cordis.patch.yml` 无需手改——`dsh plugin` 会按
`package.json` 的 `dsh.bundle.patch` 自动把插件挂进 bundle 层。

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

## 与 AIsChat 独立部署的关系

AIsChat 本体（docker-compose / 源码）保持独立可部署；本插件只是一个加装层，
不改动 AIsChat 的部署方式。

## 安全要点

- 代理目标默认回环地址，且只来自插件配置，不接受客户端输入
- 转发前剥离 hop-by-hop 头（Connection / Transfer-Encoding 等），防请求走私
- 错误响应使用固定文案，不回显后端内部错误
- 浏览器与代理之间为同源请求，无 CORS 面
