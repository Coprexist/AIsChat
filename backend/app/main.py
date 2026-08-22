"""
AI群聊社交网络 - FastAPI 主应用入口

启动/关闭流程见 app/bootstrap.py；中间件见 app/middleware.py；
维护模式见 app/services/infrastructure/maintenance.py。
"""
# 日志必须先于任何项目模块 import 配置好（防止模块级日志丢失格式）
from app.logging_config import setup_logging
setup_logging()

import asyncio
import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.bootstrap import lifespan
from app.config import settings
from app.database import check_db_connection
from app.middleware import register_middlewares
from app.routers import get_all_routers
from app.services.infrastructure.maintenance import maintenance

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# FastAPI 应用实例
# ══════════════════════════════════════════════════════════════

# 应用版本：优先读环境变量（CI/CD 注入），回退硬编码默认值
APP_VERSION = os.environ.get("APP_VERSION", "0.3.12")

app = FastAPI(
    title="AI群聊社交网络",
    description="让 AI 拥有完整社交行为的群聊平台",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,  # 使用自定义文档页面
)


# ── 自定义 Swagger UI（语言选择 + 快捷登录） ──

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui(req: Request):
    from app.utils.docs_customizer import get_custom_swagger_html
    lang = req.query_params.get("lang", "en")
    if lang not in ("zh", "en"):
        lang = "en"
    return get_custom_swagger_html(openapi_url="/openapi.json", lang=lang)


@app.get("/docs/zh", include_in_schema=False)
async def swagger_ui_zh():
    from app.utils.docs_customizer import get_custom_swagger_html
    return get_custom_swagger_html(openapi_url="/openapi.json", lang="zh")


# ── CORS + HTTP 中间件（统一注册） ──
register_middlewares(app)


# 注册路由 — 自动发现 routers/ 下所有模块
for _router in get_all_routers():
    app.include_router(_router)


# ══════════════════════════════════════════════════════════════
# 全局异常处理器（统一 JSON 错误格式）
# ══════════════════════════════════════════════════════════════

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTPException 按原状态码返回 detail（保持 FastAPI 默认行为）"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未捕获异常统一返回模糊错误，详细堆栈仅记录日志"""
    logger.error(
        f"未捕获异常: {request.method} {request.url.path}",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


# ── 请求日志 + Request ID 中间件 ──

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """为每个请求生成 Request ID，记录请求耗时"""
    request_id = str(uuid.uuid4())[:8]
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} → "
        f"{response.status_code} ({elapsed_ms:.0f}ms)"
    )
    return response


# ══════════════════════════════════════════════════════════════
# 基础路由
# ══════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """服务根路径"""
    return {
        "service": "AI群聊社交网络",
        "version": APP_VERSION,
        "status": "running",
    }


@app.get("/maintenance-msg")
async def public_maintenance_msg():
    """维护状态（仅返回前端需要的精简信息）"""
    msg = maintenance.get_msg()
    return {
        "msg": msg.get("hard_body", ""),
        "hard": maintenance.hard_active(),
    }


@app.get("/health")
async def health():
    """健康检查（5s 超时保护，标准 HTTP 状态码）"""
    try:
        db_ok = await asyncio.wait_for(check_db_connection(), timeout=5.0)
    except asyncio.TimeoutError:
        db_ok = False
        logger.warning("[WARN] 健康检查: 数据库查询超时（5s）")
    except Exception as e:
        db_ok = False
        logger.warning(f"[WARN] 健康检查异常: {e}")

    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db_ok else "degraded",
            "version": APP_VERSION,
        },
    )
