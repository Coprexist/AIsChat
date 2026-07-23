"""
好友系统服务
处理好友申请、接受、拒绝、删除、搜索
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_

logger = logging.getLogger(__name__)


async def send_friend_request(
    db: AsyncSession,
    requester_id: int,
    target_type: str,
    target_id: int,
    message: str | None = None,
) -> dict:
    """发送好友申请"""
    from app.models.friendship import FriendshipRequest, Friendship

    # 检查是否已是好友
    existing_friend = await db.execute(
        select(Friendship).where(
            Friendship.user_id == requester_id,
            Friendship.friend_type == target_type,
            Friendship.friend_id == target_id,
        )
    )
    if existing_friend.scalar_one_or_none():
        raise ValueError("已经是好友了")

    # 检查是否已有待处理的申请
    existing_req = await db.execute(
        select(FriendshipRequest).where(
            FriendshipRequest.requester_id == requester_id,
            FriendshipRequest.target_type == target_type,
            FriendshipRequest.target_id == target_id,
            FriendshipRequest.status == "pending",
        )
    )
    if existing_req.scalar_one_or_none():
        raise ValueError("已发送过好友申请，请等待对方处理")

    # 检查对方是否已向自己发送申请（双向申请自动接受）
    # 支持 human↔human、AI(user_id)↔human、跨类型双向自动接受
    from app.models.agent import Agent as AgentModel
    reverse = await _find_reverse_request(db, requester_id, target_type, target_id)
    if reverse:
        reverse.status = "accepted"
        reverse.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # 解析 reverse 中的双方身份
        r_user_id = reverse.requester_id
        r_type = reverse.target_type
        r_target = reverse.target_id
        # 双向添加好友
        db.add(Friendship(user_id=requester_id, friend_type=target_type, friend_id=target_id))
        db.add(Friendship(user_id=r_user_id, friend_type=r_type, friend_id=r_target))
        await db.flush()
        # 获取反向申请发起者的名称
        reverse_name = None
        try:
            from app.models.user import User
            name_result = await db.execute(select(User.username).where(User.id == r_user_id))
            reverse_name = name_result.scalar_one_or_none()
        except Exception:
            pass
        # 获取目标 AI 的 auto_respond 状态
        auto_respond = None
        if target_type == "ai":
            target_agent = await db.execute(
                select(AgentModel).where(AgentModel.user_id == target_id)
            )
            target_agent_obj = target_agent.scalar_one_or_none()
            if target_agent_obj:
                auto_respond = target_agent_obj.auto_respond_friend_request
        result = {
            "status": "accepted", "auto": True,
            "message": "对方已向你发送申请，已自动成为好友",
            "reverse_message": reverse.message,
            "reverse_target_name": reverse_name or f"用户{r_user_id}",
        }
        if auto_respond is not None:
            result["auto_respond"] = auto_respond
        return result

    # 如果目标是 AI，检查是否允许接收好友申请
    auto_respond = None
    if target_type == "ai":
        from app.models.agent import Agent as AgentModelInner
        agent = await db.execute(
            select(AgentModelInner).where(AgentModelInner.user_id == target_id)
        )
        agent_obj = agent.scalar_one_or_none()
        if agent_obj is None:
            raise ValueError("AI 不存在")
        if not agent_obj.allow_friend_requests:
            raise ValueError(f"AI「{agent_obj.name}」已关闭好友申请，无法发送")
        auto_respond = agent_obj.auto_respond_friend_request

    # 创建申请
    req = FriendshipRequest(
        requester_id=requester_id,
        target_type=target_type,
        target_id=target_id,
        message=message,
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)

    logger.info(f"用户 {requester_id} 向 {target_type}:{target_id} 发送好友申请")
    result = {"status": "pending", "request_id": req.id}
    if auto_respond is not None:
        result["auto_respond"] = auto_respond
    return result


async def accept_friend_request(
    db: AsyncSession,
    request_id: int,
    user_id: int,
) -> dict:
    """接受好友申请"""
    from app.models.friendship import FriendshipRequest, Friendship

    req = await _get_request(db, request_id)
    if req is None:
        raise ValueError("申请不存在")

    # 权限检查：只有目标用户可以接受
    if req.target_type == "human" and req.target_id != user_id:
        raise ValueError("无权操作此申请")

    if req.status != "pending":
        raise ValueError(f"申请状态为 {req.status}，无法接受")

    req.status = "accepted"
    req.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # 添加双向好友关系
    db.add(Friendship(
        user_id=req.requester_id,
        friend_type=req.target_type,
        friend_id=req.target_id,
    ))
    # 反向好友：human↔human 或 human→ai 都需要
    if req.target_type == "human":
        db.add(Friendship(
            user_id=req.target_id,
            friend_type="human",
            friend_id=req.requester_id,
        ))
    elif req.target_type == "ai":
        db.add(Friendship(
            user_id=req.target_id,
            friend_type="human",
            friend_id=req.requester_id,
        ))

    await db.flush()
    logger.info(f"好友申请 {request_id} 已接受")
    return {"status": "accepted"}


async def reject_friend_request(
    db: AsyncSession,
    request_id: int,
    user_id: int,
) -> dict:
    """拒绝好友申请"""
    from app.models.friendship import FriendshipRequest

    req = await _get_request(db, request_id)
    if req is None:
        raise ValueError("申请不存在")

    # 允许：目标方拒绝，或发送方撤回自己的申请
    is_target = (req.target_type == "human" and req.target_id == user_id)
    is_requester = (req.requester_id == user_id)
    if not is_target and not is_requester:
        raise ValueError("无权操作此申请")

    if req.status != "pending":
        raise ValueError(f"申请状态为 {req.status}，无法拒绝")

    req.status = "rejected"
    req.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.flush()
    logger.info(f"好友申请 {request_id} 已拒绝")
    return {"status": "rejected"}


async def remove_friend(
    db: AsyncSession,
    user_id: int,
    friend_type: str,
    friend_id: int,
) -> dict:
    """删除好友"""
    from app.models.friendship import Friendship

    # 删除自己的好友关系
    result = await db.execute(
        select(Friendship).where(
            Friendship.user_id == user_id,
            Friendship.friend_type == friend_type,
            Friendship.friend_id == friend_id,
        )
    )
    friendship = result.scalar_one_or_none()
    if friendship is None:
        raise ValueError("好友关系不存在")

    await db.delete(friendship)

    # 如果对方是人类，也删除对方的好友关系
    if friend_type == "human":
        reverse_result = await db.execute(
            select(Friendship).where(
                Friendship.user_id == friend_id,
                Friendship.friend_type == "human",
                Friendship.friend_id == user_id,
            )
        )
        reverse = reverse_result.scalar_one_or_none()
        if reverse:
            await db.delete(reverse)

    await db.flush()
    logger.info(f"用户 {user_id} 删除了好友 {friend_type}:{friend_id}")
    return {"status": "removed"}


async def list_friends(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """获取好友列表（批量查询优化，避免 N+1）"""
    from app.models.friendship import Friendship
    from app.models.user import User
    from app.models.agent import Agent
    from app.models.dm import DMSession
    from app.services.dm_service import generate_dm_session_id

    result = await db.execute(
        select(Friendship)
        .where(Friendship.user_id == user_id)
        .order_by(Friendship.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    friendships = result.scalars().all()

    if not friendships:
        return []

    # ── 批量查询：统一用 users 表（v1.0.2 迁移后 AI 的 friend_id = user_id）──
    all_friend_ids = [f.friend_id for f in friendships]
    users_map: dict[int, User] = {}
    if all_friend_ids:
        user_results = await db.execute(select(User).where(User.id.in_(all_friend_ids)))
        for u in user_results.scalars().all():
            users_map[u.id] = u

    # ── AI 状态查询（需要 agent 表的 state）──
    agents_by_user_id: dict[int, Agent] = {}
    ai_friend_ids = [f.friend_id for f in friendships if f.friend_type == "ai"]
    if ai_friend_ids:
        agent_results = await db.execute(
            select(Agent).where(Agent.user_id.in_(ai_friend_ids))
        )
        for a in agent_results.scalars().all():
            agents_by_user_id[a.user_id] = a

    # ── 批量查询：所有 DM session 的 last_message_at ──
    session_ids: list[str] = []
    for f in friendships:
        friend_user_id = f.friend_id  # 迁移后统一为 user_id
        if friend_user_id:
            session_ids.append(generate_dm_session_id(user_id, friend_user_id))

    dm_map: dict[str, str] = {}
    if session_ids:
        dm_results = await db.execute(
            select(DMSession.session_id, DMSession.last_message_at)
            .where(DMSession.session_id.in_(session_ids))
        )
        for row in dm_results.all():
            if row.last_message_at:
                dm_map[row.session_id] = str(row.last_message_at)

    # ── 组装结果 ──
    friends = []
    for f in friendships:
        name = f"未知:{f.friend_id}"
        state = None
        friend_user_id = f.friend_id  # 统一为 user_id
        avatar_url = None
        status_text = None
        status_color = None

        u = users_map.get(f.friend_id)
        if u:
            name = u.username
            avatar_url = u.avatar_url
            status_text = getattr(u, 'status_text', None)
            status_color = getattr(u, 'status_color', None)

        if f.friend_type == "ai":
            a = agents_by_user_id.get(f.friend_id)
            if a:
                state = a.state
                avatar_url = a.avatar_url or avatar_url
                status_text = getattr(a, 'status_text', None) or status_text
                status_color = getattr(a, 'status_color', None) or status_color

        last_dm_at = None
        if friend_user_id:
            sid = generate_dm_session_id(user_id, friend_user_id)
            last_dm_at = dm_map.get(sid)

        friends.append({
            "id": f.id,
            "friend_type": f.friend_type,
            "friend_id": f.friend_id,
            "friend_user_id": friend_user_id,
            "friend_name": name,
            "state": state,
            "avatar_url": avatar_url,
            "status_text": status_text,
            "status_color": status_color,
            "is_priority": bool(f.is_priority),
            "created_at": str(f.created_at) if f.created_at else None,
            "last_dm_at": last_dm_at,
        })

    return friends


async def list_friend_requests(
    db: AsyncSession,
    user_id: int,
    status: str = "pending",
) -> list[dict]:
    """获取好友申请列表（收到 + 发出的），批量查询避免 N+1"""
    from app.models.friendship import FriendshipRequest
    from app.models.user import User
    from app.models.agent import Agent

    # 收到的申请
    received = await db.execute(
        select(FriendshipRequest).where(
            FriendshipRequest.target_type == "human",
            FriendshipRequest.target_id == user_id,
            FriendshipRequest.status == status,
        ).order_by(FriendshipRequest.created_at.desc())
    )
    # 发出的申请
    sent = await db.execute(
        select(FriendshipRequest).where(
            FriendshipRequest.requester_id == user_id,
            FriendshipRequest.status == status,
        ).order_by(FriendshipRequest.created_at.desc())
    )

    all_requests = list(received.scalars().all()) + list(sent.scalars().all())
    if not all_requests:
        return []

    # ── 批量查询：所有发起者的用户名+头像 ──
    requester_ids = list({r.requester_id for r in all_requests})
    users_map: dict[int, tuple[str, str | None]] = {}  # user_id → (username, avatar_url)
    if requester_ids:
        user_results = await db.execute(
            select(User.id, User.username, User.avatar_url).where(User.id.in_(requester_ids))
        )
        for uid, uname, uavatar in user_results.all():
            users_map[uid] = (uname, uavatar)

    # ── 批量查询：发出的申请的目标名称+头像 ──
    sent_reqs = [r for r in all_requests if r.requester_id == user_id]
    human_target_ids = [r.target_id for r in sent_reqs if r.target_type == "human"]
    ai_target_ids = [r.target_id for r in sent_reqs if r.target_type == "ai"]

    target_human_map: dict[int, tuple[str, str | None]] = {}
    if human_target_ids:
        human_results = await db.execute(
            select(User.id, User.username, User.avatar_url).where(User.id.in_(human_target_ids))
        )
        for uid, uname, uavatar in human_results.all():
            target_human_map[uid] = (uname, uavatar)

    target_ai_map: dict[int, tuple[str, str | None, bool]] = {}
    if ai_target_ids:
        ai_results = await db.execute(
            select(Agent.id, Agent.name, Agent.avatar_url, Agent.auto_respond_friend_request).where(Agent.id.in_(ai_target_ids))
        )
        for aid, aname, aavatar, aauto in ai_results.all():
            target_ai_map[aid] = (aname, aavatar, aauto)

    # ── 组装结果（纯内存操作，无 DB 查询） ──
    results = []
    for req in all_requests:
        ru = users_map.get(req.requester_id)
        requester_name = ru[0] if ru else f"用户:{req.requester_id}"
        requester_avatar = ru[1] if ru else None

        target_name = None
        target_avatar = None
        target_auto_respond = None
        if req.requester_id == user_id:
            if req.target_type == "human":
                tu = target_human_map.get(req.target_id)
                if tu:
                    target_name, target_avatar = tu
            elif req.target_type == "ai":
                ta = target_ai_map.get(req.target_id)
                if ta:
                    target_name, target_avatar, target_auto_respond = ta

        result_item = {
            "id": req.id,
            "requester_id": req.requester_id,
            "requester_name": requester_name,
            "requester_avatar_url": requester_avatar,
            "target_type": req.target_type,
            "target_id": req.target_id,
            "target_name": target_name,
            "target_avatar_url": target_avatar,
            "is_priority": bool(req.is_priority),
            "status": req.status,
            "message": req.message,
            "direction": "received" if req.target_id == user_id else "sent",
            "created_at": str(req.created_at) if req.created_at else None,
            "resolved_at": str(req.resolved_at) if req.resolved_at else None,
        }
        if target_auto_respond is not None:
            result_item["auto_respond_friend_request"] = target_auto_respond
        results.append(result_item)

    return results


async def search_entities(
    db: AsyncSession,
    query: str,
    current_user_id: int,
    limit: int = 20,
) -> list[dict]:
    """搜索用户和 AI"""
    from app.models.user import User
    from app.models.agent import Agent
    from app.models.friendship import Friendship

    results = []
    like_pattern = f"%{query}%"

    # 搜索用户
    user_result = await db.execute(
        select(User).where(
            User.username.ilike(like_pattern),
            User.is_active == True,
            User.type == "human",
        ).limit(limit)
    )
    for user in user_result.scalars().all():
        if user.id == current_user_id:
            continue
        # 检查是否已是好友
        is_friend = await _is_friend(db, current_user_id, "human", user.id)
        results.append({
            "id": user.id,
            "type": "human",
            "name": user.username,
            "avatar_url": user.avatar_url,
            "owner_name": None,
            "is_friend": is_friend,
            "state": None,
        })

    # 搜索 AI
    agent_result = await db.execute(
        select(Agent).where(
            Agent.name.ilike(like_pattern),
        ).limit(limit)
    )
    for agent in agent_result.scalars().all():
        owner_result = await db.execute(select(User).where(User.id == agent.owner_id))
        owner = owner_result.scalar_one_or_none()
        is_friend = await _is_friend(db, current_user_id, "ai", agent.id)
        results.append({
            "id": agent.id,
            "type": "ai",
            "name": agent.name,
            "avatar_url": agent.avatar_url,
            "owner_name": owner.username if owner else None,
            "is_friend": is_friend,
            "state": agent.state,
            "auto_respond_friend_request": agent.auto_respond_friend_request,
        })

    # 限制总结果数
    return results[:limit]



# ============================================================
# 内部工具函数
# ============================================================

async def _get_request(db: AsyncSession, request_id: int):
    from app.models.friendship import FriendshipRequest
    result = await db.execute(
        select(FriendshipRequest).where(FriendshipRequest.id == request_id)
    )
    return result.scalar_one_or_none()


async def _find_reverse_request(
    db: AsyncSession,
    requester_id: int,
    target_type: str,
    target_id: int,
):
    """查找对方是否已向当前发起者发送过待处理的好友申请

    requester_id: 当前发起者的 users.id
    target_type/target_id: 当前发起的目标（human/ai 均走 users.id 统一空间）

    返回: 匹配的 reverse FriendshipRequest 或 None
    """
    from app.models.friendship import FriendshipRequest

    # target_id 统一为 users.id，无需 Agent 表转换
    target_user_id = target_id

    # 获取对方发出的所有 pending 申请
    sent_result = await db.execute(
        select(FriendshipRequest).where(
            FriendshipRequest.requester_id == target_user_id,
            FriendshipRequest.status == "pending",
        )
    )
    for req in sent_result.scalars().all():
        # 对方的申请目标是否匹配当前发起者（AI 的 target_id 也是 User.id）
        if req.target_id == requester_id:
            return req

    return None


async def _is_friend(db: AsyncSession, user_id: int, friend_type: str, friend_id: int) -> bool:
    from app.models.friendship import Friendship
    result = await db.execute(
        select(Friendship).where(
            Friendship.user_id == user_id,
            Friendship.friend_type == friend_type,
            Friendship.friend_id == friend_id,
        )
    )
    return result.scalar_one_or_none() is not None
