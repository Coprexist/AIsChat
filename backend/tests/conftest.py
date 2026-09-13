"""
pytest 全局配置 — 测试用独立数据库 ai_group_chat_test（不碰生产数据）

- 连接串**必须由环境变量提供**：真实口令不进仓库（历史版本曾把口令写死在此文件，
  已进 git 历史，口令没轮换过就等于公开）
- fixture `test_db`：每个测试独立事务回滚（或建表）
- 迁移测试需要真实建表：用 alembic upgrade head 到测试库
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).parent.parent  # backend/
sys.path.insert(0, str(BACKEND_DIR))


def _require_test_database_url() -> str:
    """测试库连接串必须显式传入（跑法见 docs/guides/test_strategy.md）。"""
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "缺少 TEST_DATABASE_URL：测试会 drop_all + TRUNCATE，必须显式指向测试库；"
            "跑法见 docs/guides/test_strategy.md"
        )
    return url


TEST_DATABASE_URL = _require_test_database_url()
# sync 驱动由 async 连接串推导：少传一个环境变量，也少一处可写错的地方
TEST_DATABASE_URL_SYNC = (
    os.environ.get("TEST_DATABASE_URL_SYNC") or TEST_DATABASE_URL.replace("+asyncpg", "")
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
