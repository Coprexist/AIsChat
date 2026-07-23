"""
invite_to_group 工具 — AI 邀请成员加入群聊
"""
import logging
from sqlalchemy import select as _sel2
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class InviteToGroup(ToolPlugin):
    name = "invite_to_group"
    description = "邀请成员加入群聊"
    segment = "group_management"
    parameters = {
        "group_id": {"type": "integer", "description": "目标群聊 ID"},
        "member_type": {"type": "string", "enum": ["human", "ai"], "description": "成员类型"},
        "member_id": {"type": "integer", "description": "成员 ID"},
    }
    required = ["group_id", "member_type", "member_id"]
    states = ["active"]
    admin_description = "邀请用户或其他 AI 加入群聊。需要是群主或具有管理权限的成员才能操作。"
    trigger_condition = "有新成员需要加入群聊时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.chat.message import add_member
        from app.models.agent import Agent

        agent_result = await db.execute(_sel2(Agent).where(Agent.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        if agent and (agent.ai_type or "resonance") == "general":
            return {"error": True, "message": "通用AI不能邀请成员进群"}

        target_group = arguments.get("group_id", group_id)
        member_type = arguments["member_type"]
        member_id = arguments["member_id"]

        try:
            await add_member(db, target_group, member_type, member_id)
            await db.commit()
            return {"success": True, "message": f"已邀请 {member_type}:{member_id} 加入群聊"}
        except ValueError as e:
            return {"error": True, "message": str(e)}


ToolRegistry.register(InviteToGroup)
