"""
AI 专属群聊逻辑 —— 从 group_service.py 迁移而来

包含 AI 特有的群聊策略：
  - is_ai_only_group: 检查群是否全部由 AI 成员组成
  - pause_notifications: 暂停通知（任务期间暂存消息）
  - resume_and_fetch: 恢复通知并获取暂存消息
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.group import Group, GroupMember as GM
from app.chat.delivery import get_pending_messages, mark_pending_read

logger = logging.getLogger(__name__)


async def is_ai_only_group(
    db: AsyncSession,
    group_id: int,
    group: Group | None = None,
) -> bool:
    """检查群聊是否全部由 AI 成员组成（无人类成员）"""
    human_count_result = await db.execute(
        select(GM.member_id).where(
            GM.group_id == group_id,
            GM.member_type == "human",
        )
    )
    human_count = len(human_count_result.all())

    if group is None:
        group = await db.get(Group, group_id)
    if group is None:
        return False

    return human_count == 0 and group.owner_type == "ai"


async def pause_notifications(db: AsyncSession, agent_id: int) -> Agent:
    """暂停所有群聊的通知（任务期间暂存消息）"""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError("AI 代理不存在")
    agent.is_paused = True
    await db.flush()
    logger.info(f"AI {agent_id} 已暂停通知，消息将暂存")
    return agent


async def resume_and_fetch(
    db: AsyncSession,
    agent_id: int,
) -> tuple[Agent, list[dict]]:
    """恢复通知，并返回暂停期间的所有暂存消息，标记为已读"""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError("AI 代理不存在")
    if not agent.is_paused:
        raise ValueError("AI 代理未处于暂停状态")

    pending = await get_pending_messages(db, agent_id, unread_only=True)
    await mark_pending_read(db, agent_id)
    agent.is_paused = False
    await db.flush()

    logger.info(f"AI {agent_id} 已恢复通知，返回 {len(pending)} 条暂存消息")
    return agent, pending