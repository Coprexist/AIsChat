"""
AI群聊社交网络 - FastAPI 主应用入口
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import check_db_connection

logger = logging.getLogger("app.main")

def _spawn(coro, name: str) -> asyncio.Task:
    """创建后台任务并监控异常退出（异常不静默——记 ERROR 日志，方便发现 Worker 死亡）"""
    task = asyncio.create_task(coro)

    def _done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error(f"💥 后台任务 {name} 异常退出: {exc!r}", exc_info=exc)

    task.add_done_callback(_done)
    return task



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
        logger.warning(f"⚠️  浏览器服务启动失败（非致命）: {e}", exc_info=True)


async def _stop_browser_service():
    """停止共享 Chromium CDP 服务"""
    try:
        from app.services.infrastructure.plugin_registry import PluginRegistry
        plugin = PluginRegistry.get("browser")
        if plugin is not None:
            await plugin.stop()
    except Exception:
        pass

# 配置日志（路径可配：LOG_FILE env，默认后端目录 app.log）
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

    # 加载 DB 覆盖配置（管理员前端图形化修改的配置组，覆盖 env）
    try:
        from app.database import async_session
        from app.services.infrastructure.app_config_service import load_all_configs
        async with async_session() as cfg_db:
            await load_all_configs(cfg_db)
    except Exception as e:
        logger.warning(f"⚠️ 加载 DB 配置覆盖失败（使用 env 配置）: {e}")

    # 统一插件：磁盘扫描同步 + 技能插件注册（目录即插件，装好即可用）
    try:
        from app.database import async_session
        from app.services.plugin.catalog import sync_plugins_to_db
        from app.services.plugin.skill_bridge import apply_skill_plugins
        async with async_session() as plugin_db:
            changed = await sync_plugins_to_db(plugin_db)
            await apply_skill_plugins(plugin_db)
        logger.info(f"🧩 插件目录同步完成（{changed} 项变更）")
    except Exception as e:
        logger.warning(f"⚠️ 插件目录同步失败（不影响启动）: {e}", exc_info=True)

    # 平台能力版本化（skills/tools 懒加载）：启动时对比内置工具定义，变更则写新版本
    try:
        from app.database import async_session
        async with async_session() as cap_db:
            from app.services.capability_versioning import ensure_platform_version
            v = await ensure_platform_version(cap_db)
            logger.info(f"🧬 平台能力版本: v{v}")
    except Exception as e:
        logger.warning(f"⚠️ 平台能力版本化失败（不影响启动）: {e}", exc_info=True)

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
        logger.warning(f"⚠️ 重置在线用户活跃时间失败: {e}", exc_info=True)

    # 启动 AI 回复 Worker
    from app.ai.response_worker import ai_response_worker
    ai_worker_task = _spawn(ai_response_worker(), "ai_response_worker")

    # 启动向量化 Pipeline Worker
    from app.services.memory.vector_pipeline import vector_pipeline_worker
    vector_worker_task = _spawn(vector_pipeline_worker(), "vector_pipeline_worker")

    # 启动闹钟调度器（心跳机制 — 事件驱动模式）
    from app.ai.alarm import alarm_scheduler
    alarm_scheduler_task = _spawn(alarm_scheduler(), "alarm_scheduler")

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
    audit_cleanup_task = _spawn(audit_cleanup_loop(), "audit_cleanup_loop")

    # 启动每日数据库备份（管理员开关 daily_backup_enabled；保留份数 daily_backup_keep）
    async def daily_backup_loop():
        from app.services.infrastructure.backup_service import create_backup, save_backup, prune_backups
        from app.services.infrastructure.system_settings_service import get_settings
        from app.database import async_session
        while True:
            await asyncio.sleep(86400)  # 24h
            try:
                async with async_session() as backup_db:
                    s = await get_settings(backup_db)
                if not s.get("daily_backup_enabled"):
                    continue
                sql_bytes = await create_backup()
                await save_backup(sql_bytes)
                deleted = prune_backups(int(s.get("daily_backup_keep", 7) or 7))
                logger.info(f"💾 每日备份完成（清理 {deleted} 份过期）")
            except Exception as e:
                logger.warning(f"⚠️ 每日备份失败: {e}", exc_info=True)
    daily_backup_task = _spawn(daily_backup_loop(), "daily_backup_loop")

    # 启动世界懒加载调度器（休眠/唤醒 + 离线时间补偿；手动模式下 no-op）
    from app.services.world.world_scheduler import world_scheduler
    world_scheduler_task = _spawn(world_scheduler(), "world_scheduler")

    # 2.5：恢复常驻世界（config.resident=true）——后端重启后常驻进程继续跑
    try:
        from app.database import async_session as _as
        async with _as() as restore_db:
            from app.services.world.world_resident import manager
            await manager.restore_all(restore_db)
    except Exception as e:
        logger.warning(f"🌐 常驻世界恢复异常: {e}")

    # 世界商城 GitHub 自动同步（配置开启时启动拉取一次最新索引）
    try:
        from app.services.world.market_github import refresh_from_github, get_market_config
        async with async_session() as _mdb:
            _mcfg = await get_market_config(_mdb)
        if _mcfg.get("auto_sync_enabled") and _mcfg.get("github_repo") and _mcfg.get("github_token"):
            async with async_session() as _mdb2:
                r = await refresh_from_github(_mdb2)
            logger.info(f"🏪 商城 GitHub 启动同步完成: +{r.get('added', 0)} 新增")
    except Exception as e:
        logger.warning(f"🏪 商城 GitHub 启动同步失败（不影响启动）: {e}")

    # 启动记忆批量写入 worker
    from app.services.memory.memory_buffer import memory_flush_worker
    memory_flush_task = _spawn(memory_flush_worker(), "memory_flush_worker")

    # 启动孤儿文件清理 worker
    from app.services.content.file_service import orphan_cleanup_worker
    orphan_cleanup_task = _spawn(orphan_cleanup_worker(), "orphan_cleanup_worker")

    # 启动系统指标收集 flush worker
    from app.services.infrastructure.metrics_collector import metrics_flush_worker
    metrics_flush_task = _spawn(metrics_flush_worker(), "metrics_flush_worker")

    # 启动联邦通信（v0.1.2 跨实例直连）
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
    fed_connect_task = _spawn(federation_manager.connect_all_enabled_peers(), "federation_manager")
    fed_heartbeat_task = _spawn(federation_heartbeat(), "federation_heartbeat")
    fed_reconnect_task = _spawn(federation_reconnect(), "federation_reconnect")
    fed_profile_sync_task = _spawn(federation_profile_sync(), "federation_profile_sync")

    # 启动共享 Chromium 服务（所有 AI 共用的浏览器 CDP）
    browser_start_task = _spawn(_start_browser_service(), "_start_browser_service")

    # 启动薄大脑控制系统（心跳）
    from app.services.brain.brain_controller import brain_controller
    brain_init_task = _spawn(brain_controller.initialize(), "brain_controller")

    # 技能运行时：注册为 Skill 事件总线的派发器（自治 Skill 执行引擎）
    from app.services.skill.skill_runtime import skill_runtime
    await skill_runtime.init_dispatcher()

    # 启动时间触发器周期扫描（time 维度的执行引擎）
    from app.services.skill.trigger_sweep import trigger_sweep_worker
    trigger_sweep_task = _spawn(trigger_sweep_worker(), "trigger_sweep_worker")

    logger.info("✅ 后台 worker 已全部启动（含联邦通信）")

    # 发出系统启动完成事件
    from app.services.brain.event_bus import event_bus, EventType
    _spawn(event_bus.emit(EventType.SYSTEM_STARTUP), "event_bus")

    # 启动完成，退出自动维护（但手动维护仍生效）
    if os.path.exists(_MAINTENANCE_AUTO):
        os.remove(_MAINTENANCE_AUTO)
        logger.info("🟢 自动维护已关闭，服务就绪" if not os.path.exists(_MAINTENANCE_SOFT) else "🟡 服务就绪但软维护仍开启")

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
                  fed_heartbeat_task, fed_reconnect_task, fed_profile_sync_task,
                  fed_connect_task, browser_start_task, brain_init_task,
                  trigger_sweep_task]:
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

# 维护模式中间件（文件路径可配：MAINTENANCE_DIR env，默认 /tmp；Linux 容器部署）
_MAINTENANCE_DIR = os.environ.get("MAINTENANCE_DIR", "/tmp")
_MAINTENANCE_AUTO = os.path.join(_MAINTENANCE_DIR, "maintenance_startup")
_MAINTENANCE_SOFT = os.path.join(_MAINTENANCE_DIR, "maintenance_soft")
_MAINTENANCE_ADMIN_HARD = os.path.join(_MAINTENANCE_DIR, "maintenance_admin_hard")
_MAINTENANCE_MSG_FILE = os.path.join(_MAINTENANCE_DIR, "maintenance_msg.json")

def _get_maintenance_msg() -> dict:
    """读取自定义维护文本，不存在则返回默认"""
    try:
        if os.path.exists(_MAINTENANCE_MSG_FILE):
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
async def client_ip_middleware(request, call_next):
    """记录请求 IP 到 contextvar（供审计日志使用）"""
    try:
        from app.utils.auth import set_current_request_ip
        ip = request.client.host if request.client else None
        if ip and request.headers.get("X-Forwarded-For"):
            ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        set_current_request_ip(ip)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"client_ip_middleware error: {e}")
    return await call_next(request)


@app.middleware("http")
async def maintenance_middleware(request, call_next):
    path = request.url.path
    bypass = path in ("/health", "/", "/docs", "/openapi.json") or path.startswith("/admin") or path.startswith("/auth") or path.startswith("/maintenance-msg")

    # 硬维护（自动启动/关闭 或 管理员手动）：503 拦截
    if (os.path.exists(_MAINTENANCE_AUTO) or os.path.exists(_MAINTENANCE_ADMIN_HARD)) and not bypass:
        msg = _get_maintenance_msg()
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"detail": msg["hard_body"], "maintenance": True, "hard": True, "msg": msg}
        )

    # 软维护（手动）：API 正常但前端显示提示
    response = await call_next(request)
    if os.path.exists(_MAINTENANCE_SOFT) and not bypass:
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
