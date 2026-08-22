"""
基础系统路由：健康检查、维护消息、服务根路径。
"""
import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import check_db_connection
from app.services.infrastructure.maintenance import maintenance

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def root():
    """服务根路径"""
    return {
        "service": "AI群聊社交网络",
        "version": settings.app_version,
        "status": "running",
    }


@router.get("/maintenance-msg")
async def public_maintenance_msg():
    """维护状态公开接口"""
    return maintenance.get_public_message()


@router.get("/health")
async def health():
    """健康检查：数据库可用性，5s 超时保护"""
    try:
        db_ok = await asyncio.wait_for(check_db_connection(), timeout=5.0)
    except asyncio.TimeoutError:
        db_ok = False
        logger.warning("健康检查超时: 数据库查询超过 5s")
    except Exception as e:
        db_ok = False
        logger.warning("健康检查异常: %s", e)

    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db_ok else "degraded",
            "version": settings.app_version,
        },
    )
