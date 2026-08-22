"""
SQLAlchemy Repository 实现。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import Repository


class SQLAlchemyRepository(Repository):
    """基于 SQLAlchemy AsyncSession 的仓库实现。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def flush(self) -> None:
        await self.session.flush()
