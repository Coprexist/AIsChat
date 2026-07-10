"""
群聊服务
处理群聊创建、成员管理、消息收发、免打扰、消息聚合等
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, update, delete, func as sqlfunc
from app.models.group import Group, GroupMember
from app.models.message import Message, PendingMessage
from app.models.agent import Agent

logger = logging.getLogger(__name__)


async def create_group(
    db: AsyncSession,
    name: str,
    owner_type: str,
    owner_id: int,
    initial_members: list[dict] | None = None,
) -> Group:
    """创建群聊"""
    # 从系统设置获取默认并发数
    from app.models.system_settings import SystemSettings
    ss_result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    ss = ss_result.scalar_one_or_none()
    default_limit = ss.default_concurrent_ai_limit if ss and ss.default_concurrent_ai_limit else 3

    group = Group(
        name=name,
        owner_type=owner_type,
        owner_id=owner_id,
        concurrent_ai_limit=default_limit,
    )
    db.add(group)
    await db.flush()
    await db.refresh(group)

    # 添加群主为成员
    owner_member = GroupMember(
        group_id=group.id,
        member_type=owner_type,
        member_id=owner_id,
        role="owner",
    )
    db.add(owner_member)

    # 添加初始成员
    if initial_members:
        for member in initial_members:
            gm = GroupMember(
                group_id=group.id,
                member_type=member["type"],
                member_id=member["id"],
                role="member",
            )
            db.add(gm)

    await db.flush()
    logger.info(f"群聊 '{name}' (id={group.id}) 由 {owner_type}:{owner_id} 创建")
    return group


async def get_group(db: AsyncSession, group_id: int) -> Group | None:
    """获取群聊"""
    result = await db.execute(select(Group).where(Group.id == group_id))
    return result.scalar_one_or_none()


async def list_user_groups(db: AsyncSession, user_id: int) -> list[dict]:
    """列出用户所属的群聊（含未读信息、公告摘要等）"""
    from app.models.user import User
    from app.models.agent import Agent as AgentModel

    result = await db.execute(
        select(GroupMember).where(
            GroupMember.member_type == "human",
            GroupMember.member_id == user_id,
        )
    )
    memberships = result.scalars().all()

    # 获取用户名（用于 @提及检测）
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    username = user.username if user else ""

    groups = []
    for m in memberships:
        group = await db.get(Group, m.group_id)
        if not group:
            continue

        # 公告摘要（截断）
        announcement = None
        if group.announcement:
            announcement = group.announcement[:100] if len(group.announcement) > 100 else group.announcement

        # DND 状态
        dnd_until = str(m.dnd_until) if m.dnd_until else None

        # 未读计数和最后消息
        unread_count = 0
        has_mention = False
        last_message_preview = None
        last_message_at = None

        # 兜底：last_read_at 为 NULL 时用 joined_at，避免统计全量历史
        read_baseline = m.last_read_at or m.joined_at
        if read_baseline:
            count_result = await db.execute(
                select(sqlfunc.count(Message.id)).where(
                    Message.group_id == group.id,
                    Message.created_at > read_baseline,
                    ~((Message.sender_type == "human") & (Message.sender_id == user_id)),
                )
            )
            unread_count = count_result.scalar() or 0

            if username and unread_count > 0:
                mention_result = await db.execute(
                    select(Message).where(
                        Message.group_id == group.id,
                        Message.created_at > read_baseline,
                        Message.content.contains(f"@{username}"),
                    ).limit(1)
                )
                has_mention = mention_result.scalar_one_or_none() is not None
        # read_baseline 为 None（极端情况：无 last_read_at 也无 joined_at）→ unread_count = 0

        # 最后一条消息预览（始终查询，无论是否访问过）
        last_msg_result = await db.execute(
            select(Message).where(
                Message.group_id == group.id,
            ).order_by(Message.created_at.desc()).limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()
        if last_msg:
            last_message_at = str(last_msg.created_at) if last_msg.created_at else None
            from app.utils.message_serializer import make_preview
            preview = make_preview(last_msg.content, last_msg.attachments, max_len=50)
            # 解析发送者名称
            if last_msg.sender_type == "ai":
                a_result = await db.execute(select(AgentModel).where(AgentModel.user_id == last_msg.sender_id)); a = a_result.scalar_one_or_none()
                sender = a.name if a else "AI"
            elif last_msg.sender_type == "system":
                sender = "系统"
            else:
                u = await db.get(User, last_msg.sender_id)
                sender = u.username if u else "用户"
            last_message_preview = f"{sender}: {preview}"

        # 获取前 4 个成员头像（用于头像组展示）
        member_avatars: list[str] = []
        try:
            avatar_result = await db.execute(
                select(GroupMember).where(
                    GroupMember.group_id == group.id,
                ).limit(4)
            )
            avatar_members = avatar_result.scalars().all()
            for am in avatar_members:
                avatar_url = None
                if am.member_type == "ai":
                    # v2.0.0: member_id 统一为 user_id，同时兼容旧 agent.id
                    a_result = await db.execute(
                        select(AgentModel).where(AgentModel.user_id == am.member_id)
                    )
                    a = a_result.scalar_one_or_none()
                    if a is None:
                        a_result = await db.execute(
                            select(AgentModel).where(AgentModel.id == am.member_id)
                        )
                        a = a_result.scalar_one_or_none()
                    avatar_url = getattr(a, 'avatar_url', None) if a else None
                else:
                    u = await db.get(User, am.member_id)
                    avatar_url = getattr(u, 'avatar_url', None) if u else None
                if avatar_url:
                    member_avatars.append(avatar_url)
        except Exception:
            logger.warning("获取群聊 %d 成员头像失败，跳过", group.id, exc_info=True)

        groups.append({
            "id": group.id,
            "name": group.name,
            "owner_type": group.owner_type,
            "owner_id": group.owner_id,
            "is_vector_accelerated": group.is_vector_accelerated,
            "announcement": announcement,
            "speak_limit_per_minute": group.speak_limit_per_minute or 0,
            "speak_limit_window_seconds": group.speak_limit_window_seconds or 120,
            "my_role": m.role,
            "unread_count": unread_count,
            "has_mention": has_mention,
            "last_message_preview": last_message_preview,
            "last_message_at": last_message_at,
            "dnd_until": dnd_until,
            "member_avatars": member_avatars,
            "created_at": str(group.created_at) if group.created_at else None,
        })
    return groups


async def add_member(
    db: AsyncSession,
    group_id: int,
    member_type: str,
    member_id: int,
    role: str = "member",
) -> GroupMember:
    """添加群成员。AI 类型自动用 user_id 作为 member_id，统一 ID 空间。"""
    from app.models.agent import Agent as AgentModel

    resolved_type = member_type
    resolved_id = member_id

    # AI 成员：member_id 统一指向 users 表（agent.user_id）
    if member_type == "ai":
        # 尝试按 agent.id 查找（可能是旧代码传入的 agent_id）
        agent = await db.get(AgentModel, member_id)
        if not agent:
            # 也可能是已经迁移后的 user_id，尝试反向查找
            agent_result = await db.execute(
                select(AgentModel).where(AgentModel.user_id == member_id)
            )
            agent = agent_result.scalar_one_or_none()

        if agent and agent.user_id:
            resolved_id = agent.user_id
        else:
            raise ValueError(f"AI agent {member_id} 没有关联的 user_id")

    # 检查是否已在群中（按 user_id 去重）
    result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.member_id == resolved_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        # AI 类型优先：已存在 AI 记录时不被 human 覆盖
        if existing.member_type != resolved_type:
            # human → ai 可以升级，ai → human 不允许（保留 AI 标识）
            if existing.member_type != "ai":
                existing.member_type = resolved_type
                await db.flush()
        return existing

    member = GroupMember(
        group_id=group_id,
        member_type=resolved_type,
        member_id=resolved_id,
        role=role,
    )
    db.add(member)
    await db.flush()
    return member


async def get_group_members(db: AsyncSession, group_id: int) -> list[GroupMember]:
    """获取群成员列表"""
    result = await db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id)
    )
    return list(result.scalars().all())


async def create_message(
    db: AsyncSession,
    group_id: int,
    sender_type: str,
    sender_id: int,
    content: str,
    reply_to: int | None = None,
    attachments: list[dict] | None = None,
) -> Message:
    """创建消息（支持附件，非 owner 发送含附件消息时自动创建转发引用）"""
    message = Message(
        group_id=group_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        reply_to=reply_to,
        attachments=attachments,
    )
    db.add(message)
    await db.flush()

    # 附件自动创建转发引用（非 owner 发送时）
    if attachments:
        from app.services.file_service import track_forward_reference
        for att in attachments:
            fid = att.get("file_id") if isinstance(att, dict) else getattr(att, "file_id", None)
            if fid:
                await track_forward_reference(db, fid, sender_type, sender_id)

    await db.refresh(message)
    return message


async def get_recent_messages(
    db: AsyncSession,
    group_id: int,
    limit: int = 20,
    before_id: int | None = None,
    after_id: int | None = None,
    after_time: datetime | None = None,
) -> list[Message]:
    """获取群聊消息（支持游标分页 + 按时间过滤未读）"""
    query = select(Message).where(Message.group_id == group_id)

    if after_time:
        query = query.where(Message.created_at > after_time)
        query = query.order_by(desc(Message.created_at))
    elif before_id:
        query = query.where(Message.id < before_id)
    elif after_id:
        query = query.where(Message.id > after_id)
        query = query.order_by(desc(Message.created_at))
    else:
        query = query.order_by(desc(Message.created_at))

    query = query.limit(limit)
    result = await db.execute(query)
    messages = list(result.scalars().all())
    logger.warning(f"🔍 get_recent_messages group={group_id} limit={limit} after_time={after_time} after_id={after_id}: got {len(messages)} results")

    # 降序取最近 N 条未读后反转成升序给 AI
    if not after_id:
        messages = list(reversed(messages))
    return messages


def message_to_dict(message: Message, sender_name: str | None = None, sender_avatar_url: str | None = None, sender_state: str | None = None) -> dict:
    """将 Message ORM 对象转为字典"""
    from app.utils.message_serializer import serialize_message
    return serialize_message(
        message,
        sender_name=sender_name,
        sender_avatar_url=sender_avatar_url,
        sender_state=sender_state,
        conversation_key='group_id',
        include_read_at=False,
    )


# ============================================================
# 免打扰 (DND) 相关
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
    - duration_minutes > 0 → 临时免打扰 (dnd_until = NOW() + interval)

    ⚠️ member_type 默认为 "ai"（向后兼容 AI worker），前端路由调用时必须显式传 "human"，
    否则 human 用户设 DND 会因 member_type 不匹配找不到记录。
    ⚠️ dnd_until 必须用 offset-naive datetime（无 tzinfo），因为 DB 列是 TIMESTAMP WITHOUT TIME ZONE。
    混用 offset-aware datetime 会导致 asyncpg DataError。
    """
    # v2.0.0: AI 类型用 agent.user_id 查找（group_members 统一为 user_id）
    lookup_id = agent_id
    if member_type == "ai":
        agent = await db.get(Agent, agent_id)
        if agent is None:
            # 可能是 user_id 传入，尝试反向查找
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
        member.dnd_until = datetime(2099, 12, 31, 23, 59, 59)  # 永久免打扰
        logger.info(f"用户 {agent_id} 在群聊 {group_id} 设置永久免打扰")

    await db.flush()
    return member


