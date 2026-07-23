"""
记忆分发引擎 — 智能分发记忆给 AI 上下文

根据上下文类型和 token 限制，智能分发记忆：
  1. 查询结构记忆索引（始终注入）
  2. 根据上下文类型语义搜索相关记忆
  3. 按重要性和相关性排序
  4. 裁剪到 token 限制以内
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MemoryDistributionEngine:
    async def get_context_for_ai(self, db: AsyncSession, agent_id: int, context_type: str, max_tokens: int) -> dict:
        """
        根据上下文类型和 token 限制，智能分发记忆
        
        Args:
            agent_id: AI 代理 ID
            context_type: 上下文类型（group_chat/dm/task/workspace）
            max_tokens: 最大 token 数
            
        Returns:
            包含记忆索引和相关记忆的上下文字典
        """
        context = {
            "memory_index": await self._get_memory_index(db, agent_id),
            "relevant_memories": await self._get_relevant_memories(db, agent_id, context_type, max_tokens),
        }
        return context

    async def _get_memory_index(self, db: AsyncSession, agent_id: int) -> dict:
        """获取结构记忆索引"""
        from app.services.memory.structured_memory_service import structured_memory_service
        return await structured_memory_service.get_categories(db, agent_id)

    async def _get_relevant_memories(self, db: AsyncSession, agent_id: int, context_type: str, max_tokens: int) -> list[dict]:
        """获取相关记忆"""
        return []


memory_distribution_engine = MemoryDistributionEngine()