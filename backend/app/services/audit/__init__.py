"""
审计日志存储后端抽象

当前实现：PostgresAuditBackend（默认）
可扩展：S3AuditBackend / ElasticsearchBackend / ClickHouseBackend
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession


class AuditStorageBackend(ABC):
    """审计日志存储后端接口"""

    @abstractmethod
    async def write(self, entry: dict, db: AsyncSession | None = None) -> None:
        """写入一条审计日志"""

    @abstractmethod
    async def query(self, filters: dict, page: int, page_size: int, db: AsyncSession | None = None) -> dict:
        """查询审计日志，返回 {"items": [...], "total": int, "page": int, "page_size": int}"""

    @abstractmethod
    async def cleanup(self, before: str, batch_size: int = 5000, db: AsyncSession | None = None) -> dict:
        """清理指定时间之前的日志，返回 {"deleted": int, "cutoff": str}"""

    @abstractmethod
    async def verify_chain(self, limit: int = 1000, db: AsyncSession | None = None) -> dict:
        """验证哈希链完整性，返回 {"valid": bool, "checked": int, "first_broken": int | None}"""


_backend: AuditStorageBackend | None = None


def get_backend() -> AuditStorageBackend:
    if _backend is None:
        raise RuntimeError("审计存储后端未初始化")
    return _backend


def set_backend(backend: AuditStorageBackend) -> None:
    global _backend
    _backend = backend
