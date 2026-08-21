# 10 同步与限流机制
> DSH 世界镜像双向同步（world_pull/world_push）与写操作限流（429）的完整机制。**改文件后 push 报「无变化」、pull 报「pulled N 却无变化」、页面操作触发 429 时看本区。**

## 1. 这是什么

世界文件有两份：**AIsChat 后端**（`data/worlds/{id}/`，页面实际加载的权威副本）和 **DSH 工作区镜像**（`~/.dsh/aischat-worlds/AIC群视界-<世界名>/`，你在 DSH 会话里直接读写的那份）。
两者靠 `.aischat-sync.json` 快照做 **GitHub 式三路对比同步**——不是自动实时同步，**改完必须主动 `world_push` 才会到远端**。

## 2. 快照与三路对比（判定依据，必读）

快照 `.aischat-sync.json` 记录每个文件的：
- `lm` = **上次同步时本地 mtime（毫秒）**
- `rm` = **上次同步时远端 mtime（秒）**

每次 `world_pull` / `world_push` 都会重扫两边实际 mtime 与快照对比：

| 判定 | 含义 | 该做什么 |
|------|------|----------|
| `changedLocal` | 本地 mtime 变了、远端没变 | `world_push` 推送 |
| `changedRemote` | 远端变了、本地没变 | `world_pull` 拉取 |
| `conflict` | 两边都变了 | 手动裁决，或 `force` 以一边为准 |
| `added` / `removed` | 单边新增/删除 | 按方向同步 |

**常见误判排查**：
- `world_push` 报「已同步到世界（无变化）」= 快照认为本地与远端 mtime 一致。**这通常意味着改动已经在远端了**（可能之前 push 成功过），不是"没生效"——用 `world_read_file` 直接读远端确认内容即可，不要靠猜。
- `world_pull` 报 `pulled: N` 却 message「无变化」= N 个文件在 **force 模式下被远端覆盖**（本地的改动/冲突以远端为准）。`pulled` 是**实际下载写盘数**，不是"有差异数"。

## 3. 正确工作流

1. 改完文件 → **`world_push`**，看返回的 `pushed` 数。
2. `pushed > 0` = 推送成功；`pushed: 0` + 「无变化」= 远端已是最新（用 `world_read_file` 复核内容）。
3. 想拿远端最新 → **`world_pull`**。不要用 `force` 除非明确要**丢弃本地改动以远端为准**（force 会覆盖本地！）。
4. 判断"远端是不是旧的"一律以 `world_read_file` 读到的内容为准，**不要凭快照数字或 push 返回猜测**。

## 4. 写操作限流（429）

页面事件通道 / 群消息等写操作有**滑动窗口限流**（默认 10 秒窗口）：

```
写配额 = api_group_msg_limit（默认 20）+ api_group_msg_limit_per_user（默认 10）× 活跃人数
```

- **HTTP 429 = "操作太快了，稍后再试"**，**不是通道故障、不是权限问题、不是代码没生效**。
- 前端事件通道 `sendCommand` 对 429 **不降级发群消息**（只提示"操作太频繁"）；只有 **404 / 网络错误**才回退到群消息通道。
- 世界级配额在 `worlds.config`（`api_group_msg_limit` / `api_group_msg_limit_per_user`），可调大。

**排查口诀**：429 → 等一下再试 / 调大配额；不要当成"直连失败"去改降级逻辑或怀疑同步。

## 5. 事件通道（页面操作不借道群聊）

- 页面操作走 `POST /world/{id}/api/event`（payload `{type, payload}`），由世界程序 `handle()` 处理，**不产生群消息**。
- 鉴权：主站登录用户 + 群绑定/成员校验（owner 或绑定群 human 成员）。
- 前端失败降级规则见上一条（只有 404/网络错误才降级到群消息）——**看到群里出现命令 = 事件通道真的 404/断网了，或操作在旧页面**，先刷新页面再查。

## 6. 常见问题速查

| 现象 | 原因 | 处理 |
|------|------|------|
| push「无变化」 | 快照认为已同步 | `world_read_file` 复核远端内容 |
| pull「pulled N 无变化」 | force 覆盖了 N 个本地文件 | 非必要别用 force |
| 页面点击出现群消息 | 事件通道 404/断网，或旧页面缓存 | 强刷页面；查 `/api/event` 状态码 |
| HTTP 429 | 写操作太快 | 稍后再试 / 调大配额 |
| 本地文件有乱码（U+FFFD） | 旧版同步工具跨 chunk 截断 | 重新 world_pull（新版已修复） |
