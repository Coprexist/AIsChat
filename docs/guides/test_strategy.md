# AIsChat 测试策略文档 / Testing Strategy

> **面向开发者和质量保证人员。** 多层次测试策略、测试规范和质量标准。
> **For developers and QA.** Multi-level testing strategy, test standards, and quality criteria.
>
> 本文档只描述**仓库里真实存在**的东西。尚未落地的能力一律显式标注「目标」/「未落地」，
> 不写成既有事实——目录结构与命令必须能原样粘贴执行。

---

## 目录

1. [当前套件与运行方式](#一当前套件与运行方式)
2. [测试策略概述](#二测试策略概述)
3. [测试金字塔现状](#三测试金字塔现状)
4. [单元测试](#四单元测试)
5. [集成测试](#五集成测试)
6. [端到端测试](#六端到端测试)
7. [性能测试](#七性能测试)
8. [测试环境](#八测试环境)
9. [测试覆盖率](#九测试覆盖率)
10. [CI/CD 集成](#十cicd-集成)

---

## 一、当前套件与运行方式

后端用例全部平铺在 `backend/tests/`，**没有子目录**。

| 文件 | 类型 | 用例数 | 覆盖 |
|------|------|--------|------|
| `backend/tests/test_api_probe.py` | 单元（零网络） | 17 | 供应商探针判定、错误文案、响应脱敏、内网地址围栏 |
| `backend/tests/test_world_chat_images.py` | 集成（真库 + 真文件） | 5 | 群视界发图链路：真调 `_prepare_world_chat`，零 LLM 消耗 |
| `backend/tests/test_agent_resolution.py` | 集成（真库） | 2 | 群成员 `member_id` 解析优先级 |

辅助文件：

- `backend/tests/conftest.py` —— 测试库环境变量与 `migrated_db` fixture
- `backend/tests/run_without_pytest.py` —— 后端容器里**没装 pytest**，这是最小运行器

### 1.1 两种跑法

CI 与装了 pytest 的机器：

```bash
cd backend && python -m pytest tests/ -q
```

后端容器 / 没装 pytest 的机器（走自带运行器）：

```bash
PROD=$(docker exec ai_group_backend printenv DATABASE_URL)
TEST=${PROD/\/ai_group_chat/\/ai_group_chat_test}
docker exec -w /app \
  -e TEST_DATABASE_URL="$TEST" \
  -e TEST_DATABASE_URL_SYNC="${TEST/+asyncpg/}" \
  ai_group_backend python tests/run_without_pytest.py
```

运行器只实现了 `pytest.fixture` 与 `pytest.mark`。需要参数化、插件、覆盖率就去装 pytest，
不要往运行器里加功能。

**启动闸**：库名不以 `_test` 结尾直接拒绝启动。运行器会 `drop_all` + `TRUNCATE`，
而生产库与测试库在同一个 PostgreSQL 实例里、只差库名——这个闸不是形式主义。

### 1.2 写完用例要证明「它会红」

只跑到绿不算完成。把 bug 放回去（用 monkeypatch，别改源码，更别改正在被生产容器挂载的目录）
确认用例转红，否则它只是摆设。`test_world_chat_images.py` 的 5 条就是这么定稿的：

| 放回去的 bug | 结果 |
|---|---|
| `image_attachments` 去掉 `or []`（P0 本体） | ✅ 被抓住：`TypeError: 'NoneType' object is not iterable` |
| `build_content` 忽略图片（静默丢弃） | ✅ 被抓住 |
| 不发「本轮附图」便签 | ✅ 被抓住 |
| 历史图片不降级成 `[图片]` | ✅ 被抓住 |

**第一版是假覆盖**：只跑了首轮，而首轮历史是空的、`None` 根本不会出现——
P0 只在「上一轮存过不带附件的消息」时才触发。是变异测试把这个漏洞逼出来的。

---

## 二、测试策略概述

### 2.1 测试分层模型

```mermaid
flowchart TD
    subgraph "测试金字塔"
        E2E[端到端测试<br/>E2E Tests]
        Integration[集成测试<br/>Integration Tests]
        Unit[单元测试<br/>Unit Tests]
    end

    subgraph "数量比例"
        E2ERatio[~5%]
        IntegrationRatio[~20%]
        UnitRatio[~75%]
    end

    subgraph "执行速度"
        E2ESpeed[慢 (分钟级)]
        IntegrationSpeed[中等 (秒级)]
        UnitSpeed[快 (毫秒级)]
    end

    subgraph "维护成本"
        E2ECost[高]
        IntegrationCost[中]
        UnitCost[低]
    end

    E2E --> E2ERatio
    Integration --> IntegrationRatio
    Unit --> UnitRatio

    E2E --> E2ESpeed
    Integration --> IntegrationSpeed
    Unit --> UnitSpeed

    E2E --> E2ECost
    Integration --> IntegrationCost
    Unit --> UnitCost

    style E2E fill:#7c3aed,color:#fff
    style Integration fill:#2563eb,color:#fff
    style Unit fill:#059669,color:#fff
```

> 上表是**目标**比例。截至 2026-09-13 的实际构成是 24 条用例（单元 17 / 集成 7），
> 清单见第一节。

### 2.2 测试目标

| 维度 | 目标 | 衡量指标 |
|------|------|---------|
| 功能正确性 | 核心功能 100% 覆盖 | 需求覆盖率 |
| 回归稳定性 | 代码变更不破坏现有功能 | 回归测试通过率 |
| 性能满足 | 关键路径响应可接受 | P95 响应时间 |
| 安全性 | 无已知高危漏洞 | 安全扫描结果 |

---

## 三、测试金字塔现状

```mermaid
graph TD
    subgraph "手工回归（部署后人工执行）"
        E2E1[注册登录]
        E2E2[群聊与消息]
        E2E3[AI 对话与工具调用]
        E2E4[文件上传与发图]
        E2E5[群视界世界]
    end

    subgraph "集成测试（真库 · backend/tests/）"
        INT1[test_agent_resolution.py]
        INT2[test_world_chat_images.py]
    end

    subgraph "单元测试（零网络 · backend/tests/）"
        UNIT1[test_api_probe.py]
    end

    E2E --> INT
    INT --> UNIT

    style E2E1 fill:#7c3aed,color:#fff
    style E2E2 fill:#7c3aed,color:#fff
    style E2E3 fill:#7c3aed,color:#fff
    style E2E4 fill:#7c3aed,color:#fff
    style E2E5 fill:#7c3aed,color:#fff
    style INT1 fill:#2563eb,color:#fff
    style INT2 fill:#2563eb,color:#fff
    style UNIT1 fill:#059669,color:#fff
```

三层的分界在本仓库里的具体含义：

| 层 | 判据 | 例 |
|----|------|----|
| 单元 | 不连数据库、不出网 | `test_api_probe.py` 用 `httpx.MockTransport` 顶掉真实出网 |
| 集成 | 连真库，但**不花 LLM 额度** | `test_world_chat_images.py` 真调业务函数，只断言 LLM payload |
| 端到端 | 真环境、真模型、真浏览器 | 目前**没有自动化**，见第六节 |

---

## 四、单元测试

### 4.1 已有覆盖

| 模块 | 测试重点 | 用例文件 |
|------|---------|---------|
| `app/services/agent/api_probe.py` | 探针判定、错误文案、响应脱敏 | `backend/tests/test_api_probe.py` |
| `app/utils/pure/url_guard.py` | 内网/公网地址判定（含 DNS 解析绕过） | `backend/tests/test_api_probe.py` |
| `app/services/agent/base_url_registry.py` | 「已登记私网地址」的允许清单 | `backend/tests/test_api_probe.py` |

### 4.2 尚未覆盖（把缺口写出来，别让它不可见）

| 模块 | 应覆盖 | 现状 |
|------|--------|------|
| `app/ai/decider.py` | 决策逻辑、意愿分计算 | 无用例 |
| `app/ai/executor.py` | 工具调用循环、上下文压缩 | 无用例 |
| `app/ai/llm.py` | API Key 解析、消息构建、视觉降级重试 | 无用例 |
| `app/utils/multimodal.py` | 附件 → 多模态 content（纯函数部分） | 只能由 `test_world_chat_images.py` 间接覆盖 |
| `app/utils/pure/llm_endpoint.py` | 端点拼接（`/vN` 规则） | 无用例（曾在 9 个 preset 上人工核验） |
| `app/tools/` | 工具参数校验、执行 | 无用例 |
| `app/services/memory/` | 记忆检索、遗忘机制、压缩阈值 | 无用例 |
| `app/services/brain/` | 状态机转换、心跳 | 无用例 |
| `app/chat/` | 消息管道、可达性 | 无用例 |

### 4.3 示例：零网络单测

单元用例**不许出网**。需要 HTTP 的地方一律用 `httpx.MockTransport` 顶掉传输层，
这样「供应商返回 404 但聊天其实是通的」这类真实事故路径才能便宜地复现：

```python
# backend/tests/test_api_probe.py
def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_models_404_falls_back_to_tiny_chat():
    """/models 不存在 → 真发一次极小 chat；MiMo 这条路径必须判成功"""
    calls: list[str] = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(404, text="<html>404 Not Found</html>")
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    async with _client(handler) as c:
        r = await probe_provider(MIMO, "sk-test", client=c)

    assert r.ok and r.kind == "ok"
    assert calls == ["/v1/models", "/v1/chat/completions"]
    assert "mimo-v2.5" in r.message          # 模型名取自预设
```

### 4.4 运行

```bash
# 装了 pytest
cd backend && python -m pytest tests/test_api_probe.py -v

# 容器里没装 pytest（完整命令见 1.1）
cd /tmp/zfsv3/sata11/15228874271/data/aischat && \
  docker exec -w /app ai_group_backend python tests/run_without_pytest.py
```

---

## 五、集成测试

### 5.1 现有用例

| 场景 | 涉及模块 | 用例文件 |
|------|---------|---------|
| 群成员 ID → Agent 解析 | 群成员表 + Agent 模型 | `backend/tests/test_agent_resolution.py` |
| 世界对话准备 → LLM payload | 路由入参 + ChatItem + 落库 + `multimodal` | `backend/tests/test_world_chat_images.py` |

集成用例连**测试库** `ai_group_chat_test`，但**不花 LLM 额度**：跑的是业务函数，不是真的对话。
`test_world_chat_images.py` 走完 `_prepare_world_chat` 后只断言「送给模型的 messages 长什么样」。

### 5.2 示例：真调业务函数，只断言 payload

```python
# backend/tests/test_world_chat_images.py
async def test_image_turn_injects_multimodal_parts_and_note(migrated_db):
    """带图消息：最后一条 user 是多模态 parts，便签数与**实际注入数**一致。"""
    async with async_session() as db:
        world_id, attachment = await _seed_world(db, with_image=True)
        try:
            ctx = await _prepare(db, world_id, [
                ChatItem(text="这是什么？", attachments=(attachment,)),
            ])
        finally:
            _drop_image_file(attachment)

    body = _last_user(ctx["messages"])
    assert isinstance(body["content"], list), "图片被静默丢弃了：content 本应是 parts 列表"
    urls = [p["image_url"]["url"] for p in body["content"] if p.get("type") == "image_url"]
    assert urls[0].startswith("data:image/png;base64,")
```

### 5.3 conftest.py

集成用例共享 `backend/tests/conftest.py`。它做三件事：把 `DATABASE_URL` 指向测试库、
提供 `migrated_db` fixture、注册 anyio backend：

```python
# backend/tests/conftest.py（节选）
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ai_chat:<pwd>@localhost:5432/ai_group_chat_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_URL_SYNC"] = TEST_DATABASE_URL_SYNC


@pytest.fixture(scope="session")
async def migrated_db():
    """用模型 metadata 建全量表（不跑 alembic：历史迁移链无法从空库重建，模型即 schema）"""
    ...
    await conn.run_sync(Base.metadata.drop_all)
    await conn.run_sync(Base.metadata.create_all)
```

注意 `migrated_db` 是 **session 级**且会 `drop_all`：用例自己负责播种
（现有集成用例的做法是开头 `TRUNCATE ... CASCADE`，再插入自己需要的最小数据）。

### 5.4 运行

需要 `TEST_DATABASE_URL` 指向测试库。在容器里用 1.1 的运行器（它会替你推导 URL 并加闸）。

---

## 六、端到端测试

### 6.1 现状：没有自动化 E2E

仓库里**没有**前端 E2E 套件：没有 Playwright 依赖、没有 `frontend/e2e/` 目录，
`frontend/package.json` 的 scripts 只有 `dev` / `build` / `build:demo` / `preview`。
CI 里有一个前端 job，但它只做**类型检查**（`tsc --noEmit`），不跑任何测试（见第十节）。

因此「端到端」目前 = **部署后人工回归**，按附录清单走一遍。

`test_world_chat_images.py` 是其中能自动化部分的替代品：它咬得住「接线级」回归
（payload 形状、便签、降级路径），咬不住 UI 与真实模型行为。

### 6.2 手工回归清单

见附录。改动核心链路（聊天管道 / 世界 / 模型解析 / 附件）后按清单走。

### 6.3 若要引入自动化（目标，尚未落地）

1. 先补**后端**：真起服务 + 真调一次模型。成本可控，且能验证只有真模型才会暴露的行为
   （例如模型不承认自己能看图）；
2. 再补**前端**：登录 → 发消息 → 发图 → 断言气泡与缩略图。

---

## 七、性能测试

### 7.1 现状：未落地

没有性能测试目录，`backend/requirements.txt` 里没有 locust / k6 之类依赖，也没有压测脚本；
CI 不跑性能。

### 7.2 目标矩阵

| 测试场景 | 工具（目标） | 指标 | 通过标准 |
|---------|-------------|------|---------|
| API 响应时间 | Locust / wrk | P95 响应时间 | < 500ms |
| WebSocket 并发 | k6 | 同时在线用户 | > 1000 |
| AI 回复延迟 | 自定义脚本 | 端到端延迟 | < 5s（受模型侧影响，只作趋势观测）|
| 数据库查询 | pgbench | QPS | > 1000 |
| 文件上传 | curl / wrk | 上传速度 | > 10MB/s |

### 7.3 目前怎么测

手工观测，够用为止：

```bash
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" http://127.0.0.1:5228/health
docker logs --since 10m ai_group_backend 2>&1 | grep -E "🌐"
```

**不要**把手工观测到的单次数字当成基准写进文档 —— 没有固定负载的「基准」是误导。

---

## 八、测试环境

### 8.1 真实环境链

只有三段，没有 staging / pre-production：

```mermaid
flowchart LR
    Dev[开发容器 / 本机] -->|push backend/**| CI[GitHub Actions]
    CI -->|测试通过| Merge[合并]
    Merge -->|/usr/local/bin/dsh-web-restart| Prod[生产：NAS 容器]

    style Dev fill:#6366f1,color:#fff
    style CI fill:#f59e0b,color:#fff
    style Prod fill:#dc2626,color:#fff
```

### 8.2 数据库

生产库与测试库在**同一个 PostgreSQL 实例**里，只差库名：

| 用途 | 库名 | 谁在用 |
|------|------|--------|
| 生产 | `ai_group_chat` | `ai_group_backend` 容器（挂载 `./backend:/app`）|
| 测试 | `ai_group_chat_test` | `conftest.py` 的 `migrated_db` + 集成用例 |

正因为同实例、只差库名，`run_without_pytest.py` 才必须有那个「库名以 `_test` 结尾」的启动闸。

### 8.3 测试数据管理

没有 `setup_test_data` / 脱敏复制之类的脚本，也不需要：

- schema 由 `migrated_db` 从**模型 metadata** 建全量（`drop_all` + `create_all`）。
  历史迁移链无法从空库重建，所以**模型即 schema**，测试库不跑 alembic；
- 数据由每个用例自己播种，开头 `TRUNCATE ... CASCADE` 保证从干净状态开始；
- 用例造的临时文件（如 `test_world_chat_images.py` 的 1×1 PNG）自己删干净。

---

## 九、测试覆盖率

### 9.1 目标

| 测试类型 | 目标覆盖率 | 最低覆盖率 | 关键模块 |
|---------|-----------|-----------|---------|
| 单元测试 | 80% | 60% | AI 核心: 90%+ |
| 集成测试 | 70% | 50% | API 端点: 100% |
| 端到端测试 | 核心链路 100% | 核心链路 100% | 所有业务链路 |

### 9.2 现状：未接入

CI 只装 `pytest pytest-asyncio pytest-timeout`，**没有** `pytest-cov`；
`backend/requirements.txt` 里也没有覆盖率依赖。前端没有测试框架，因此也没有前端覆盖率。
所以上面那张表是**目标**，不是当前达标情况。

### 9.3 接入方式（目标）

```bash
pip install pytest-cov
cd backend && python -m pytest tests/ --cov=app --cov-report=term-missing
```

接入前请先补 4.2 的缺口——覆盖率数字本身不解决「关键路径没有用例」。

---

## 十、CI/CD 集成

### 10.1 真实的 workflow

`.github/workflows/test.yml` 就是全部检查（另有 `deploy-demo.yml` 负责 push 到 main 时构建并发布 Pages）。
为节省篇幅，下面省掉了 `--health-cmd` 等编排细节，但**作业、触发路径、命令都是原样**：

```yaml
name: Tests

on:
  push:
    paths:
      - 'backend/**'
      - 'frontend/**'
      - '.github/workflows/test.yml'
  pull_request:
    paths:
      - 'backend/**'
      - 'frontend/**'

jobs:
  # 作业 id 与名称保持原样：改名会让 GitHub 上的 required status check 失效
  pytest:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg17
        env:
          POSTGRES_USER: ai_chat
          POSTGRES_PASSWORD: test-pass
          POSTGRES_DB: ai_group_chat_test
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: backend/requirements.txt
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install pytest pytest-asyncio pytest-timeout
      - name: Run backend tests
        env:
          TEST_DATABASE_URL: postgresql+asyncpg://ai_chat:test-pass@localhost:5432/ai_group_chat_test
          TEST_DATABASE_URL_SYNC: postgresql://ai_chat:test-pass@localhost:5432/ai_group_chat_test
        run: |
          cd backend
          python -m pytest tests/ -q

  # 前端此前在 PR 阶段零检查：deploy-demo.yml 只在 push 到 main 时跑，
  # 且跑的是 vite build（不含 tsc），类型错误一路裸奔到部署。
  frontend:
    name: Frontend (typecheck)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        run: npm ci
      # 必须走 node_modules 里的 tsc：npx 在缺包时会去装一个同名的假 tsc@2.0.3
      - name: Typecheck
        run: ./node_modules/.bin/tsc --noEmit
```

> `frontend` job 不跑任何测试，只做类型检查。它拦得住的东西已用「注入一个类型错误」验证过：
> 有错时 `tsc` 退出码 2 并打印 `error TS2322`，删掉后退出码 0。

注意 CI 里的库名是 `ai_group_chat_test`、跑的是 `pytest tests/`（**平铺**，不是 `tests/unit/`）。

### 10.2 触发条件与缺口

| 项 | 现状 |
|----|------|
| 触发路径 | `backend/**`、`frontend/**` 与 workflow 自身 |
| 前端改动（PR） | 类型检查 `tsc --noEmit`；**没有任何测试** |
| 前端改动（push main） | 另有 `deploy-demo.yml` 跑 `vite build --mode demo`（**不含 tsc**）并发布 Pages |
| 文档改动 | 不触发（合理）|
| 依赖安装 | 均已开缓存：后端 `cache: pip`、前端 `cache: npm` |

### 10.3 质量门禁现状

| 门禁 | 现状 |
|------|------|
| 后端测试全绿 | ✅ CI 阻断（`pytest tests/ -q` 非零即红）|
| 前端类型检查 | ✅ CI 阻断（`tsc --noEmit`）——2026-09-13 新增 |
| 代码风格（Ruff / ESLint）| ❌ 未接入 CI |
| 覆盖率阈值 | ❌ 未接入 |
| 前端测试 / E2E | ❌ 未接入 |
| 安全扫描 | ❌ 未接入 |

---

## 附录：手工回归清单

### 功能测试清单

| # | 功能点 | 测试用例 | 状态 | 备注 |
|---|--------|---------|------|------|
| 1 | 用户注册登录 | 正常注册 / 重复用户名 / 错误密码 | ✅ | 注册当前开放（`registration_enabled`）|
| 2 | 消息发送 | 文本 / 图片 / 文件 | ✅ | 图片必须**真被模型看见**，不能只看气泡 |
| 3 | AI 回复 | @AI / 主动唤醒 / 工具调用 | ✅ | |
| 4 | 群视界发图 | 点选 / 拖拽 / Ctrl+V 三种入法 | ✅ | 蒙版高亮 + 当前区块加深 |
| 5 | 群视界发图（模型侧）| 换纯文本模型时应如实说「看不到图」，不编造 | ✅ | 降级靠 `strip_image_parts` |
| 6 | 「新对话」 | 不占轮次、不写旧会话 | ✅ | 走 `POST /worlds/{id}/chat/session/new` |
| 7 | 供应商连接测试 | 公网 / 已登记私网 / 未登记私网 | ✅ | 未登记私网必须零请求 |
| 8 | 管理页获取模型 | 填 base_url → 点「获取模型」| ✅ | key 一次性，不保存 |
| 9 | AI 主动 compact | 消息不足时应回「无需压缩」而非「失败」| ✅ | 空操作不是失败 |
| 10 | 记忆管理 | 增删改查 | ✅ | |

### 回归测试清单

| # | 场景 | 关联版本 | 上次测试 | 状态 |
|---|------|---------|---------|------|
| 1 | 创建群聊 | v0.1.0 | 2026-08-01 | ✅ |
| 2 | 添加 AI | v0.1.0 | 2026-08-01 | ✅ |
| 3 | AI 对话 | v0.1.5 | 2026-08-05 | ✅ |
| 4 | 记忆管理 | v0.2.0 | 2026-08-08 | ✅ |
| 5 | 群视界 | v0.3.0 | 2026-08-10 | ✅ |
| 6 | 群视界发图 + 附件交互 | Unreleased | 2026-09-13 | ✅ |
| 7 | 内网地址围栏 | Unreleased | 2026-09-13 | ✅ |

> **文档版本**: v2.0.0 | **更新日期**: 2026-09-13
> v2.0.0 起本文档只写事实：目录、命令、依赖均可原样执行。
