"""
用户仓库接口 + SQLAlchemy 实现。
"""
from abc import abstractmethod
from typing import Optional

from sqlalchemy import select, func

from app.models.user import User
from app.repositories.base import Repository
from app.repositories.sqlalchemy_base import SQLAlchemyRepository


class UserRepository(Repository):
    """用户数据访问接口。"""

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[User]:
        ...

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        ...

    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[User]:
        ...

    @abstractmethod
    async def count_non_system_users(self) -> int:
        ...

    @abstractmethod
    async def add(self, user: User) -> None:
        ...

    @abstractmethod
    async def refresh(self, user: User) -> None:
        ...


class SQLAlchemyUserRepository(SQLAlchemyRepository, UserRepository):
    """SQLAlchemy 用户仓库实现。"""

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def count_non_system_users(self) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.type != 'system')
        )
        return result.scalar() or 0

    async def add(self, user: User) -> None:
        self.session.add(user)

    async def refresh(self, user: User) -> None:
        await self.session.refresh(user)
