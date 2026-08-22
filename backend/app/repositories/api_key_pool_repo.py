"""
API Key 池仓库接口（Protocol）+ SQLAlchemy 实现。
"""
from typing import Optional, Protocol
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.api_key_pool import ApiKeyPool, UserApiAssignment


class ApiKeyPoolRepository(Protocol):
    async def get_assigned_pool_key_name(self, user_id: int) -> Optional[str]: ...


class SQLAlchemyApiKeyPoolRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_assigned_pool_key_name(self, user_id: int) -> Optional[str]:
        result = await self.session.execute(
            select(ApiKeyPool.name)
            .join(UserApiAssignment, UserApiAssignment.pool_key_id == ApiKeyPool.id)
            .where(UserApiAssignment.user_id == user_id)
        )
        return result.scalar()
