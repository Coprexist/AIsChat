"""
AI群聊社交网络 - FastAPI 主应用入口
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import check_db_connection

logger = logging.getLogger("app.main")


async def _start_browser_service():
    """启动共享 Chromium CDP 服务（稍延迟，等数据库就绪）"""
    await asyncio.sleep(3)  # 等数据库和网络就绪
    try:
        from app.services.infrastructure.plugin_registry import PluginRegistry
        plugin = PluginRegistry.get("browser")
        if plugin is None:
            logger.warning("⚠️  Browser 插件未注册，browser 命令将不可用")
            return
        status = await plugin.get_status()
        if status.get("running"):
            logger.info(f"🔍 Chromium CDP 已在运行 (port {status.get('port')})")
            return
        ok = await plugin.start()
        if ok:
            logger.info("🔍 Chromium CDP 已启动，所有 AI 共用")
        else:
            logger.warning("⚠️  Chromium CDP 启动失败，browser 命令将不可用")
    except Exception as e:
        logger.warning(f"⚠️  浏览器服务启动失败（非致命）: {e}")


async def _stop_browser_service():
    """停止共享 Chromium CDP 服务"""
    try:
        from app.services.infrastructure.plugin_registry import PluginRegistry
        plugin = PluginRegistry.get("browser")
        if plugin is not None:
            await plugin.stop()
    except Exception:
        pass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 AI群聊社交网络系统启动中...")
    logger.info(f"  默认聊天模型: {settings.default_chat_model}")
    logger.info(f"  默认工作模型: {settings.default_work_model}")

    # 启动时进入自动维护模式
    open(_MAINTENANCE_AUTO, "w").close()

    # 检查数据库连接
    db_ok = await check_db_connection()
    if db_ok:
        logger.info("✅ 数据库连接正常")
    else:
        logger.warning("⚠️  数据库连接失败，请检查配置")

    # 执行数据库迁移（幂等）
    from app.migration import run_migrations
    await run_migrations()

    # 启动时将 last_active_at=NULL 标记为当前时间（服务器重启前在线的用户）
    from app.database import async_session
    from sqlalchemy import update as sa_update, func
    from app.models.user import User as UserModel
    try:
        async with async_session() as startup_db:
            await startup_db.execute(
                sa_update(UserModel).where(UserModel.last_active_at.is_(None)).values(last_active_at=func.now())
            )
            await startup_db.commit()
        logger.info("✅ 已重置在线用户的上次活跃时间")
    except Exception as e:
        logger.warning(f"⚠️ 重置在线用户活跃时间失败: {e}")

    # 启动 AI 回复 Worker
    from app.ai.response_worker import ai_response_worker
    ai_worker_task = asyncio.create_task(ai_response_worker())

    # 启动向量化 Pipeline Worker
    from app.services.memory.vector_pipeline import vector_pipeline_worker
    vector_worker_task = asyncio.create_task(vector_pipeline_worker())

    # 启动闹钟调度器（心跳机制 — 事件驱动模式）
    from app.ai.alarm import alarm_scheduler
    alarm_scheduler_task = asyncio.create_task(alarm_scheduler())

    # 启动审计日志清理（每天凌晨 3 点检查）
    async def audit_cleanup_loop():
        from app.services.audit_service import cleanup_old_logs
        from app.database import async_session
        while True:
            await asyncio.sleep(86400)  # 24h
            try:
                async with async_session() as clean_db:
                    result = await cleanup_old_logs(clean_db)
                    if result["deleted"]:
                        logging.getLogger(__name__).info(f"审计日志清理: 删除 {result['deleted']} 条")
            except Exception:
                pass
    audit_cleanup_task = asyncio.create_task(audit_cleanup_loop())

    # 启动记忆批量写入 worker
    from app.services.memory.memory_buffer import memory_flush_worker
    memory_flush_task = asyncio.create_task(memory_flush_worker())

    # 启动孤儿文件清理 worker
    from app.services.content.file_service import orphan_cleanup_worker
    orphan_cleanup_task = asyncio.create_task(orphan_cleanup_worker())

    # 启动系统指标收集 flush worker
    from app.services.infrastructure.metrics_collector import metrics_flush_worker
    metrics_flush_task = asyncio.create_task(metrics_flush_worker())

    # 启动联邦通信（v0.3.0 跨实例直连）
    from app.database import async_session
    from app.services.federation.federation_service import initialize_instance
    from app.services.federation.federation_manager import (
        federation_manager,
        federation_heartbeat,
        federation_reconnect,
        federation_profile_sync,
    )
    async with async_session() as db:
        await initialize_instance(db)
    # 连接所有已启用的对等端（在后台执行，不阻塞启动）
    asyncio.create_task(federation_manager.connect_all_enabled_peers())
    fed_heartbeat_task = asyncio.create_task(federation_heartbeat())
    fed_reconnect_task = asyncio.create_task(federation_reconnect())
    fed_profile_sync_task = asyncio.create_task(federation_profile_sync())

    # 启动共享 Chromium 服务（所有 AI 共用的浏览器 CDP）
    asyncio.create_task(_start_browser_service())

    logger.info("✅ 后台 worker 已全部启动（含联邦通信）")

    # 发出系统启动完成事件
    from app.services.brain.event_bus import event_bus, EventType
    asyncio.create_task(event_bus.emit(EventType.SYSTEM_STARTUP))

    # 启动完成，退出自动维护（但手动维护仍生效）
    if _os.path.exists(_MAINTENANCE_AUTO):
        _os.remove(_MAINTENANCE_AUTO)
        logger.info("🟢 自动维护已关闭，服务就绪" if not _os.path.exists(_MAINTENANCE_SOFT) else "🟡 服务就绪但软维护仍开启")

    yield

    # 进入关闭流程，自动维护
    logger.info("👋 系统关闭，正在停止后台 worker...")
    open(_MAINTENANCE_AUTO, "w").close()

    logger.info("👋 系统关闭，正在停止后台 worker...")
    # 发出系统关闭事件
    try:
        from app.services.brain.event_bus import event_bus, EventType
        await event_bus.emit(EventType.SYSTEM_SHUTDOWN)
    except Exception:
        pass

    # 优雅关闭：排空记忆缓冲区
    try:
        from app.services.memory.memory_buffer import drain_buffer_on_shutdown
        await drain_buffer_on_shutdown()
    except Exception:
        pass
    # 先断开所有联邦连接
    try:
        await federation_manager.disconnect_all()
    except Exception:
        pass
    for task in [ai_worker_task, vector_worker_task, alarm_scheduler_task, audit_cleanup_task,
                  memory_flush_task, metrics_flush_task, orphan_cleanup_task,
                  fed_heartbeat_task, fed_reconnect_task]:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # 停止共享 Chromium
    await _stop_browser_service()
    logger.info("后台 worker 已停止")


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
    from app.utils.docs_customizer import get_custom_swagger_html
    lang = req.query_params.get("lang", "en")
    if lang not in ("zh", "en"):
        lang = "en"
    return get_custom_swagger_html(openapi_url="/openapi.json", lang=lang)


@app.get("/docs/zh", include_in_schema=False)
async def swagger_ui_zh():
    from app.utils.docs_customizer import get_custom_swagger_html
    return get_custom_swagger_html(openapi_url="/openapi.json", lang="zh")

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 维护模式中间件
import os as _os
_MAINTENANCE_AUTO = "/tmp/maintenance_startup"
_MAINTENANCE_SOFT = "/tmp/maintenance_soft"
_MAINTENANCE_ADMIN_HARD = "/tmp/maintenance_admin_hard"
_MAINTENANCE_MSG_FILE = "/tmp/maintenance_msg.json"

def _get_maintenance_msg() -> dict:
    """读取自定义维护文本，不存在则返回默认"""
    try:
        if _os.path.exists(_MAINTENANCE_MSG_FILE):
            with open(_MAINTENANCE_MSG_FILE) as f:
                return json.loads(f.read())
    except Exception:
        pass
    return {
        "hard_title": "正在更新",
        "hard_body": "服务器正在更新，稍等一下就好~",
        "hard_color": "#f59e0b", "hard_text_color": "#ffffff",
        "hard_image": "", "hard_style": "popup",
        "soft_text": "服务器正在调整，功能可能偶尔不稳定",
        "soft_color": "#f59e0b", "soft_text_color": "#ffffff",
        "soft_style": "banner", "soft_once": False,
    }

@app.middleware("http")
async def maintenance_middleware(request, call_next):
    path = request.url.path
    bypass = path in ("/health", "/", "/docs", "/openapi.json") or path.startswith("/admin") or path.startswith("/auth") or path.startswith("/maintenance-msg")

    # 硬维护（自动启动/关闭 或 管理员手动）：503 拦截
    if (_os.path.exists(_MAINTENANCE_AUTO) or _os.path.exists(_MAINTENANCE_ADMIN_HARD)) and not bypass:
        msg = _get_maintenance_msg()
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"detail": msg["hard_body"], "maintenance": True, "hard": True, "msg": msg}
        )

    # 软维护（手动）：API 正常但前端显示提示
    response = await call_next(request)
    if _os.path.exists(_MAINTENANCE_SOFT) and not bypass:
        response.headers["X-Maintenance"] = "true"
    return response


# 注册路由 — 自动发现 routers/ 下所有模块
from app.routers import get_all_routers
for _router in get_all_routers():
    app.include_router(_router)


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
    return _get_maintenance_msg()


@app.get("/health")
async def health():
    """健康检查（详细）"""
    db_ok = await check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }
