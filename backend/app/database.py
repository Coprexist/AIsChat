"""
数据库连接管理模块
使用 SQLAlchemy 2.0 异步引擎，存储后端由 DB_BACKEND 选择（postgres | sqlite）。
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
from app.db_providers import get_provider
import logging

logger = logging.getLogger(__name__)

# 当前生效的存储后端
provider = get_provider()

# 异步引擎
# 注意：SQLite(aiosqlite) 使用 NullPool，不接受 pool_size/max_overflow/pool_pre_ping 参数
if provider.name == "postgres":
    engine = create_async_engine(
        provider.async_engine_url(),
        pool_size=10,
        max_overflow=40,
        pool_pre_ping=True,
        echo=False,
    )
else:
    engine = create_async_engine(
        provider.async_engine_url(),
        echo=False,
    )

# 会话工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_connection() -> bool:
    """检查数据库连接是否正常"""
    try:
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        return True
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return False
