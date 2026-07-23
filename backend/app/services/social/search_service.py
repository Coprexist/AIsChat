"""
搜索服务（v0.4.0: 从 friend_service 中提取，不再依赖好友系统）
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def search_entities(
    db: AsyncSession,
    query: str,
    current_user_id: int,
    limit: int = 20,
) -> list[dict]:
    """搜索用户和 AI（无需好友关系即可发起 DM），附带 is_friend 标记"""
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
        is_friend = False
        friend_check = await db.execute(
            select(Friendship).where(
                Friendship.user_id == current_user_id,
                Friendship.friend_type == "human",
                Friendship.friend_id == user.id,
            )
        )
        is_friend = friend_check.scalar_one_or_none() is not None
        results.append({
            "id": user.id,
            "type": "human",
            "name": user.username,
            "avatar_url": user.avatar_url,
            "owner_name": None,
            "state": None,
            "user_id": user.id,
            "is_friend": is_friend,
        })

    # 搜索 AI（仅返回 discoverable 的 AI）
    agent_result = await db.execute(
        select(Agent).where(
            Agent.name.ilike(like_pattern),
            Agent.discoverable == True,
        ).limit(limit)
    )
    for agent in agent_result.scalars().all():
        from app.models.user import User as UserModel
        owner_result = await db.execute(
            select(UserModel).where(UserModel.id == agent.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        # 检查是否已是好友（以 AI 的 unified user_id 为 friend_id）
        is_friend = False
        friend_check = await db.execute(
            select(Friendship).where(
                Friendship.user_id == current_user_id,
                Friendship.friend_type == "ai",
                Friendship.friend_id == agent.user_id,
            )
        )
        is_friend = friend_check.scalar_one_or_none() is not None
        results.append({
            "id": agent.user_id,  # 对外统一用 User.id（AI 也是 users 表的一条记录）
            "type": "ai",
            "name": agent.name,
            "avatar_url": agent.avatar_url,
            "owner_name": owner.username if owner else None,
            "state": agent.state,
            "user_id": agent.user_id,
            "is_friend": is_friend,
        })

    return results[:limit]
