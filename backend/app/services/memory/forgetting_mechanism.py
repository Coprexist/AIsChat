"""
遗忘机制 — 根据遗忘曲线衰减记忆重要性

规则：
  - 基于时间和访问频率计算衰减因子
  - 更新记忆的 value_score 字段
  - 删除 value_score 低于阈值的记忆
  
阈值：
  - 结构记忆：0.1
  - 向量记忆 - rough：0.1
  - 向量记忆 - detail：0.05
"""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.memory_repo import MemoryRepository, SQLAlchemyMemoryRepository

logger = logging.getLogger(__name__)


def _ensure_repo(db_or_repo):
    """兼容旧调用：传入 AsyncSession 时包装为 SQLAlchemyMemoryRepository。"""
    if isinstance(db_or_repo, AsyncSession):
        return SQLAlchemyMemoryRepository(db_or_repo)
    return db_or_repo


class ForgettingMechanism:
    async def decay_memory(self, db: AsyncSession, agent_id: int) -> None:
        """根据遗忘曲线衰减记忆重要性"""
        db = _ensure_repo(db)
        await self._decay_vector_memories(db, agent_id)

    async def _decay_vector_memories(self, db: AsyncSession, agent_id: int) -> None:
        """衰减向量记忆"""
        db = _ensure_repo(db)
        from app.models.memory import RoughMemory
        from sqlalchemy import update
        await db.execute(
            update(RoughMemory)
            .where(RoughMemory.owner_type == "ai", RoughMemory.owner_id == agent_id)
            .values(value_score=RoughMemory.value_score * 0.99)
        )
        await db.flush()

    async def update_importance(self, db: AsyncSession, memory_id: int, accessed: bool = False, referenced: bool = False) -> None:
        """
        更新记忆重要性：
        - 被访问：+1
        - 被引用：+2
        - 超过 10 封顶
        """
        db = _ensure_repo(db)
        from app.models.memory import RoughMemory
        from sqlalchemy import select
        result = await db.execute(select(RoughMemory).where(RoughMemory.id == memory_id))
        memory = result.scalar_one_or_none()
        if memory:
            increment = 0
            if accessed:
                increment += 1
            if referenced:
                increment += 2
            memory.value_score = min(10, memory.value_score + increment)
            await db.flush()


forgetting_mechanism = ForgettingMechanism()