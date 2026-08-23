"""
API Key 池管理服务 — 管理多个 API Key 的轮换和选择

支持：
  - Key 轮询选择
  - 优先级排序
  - 故障切换
  - 配额管理
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.infra_repo import InfraRepository, SQLAlchemyInfraRepository

logger = logging.getLogger(__name__)


def _ensure_repo(db_or_repo):
    """兼容旧调用：传入 AsyncSession 时包装为 SQLAlchemyInfraRepository。"""
    if isinstance(db_or_repo, AsyncSession):
        return SQLAlchemyInfraRepository(db_or_repo)
    return db_or_repo


class ApiKeyPoolService:
    async def get_next_key(self, db: AsyncSession, agent_id: int) -> dict | None:
        """获取下一个可用的 API Key"""
        db = _ensure_repo(db)
        from app.models.api_key_pool import ApiKeyPool
        from sqlalchemy import select
        result = await db.execute(
            select(ApiKeyPool)
            .where(ApiKeyPool.is_active == True)
            .order_by(ApiKeyPool.priority.desc(), ApiKeyPool.last_used_at)
        )
        key = result.scalar_one_or_none()
        if key:
            key.last_used_at = __import__('datetime').datetime.now()
            db.flush()
            return {
                "id": key.id,
                "provider": key.provider,
                "api_key": key.api_key,
                "base_url": key.base_url,
            }
        return None

    async def add_key(self, db: AsyncSession, agent_id: int, provider: str, api_key: str, base_url: str = "", priority: int = 50) -> dict:
        """添加新的 API Key"""
        db = _ensure_repo(db)
        from app.models.api_key_pool import ApiKeyPool
        new_key = ApiKeyPool(
            agent_id=agent_id,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            priority=priority,
            is_active=True,
        )
        db.add(new_key)
        db.flush()
        return {"id": new_key.id, "provider": new_key.provider}

    async def deactivate_key(self, db: AsyncSession, key_id: int) -> None:
        """停用 API Key"""
        db = _ensure_repo(db)
        from app.models.api_key_pool import ApiKeyPool
        await db.execute(
            ApiKeyPool.__table__.update()
            .where(ApiKeyPool.id == key_id)
            .values(is_active=False)
        )
        db.flush()


api_key_pool_service = ApiKeyPoolService()