async def is_member_in_dnd(db: AsyncSession, agent_id: int, group_id: int) -> bool:
    """检查 AI 在指定群聊是否处于免打扰状态"""
    # 1. 先检查全局暂停
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent and agent.is_paused:
        return True

    # 2. 再检查按群 DND（v2.0.0: group_members.member_id 统一为 user_id）
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

    # NULL = 未设置 DND，不在免打扰状态
    if member.dnd_until is None:
        return False

    # 有值 = 检查是否过期
    now = datetime.utcnow()
    return member.dnd_until > now

async def is_member_muted(db: AsyncSession, agent_id: int, group_id: int) -> bool:
    """检查 AI 在指定群聊是否处于屏蔽状态（比 DND 更强，@/公告也不穿透）"""
    from app.models.agent import Agent as AgentModel
    agent_result = await db.execute(select(AgentModel).where(AgentModel.id == agent_id))
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


async def is_member_of_group(
    db: AsyncSession,
    member_id: int,
    member_type: str,
    group_id: int,
) -> bool:
    """检查成员是否在指定群聊中。
    v2.0.0: AI 类型兼容 agent.id 和 user_id 两种查找。
    """
    lookup_id = member_id
    if member_type == "ai":
        # 尝试 agent.id → user_id 转换
        agent = await db.get(Agent, member_id)
        if agent is None:
            agent_result = await db.execute(
                select(Agent).where(Agent.user_id == member_id)
            )
            agent = agent_result.scalar_one_or_none()
        if agent and agent.user_id:
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
    return result.scalar_one_or_none() is not None


