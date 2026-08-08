"""
pytest 全局配置 — 测试用独立数据库 ai_group_chat_test（不碰生产数据）

- 所有测试通过 TEST_DATABASE_URL 连测试库
- fixture `test_db`：每个测试独立事务回滚（或建表）
- 迁移测试需要真实建表：用 alembic upgrade head 到测试库
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).parent.parent  # backend/
sys.path.insert(0, str(BACKEND_DIR))

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ai_chat:lmwu0yIBxAiAqAP0pYfeFjMAEe8@localhost:5432/ai_group_chat_test",
)
TEST_DATABASE_URL_SYNC = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    "postgresql://ai_chat:lmwu0yIBxAiAqAP0pYfeFjMAEe8@localhost:5432/ai_group_chat_test",
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_URL_SYNC"] = TEST_DATABASE_URL_SYNC
os.environ["JWT_SECRET_KEY"] = "test-secret"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def migrated_db():
    """用模型 metadata 建全量表（不跑 alembic：历史迁移链无法从空库重建，模型即 schema）"""
    from sqlalchemy.ext.asyncio import create_async_engine
    import app.models  # noqa: F401  确保全部模型注册到 Base.metadata
    from app.database import Base

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield
