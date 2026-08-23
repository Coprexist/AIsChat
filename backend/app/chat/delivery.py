"""
消息可达性管理 —— 消息能否送达的判断逻辑

职责：
  - DND 设置/取消/查询（群聊 + 私信）
  - 屏蔽（mute）查询
  - 暂存消息（pending messages）
  - 未读消息聚合

这是聊天世界的物理规则，不含 AI 决策逻辑。
人类和 AI 一视同仁通过这些规则判断消息是否能送达。
"""

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, desc, func as sqlfunc
from app.models.group import Group, GroupMember
from app.models.message import PendingMessage, Message
from app.models.agent import Agent

logger = logging.getLogger(__name__)


# ============================================================
# 群聊 DND
# ============================================================

async def set_group_dnd(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
    duration_minutes: int | None = None,
    member_type: str = "ai",
) -> GroupMember:
    """
    为群成员设置免打扰（支持 human 和 ai）。
    - duration_minutes = 0 或 None → 永久免打扰 (dnd_until = 2099-12-31)
    - duration_minutes > 0 → 临时免打扰
    """
    lookup_id = agent_id
    if member_type == "ai":
        agent = await db.get(Agent, agent_id)
        if agent is None:
            agent_result = await db.execute(
                select(Agent).where(Agent.user_id == agent_id)
            )
            agent = agent_result.scalar_one_or_none()
        if agent:
            lookup_id = agent.user_id

    result = await db.execute(
        select(GroupMember).where(
            and_(
                GroupMember.group_id == group_id,
                GroupMember.member_type == member_type,
                GroupMember.member_id == lookup_id,
            )
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise ValueError(f"用户 {agent_id} 不在群聊 {group_id} 中")

    if duration_minutes is not None and duration_minutes > 0:
        member.dnd_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        logger.info(f"用户 {agent_id} 在群聊 {group_id} 设置临时免打扰 {duration_minutes} 分钟")
    else:
        member.dnd_until = datetime(2099, 12, 31, 23, 59, 59)
        logger.info(f"用户 {agent_id} 在群聊 {group_id} 设置永久免打扰")

    db.flush()
    return member


async def cancel_group_dnd(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
    member_type: str = "ai",
) -> GroupMember:
    """取消群聊免打扰"""
    lookup_id = agent_id
    if member_type == "ai":
        agent = await db.get(Agent, agent_id)
        if agent is None:
            agent_result = await db.execute(
                select(Agent).where(Agent.user_id == agent_id)
            )
            agent = agent_result.scalar_one_or_none()
        if agent:
            lookup_id = agent.user_id

    result = await db.execute(
        select(GroupMember).where(
            and_(
                GroupMember.group_id == group_id,
                GroupMember.member_type == member_type,
                GroupMember.member_id == lookup_id,
            )
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise ValueError(f"用户 {agent_id} 不在群聊 {group_id} 中")

    member.dnd_until = datetime(2000, 1, 1)
    db.flush()
    logger.info(f"用户 {agent_id} 在群聊 {group_id} 已取消免打扰")
    return member


async def is_member_in_dnd(db: AsyncSession, agent_id: int, group_id: int) -> bool:
    """检查成员在指定群聊是否处于免打扰状态"""
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent and agent.is_paused:
        return True

    lookup_id = agent.user_id if agent else agent_id
    result = await db.execute(
        select(GroupMember).where(
            and_(
                GroupMember.group_id == group_id,
                GroupMember.member_type == "ai",
                GroupMember.member_id == lookup_id,
            )
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        return False
    if member.dnd_until is None:
        return False
    now = datetime.utcnow()
    return member.dnd_until > now


async def is_member_muted(db: AsyncSession, agent_id: int, group_id: int) -> bool:
    """检查成员在指定群聊是否处于屏蔽状态（比 DND 更强，@/公告也不穿透）"""
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    lookup_id = agent.user_id if agent else agent_id
    result = await db.execute(
        select(GroupMember).where(
            and_(
                GroupMember.group_id == group_id,
                GroupMember.member_type == "ai",
                GroupMember.member_id == lookup_id,
            )
        )
    )
    member = result.scalar_one_or_none()
    if member is None or member.muted_until is None:
        return False
    now = datetime.utcnow()
    return member.muted_until > now


# ============================================================
# 暂存消息 (Pending Messages)
# ============================================================

async def store_pending_message(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
    message_id: int,
) -> PendingMessage:
    """将消息暂存到接收者的 pending 列表（离线/DND 时使用）"""
    pending = PendingMessage(
        agent_id=agent_id,
        group_id=group_id,
        message_id=message_id,
    )
    db.add(pending)
    db.flush()
    db.refresh(pending)
    return pending


async def get_pending_messages(
    db: AsyncSession,
    agent_id: int,
    group_id: int | None = None,
    unread_only: bool = True,
) -> list[dict]:
    """获取暂存消息，可按群聊过滤"""
    query = select(PendingMessage, Message).join(
        Message, PendingMessage.message_id == Message.id
    ).where(PendingMessage.agent_id == agent_id)

    if unread_only:
        query = query.where(PendingMessage.is_read == False)
    if group_id is not None:
        query = query.where(PendingMessage.group_id == group_id)

    query = query.order_by(desc(Message.created_at))

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "pending_id": pm.id,
            "group_id": pm.group_id,
            "message_id": pm.message_id,
            "content": msg.content,
            "sender_type": msg.sender_type,
            "sender_id": msg.sender_id,
            "created_at": str(msg.created_at) if msg.created_at else None,
        }
        for pm, msg in rows
    ]


async def mark_pending_read(
    db: AsyncSession,
    agent_id: int,
    group_id: int | None = None,
):
    """标记暂存消息为已读"""
    query = (
        update(PendingMessage)
        .where(PendingMessage.agent_id == agent_id)
        .where(PendingMessage.is_read == False)
    )
    if group_id is not None:
        query = query.where(PendingMessage.group_id == group_id)

    query = query.values(is_read=True)
    await db.execute(query)
    db.flush()


# ============================================================
# 未读消息聚合
# ============================================================

async def check_unread(db: AsyncSession, agent_id: int) -> list[dict]:
    """
    获取各群聊的未读消息摘要（按群分组）。
    返回: [{group_id, group_name, unread_count, last_message_preview, last_message_at}, ...]
    """
    result = await db.execute(
        select(
            PendingMessage.group_id,
            sqlfunc.count(PendingMessage.id).label("unread_count"),
            sqlfunc.max(Message.created_at).label("last_message_at"),
        )
        .join(Message, PendingMessage.message_id == Message.id)
        .where(
            and_(
                PendingMessage.agent_id == agent_id,
                PendingMessage.is_read == False,
            )
        )
        .group_by(PendingMessage.group_id)
    )

    summaries = []
    for row in result:
        group_result = await db.execute(select(Group).where(Group.id == row.group_id))
        group = group_result.scalar_one_or_none()
        group_name = group.name if group else f"群聊#{row.group_id}"

        latest = await db.execute(
            select(Message.content)
            .join(PendingMessage, PendingMessage.message_id == Message.id)
            .where(
                and_(
                    PendingMessage.agent_id == agent_id,
                    PendingMessage.group_id == row.group_id,
                    PendingMessage.is_read == False,
                )
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        preview_row = latest.scalar_one_or_none()
        preview = preview_row[:100] if preview_row else "..."

        summaries.append({
            "group_id": row.group_id,
            "group_name": group_name,
            "unread_count": row.unread_count,
            "last_message_preview": preview,
            "last_message_at": str(row.last_message_at) if row.last_message_at else None,
        })

    return summaries


async def generate_llm_summary(
    agent_id: int,
    group_id: int,
    group_name: str,
    unread_count: int,
    last_message_preview: str,
    api_base_url: str = "https://api.deepseek.com",
    api_key: str | None = None,
) -> str:
    """调用 LLM 生成自然语言摘要（骨架实现）"""
    if unread_count == 0:
        return f"群聊【{group_name}】没有新消息。"
    return (
        f"群聊【{group_name}】有 {unread_count} 条新消息，"
        f"最后一条：「{last_message_preview[:50]}」"
    )
