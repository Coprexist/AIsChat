"""
共享路由依赖 — Agent 访问校验等

routers/ 自动发现只注册含 `router` 变量的模块，本文件不会产生路由。
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.user_repo import UserRepository, SQLAlchemyUserRepository
from app.repositories.system_settings_repo import SystemSettingsRepository, SQLAlchemySystemSettingsRepository
from app.repositories.verification_repo import VerificationRepository, SQLAlchemyVerificationRepository
from app.repositories.api_key_pool_repo import ApiKeyPoolRepository, SQLAlchemyApiKeyPoolRepository
from app.repositories.friend_repo import FriendRepository, SQLAlchemyFriendRepository
from app.repositories.world_repo import WorldRepository, SQLAlchemyWorldRepository
from app.repositories.invitation_repo import InvitationRepository, SQLAlchemyInvitationRepository
from app.repositories.search_repo import SearchRepository, SQLAlchemySearchRepository
from app.repositories.export_repo import ExportRepository, SQLAlchemyExportRepository
from app.repositories.content_repo import ContentRepository, SQLAlchemyContentRepository
from app.utils.auth import get_current_user
from app.services.agent.agent_service import get_agent


async def require_agent_access(
    agent_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """依赖注入：获取 Agent 并校验访问权限（owner / 合作者，管理员可绕过）"""
    result = await get_agent(db, agent_id)
    if result.is_err():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error)
    agent = result.ok
    if agent.owner_id != current_user["user_id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该 AI")
    return agent


async def get_user_repo(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """依赖注入：构造用户仓库。"""
    return SQLAlchemyUserRepository(db)


async def get_system_settings_repo(db: AsyncSession = Depends(get_db)) -> SystemSettingsRepository:
    """依赖注入：构造系统设置仓库。"""
    return SQLAlchemySystemSettingsRepository(db)


async def get_verification_repo(db: AsyncSession = Depends(get_db)) -> VerificationRepository:
    """依赖注入：构造验证码仓库。"""
    return SQLAlchemyVerificationRepository(db)


async def get_api_key_pool_repo(db: AsyncSession = Depends(get_db)) -> ApiKeyPoolRepository:
    """依赖注入：构造 API Key 池仓库。"""
    return SQLAlchemyApiKeyPoolRepository(db)


async def get_friend_repo(db: AsyncSession = Depends(get_db)) -> FriendRepository:
    """依赖注入：构造好友仓库。"""
    return SQLAlchemyFriendRepository(db)


async def get_world_repo(db: AsyncSession = Depends(get_db)) -> WorldRepository:
    return SQLAlchemyWorldRepository(db)


async def get_invitation_repo(db: AsyncSession = Depends(get_db)) -> InvitationRepository:
    """依赖注入：构造群邀请仓库。"""
    return SQLAlchemyInvitationRepository(db)


async def get_search_repo(db: AsyncSession = Depends(get_db)) -> SearchRepository:
    """依赖注入：构造搜索仓库。"""
    return SQLAlchemySearchRepository(db)


async def get_export_repo(db: AsyncSession = Depends(get_db)) -> ExportRepository:
    """依赖注入：构造导出仓库。"""
    return SQLAlchemyExportRepository(db)


async def get_content_repo(db: AsyncSession = Depends(get_db)) -> ContentRepository:
    """依赖注入：构造内容仓库。"""
    return SQLAlchemyContentRepository(db)
