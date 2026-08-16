# 统一插件系统设计文档

> **服务定位**：AIsChat 的 DSH 式插件化——目录即插件，装好即可用；管理员一键全局开放/关闭，用户设置页一键启用/停用
> **版本**：v1.0
> **日期**：2026-08-17
> **文档规范**：设计类文档统一结构，语言规范，命名规范

---

## 目录

1. [设计目标](#一设计目标)
2. [插件协议](#二插件协议)
3. [目录约定与扫描](#三目录约定与扫描)
4. [两级开关模型](#四两级开关模型)
5. [皮肤插件](#五皮肤插件)
6. [技能插件桥接](#六技能插件桥接)
7. [API 端点](#七api-端点)
8. [数据库](#八数据库)
9. [前端](#九前端)
10. [关键文件索引](#十关键文件索引)
11. [示例插件](#十一示例插件)
12. [未来扩展](#十二未来扩展)

---

## 一、设计目标

对齐 DSH（DeepSeek Harness）的插件体验，但保持 AIsChat 自研架构的简洁：

| 目标 | 说明 |
|------|------|
| **装好即可用** | 插件 = 一个目录 + `plugin.json`，放入插件目录即自动发现，无需改代码、无需重启 |
| **两级开关** | 管理员在管理面板一键全局开放/关闭；用户在自己设置页一键启用/停用 |
| **统一协议** | 皮肤 / 技能 / 世界包等一律走同一套 manifest + 启停机制，不再各自为政 |
| **零门槛安装** | 复制目录即安装；后续演进出 zip 一键安装 / CLI 命令 |

不做什么（本期边界）：不做运行时热加载 Python 代码（FastAPI 进程内动态 import 风险高），
插件当前是**声明式资产**（变量包 / 技能声明），由宿主进程按开关状态消费。

---

## 二、插件协议

### 2.1 目录结构

```
plugins/
  <plugin_id>/
    plugin.json      # manifest（必填）
    skin.json        # 皮肤载荷（category=skin 时）
    skill.json       # 技能声明（category=skill 时）
```

目录名即插件 id（如 `skin-aurora`），全局唯一。

### 2.2 plugin.json 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 否* | 插件 id；缺省取目录名（推荐始终写） |
| `name` | string | 是 | 显示名称 |
| `description` | string | 否 | 描述 |
| `category` | string | 否 | `skin` / `skill` / `world` / `other`，缺省 `other` |
| `version` | string | 否 | 语义化版本，如 `1.0.0` |
| `author` | string | 否 | 作者 |
| `icon` | string | 否 | lucide 图标名（前端渲染，如 `Palette`） |
| `entry` | string | 否 | 载荷文件名；按 category 自动推断（skin→skin.json、skill→skill.json） |
| `default_enabled` | bool | 否 | 首次发现时的全局默认开关，缺省 `true`（装好即可用） |

### 2.3 类别约定

| category | entry 载荷 | 消费方 |
|----------|-----------|--------|
| `skin` | `skin.json`：`{light:{var:hex}, dark:{var:hex}}` | 前端 CSS 变量覆盖 |
| `skill` | `skill.json`：`{skills:[{type,name,category,description,config_schema}]}` | 后端注册进 SkillRegistry |
| `world` | 预留 | 世界包（后续接入 market 世界商城） |
| `other` | — | 其他扩展 |

---

## 三、目录约定与扫描

### 3.1 双目录

| 目录 | 位置 | 语义 |
|------|------|------|
| 内置 | `backend/plugins/` | 随代码走，git 跟踪，随部署分发 |
| 用户 | `$DATA_DIR/plugins/` | 持久化目录，覆盖内置同名 id（升级覆盖场景） |

### 3.2 扫描时机

- **启动**：lifespan 中 `sync_plugins_to_db` + `apply_skill_plugins`（技能类型启动即可用）
- **懒同步**：`GET /plugins` 每次调用前同步（装好即可用，无需重启）
- **手动重扫**：管理面板「重扫目录」→ `POST /plugins/rescan`

### 3.3 同步语义

磁盘是唯一事实源：新增 → 插入 DB；manifest 变化 → 更新字段；**目录消失 → 删除 DB 记录（卸载）**，级联删除用户偏好。

---

## 四、两级开关模型

```
生效(effective) = plugins.enabled(管理员全局) AND user_plugin_prefs.enabled(用户个人)
```

- **管理员全局**：`plugins.enabled`，管理面板「插件管理 → 统一插件」区一键切换（`POST /plugins/{id}/toggle`）
- **用户个人**：`user_plugin_prefs.enabled`，用户设置页一键切换（`POST /plugins/{id}/pref`）
- **默认**：无用户偏好记录时视为 `true`（装好即可用）；管理员关闭时用户无法启用（返回 403 提示）
- **皮肤互斥**：同一时刻只生效一个 skin 插件——启用 A 时后端显式把其他皮肤的用户偏好置为 `false`（含无记录者，防止默认 true 造成多皮肤同时生效）

---

## 五、皮肤插件

### 5.1 skin.json 协议

```json
{
  "light": { "primary_400": "#34D399", "primary_500": "#10B981", "...": "..." },
  "dark":  { "primary_400": "#34D399", "primary_500": "#10B981", "...": "..." }
}
```

合法 key 与主题定制一致：`primary_400/500/600`、`accent_400/500`、`mint_400/500`、`rose_400/500`、`bubble`（气泡色）。

### 5.2 应用链路（前端）

```
登录/刷新 → GET /plugins → 找 category=skin 且 effective 的插件
  → applySkin(id, skin_vars, isDark)     # 按当前主题模式应用对应套变量
主题切换 → AuthContext 依赖 theme 重新应用（inline style 只能存一份值）
停用皮肤 → clearSkin() → 用户自选主色（theme_colors）自然恢复
```

- 皮肤最后应用，**覆盖**用户自选主色之上；停用后自选色恢复
- `utils/skin.ts`：`applySkin` / `clearSkin` / `skinVarName`（key → `--tw-*` CSS 变量）

---

## 六、技能插件桥接

### 6.1 skill.json 协议

```json
{
  "skills": [
    {
      "type": "writing_studio",
      "name": "写作工坊",
      "category": "inject",
      "description": "……",
      "config_schema": { "style": {"type": "string", "default": "default"} }
    }
  ]
}
```

### 6.2 注册规则（`services/plugin/skill_bridge.py`）

- 插件**全局启用**时，其声明的技能类型注册进 `SkillRegistry`（`app/utils/pure/skill_registry.py`）
- 管理员关闭 / 目录消失 → `unregister` 注销对应类型
- 由插件注册的类型记录在 `_from_plugins`，注销时只动这些，**绝不误删内置类型**

效果：插件技能类型出现在 `GET /skills`（可用类型），AI 可按现有技能流程添加使用。

---

## 七、API 端点

路由自动发现（`routers/` 目录即注册），前缀 `/plugins`：

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/plugins` | 登录 | 插件列表（含全局开关、用户偏好、生效状态、皮肤变量）；调用前懒同步 |
| POST | `/plugins/{id}/toggle` | 管理员 | 全局开放/关闭 |
| POST | `/plugins/{id}/pref` | 登录 | 用户个人启用/停用；skin 互斥 |
| POST | `/plugins/rescan` | 管理员 | 手动重扫磁盘目录 |

---

## 八、数据库

### plugins

| 列 | 类型 | 说明 |
|----|------|------|
| id | string(80) PK | 插件 id |
| name / description / category / version / author / icon | — | manifest 快照 |
| enabled | bool | 管理员全局开关 |
| builtin | bool | 是否内置（backend/plugins） |
| created_at / updated_at | datetime | 时间戳 |

### user_plugin_prefs

| 列 | 类型 | 说明 |
|----|------|------|
| id | int PK | — |
| user_id | FK users.id CASCADE | 用户 |
| plugin_id | FK plugins.id CASCADE | 插件 |
| enabled | bool | 用户个人开关 |
| UNIQUE(user_id, plugin_id) | — | 一用户一插件一行 |

迁移：Alembic `a9b8c7d6e5f4`（down_revision `e6f7a8b9c0d2`）。

---

## 九、前端

| 文件 | 说明 |
|------|------|
| `src/utils/skin.ts` | 皮肤应用/清除/变量名映射（模块级状态） |
| `src/components/SkinPicker.tsx` | 设置页「外观 → 皮肤」区块：卡片 + 一键启停 + 即时应用 |
| `src/context/AuthContext.tsx` | 登录/刷新/主题切换时自动应用生效皮肤；登出清除 |
| `src/components/PluginManager.tsx` | 管理面板「插件管理 → 统一插件」区：全局开关 + 重扫目录 |

---

## 十、关键文件索引

| 文件 | 职责 |
|------|------|
| `backend/app/services/plugin/catalog.py` | 扫描 / manifest 解析 / 载荷读取 / DB 同步 |
| `backend/app/services/plugin/skill_bridge.py` | 技能插件注册 / 注销 |
| `backend/app/routers/plugins.py` | 插件 API |
| `backend/app/models/plugin.py` | Plugin / UserPluginPref 模型 |
| `backend/app/utils/pure/skill_registry.py` | SkillRegistry（新增 `unregister`） |
| `backend/app/main.py` | 启动时插件同步 |

---

## 十一、示例插件

| id | 类别 | 说明 |
|----|------|------|
| `skin-aurora` | skin | 极光青碧（青碧色系，日夜两套） |
| `skin-sakura` | skin | 樱粉物语（樱粉色系，日夜两套） |
| `skill-writing-studio` | skill | 写作工坊（技能类型 `writing_studio`） |

复制示例目录改名改字段，即是新插件。

---

## 十二、未来扩展

- [ ] 世界包（world 类别）接入市场一键导入，统一启停
- [ ] 插件市场协议：zip 打包 / 一键安装 / 更新 / 卸载
- [ ] CLI 安装命令（DSH `plugin add` 同款体验）
- [ ] 皮肤组件级扩展（超越变量包：布局/图标包）
- [ ] 插件审核与签名（公网分发安全）