async def cancel_group_dnd(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
    member_type: str = "ai",
) -> GroupMember:
    """
    取消群聊免打扰（设为正常接收消息），支持 human 和 ai。

    ⚠️ 此处 dnd_until 设为 datetime(2000,1,1) 必须无 tzinfo（DB 列是 TIMESTAMP WITHOUT TIME ZONE），
    不可加 tzinfo=timezone.utc，否则 asyncpg 抛 DataError。
    ⚠️ 同样，member_type 默认为 "ai"，前端路由调用时必须传 "human"。
    """
    # v2.0.0: AI 类型用 agent.user_id 查找（group_members 统一为 user_id）
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

    # 设为一个过去的时间表示正常状态（不带 tzinfo，与 DB 列 TIMESTAMP WITHOUT TIME ZONE 一致）
    member.dnd_until = datetime(2000, 1, 1)
    await db.flush()
    logger.info(f"用户 {agent_id} 在群聊 {group_id} 已取消免打扰")
    return member


# ============================================================
# 暂存消息 (Pending Messages)
# ============================================================

async def store_pending_message(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
    message_id: int,
) -> PendingMessage:
    """将消息暂存到 AI 的 pending 列表"""
    pending = PendingMessage(
        agent_id=agent_id,
        group_id=group_id,
        message_id=message_id,
    )
    db.add(pending)
    await db.flush()
    await db.refresh(pending)
    return pending


