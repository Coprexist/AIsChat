"""
set_friend_priority 工具 — AI/人类设置特别关心好友
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class SetFriendPriority(ToolPlugin):
    name = "set_friend_priority"
    description = (
        "设置或取消特别关心好友。设为特别关心后，该好友的消息可穿透免打扰。"
    )
    segment = "chat_social"
    parameters = {
        "friend_id": {"type": "integer", "description": "好友的用户 ID"},
        "enabled": {"type": "boolean", "description": "True=设特别关心，False=取消"},
    }
    required = ["friend_id", "enabled"]
    states = ["active", "dnd"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.models.friendship import Friendship
        from app.models.agent import Agent as AgentModel

        friend_id = arguments["friend_id"]
        enabled = arguments["enabled"]

        # 获取 AI 的 owner_id
        a_result = await db.execute(select(AgentModel).where(AgentModel.id == agent_id))
        agent = a_result.scalar_one_or_none()
        if not agent:
            return {"error": True, "message": "AI 不存在"}
        owner_id = agent.owner_id

        f_result = await db.execute(
            select(Friendship).where(
                Friendship.user_id == owner_id,
                Friendship.friend_id == friend_id,
            )
        )
        friendship = f_result.scalar_one_or_none()
        if not friendship:
            return {"error": True, "message": "还不是好友，无法设置特别关心"}

        friendship.is_priority = enabled
        await db.commit()

        return {
            "success": True,
            "message": f"已{'设为' if enabled else '取消'}特别关心",
        }


ToolRegistry.register(SetFriendPriority)
