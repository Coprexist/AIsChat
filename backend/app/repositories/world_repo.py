"""
世界仓库接口（Protocol）+ SQLAlchemy 实现。
"""
from typing import Optional, Protocol
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.world import World, WorldBinding, WorldAI, WorldAgent, WorldData


class WorldRepository(Protocol):
    async def execute(self, stmt): ...
    async def add(self, obj): ...
    async def delete(self, obj): ...
    async def flush(self): ...
    async def refresh(self, obj): ...
    async def commit(self): ...
    async def get(self, model, pk): ...

    @property
    def session(self) -> AsyncSession:
        """底层会话——仅供跨模块辅助调用桥接（如 chat 模块）。"""
        ...


class SQLAlchemyWorldRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(self, stmt):
        return await self.session.execute(stmt)

    async def add(self, obj):
        self.session.add(obj)

    async def delete(self, obj):
        await self.session.delete(obj)

    async def flush(self):
        await self.session.flush()

    async def refresh(self, obj):
        await self.session.refresh(obj)

    async def commit(self):
        await self.session.commit()

    async def get(self, model, pk):
        return await self.session.get(model, pk)

    @property
    def session(self) -> AsyncSession:
        return self._session
