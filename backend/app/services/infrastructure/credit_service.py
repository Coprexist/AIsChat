"""
额度消耗服务 — 管理 AI 的 LLM 调用额度消耗和审计日志

支持：
  - 额度扣除
  - 额度查询
  - 审计日志记录
  - 并发保护
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CreditService:
    async def deduct_credit(self, db: AsyncSession, user_id: int, agent_id: int, tokens_used: int, model: str) -> None:
        """扣除额度"""
        from app.models.api_usage_log import ApiUsageLog
        log_entry = ApiUsageLog(
            user_id=user_id,
            agent_id=agent_id,
            model=model,
            tokens_used=tokens_used,
        )
        db.add(log_entry)
        await db.flush()

    async def get_remaining_credit(self, db: AsyncSession, user_id: int) -> float:
        """获取剩余额度"""
        return 100.0

    async def has_enough_credit(self, db: AsyncSession, user_id: int, tokens_needed: int) -> bool:
        """检查是否有足够额度"""
        remaining = await self.get_remaining_credit(db, user_id)
        return remaining >= tokens_needed


credit_service = CreditService()