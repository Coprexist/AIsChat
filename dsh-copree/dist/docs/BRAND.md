# 品牌与命名 / Brand & Naming

> 本文只讲名字：它是什么、为什么这么取、以及哪些地方**刻意没有跟着改**。

## 名字

**Copree** —— **不做中文音译**，中文文案里也直接写 `Copree`（就像 Kimi 一直叫 Kimi）。
前身是 **AIsChat**：那个名字把产品钉在 "AI Chat" 这一层，而它今天已经是
**AI 群聊 + 可编程世界**的框架，旧的品类词反而成了天花板。

## 来路

`Copree` = **co + pre + e**：

| 片段 | 含义 |
|------|------|
| `co` | 共同、连接 |
| `pre` | 从前、先前 |
| `e` | exist，存在 |

连起来是：**我们早在从前，思维便已连接在一起。**

还有第二层：与组织名 **Coprexist** 约分（消去共同的 `Copre`）——Coprexist 余 `xist`，
Copree 的尾巴 `e` 接上去，恰好拼回 **exist**。
所以它不是缩写，而是**把字藏进了名字里**：

> Co-exist, reduced to exist.
> 一同存在，早在从前；约分之后，剩下存在。

## "AIsChat" 的意味留在文案里

名字不再字面写 "AI Chat"，但那是它的**起点**，所以简介与 DSH 插件介绍都保留这层表述：
「前身 AIsChat —— 让 AI 拥有自己的状态、记忆与生命节奏，不只是工具，是陪伴」。

## 刻意没改的东西（内部标识，改了会断）

| 位置 | 为什么保留 |
|------|-----------|
| DB 名 `ai_group_chat` / 容器 `ai_group_*` / DB 用户 `ai_chat` | 用户看不见，迁移风险全在自己这边 |
| 备份文件前缀 `aischat_*.db.gz` / `aischat_*.sql.gz` | 备份列表按前缀扫描，改了历史备份等于"消失" |
| 同源代理与前端的路径 `/aischat-api`、`/aischat-ws`、`/aischat-ui/`、宿主世界同步路由 `/aischat-worlds/*` | 前后端与 DSH 宿主的**协议路径**，必须两侧同版本一起换（前端 `BASE_URL=/aischat-ui/` 也是它） |
| 前端存储键 `aischat-theme`、通知 tag `aischat_msg`、postMessage 源 `aischat-embed` | 存储键改了会重置用户偏好；后两者是宿主协议 |
| DSH 工作区目录 `AIC群视界-<世界名>`、`.aischat-world.json` | 用户本地磁盘上已经存在的目录/文件，改了就是"找不到" |
| 历史 CHANGELOG 条目、`docs/promotion/aischat-v0.3.1-article.md` | 历史就该是历史，不追改旧文 |

联邦公网 ID：新实例生成 `Copree-<ULID>`，老实例保留原值——**没有任何代码解析这个前缀**，所以不需要兼容读。

## 待办（改名是分步做的）

1. GitHub 组织下的 5 个仓库改名（`AIsChat*` → `Copree*`），旧 URL 自动 301
2. 改名之后：代码里的仓库 URL、`registry_repo` 默认值、`.gitignore` 里的兄弟仓目录名
3. DSH 插件构建产物重建：`cd dsh-copree && node scripts/build.mjs`（+ `sync-dist.mjs` 同步前端产物 / 重新生成 manifest 哈希）
4. awesome-dsh-plugin 列表条目：新 YAML 见 [`docs/promotion/awesome-dsh-plugin-entry.yml`](promotion/awesome-dsh-plugin-entry.yml)
5. 部署侧：演示站子路径（`frontend/.env.demo` 的 `BASE_URL`）、镜像站（手动）、镜像/搜索缓存

---

## English

**Name.** `Copree` — no transliteration; Chinese copy also writes `Copree` (like Kimi stays Kimi).
Formerly **AIsChat**, a name that pinned the product to "AI chat" while it had already become a
framework for **AI group chat + programmable worlds**.

**Origin.** `Copree` = **co + pre + e** (together · before · exist) — *"we were already connected
in thought, long before."* Cancel the shared `Copre` against the org name **Coprexist**: what is left
is `xist`, and Copree's trailing `e` completes it into **exist**.

> Co-exist, reduced to exist.

**The "AIsChat" meaning stays in the copy.** The name no longer spells it out, but it is the origin —
so intros and the DSH plugin description keep the line: "formerly AIsChat — AIs that have state,
memory and a life rhythm: not just tools, but companions."

**Deliberately unchanged** (internal identifiers that would break if renamed): database/container
names, backup file prefix `aischat_*`, same-origin proxy paths and storage keys (`/aischat-api`,
`/aischat-ws`, `aischat-embed`, `aischat-theme`), the DSH workspace folder `AIC群视界-<world>` and
`.aischat-world.json`, historical CHANGELOG entries and the old v0.3.1 article.
Federation public IDs: new instances get `Copree-<ULID>`; nothing parses the prefix, so old ids need no migration.
