"""
Alembic 迁移辅助工具 — 新旧库检测。

prestart.py（asyncpg）和 bootstrap.py（SQLAlchemy）共享同一判断逻辑：
  alembic_version 表不存在 → 全新库
  alembic_version 表存在   → 已有库
"""


async def has_alembic_version_async(conn) -> bool:
    """异步连接（asyncpg）检查 alembic_version 表是否存在"""
    row = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'alembic_version')"
    )
    return bool(row)


def has_alembic_version_sync(conn) -> bool:
    """同步连接（SQLAlchemy）检查 alembic_version 表是否存在"""
    from sqlalchemy import text
    result = conn.execute(
        text("SELECT EXISTS(SELECT 1 FROM information_schema.tables "
             "WHERE table_name = 'alembic_version')")
    )
    return bool(result.scalar())
