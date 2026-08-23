"""
注意力系统 — AI 主动过滤消息，声明兴趣域

前置过滤流程：
  1. 消息来了 → 查每个 AI 的 AgentAttention
  2. 命中 interested → 加分
  3. 命中 ignored → 直接剔除
  4. 否则 → 正常 willingness 算分
"""
import logging
import re
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.skill_repo import SkillRepository, SQLAlchemySkillRepository

logger = logging.getLogger(__name__)


def _ensure_repo(db_or_repo):
    """兼容旧调用：传入 AsyncSession 时包装为 SQLAlchemySkillRepository。"""
    if isinstance(db_or_repo, AsyncSession):
        return SQLAlchemySkillRepository(db_or_repo)
    return db_or_repo


class AttentionSystem:
    async def check_attention(self, db: AsyncSession, agent_id: int, group_id: int, message_content: str, sender_id: int) -> str:
        """
        检查注意力匹配：
        - highlight: 高亮显示
        - wake: 唤醒 AI
        - silent_remember: 静默记忆
        - ignore: 忽略
        
        Returns:
            匹配动作类型
        """
        db = _ensure_repo(db)
        from app.models.agent_attention import AgentAttention
        from sqlalchemy import select
        result = await db.execute(
            select(AgentAttention)
            .where(AgentAttention.agent_id == agent_id, AgentAttention.group_id == group_id)
        )
        attention = result.scalar_one_or_none()
        if not attention:
            return "normal"

        if sender_id in attention.interested_users:
            return attention.match_action

        for pattern in attention.interested_patterns:
            if re.search(pattern, message_content):
                return attention.match_action

        for topic in attention.interested_topics:
            if topic.lower() in message_content.lower():
                return attention.match_action

        for pattern in attention.ignored_patterns:
            if re.search(pattern, message_content):
                return "ignore"

        for topic in attention.ignored_topics:
            if topic.lower() in message_content.lower():
                return "ignore"

        return "normal"

    async def update_attention(self, db: AsyncSession, agent_id: int, group_id: int, settings: dict) -> None:
        """更新注意力设置"""
        db = _ensure_repo(db)
        from app.models.agent_attention import AgentAttention
        from sqlalchemy import select
        result = await db.execute(
            select(AgentAttention)
            .where(AgentAttention.agent_id == agent_id, AgentAttention.group_id == group_id)
        )
        attention = result.scalar_one_or_none()

        if attention:
            attention.interested_topics = settings.get("interested_topics", [])
            attention.interested_users = settings.get("interested_users", [])
            attention.interested_patterns = settings.get("interested_patterns", [])
            attention.ignored_topics = settings.get("ignored_topics", [])
            attention.ignored_patterns = settings.get("ignored_patterns", [])
            attention.match_action = settings.get("match_action", "highlight")
        else:
            db.add(AgentAttention(
                agent_id=agent_id,
                group_id=group_id,
                interested_topics=settings.get("interested_topics", []),
                interested_users=settings.get("interested_users", []),
                interested_patterns=settings.get("interested_patterns", []),
                ignored_topics=settings.get("ignored_topics", []),
                ignored_patterns=settings.get("ignored_patterns", []),
                match_action=settings.get("match_action", "highlight"),
            ))
        db.flush()

    async def get_attention(self, db: AsyncSession, agent_id: int, group_id: int | None = None) -> list[dict]:
        """获取注意力设置列表（group_id 缺省时返回该 AI 全部）"""
        db = _ensure_repo(db)
        from app.models.agent_attention import AgentAttention
        from sqlalchemy import select

        query = select(AgentAttention).where(AgentAttention.agent_id == agent_id)
        if group_id is not None:
            query = query.where(AgentAttention.group_id == group_id)
        result = await db.execute(query)
        rows = result.scalars().all()
        return [
            {
                "agent_id": r.agent_id,
                "group_id": r.group_id,
                "interested_topics": r.interested_topics or [],
                "interested_users": r.interested_users or [],
                "interested_patterns": r.interested_patterns or [],
                "ignored_topics": r.ignored_topics or [],
                "ignored_patterns": r.ignored_patterns or [],
                "match_action": r.match_action,
            }
            for r in rows
        ]


attention_system = AttentionSystem()