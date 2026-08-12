# 03 文件操作
> `file_list / file_write / file_read / file_edit / file_delete` 全部参数与返回、类型白名单、越界防护、读取截断规则。**建/改世界网页代码前必读**。

## 1. 概述

世界文件存储在**隔离目录** `data/worlds/{world_id}/`，只能通过工具或 `/world/{id}/files/` 路由访问。**不允许越界访问**：`../`、绝对路径、符号链接逃逸一律拒绝。

## 2. 工具一览

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `file_list` | 列出世界文件夹里的文件 | 无 |
| `file_write` | 创建或写入文件（自动建目录） | `path`（相对路径，如 `css/style.css`）、`content` |
| `file_read` | 读取文件内容（编辑前确认用） | `path` |
| `file_edit` | 增量编辑（查找替换/插入/删行），省 token | `path`、`operation`、按需参数 |
| `file_delete` | 删除文件 | `path` |

## 3. 各工具详细

### 3.1 file_list

```
→ { "success": true, "files": ["index.html", "css/style.css", "img/logo.png"] }
```

- 返回**相对路径列表**，可用于确认目录结构后再读写。

### 3.2 file_write

```json
{ "path": "css/style.css", "content": "body { color: red; }" }
```

- **自动创建缺失目录**；目标已存在则覆盖。
- **类型白名单**（不在白名单内直接拒绝）：`html / htm / css / js / json / md / txt / png / jpg / jpeg / gif / svg / webp / ico / woff / woff2 / ttf / mp3 / wav / ogg / mp4 / webm / py`（`py` 仅存储，**阶段 2 才可执行**）。
- **单文件上限 5MB**。
- **温和去重**：若新内容与现有内容完全一致，返回 `unchanged: true` + 提示，不重复写入（不是错误，别重试）。

### 3.3 file_read

```
→ { "success": true, "path": "index.html", "content": "<html>…", "binary": false }
```

- 二进制文件：返回 `binary: true`，`content` 为 null（工具侧显示"二进制文件，内容不返回"）。
- **长文件截断**：超过 6000 字符截断显示，末尾附提示——需要改内容时用 `file_edit` 定位，不要全文重写。
- **建议**：编辑前先 `file_read` 确认当前内容，避免误覆盖。

### 3.4 file_edit（增量编辑，推荐）

```json
{ "path": "index.html", "operation": "str_replace",
  "old_string": "<title>旧标题</title>", "new_string": "<title>新标题</title>" }
```

三种 `operation`：

| operation | 必填参数 | 行为 |
|-----------|----------|------|
| `str_replace` | `old_string` + `new_string` | 精确替换；`old_string` 必须**唯一**，否则报错 |
| `insert` | `line` + `new_string` | 在 `line` 行之后插入（1 开头，`0` = 文件开头） |
| `delete_lines` | `start_line` + `end_line` | 删除 `start_line..end_line`（**含两端**） |

- **多次插入时从最大行号开始往小插**（行号会随插入变化，从大往小插不会错位）。
- 编辑核心与主站共用同一份实现（`apply_file_edit`），语义一致。
- 二进制文件不可编辑。

### 3.5 file_delete

```json
{ "path": "old.html" }
```

- 删除文件；目录需先清空内容再删（或留空目录）。

## 4. 页面内访问静态资源（不是工具，是路由）

写死这段路径即可，编号用变量：

```
GET /world/${WORLD_ID}/files/<相对路径>     # 静态资源（css/js/图片/页面）
```

```html
<link rel="stylesheet" href="/world/${WORLD_ID}/files/css/style.css">
<img src="/world/${WORLD_ID}/files/img/logo.png">
```

## 5. 约定与防呆

- 页面内资源一律**相对路径**引用（跨文件夹用 `../`），不要用 `/` 开头绝对路径（会 404）。
- 创建文件后**告知用户文件路径**；调用工具时不要把工具调用的原始内容写进回复文本，直接说做了什么。
- 写文件前先 `file_list` / `file_read` 确认现状，避免重复写入或误覆盖用户改动。