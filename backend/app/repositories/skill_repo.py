"""
Skill 仓库接口（Protocol）+ SQLAlchemy 实现。

思维技能相关服务（skill_service / skill_engine / trigger_engine / attention_system）
共用的通用数据访问接口。
"""
from typing import Any, Protocol
from sqlalchemy.ext.asyncio import AsyncSession


class SkillRepository(Protocol):
    """Skill 数据访问接口（结构化类型）。"""

    async def execute(self, stmt, params: Any = None): ...
    async def get(self, model, pk): ...
    async def add(self, obj) -> None: ...
    async def delete(self, obj) -> None: ...
    async def flush(self) -> None: ...
    async def refresh(self, obj) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SQLAlchemySkillRepository:
    """SQLAlchemy Skill 仓库实现。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, stmt, params: Any = None):
        if params is not None:
            return await self.session.execute(stmt, params)
        return await self.session.execute(stmt)

    async def get(self, model, pk):
        return await self.session.get(model, pk)

    async def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
