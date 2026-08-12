# 世界块体系（积木）

> **面向**：开发者（维护/扩展积木）与管理员（积木更新）
> **版本**：v1.0 ｜ **日期**：2026-08-12
> **关联**：接口文档 04 区（AI 视角速查）、`troubleshooting.md`

## 一、定位

**积木（世界块）= 平台提供的可复用 UI 组件包**。世界 AI 通过 `list_world_blocks / view_world_block / apply_world_block` 三件套直接应用现成组件（侧边栏、群聊窗等），避免重复造轮子；用户/世界可在此基础上 DIY 定制，且定制不会被平台更新覆盖。

## 二、架构

```
data/world_blocks/{block_id}/      ← 平台侧积木源（随项目 git 跟踪）
├── manifest.json   {id, name, description, version, files[], entry, usage}
├── *.js / *.css   主文件（平台管）

apply_world_block 复制进世界 →
worlds/{world_id}/blocks/{block_id}/
├── manifest.json      主文件（平台管，可更新覆盖）
├── sidebar.js         主文件（平台管）
├── sidebar.css        主文件（平台管）
├── diy/               ★ 用户定制区（平台更新跳过不覆盖）
│   ├── custom.css     自动加载（顺序在主文件后，覆盖基础样式）
│   └── custom.js      自动加载（主文件后执行，可访问积木全局对象）
└── .bak/              更新备份（旧主文件，可手动回滚）
```

**三权分离原则**：
- **主文件** → 平台管：更新/修复/升级由平台侧改 `data/world_blocks/` 源
- **diy/** → 用户/世界管：一切自定义样式与逻辑写这里，更新永不触碰
- **.bak/** → 保险：更新时自动留存旧主文件，DIY 依赖旧版可回滚

## 三、工具与流程

| 工具 | 用途 |
|------|------|
| `list_world_blocks` | 列出平台所有积木（id/名/介绍） |
| `view_world_block` | 查看积木详情+完整代码（应用前先看） |
| `apply_world_block` | 部署进世界 `blocks/{id}/`，返回 usage |

推荐流程：list → view → apply。应用是**复制语义**（非引用），世界包导出时积木随世界走，离线可用。

## 四、DIY 定制体系

- **改样式** → `diy/custom.css`（覆盖规则，优先级高于主文件）
- **加逻辑** → `diy/custom.js`（主文件后执行）
- **配置项** → 积木暴露的 window 钩子（如 `SIDEBAR_ITEMS`）
- **纪律**：不改主文件——更新会覆盖主文件；DIY 区永远保留
- 首次 apply 自动生成 diy 模板（带注释说明）；主文件内置 DIY 加载器（`currentScript` 推导路径 + fetch 存在性检查，避免 404 噪音）

## 五、更新机制

| 环节 | 说明 |
|------|------|
| 触发 | 世界 AI 重新 `apply_world_block`，或管理员 `POST /admin/blocks/{block_id}/update`（批量更新所有使用世界） |
| 版本检测 | 对比世界内 manifest 与平台源 version；变化 → 视为更新 |
| 覆盖范围 | 只覆盖主文件；`diy/` 跳过不覆盖 |
| 备份 | 旧主文件写入 `.bak/`（可手动回滚） |
| 通知 | 更新后写懒通知 → 世界 AI 下次对话收到「积木已更新 vX → vY，你的 DIY 已保留」，并在回复中向用户说明 |

## 六、现有积木

| 积木 | 能力 |
|------|------|
| platform-sidebar | 平台侧边栏：基础菜单（必保留）+ 自定义菜单、折叠开关、明暗自适应、自动隐藏悬浮图标 |
| group-chat | 群聊对话窗：消息列表/输入/Markdown/附件，样式与主界面一致 |
| 2d-adventure | 2D 冒险世界示例（游戏指令→状态发布→SSE 实时应用） |
| identity | 身份展示块 |

## 七、硬性约定

- **侧边栏必须保留平台基础菜单**（首页/聊天/世界列表/设置，可折叠成「平台」组但不可缺失）
- **手机版适配**：窄屏（<768px）默认收拢/隐藏 + 提供展开入口，绝不全屏占满
- 详情见接口文档 04 区第 6 节

## 八、维护与扩展

- 新增积木：在 `data/world_blocks/` 建目录（manifest + 文件），无需改代码（自动发现）
- 更新积木：改源文件 → 升 version → 管理员批量更新（或世界 AI 重新 apply）
- 兼容纪律：**主文件更新必须向后兼容**（类名/CSS 变量/API 钩子只增不改），保证 diy/ 覆盖规则长期有效
