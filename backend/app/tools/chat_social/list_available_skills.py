"""
list_available_skills 工具 — AI 查看所有可用技能段和工具
"""
import logging
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class ListAvailableSkills(ToolPlugin):
    name = "list_available_skills"
    description = "查看所有可用的技能段（skill segments）。你可以看到哪些技能模块存在、每个模块包含什么工具、以及当前是否已加载。如果当前模式缺少你需要的能力（比如文件操作），可以调用此工具了解如何获取。"
    segment = "chat_social"
    parameters = {}
    required = []
    states = ["active", "dnd", "inactive"]
    admin_description = "列出当前可用的所有技能段和工具。AI 查看自己的「技能背包」了解当前能力边界。"
    trigger_condition = "AI 需要了解自身能力时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.models.agent import Agent as AgentModel
        from app.services.skill.skill_engine import _is_delay_reply_allowed

        agent_result = await db.execute(
            sa_select(AgentModel).where(AgentModel.id == agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if agent is None:
            return {"error": True, "message": "AI 代理不存在"}

        current_state = agent.state
        thinking_enabled = agent.thinking_enabled

        delay_allowed = await _is_delay_reply_allowed(db, agent)
        current_tools = ToolRegistry.get_allowed_tools(
            current_state, thinking_enabled=thinking_enabled,
            delay_reply_allowed=delay_allowed,
        )
        current_tool_names = {t["function"]["name"] for t in current_tools}

        segments = []
        for seg_key, seg_info in ToolRegistry.get_segments().items():
            seg_tools = seg_info["tools"]
            loaded_tools = [t for t in seg_tools if t["name"] in current_tool_names]
            segments.append({
                "key": seg_key,
                "name": seg_info["name"],
                "description": seg_info["description"],
                "total_tools": len(seg_tools),
                "loaded_tools": len(loaded_tools),
                "is_fully_loaded": len(loaded_tools) == len(seg_tools),
                "is_partially_loaded": 0 < len(loaded_tools) < len(seg_tools),
                "available_tools": loaded_tools,
                "unavailable_tools": [t for t in seg_tools if t["name"] not in current_tool_names],
            })

        return {
            "current_state": current_state,
            "thinking_enabled": thinking_enabled,
            "total_available_tools": len(current_tool_names),
            "segments": segments,
        }


ToolRegistry.register(ListAvailableSkills)
