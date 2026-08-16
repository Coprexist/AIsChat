"""
AI群聊社交网络 - FastAPI 主应用入口

启动/关闭流程见 app/bootstrap.py；维护模式见 app/services/infrastructure/maintenance.py。
"""
import logging
import os
from pathlib import Path

# 日志必须先于任何项目模块 import 配置好（防止模块级日志丢失格式）
_LOG_FILE = os.environ.get(
    "LOG_FILE",
    str(Path(__file__).resolve().parent.parent / "app.log"),
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
    ],
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.bootstrap import lifespan
from app.config import settings
from app.database import check_db_connection
from app.routers import get_all_routers
from app.services.infrastructure.maintenance import maintenance
from app.utils.auth import set_current_request_ip
from app.utils.docs_customizer import get_custom_swagger_html

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# FastAPI 应用实例
# ══════════════════════════════════════════════════════════════

app = FastAPI(
    title="AI群聊社交网络",
    description="让 AI 拥有完整社交行为的群聊平台",
    version="1.0.2",
    lifespan=lifespan,
    docs_url=None,  # 使用自定义文档页面
)


# ── 自定义 Swagger UI（语言选择 + 快捷登录） ──

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui(req: Request):
    lang = req.query_params.get("lang", "en")
    if lang not in ("zh", "en"):
        lang = "en"
    return get_custom_swagger_html(openapi_url="/openapi.json", lang=lang)


@app.get("/docs/zh", include_in_schema=False)
async def swagger_ui_zh():
    return get_custom_swagger_html(openapi_url="/openapi.json", lang="zh")


# CORS 配置：默认允许所有来源（内网部署，保持既有行为）。
# 需要收紧时设 ALLOWED_ORIGINS env（逗号分隔的具体域名），带凭据跨域将精确匹配。
_ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["*"]
        if _ALLOWED_ORIGINS == "*"
        else [o.strip() for o in _ALLOWED_ORIGINS.split(",") if o.strip()]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 中间件 ──

@app.middleware("http")
async def client_ip_middleware(request, call_next):
    """记录请求 IP 到 contextvar（供审计日志使用）"""
    try:
        ip = request.client.host if request.client else None
        if ip and request.headers.get("X-Forwarded-For"):
            ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        set_current_request_ip(ip)
    except Exception as e:
        logger.exception(f"client_ip_middleware error: {e}")
    return await call_next(request)


@app.middleware("http")
async def maintenance_middleware(request, call_next):
    """维护模式拦截（硬维护 503；软维护响应带头，前端据此显隐提示）"""
    path = request.url.path
    # bypass：健康检查/文档/管理/认证/维护消息本身/维护弹窗公开图片
    bypass = (
        path in ("/health", "/", "/docs", "/openapi.json")
        or path.startswith("/admin")
        or path.startswith("/auth")
        or path.startswith("/maintenance-msg")
        or path.startswith("/fs/public")
    )

    # 硬维护（自动启动/关闭 或 管理员手动）：503 拦截
    if maintenance.hard_active() and not bypass:
        msg = maintenance.get_msg()
        return JSONResponse(
            status_code=503,
            content={"detail": msg["hard_body"], "maintenance": True, "hard": True, "msg": msg}
        )

    # 软维护（手动）：API 正常但前端显示提示
    response = await call_next(request)
    if maintenance.is_soft():
        # 所有响应（含 bypass）都带维护头，前端据此显隐提示且不会误判"已关闭"
        response.headers["X-Maintenance"] = "true"
        if not path.startswith("/maintenance-msg"):
            response.headers["X-Maintenance-Hard"] = str(maintenance.hard_active())
    return response


# 注册路由 — 自动发现 routers/ 下所有模块
for _router in get_all_routers():
    app.include_router(_router)


# ── 基础路由 ──

@app.get("/")
async def root():
    """健康检查"""
    return {
        "service": "AI群聊社交网络",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/maintenance-msg")
async def public_maintenance_msg():
    msg = maintenance.get_msg()
    return {
        **msg,
        "hard": maintenance.hard_active(),
        "soft": maintenance.is_soft(),
    }


@app.get("/health")
async def health():
    """健康检查（详细）"""
    db_ok = await check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }
