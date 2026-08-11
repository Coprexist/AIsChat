# 06 页面与资源

> 区介绍：沉浸界面预览入口、静态资源路由 `/world/{id}/files/`、相对路径规则、资源类型。

## 1. 沉浸界面入口

```
GET /world/${WORLD_ID}/preview     # 加载世界 index.html 的沉浸界面
```

- 用户从群聊/设计页点「在沉浸界面打开」即进入此入口。
- 进入时宿主会注入 `window.WORLD_ID / GROUP_ID / USER_ID / WORLD_AI_ID / WORLD_AI_NAME` 等变量（见 01 分区）。

## 2. 静态资源路由

世界代码写死这段路径即可，编号用变量：

```
GET /world/${WORLD_ID}/files/<相对路径>
```

```html
<link rel="stylesheet" href="/world/${WORLD_ID}/files/css/style.css">
<script src="/world/${WORLD_ID}/files/js/app.js"></script>
<img src="/world/${WORLD_ID}/files/img/logo.png">
```

- 后端按世界编号路由到对应世界的隔离目录，**不会暴露后端真实结构**。
- 支持的类型与工具白名单一致（html/css/js/json/md/txt/图片/音频/视频/字体等，见 03 分区）。

## 3. 相对路径规则（防呆）

- 页面内资源（css/js/图片）**一律相对路径引用**（支持跨文件夹 `../`），**不要用 `/` 开头绝对路径**（会 404）。
- 例外：`/world/${WORLD_ID}/...` 变量路由按上方写法使用。

```html
<!-- ✅ 正确：相对路径 -->
<link rel="stylesheet" href="css/style.css">
<!-- ✅ 正确：变量路由 -->
<img src="/world/${WORLD_ID}/files/img/logo.png">
<!-- ❌ 错误：绝对路径会 404 -->
<link rel="stylesheet" href="/css/style.css">
```

## 4. 数据请求（阶段 2 开放）

```
GET /world/${WORLD_ID}/api/state      # 阶段 2：世界受控数据 API
```

阶段 1 数据以文件（json/md）形式放在世界文件夹，页面 `fetch` 相对路径读取；阶段 2 提供受控数据 API 与 py 沙箱。

## 5. 打包导出

- 一键打包：`GET /worlds/{world_id}/export` 返回 zip（代码 + 数据）。
- 打包后积木文件、相对路径资源随世界一起走，任何实例注入变量即可运行（即插即用）。

## 6. 常见错误

| 症状 | 原因 | 处理 |
|------|------|------|
| 页面样式/脚本 404 | 用了 `/` 开头绝对路径 | 改成相对路径 |
| 图片不显示 | 路径跨文件夹写错 | 用 `../` 或变量路由 |
| 预览空白 | `index.html` 不存在或未命名 | 先 `file_write` 创建 `index.html` |
