# 01 世界编号变量

> 区介绍：window 注入的 `WORLD_ID / GROUP_ID / USER_ID / WORLD_AI_ID` 等变量与打包原则。**写任何世界页面代码前必读**，杜绝硬编码编号。

## 1. 核心原则

**你（世界 AI / 世界代码）不需要关心任何编号的具体数值。** 后端在服务世界页面时自动注入以下变量——打包、换实例、迁移即插即用，代码里**一律用变量，不硬编码**。

## 2. 注入变量表

| 变量 | 含义 | 示例 | 可能为 null 的情况 |
|------|------|------|--------------------|
| `window.WORLD_ID` | 当前世界编号 | `3` | 极少（非世界环境加载页面时） |
| `window.WORLD_AI_ID` | 群视界 AI 身份（= `world-{id}`） | `"world-3"` | 无 |
| `window.WORLD_AI_NAME` | 群视界 AI 名字 | `"群视界机器人"` | 无 |
| `window.GROUP_ID` | 当前入口群聊编号（沉浸入口来自群聊时） | `12` | **无入口群聊时 = null**，此时需显式配置 |
| `window.USER_ID` | 当前用户编号 | `5` | **无登录态 = null**，宿主可补 |
| `window.WORLD_ENTRY` | 入口分流信息 `{kind, group_id, group_type_slug}` | `{"kind":"group","group_id":12,"group_type_slug":"adventure"}` | 无（缺省 kind=`main`） |

## 2.5 入口分流（WORLD_ENTRY）——不同入口显示不同界面

一个世界可以有多个入口（群聊/私聊/直进），按入口渲染不同界面：

```js
var entry = window.WORLD_ENTRY || { kind: 'main', group_id: null, group_type_slug: null };
if (entry.kind === 'group') {
  // 群入口：可按 group_type_slug 渲染对应场景（如 adventure→营地、commerce→商铺）
  // entry.group_id = 入口群聊编号；entry.group_type_slug = 该群绑定的类型
} else if (entry.kind === 'dm') {
  // 私聊入口：渲染「对话地点」等私聊场景界面
} else {
  // main：直接进入主页
}
```

入口打开方式：
- 群聊 → 沉浸窗口：自动带 `group_id`（后端查绑定类型注入 slug）
- 私聊 → 沉浸窗口：`/world-view/{id}?from=dm`
- 直进（设计页预览等）：无参数 = `main`


## 3. 注入机制

- 沉浸界面（`/world/{id}/preview`）加载时，宿主会向页面窗口轮询注入以上变量（约 5 秒窗口）。
- 世界页面内嵌的**群聊对话窗积木**等组件也依赖这些变量（如 `GROUP_ID`），因此在页面脚本中读取时建议先判空再使用：

```js
var gid = window.GROUP_ID != null ? window.GROUP_ID : null;
if (gid == null) { /* 未绑定群聊：降级处理 */ }
```

## 4. 群视界机器人身份

- 每个世界**默认自带**一个群视界机器人（创造者 AI），创建世界时自动就位，**不占用全局 agent 编号**。
- 身份固定为 **`world-{世界 id}`**（如 `world-3`），对话按世界 id 路由——你的代码只需认 `world-{id}`，无需关心内部 `agent_id` / `user_id`。
- 懒通知的**默认收件人**：不带 `agent_id` 的通知都发给它（见 07 分区）。

## 5. 打包原则（防呆清单）

1. 页面资源（css/js/图片）一律**相对路径**引用（支持跨文件夹 `../`），**不要用 `/` 开头的绝对路径**（会 404）。
2. 数据请求用 `/world/${WORLD_ID}/` 变量路径（见 06 分区）。
3. 群聊类工具**默认作用于本世界绑定的群**，直接说目的即可，无需也不应指定群号。
4. 成员 id 一律以 `list_group_members` 的返回为准，不要假设。

## 6. 常见错误

| 症状 | 原因 | 处理 |
|------|------|------|
| 页面资源 404 | 用了 `/css/...` 绝对路径 | 改成相对路径 |
| `GROUP_ID` 为 null | 入口不是群聊 | 检查是否绑定群；配置里显式给 groupId |
| 硬编码了世界号 | 违反打包原则 | 改用 `window.WORLD_ID` |
