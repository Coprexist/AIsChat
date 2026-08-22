"""
Repository 基类 — 定义通用数据访问接口。

具体实现（如 SQLAlchemy）继承此类，业务服务只依赖接口。
"""
from abc import ABC, abstractmethod


class Repository(ABC):
    """所有仓库的基类。"""

    def __init__(self, session):
        self.session = session

    @abstractmethod
    async def commit(self) -> None:
        ...

    @abstractmethod
    async def rollback(self) -> None:
        ...

    @abstractmethod
    async def flush(self) -> None:
        ...
