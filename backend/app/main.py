"""
AI群聊社交网络 - FastAPI 主应用入口

启动/关闭流程见 app/bootstrap.py；中间件见 app/middleware.py；
维护模式见 app/services/infrastructure/maintenance.py。
"""
import logging
import os
from logging.handlers import RotatingFileHandler
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
        # 滚动文件日志：单文件 10MB，保留 5 份，避免 app.log 无限增长占满磁盘
        RotatingFileHandler(_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"),
    ],
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import lifespan
from app.config import settings
from app.database import check_db_connection
from app.middleware import register_middlewares
from app.routers import get_all_routers
from app.services.infrastructure.maintenance import maintenance
from app.utils.docs_customizer import get_custom_swagger_html

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# FastAPI 应用实例
# ══════════════════════════════════════════════════════════════

# 应用版本（单一来源，与 CHANGELOG 当前阶段保持一致，发版时同步更新）
APP_VERSION = "0.3.10"

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
    lang = req.query_params.get("lang", "en")
    if lang not in ("zh", "en"):
        lang = "en"
    return get_custom_swagger_html(openapi_url="/openapi.json", lang=lang)


@app.get("/docs/zh", include_in_schema=False)
async def swagger_ui_zh():
    return get_custom_swagger_html(openapi_url="/openapi.json", lang="zh")


# ── CORS（默认不启用：同源代理部署不需要跨域） ──
# ALLOWED_ORIGINS（逗号分隔）配置后启用：
#   - 含 "*"：允许所有来源，但不携带凭据（浏览器规范禁止 "*" 与凭据组合）
#   - 显式域名列表：允许带凭据的精确跨域
_origins = settings.allowed_origins
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials="*" not in _origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 中间件（IP 追踪 + 维护模式拦截）
register_middlewares(app)


# 注册路由 — 自动发现 routers/ 下所有模块
for _router in get_all_routers():
    app.include_router(_router)


# ── 基础路由 ──

@app.get("/")
async def root():
    """健康检查"""
    return {
        "service": "AI群聊社交网络",
        "version": APP_VERSION,
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
