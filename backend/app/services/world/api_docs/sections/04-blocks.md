# 04 积木体系（预制世界块）

> 区介绍：`list_world_blocks / view_world_block / apply_world_block` 用法、现有积木（平台侧边栏、群聊对话窗）与侧边栏约定。

## 1. 是什么

积木 = 平台提供的**可复用 UI 组件包**（自包含 css/js + manifest）。世界 AI 可查、看、直接应用，避免重复造轮子。

积木包结构（`data/world_blocks/{block_id}/`）：
```
manifest.json   {id, name, description, version, files[], entry, usage}
文件            自包含的 css/js
```

## 2. 三件套工具

| 工具 | 用途 | 参数 |
|------|------|------|
| `list_world_blocks` | 列出平台所有可用积木（id/名/介绍） | 无 |
| `view_world_block` | 查看积木详情 + 完整代码（**应用前先看**，确认是否适合本世界） | `block_id` |
| `apply_world_block` | 把积木文件部署进世界 `blocks/{block_id}/`，按返回的 `usage` 在页面引入 | `block_id` |

**推荐流程**：`list_world_blocks`（看有哪些）→ `view_world_block`（看代码和用法）→ `apply_world_block`（确认合适再应用）。

## 3. 现有积木

### 3.1 platform-sidebar（平台侧边栏）

- **内置平台基础菜单**：首页/聊天/世界列表/设置，**必保留**（可折叠成「平台」组，跳主应用 `window.parent`）。
- 世界自定义菜单：`window.SIDEBAR_ITEMS = [{ label, href }]`；组名/项名可自定义：`SIDEBAR_PLATFORM_TITLE` / `SIDEBAR_PLATFORM_LABELS`。
- 明暗主题自适应；**应用后自动隐藏平台悬浮图标**（`WorldUI.hideFloatingIcon`），无需手动调用。

用法：
```html
<script>window.SIDEBAR_ITEMS = [{ label: '藏宝阁', href: 'treasure.html' }];</script>
<link rel="stylesheet" href="blocks/platform-sidebar/sidebar.css">
<script src="blocks/platform-sidebar/sidebar.js"></script>
```

### 3.2 group-chat（群聊对话窗）

沉浸界面内嵌的群聊对话窗口：消息列表 + 输入发送 + 新消息轮询。**样式与主界面聊天一致**（渐变头像/左右布局/相对时间/Markdown 渲染/自己右侧主色气泡）。

用法：
```html
<div id="group-chat"></div>
<script>
  window.GROUP_CHAT_CONFIG = {
    mountId: 'group-chat',   // 挂载点 id，默认 group-chat
    groupId: null,           // 群编号；默认取 window.GROUP_ID（沉浸入口注入）
    height: '420px',         // 面板高度
    title: '群聊',            // 面板标题
    apiBase: '/api',         // API 前缀（默认即可）
    pollMs: 5000,            // 新消息轮询间隔
  };
</script>
<link rel="stylesheet" href="blocks/group-chat/chat-panel.css">
<script src="blocks/group-chat/chat-panel.js"></script>
```

- `groupId` 默认取 `window.GROUP_ID`；**无入口群聊时为 null，需显式配置 `groupId`**。
- 消息走现有群聊 API（`GET/POST /api/groups/{groupId}/messages`），沿用登录用户身份；自己的消息右侧蓝色气泡，别人左侧。
- 支持 Markdown 轻量渲染（标题/粗体/代码/列表/引用/链接）与附件（图片缩略图/文件芯片）。

## 4. 侧边栏约定（硬性要求）

任何世界的侧边栏/菜单**必须保留平台基础菜单**（首页/聊天/世界列表/设置）：
- 可以折叠进一个可展开的「平台」项，但**绝不能缺失**——否则用户无法回到主应用。
- 平台项跳主应用（`window.parent`），世界自定义项跳世界内页面。
- 组名/项名/样式可自行调整；**推荐直接用 `platform-sidebar` 积木**（已含全部约定）。
- ⚠️ **手机版适配（硬性要求）**：自定义侧边栏必须适配手机屏幕——窄屏（<768px）**默认收拢/隐藏**并提供展开入口（悬浮按钮/顶部按钮），**绝不能默认展开占满屏幕**；至少要实现可收拢功能，移动端优先。

## 5. 注意事项

- **已应用过积木的世界不会自动更新**：积木文件是复制进世界目录的，平台侧升级后需重新 `apply_world_block`（管理员可用 `POST /admin/blocks/{block_id}/update` 批量更新所有使用世界）。
- **DIY 定制约定（重要）**：积木应用后世界目录里有 `blocks/{block_id}/diy/custom.css` 与 `diy/custom.js`——**自定义样式/逻辑写这里**（自动加载，顺序在主文件之后），**不要改主文件**（`sidebar.js`/`sidebar.css` 等）：平台更新积木会**覆盖主文件但保留 diy/**，旧主文件备份在 `blocks/{block_id}/.bak/` 可回滚。
- **积木更新通知**：积木版本变化并重新应用后，世界会收到懒通知（下次对话注入世界 AI 上下文：「积木已更新 vX → vY，你的 DIY 已保留」），AI 应在回复中向用户体现。
- 打包导出时积木文件随世界一起走（相对路径，即插即用）。
