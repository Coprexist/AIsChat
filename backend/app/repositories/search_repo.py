"""
搜索仓库接口（Protocol）+ SQLAlchemy 实现。
"""
from typing import Protocol
from sqlalchemy.ext.asyncio import AsyncSession


class SearchRepository(Protocol):
    """全局搜索数据访问接口（结构化类型）。"""

    async def execute(self, stmt): ...


class SQLAlchemySearchRepository:
    """SQLAlchemy 搜索仓库实现。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, stmt):
        return await self.session.execute(stmt)
