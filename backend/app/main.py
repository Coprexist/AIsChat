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

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.bootstrap import lifespan
from app.database import check_db_connection
from app.middleware import register_middlewares
from app.routers import get_all_routers
from app.services.infrastructure.maintenance import maintenance

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# FastAPI 应用实例
# ══════════════════════════════════════════════════════════════

APP_VERSION = os.environ.get("APP_VERSION", "0.3.13")

app = FastAPI(
    title="AI群聊社交网络",
    description="让 AI 拥有完整社交行为的群聊平台",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,       # 使用自定义文档页面（routers/swagger_docs.py）
    redoc_url=None,      # 关闭 ReDoc，避免重复暴露
    # openapi_url 保留默认 "/openapi.json"，方便 API 调试/代码生成
)


# ── CORS + HTTP 中间件（统一注册） ──
register_middlewares(app)


# 注册路由 — 自动发现 routers/ 下所有模块（含 swagger_docs.py）
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求参数校验失败，返回统一格式，不暴露请求体内容"""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未捕获异常统一返回模糊错误，详细堆栈仅记录日志"""
    # 注意：不能使用 exc_info=True，因为异常处理器中 sys.exc_info() 可能已清空
    logger.error(
        "未捕获异常: %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


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
        logger.warning("[WARN] 健康检查异常", exc_info=True)

    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db_ok else "degraded",
            "version": APP_VERSION,
        },
    )
