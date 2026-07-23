"""
冲突仲裁器 — 当多个 Skill 同时想说话时，决定谁先说、说什么

规则：
  1. 按 priority 降序排序
  2. 取前 N 个（一轮最多 3 个 Skill 发言）
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ConflictArbiter:
    MAX_SPEAKERS_PER_ROUND = 3

    async def arbitrate(self, db: AsyncSession, speech_requests: list) -> list:
        """
        冲突仲裁：
        1. 按 priority 降序排序
        2. 取前 N 个（一轮最多 3 个 Skill 发言）
        
        Args:
            speech_requests: 包含 skill_name, priority, action_type, reason, messages 等字段
            
        Returns:
            过滤后的发言请求列表
        """
        if not speech_requests:
            return []

        speech_requests.sort(key=lambda r: r.get("priority", 0), reverse=True)

        result = []
        for request in speech_requests[:self.MAX_SPEAKERS_PER_ROUND]:
            action_type = request.get("action_type", "speak")
            
            if action_type == "speak":
                result.append(request)
            elif action_type == "remember":
                result.append(request)
            elif action_type == "silent":
                continue
            elif action_type == "internal":
                continue

        return result


conflict_arbiter = ConflictArbiter()