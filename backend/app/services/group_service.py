"""
群聊服务 —— 兼容层（委托到 chat/ 子模块）

⚠️ 旧代码直接 import 本文件，因此保留所有导出。
新代码应直接使用 app.chat 或 ChatApi。

AI 专属逻辑（is_ai_only_group, pause_notifications, resume_and_fetch）保留在此，
后续迁移到 ai/ 模块。
"""

from app.chat.message import (
    create_group,
    get_group,
    list_user_groups,
    add_member,
    get_group_members,
    create_message,
    get_recent_messages,
    message_to_dict,
    is_member_of_group,
    remove_member,
    leave_group,
    update_last_read,
    update_group_settings,
    change_member_role,
    disband_group,
)
from app.chat.delivery import (
    set_group_dnd,
    cancel_group_dnd,
    is_member_in_dnd,
    is_member_muted,
    store_pending_message,
    get_pending_messages,
    mark_pending_read,
    check_unread,
    generate_llm_summary,
)

# 保留 AI 专属逻辑（后续迁移到 ai/ 模块）
from app.chat.message import _get_member  # 内部函数，部分旧代码依赖

# ── AI 专属逻辑（暂留）──

import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent import Agent
from app.models.group import Group, GroupMember

logger = logging.getLogger(__name__)


async def is_ai_only_group(
    db: AsyncSession,
    group_id: int,
    group: Group | None = None,
) -> bool:
    """检查群聊是否全部由 AI 成员组成（无人类成员）"""
    from app.models.group import GroupMember as GM
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


__all__ = [
    "create_group", "get_group", "list_user_groups", "add_member",
    "get_group_members", "create_message", "get_recent_messages",
    "message_to_dict", "is_member_of_group", "remove_member", "leave_group",
    "update_last_read", "update_group_settings", "change_member_role",
    "disband_group",
    "set_group_dnd", "cancel_group_dnd", "is_member_in_dnd", "is_member_muted",
    "store_pending_message", "get_pending_messages", "mark_pending_read",
    "check_unread", "generate_llm_summary",
    "is_ai_only_group", "pause_notifications", "resume_and_fetch",
]
