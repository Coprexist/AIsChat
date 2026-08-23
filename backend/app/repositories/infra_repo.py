"""
基础设施仓库接口（Protocol）+ SQLAlchemy 实现。

系统设置 / 验证码 / API Key 池 / 额度 / 配置持久化等服务共用的通用数据访问接口。
"""
from typing import Any, Protocol
from sqlalchemy.ext.asyncio import AsyncSession


class InfraRepository(Protocol):
    """基础设施数据访问接口（结构化类型）。"""

    async def execute(self, stmt, params: Any = None): ...
    async def get(self, model, pk): ...
    def add(self, obj) -> None: ...
    async def delete(self, obj) -> None: ...
    async def flush(self) -> None: ...
    async def refresh(self, obj) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

    @property
    def session(self) -> AsyncSession:
        """底层会话——仅供跨模块辅助调用桥接。"""
        ...


class SQLAlchemyInfraRepository:
    """SQLAlchemy 基础设施仓库实现。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def execute(self, stmt, params: Any = None):
        if params is not None:
            return await self.session.execute(stmt, params)
        return await self.session.execute(stmt)

    async def get(self, model, pk):
        return await self.session.get(model, pk)

    def add(self, obj) -> None:
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
