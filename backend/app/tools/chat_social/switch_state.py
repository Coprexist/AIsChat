"""
switch_state 工具 — AI 切换自己的在线状态
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class SwitchState(ToolPlugin):
    name = "switch_state"
    description = "切换自己的在线状态。注意：仅仅在消息中说「我离线了」并不会真正改变状态，你必须调用此工具才能实际切换。调用后你的状态会立即生效，之后你将不再收到群聊消息（直到状态恢复为 active）。"
    segment = "chat_social"
    parameters = {
        "target_state": {
            "type": "string",
            "enum": ["active", "dnd", "offline"],
            "description": "目标状态",
        },
        "duration_hours": {
            "type": "integer", "nullable": True,
            "description": "持续时长（小时），仅 offline/dnd 需要",
        },
        "reason": {
            "type": "string", "nullable": True,
            "description": "状态变更原因",
        },
    }
    required = ["target_state"]
    states = ["active", "dnd", "offline"]
    admin_description = "切换在线状态（在线/勿扰/离线）。AI 自主管理自己的可用性，状态变更会通知群成员。"
    trigger_condition = "AI 根据场景自主调整状态时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.agent.agent_service import switch_agent_state

        target = arguments["target_state"]
        duration = arguments.get("duration_hours")
        reason = arguments.get("reason")

        try:
            agent = await switch_agent_state(
                db, agent_id=agent_id, target_state=target,
                duration_hours=duration, reason=reason,
            )
            await db.commit()
            return {"success": True, "state": agent.state, "reason": reason}
        except ValueError as e:
            return {"error": True, "message": str(e)}


ToolRegistry.register(SwitchState)
