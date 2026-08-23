"""
群邀请仓库接口（Protocol）+ SQLAlchemy 实现。
"""
from typing import Protocol
from sqlalchemy.ext.asyncio import AsyncSession


class InvitationRepository(Protocol):
    """群邀请数据访问接口（结构化类型）。"""

    async def execute(self, stmt): ...
    async def get(self, model, pk): ...
    def add(self, obj) -> None: ...
    async def flush(self) -> None: ...
    async def refresh(self, obj) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

    @property
    def session(self) -> AsyncSession:
        """底层会话——仅供跨模块辅助调用桥接（如发 DM 卡片）。"""
        ...


class SQLAlchemyInvitationRepository:
    """SQLAlchemy 群邀请仓库实现。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, stmt):
        return await self.session.execute(stmt)

    async def get(self, model, pk):
        return await self.session.get(model, pk)

    def add(self, obj) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
