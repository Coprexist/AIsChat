"""
系统设置路由
GET /system/settings — 公开（无需登录，供前端获取全局默认语言、登录方式等）
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.infrastructure.system_settings_service import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["系统设置"])


@router.get("/system/settings")
async def get_global_settings(db: AsyncSession = Depends(get_db)):
    """获取平台全局设置（公开，无需认证）"""
    s = await get_settings(db)
    # 公开接口不返回 SMTP 密码等敏感信息
    return {
        "default_language": s.get("default_language", "zh"),
        "default_platform_credit": s.get("default_platform_credit", 0),
        "default_file_quota_mb": s.get("default_file_quota_mb", 100),
        "updated_by": s.get("updated_by"),
        "updated_at": s.get("updated_at"),
        "login_providers": s.get("login_providers", ["direct"]),
        "require_email_verification": s.get("require_email_verification", False),
    }
