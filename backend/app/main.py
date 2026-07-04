"""
AI群聊社交网络 - FastAPI 主应用入口
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import check_db_connection

logger = logging.getLogger("app.main")


async def _start_browser_service():
    """启动共享 Chromium CDP 服务（稍延迟，等数据库就绪）"""
    await asyncio.sleep(3)  # 等数据库和网络就绪
    try:
        from app.services.browser_service import start, is_running, CDP_PORT
        if is_running():
            logger.info(f"🔍 Chromium CDP 已在运行 (port {CDP_PORT})")
            return
        ok = await start()
        if ok:
            logger.info(f"🔍 Chromium CDP 已启动 (port {CDP_PORT})，所有 AI 共用")
            # 设置环境变量供 opencli 使用
            import os
            os.environ["OPENCLI_CDP_ENDPOINT"] = f"http://127.0.0.1:{CDP_PORT}"
        else:
            logger.warning("⚠️  Chromium CDP 启动失败，browser 命令将不可用")
    except Exception as e:
        logger.warning(f"⚠️  浏览器服务启动失败（非致命）: {e}")


async def _stop_browser_service():
    """停止共享 Chromium CDP 服务"""
    try:
        from app.services.browser_service import stop
        await stop()
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

    # 启动 AI 回复 Worker
    from app.services.ai_response_worker import ai_response_worker
    ai_worker_task = asyncio.create_task(ai_response_worker())

    # 启动向量化 Pipeline Worker
    from app.services.vector_pipeline import vector_pipeline_worker
    vector_worker_task = asyncio.create_task(vector_pipeline_worker())

    # 启动闹钟调度器（心跳机制 — 事件驱动模式）
    from app.services.ai_response_worker import alarm_scheduler
    alarm_scheduler_task = asyncio.create_task(alarm_scheduler())

    # 启动记忆批量写入 worker
    from app.services.memory_buffer import memory_flush_worker
    memory_flush_task = asyncio.create_task(memory_flush_worker())

    # 启动孤儿文件清理 worker
    from app.services.file_service import orphan_cleanup_worker
    orphan_cleanup_task = asyncio.create_task(orphan_cleanup_worker())

    # 启动系统指标收集 flush worker
    from app.services.metrics_collector import metrics_flush_worker
    metrics_flush_task = asyncio.create_task(metrics_flush_worker())

    # 启动联邦通信（v0.3.0 跨实例直连）
    from app.database import async_session
    from app.services.federation_service import initialize_instance
    from app.services.federation_manager import (
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

    # 启动完成，退出自动维护（但手动维护仍生效）
    if _os.path.exists(_MAINTENANCE_AUTO):
        _os.remove(_MAINTENANCE_AUTO)
        logger.info("🟢 自动维护已关闭，服务就绪" if not _os.path.exists(_MAINTENANCE_SOFT) else "🟡 服务就绪但软维护仍开启")

    yield

    # 进入关闭流程，自动维护
    logger.info("👋 系统关闭，正在停止后台 worker...")
    open(_MAINTENANCE_AUTO, "w").close()

    logger.info("👋 系统关闭，正在停止后台 worker...")
    # 优雅关闭：排空记忆缓冲区
    try:
        from app.services.memory_buffer import drain_buffer_on_shutdown
        await drain_buffer_on_shutdown()
    except Exception:
        pass
    # 先断开所有联邦连接
    try:
        await federation_manager.disconnect_all()
    except Exception:
        pass
    for task in [ai_worker_task, vector_worker_task, alarm_scheduler_task,
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


app = FastAPI(
    title="AI群聊社交网络",
    description="让 AI 拥有完整社交行为的群聊平台",
    version="1.0.2",
    lifespan=lifespan,
)

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
        "soft_text": "服务器正在调整，功能可能偶尔不稳定",
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
            content={"detail": msg["hard_body"], "maintenance": True, "hard": True}
        )

    # 软维护（手动）：API 正常但前端显示提示
    response = await call_next(request)
    if _os.path.exists(_MAINTENANCE_SOFT) and not bypass:
        response.headers["X-Maintenance"] = "true"
    return response


# 注册路由
from app.routers import auth, agents, groups, ws, user, memories, files, admin, search, dm, federation_ws, conversation_log, friends, system, invitations

app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(groups.router)
app.include_router(ws.router)
app.include_router(user.router)
app.include_router(memories.router)
app.include_router(files.router)
app.include_router(admin.router)
app.include_router(search.router)
app.include_router(dm.router)
app.include_router(federation_ws.router)
app.include_router(conversation_log.router)
app.include_router(friends.router)
app.include_router(system.router)
app.include_router(invitations.router)


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