async def get_pending_messages(
    db: AsyncSession,
    agent_id: int,
    group_id: int | None = None,
    unread_only: bool = True,
) -> list[dict]:
    """获取 AI 的暂存消息，可按群聊过滤"""
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
    await db.flush()


# ============================================================
# 消息聚合 / 暂停通知
# ============================================================

async def check_unread(
    db: AsyncSession,
    agent_id: int,
) -> list[dict]:
    """
    获取 AI 各群聊的未读消息摘要（按群分组）。
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
        # 获取群聊名称
        group_result = await db.execute(select(Group).where(Group.id == row.group_id))
        group = group_result.scalar_one_or_none()
        group_name = group.name if group else f"群聊#{row.group_id}"

        # 获取最新一条消息作为预览
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
    """
    调用 LLM 生成自然语言摘要。
    实际实现需接入 LLM API，此处为基础骨架。
    """
    if unread_count == 0:
        return f"群聊【{group_name}】没有新消息。"

    # 简单模板摘要（无 LLM 调用时使用）
    return (
        f"群聊【{group_name}】有 {unread_count} 条新消息，"
        f"最后一条：「{last_message_preview[:50]}」"
    )


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
    """
    恢复通知，并返回暂停期间的所有暂存消息，标记为已读。
    返回: (agent, pending_messages_list)
    """
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError("AI 代理不存在")

    if not agent.is_paused:
        raise ValueError("AI 代理未处于暂停状态")

    # 获取暂停期间的未读消息
    pending = await get_pending_messages(db, agent_id, unread_only=True)

    # 标记已读
    await mark_pending_read(db, agent_id)

    # 恢复
    agent.is_paused = False
    await db.flush()

    logger.info(f"AI {agent_id} 已恢复通知，返回 {len(pending)} 条暂存消息")
    return agent, pending


async def is_ai_only_group(
    db: AsyncSession,
    group_id: int,
    group: Group | None = None,
) -> bool:
    """
    检查群聊是否全部由 AI 成员组成（无人类成员）。

    用于判断是否启用向量加速混合检索——该功能仅对 AI 内部协作群有意义，
    普通人类群聊使用常规历史窗口即可。

    如果调用方已持有 group 对象，通过 group 参数传入可省一次 DB 查询。
    """
    human_count_result = await db.execute(
        select(sqlfunc.count(GroupMember.member_id)).where(
            GroupMember.group_id == group_id,
            GroupMember.member_type == "human",
        )
    )
    human_count = human_count_result.scalar() or 0

    # 复用调用方传入的 group 对象，或按需查询
    if group is None:
        group = await db.get(Group, group_id)
    if group is None:
        return False

    return human_count == 0 and group.owner_type == "ai"


# ============================================================
# Phase 4: 群聊治理函数
# ============================================================


async def update_group_settings(
    db: AsyncSession,
    group_id: int,
    operator_id: int,
    updates: dict,
) -> Group:
    """
    更新群聊设置（名称、公告、发言限制、向量加速等）。
    仅群主或管理员可操作。

    updates 支持字段: name, announcement, speak_limit_per_minute,
                     speak_limit_window_seconds, is_vector_accelerated
    """
    group = await db.get(Group, group_id)
    if group is None:
        raise ValueError("群聊不存在")

    # 权限检查
    member = await _get_member(db, group_id, "human", operator_id)
    if member is None or member.role not in ("owner", "admin"):
        raise ValueError("仅群主或管理员可修改群设置")

    allowed_fields = {
        "name", "announcement",
        "speak_limit_per_minute", "speak_limit_window_seconds",
        "is_vector_accelerated",
    }

    for key, value in updates.items():
        if key not in allowed_fields:
            continue
        if key == "announcement" and value is not None:
            group.announcement = value
            group.announcement_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        elif hasattr(group, key):
            setattr(group, key, value)

    await db.flush()
    # 联邦同步：群名称变更时入队 profile 更新
    if "name" in updates:
        from app.services.federation_service import enqueue_profile_update
        await enqueue_profile_update(db, "group", group_id, "display_name", updates["name"])
    logger.info(f"群聊 {group_id} 设置已更新: {list(updates.keys())}")
    return group


async def set_announcement(
    db: AsyncSession,
    group_id: int,
    content: str,
    operator_id: int,
) -> str:
    """
    设置群公告，返回公告内容。
    仅群主或管理员可操作。
    """
    group = await db.get(Group, group_id)
    if group is None:
        raise ValueError("群聊不存在")

    member = await _get_member(db, group_id, "human", operator_id)
    if member is None or member.role not in ("owner", "admin"):
        raise ValueError("仅群主或管理员可设置群公告")

    group.announcement = content
    group.announcement_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    logger.info(f"群聊 {group_id} 公告已更新")
    return content


async def delete_announcement(
    db: AsyncSession,
    group_id: int,
    operator_id: int,
) -> None:
    """删除群公告"""
    group = await db.get(Group, group_id)
    if group is None:
        raise ValueError("群聊不存在")

    member = await _get_member(db, group_id, "human", operator_id)
    if member is None or member.role not in ("owner", "admin"):
        raise ValueError("仅群主或管理员可删除群公告")

    group.announcement = None
    group.announcement_updated_at = None
    await db.flush()


async def change_member_role(
    db: AsyncSession,
    group_id: int,
    operator_id: int,
    target_type: str,
    target_id: int,
    new_role: str,
) -> GroupMember:
    """
    修改成员角色（提拔/降级）。

    规则：
    - 仅群主可提拔他人为 admin 或降级 admin
    - 不能修改自己的角色
    - 不能修改群主的角色
    """
    if new_role not in ("admin", "member"):
        raise ValueError("角色只能是 admin 或 member")

    operator = await _get_member(db, group_id, "human", operator_id)
    if operator is None or operator.role != "owner":
        raise ValueError("仅群主可修改成员角色")

    if target_type == operator.member_type and target_id == operator_id:
        raise ValueError("不能修改自己的角色")

    target = await _get_member(db, group_id, target_type, target_id)
    if target is None:
        raise ValueError("该成员不在群内")

    if target.role == "owner":
        raise ValueError("不能修改群主的角色")

    target.role = new_role
    await db.flush()
    logger.info(f"群 {group_id} 成员 {target_type}:{target_id} 角色变更为 {new_role}")
    return target


async def remove_member(
    db: AsyncSession,
    group_id: int,
    operator_id: int,
    target_type: str,
    target_id: int,
) -> None:
    """
    将成员踢出群聊。

    规则：
    - 仅群主或管理员可踢人
    - 不能踢自己
    - 管理员不能踢群主或其他管理员
    """
    operator = await _get_member(db, group_id, "human", operator_id)
    if operator is None or operator.role not in ("owner", "admin"):
        raise ValueError("仅群主或管理员可踢人")

    if target_type == operator.member_type and target_id == operator_id:
        raise ValueError("不能踢自己")

    target = await _get_member(db, group_id, target_type, target_id)
    if target is None:
        raise ValueError("该成员不在群内")

    if target.role == "owner":
        raise ValueError("不能踢群主")
    if operator.role == "admin" and target.role == "admin":
        raise ValueError("管理员不能踢其他管理员")

    await db.delete(target)
    await db.flush()
    logger.info(f"成员 {target_type}:{target_id} 已被踢出群聊 {group_id}")


async def leave_group(
    db: AsyncSession,
    group_id: int,
    member_type: str,
    member_id: int,
) -> None:
    """
    退出群聊。

    规则：
    - 群主不能退群，需先转让群主
    - DM 群聊（群名以 DM: 开头）允许退出
    """
    member = await _get_member(db, group_id, member_type, member_id)
    if member is None:
        raise ValueError("你不在该群聊中")

    if member.role == "owner":
        # 检查是否为 DM 群聊（DM 群主可以退出）
        group = await db.get(Group, group_id)
        if group and not group.name.startswith("DM:"):
            raise ValueError("群主不能退群，请先将群主转让给其他成员")

    await db.delete(member)
    await db.flush()
    logger.info(f"成员 {member_type}:{member_id} 已退出群聊 {group_id}")


async def get_unread_info(
    db: AsyncSession,
    group_id: int,
    user_id: int,
) -> dict:
    """
    获取用户在指定群聊的未读信息。

    返回: {unread_count, has_mention, has_announcement, last_message}
    """
    from app.models.agent import Agent as AgentModel

    # 获取成员记录，查 last_read_at
    member = await _get_member(db, group_id, "human", user_id)
    last_read = member.last_read_at if member else None

    # 统计未读消息数（last_read 为 NULL 时用 joined_at 兜底）
    read_baseline = last_read or (member.joined_at if member else None)
    base_query = select(Message).where(Message.group_id == group_id)
    if read_baseline:
        base_query = base_query.where(Message.created_at > read_baseline)

    # 排除自己的消息
    base_query = base_query.where(
        ~((Message.sender_type == "human") & (Message.sender_id == user_id))
    )

    unread_result = await db.execute(base_query.order_by(Message.created_at.desc()))
    unread_messages = unread_result.scalars().all()

    unread_count = len(unread_messages)

    # 检查是否有 @提及
    has_mention = False
    user_name = None
    from app.models.user import User
    user = await db.get(User, user_id)
    if user:
        user_name = user.username
        for msg in unread_messages:
            if f"@{user_name}" in msg.content:
                has_mention = True
                break

    # 检查是否有未读公告
    group = await db.get(Group, group_id)
    has_announcement = False
    if group and group.announcement and group.announcement_updated_at:
        if last_read is None or group.announcement_updated_at > last_read:
            has_announcement = True

    # 最后一条消息
    last_msg = unread_messages[0] if unread_messages else None
    last_message = None
    if last_msg:
        sender_name = getattr(last_msg, "sender_name", None) or "未知"
        if last_msg.sender_type == "human":
            u = await db.get(User, last_msg.sender_id)
            if u:
                sender_name = u.username
        else:
            a_result2 = await db.execute(select(AgentModel).where(AgentModel.user_id == last_msg.sender_id)); a = a_result2.scalar_one_or_none()
            if a:
                sender_name = a.name

        last_message = {
            "content": last_msg.content[:100],
            "sender_name": sender_name,
            "created_at": str(last_msg.created_at) if last_msg.created_at else None,
        }

    return {
        "unread_count": unread_count,
        "has_mention": has_mention,
        "has_announcement": has_announcement,
        "last_message": last_message,
    }


async def update_last_read(
    db: AsyncSession,
    group_id: int,
    member_type: str,
    member_id: int,
) -> bool:
    """更新成员的最后阅读时间（进入群聊时调用），返回是否成功更新"""
    member = await _get_member(db, group_id, member_type, member_id)
    if member:
        # 注意：last_read_at 字段类型是 TIMESTAMP WITHOUT TIME ZONE，
        # 必须用无时区的 UTC 时间，否则 asyncpg 会报错
        member.last_read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.flush()
        return True
    logger.warning(f"update_last_read: member not found group={group_id} {member_type}={member_id}")
    return False


async def _get_member(
    db: AsyncSession,
    group_id: int,
    member_type: str,
    member_id: int,
) -> GroupMember | None:
    """获取群成员记录（内部辅助函数）。
    v2.0.0: AI 类型的 member_id 统一为 user_id，同时向后兼容 agent.id 查找。
    """
    result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.member_type == member_type,
            GroupMember.member_id == member_id,
        )
    )
    member = result.scalar_one_or_none()

    # v2.0.0: AI 类型兼容——DB 存 user_id，调用方可能传 agent.id
    if member is None and member_type == "ai":
        from app.models.agent import Agent as AgentModel
        agent = await db.get(AgentModel, member_id)
        if agent and agent.user_id and agent.user_id != member_id:
            result = await db.execute(
                select(GroupMember).where(
                    GroupMember.group_id == group_id,
                    GroupMember.member_type == member_type,
                    GroupMember.member_id == agent.user_id,
                )
            )
            member = result.scalar_one_or_none()

    return member


async def disband_group(db: AsyncSession, group_id: int, operator_id: int) -> Group:
    """
    解散群聊（仅群主可操作）。

    会清理无 CASCADE 的关联数据（rough_memories 设 NULL、conversation_logs 删除），
    有 CASCADE 的表（members/messages/pending/embeddings）由数据库自动级联删除。
    """
    group = await db.get(Group, group_id)
    if group is None:
        raise ValueError("群聊不存在")

    # 权限检查：只有 human owner 可以解散
    member = await _get_member(db, group_id, "human", operator_id)
    if member is None or member.role != "owner":
        raise ValueError("仅群主可解散群聊")

    # 清理无 CASCADE 的关联数据
    from app.models.memory import RoughMemory
    await db.execute(
        update(RoughMemory).where(RoughMemory.group_id == group_id).values(group_id=None)
    )
    from app.models.conversation_log import ConversationLog
    await db.execute(
        delete(ConversationLog).where(ConversationLog.group_id == group_id)
    )

    await db.delete(group)
    await db.flush()
    logger.info(f"群聊 '{group.name}' (id={group_id}) 已被群主 {operator_id} 解散")
    return group
