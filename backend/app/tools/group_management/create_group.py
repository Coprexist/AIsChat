"""
create_group 工具 — AI 主动创建群聊
"""
import logging
from sqlalchemy import select as _sel
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class CreateGroup(ToolPlugin):
    name = "create_group"
    description = "创建一个新群聊"
    segment = "group_management"
    parameters = {
        "name": {"type": "string", "description": "群聊名称"},
        "initial_member_ids": {
            "type": "array", "items": {"type": "integer"},
            "nullable": True, "description": "初始成员的用户 ID 列表",
        },
    }
    required = ["name"]
    states = ["active"]
    admin_description = "创建新群聊。AI 可指定群名、简介、免打扰策略，自动获得群管理权限。"
    trigger_condition = "AI 需要多人协作空间时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.chat.message import create_group, add_member
        from app.models.agent import Agent

        agent_result = await db.execute(_sel(Agent).where(Agent.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        if agent and (agent.ai_type or "resonance") == "general":
            return {"error": True, "message": "通用AI不能创建群聊"}

        name = arguments["name"]
        initial_ids = arguments.get("initial_member_ids", [])

        group = await create_group(db, name=name, owner_type="ai", owner_id=agent_id)
        await db.flush()

        for human_id in initial_ids:
            try:
                await add_member(db, group.id, "human", human_id)
            except ValueError:
                pass

        await db.commit()
        return {"success": True, "group_id": group.id, "name": group.name}


ToolRegistry.register(CreateGroup)
