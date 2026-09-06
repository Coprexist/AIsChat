"""
Alembic 迁移辅助工具 — 数据库初始化与新旧库检测。

prestart.py（asyncpg）: has_alembic_version_async / has_alembic_version_sync
bootstrap.py（SQLAlchemy AsyncEngine）: prepare_database
"""


async def has_alembic_version_async(conn) -> bool:
    """检查 alembic_version 表是否存在（asyncpg 连接，prestart.py 用）"""
    row = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'alembic_version')"
    )
    return bool(row)


async def has_alembic_version_async_engine(conn) -> bool:
    """检查 alembic_version 表是否存在（SQLAlchemy AsyncConnection）"""
    from sqlalchemy import text
    result = await conn.execute(
        text("SELECT EXISTS(SELECT 1 FROM information_schema.tables "
             "WHERE table_name = 'alembic_version')")
    )
    return bool(result.scalar())


def has_alembic_version_sync(conn) -> bool:
    """检查 alembic_version 表是否存在（同步连接，备用）"""
    from sqlalchemy import text
    result = conn.execute(
        text("SELECT EXISTS(SELECT 1 FROM information_schema.tables "
             "WHERE table_name = 'alembic_version')")
    )
    return bool(result.scalar())


async def prepare_database(engine) -> None:
    """数据库初始化入口（异步，仅 bootstrap.py 调用）。

    PostgreSQL:
      - 新库（alembic_version 不存在）→ create_all + alembic stamp head
      - 旧库 → 跳过（prestart.py 已执行 alembic upgrade head）
    SQLite:
      - create_all（幂等）
    """
    from app.db_providers import get_provider
    provider = get_provider()

    if provider.name == "postgres":
        async with engine.connect() as conn:
            is_new = not await has_alembic_version_async_engine(conn)

        if is_new:
            from app.database import Base
            import app.models  # 确保全部模型注册到 Base.metadata
            import subprocess
            import sys
            from pathlib import Path

            # 创建全部表
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # 标记 Alembic 为 head
            backend_dir = str(Path(__file__).resolve().parent.parent)
            subprocess.run(
                [sys.executable, "-m", "alembic", "stamp", "head"],
                cwd=backend_dir, check=True,
            )
    else:
        # SQLite: ORM create_all 建表（幂等）
        from app.database import Base
        import app.models
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
