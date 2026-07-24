"""
向量记忆服务（兼容层）

已委托给 memory_service.py 和 memory_index.py，此处仅做兼容导出。
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class VectorMemoryService:
    async def store_rough_memory(self, db: AsyncSession, agent_id: int, title: str, embedding: list[float]) -> dict:
        from app.models.memory import RoughMemory
        memory = RoughMemory(
            owner_type="ai",
            owner_id=agent_id,
            title=title,
            embedding=embedding,
        )
        db.add(memory)
        await db.flush()
        return {"id": memory.id, "title": memory.title}

    async def store_detail_memory(self, db: AsyncSession, agent_id: int, rough_memory_id: int, content: str, embedding: list[float]) -> dict:
        from app.models.memory import DetailMemory
        memory = DetailMemory(
            rough_id=rough_memory_id,
            content=content,
            embedding=embedding,
        )
        db.add(memory)
        await db.flush()
        return {"id": memory.id, "rough_memory_id": memory.rough_id}

    async def search_memories(self, db: AsyncSession, agent_id: int, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        return []

    async def get_memory_details(self, db: AsyncSession, rough_memory_id: int) -> list[dict]:
        from app.models.memory import DetailMemory
        result = await db.execute(DetailMemory.__table__.select().where(DetailMemory.rough_id == rough_memory_id))
        return [
            {"id": m.id, "content": m.content, "created_at": str(m.created_at)}
            for m in result.all()
        ]

    async def delete_memory(self, db: AsyncSession, memory_id: int) -> bool:
        from app.models.memory import RoughMemory
        result = await db.execute(RoughMemory.__table__.delete().where(RoughMemory.id == memory_id))
        await db.flush()
        return result.rowcount > 0


vector_memory_service = VectorMemoryService()