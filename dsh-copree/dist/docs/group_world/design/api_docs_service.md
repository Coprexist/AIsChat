# 接口文档服务（/kb + docx 导出 + pandoc）

> **面向**：后端开发者（维护）与管理员（pandoc 安装）
> **版本**：v1.0 ｜ **日期**：2026-08-11
> **关联**：[群视界 API 文档索引](../api/world_api_docs.md)（内容文档）、`troubleshooting.md` 第九章（422 坑）

## 一、功能概述

给管理员/开发者看的**平台接口文档**：管理页 → 插件管理内嵌「接口文档」区块（DocExportTab），支持：

1. **📖 查看**：分区列表 + 分区详细文档（Markdown 渲染）
2. **下载**：md 原文、docx（pandoc 转换，可选能力）
3. **安装 pandoc**：管理员一键在线安装（apt-get 后台执行，轮询状态），未装时普通用户不显示 docx 选项

## 二、架构

```
frontend/src/components/DocExportTab.tsx   →  api.get('/kb/status' | '/kb/install' | '/kb/convert')
backend/app/routers/api_docs.py            →  prefix="/kb"，路由："" /{section_id} /status /install /convert
backend/app/services/world/api_docs/       →  文档内容（sections/01-*.md … 09-*.md，随 git 跟踪）
backend/app/services/world/world_api_docs.py → 运行时读取（view_api_doc 工具与 /kb 共用同一份）
```

- 文档内容在**代码区**（`services/world/api_docs/`），改完**即时生效，无需重启**（`view_section` 每次读盘）
- 后端路由改动需重启容器生效；**建议 `docker compose up -d --force-recreate backend`**（`restart` 可能留孤儿 uvicorn 占 8000，见 troubleshooting 第九章）

## 三、路径规则（血的教训，2026-08-11）

| 层 | 路径 |
|----|------|
| 前端 api.get 路径 | `/kb/status`（**不带** /api 前缀） |
| 浏览器实际请求 | `/api/kb/status`（api client base 自动加 `/api`） |
| vite proxy rewrite | 剥掉 `/api` → 后端收到 `/kb/status` |
| 后端 router prefix | `/kb`（必须 = rewrite 后的路径） |

**约定**：
- 前端 `api.get` 路径**不要带 `/api` 前缀**——否则浏览器发 `/api/api/kb/...` 双段，此前被误判为服务器 nginx 拦截，实际与 nginx 无关（见下）
- 后端 prefix 与 vite rewrite 结果必须一致，否则 404
- 路径里避免 `export` 等词（曾有服务器层规则命中 `/export/` 子路径的误判历史，现路径已无此词）

## 四、⚠️ 422 local_kw 坑（2026-08-11 实锤根因）

**症状**：`/kb/status`、`/kb/install` 带 token → `422 {"detail":[{"type":"missing","loc":["query","local_kw"],...}]}`；不带 token → 401；源码全盘 grep 不到 `local_kw`；看起来像 nginx/网关拦截（响应头 `server: nginx`），改路径、换词、查反代都无效。

**根因**：路由里 `db: AsyncSession = Depends(_async_session)`——`_async_session` 是 **`async_sessionmaker` 实例**。FastAPI 检查依赖 callable 签名时，SQLAlchemy 的 `sessionmaker.__call__(self, **local_kw)` 里的 `**local_kw` 被当成**必填 query 参数** → 过鉴权后参数校验必 422。

**修复**：一律 `Depends(get_db)`（`app.database` 的 async generator，自带 commit/rollback）。

```python
# ❌ Depends(_async_session)   # sessionmaker 实例 → local_kw 必填 422
# ✅ Depends(get_db)
```

**快速定位**（打印运行中路由的依赖树）：

```bash
docker compose exec backend python -c "
from app.main import app
for r in app.routes:
    if getattr(r, 'path', '') == '/kb/status':
        print(r.endpoint); print(r.dependant)
"
```

依赖树出现 `call=async_sessionmaker(...)` + `query_params=[ModelField(name='local_kw', ...)]` 即实锤。

**预防**：数据库会话禁止 `Depends(<sessionmaker实例>)`；全局排查 `grep -rn "Depends(_async_session)\|Depends(async_session)" backend/app --include='*.py'`。

## 五、运维

| 事项 | 说明 |
|------|------|
| pandoc 安装 | 管理页插件管理一键装（apt-get 后台），`/kb/status` 返回 `docx_available/installing/install_error` |
| 文档更新 | 改 `services/world/api_docs/sections/` 即时生效，无需重启 |
| 路由/代码更新 | force-recreate backend |
| 排查 | `troubleshooting.md` 第九章（422 local_kw）、第十章节（错误码速查） |
