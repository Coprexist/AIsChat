"""
AI 代理仓库接口（Protocol）+ SQLAlchemy 实现。
"""
from typing import Any, Protocol
from sqlalchemy.ext.asyncio import AsyncSession


class AgentRepository(Protocol):
    async def execute(self, stmt, params=None): ...
    async def get(self, model, pk): ...
    def add(self, obj) -> None: ...
    async def flush(self) -> None: ...
    async def refresh(self, obj) -> None: ...
    async def commit(self) -> None: ...
    async def delete(self, obj) -> None: ...
    def begin_nested(self): ...


class SQLAlchemyAgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, stmt, params=None):
        if params is not None:
            return await self.session.execute(stmt, params)
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

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    def begin_nested(self):
        return self.session.begin_nested()
