"""
end_turn 工具 — AI 结束当前回复轮次（不改变状态）
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class EndTurn(ToolPlugin):
    name = "end_turn"
    description = (
        "结束当前回复轮次，把发言权交还给对方。调用后本轮终止，不会再触发后续 API。"
        "如需同时切换状态（如下线），必须在同一个 tool_calls 中先调用 switch_state/set_dnd 再调用 end_turn。"
    )
    segment = "self_management"
    parameters = {}
    required = []
    states = ["active", "dnd", "inactive"]
    admin_description = "结束当前回复轮次，将发言权交还给对话方。调用后本轮终止，不会继续触发 API 调用。"
    trigger_condition = "AI 认为本轮回复已完成时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        return {
            "success": True,
            "end_turn": True,
            "message": "已结束本轮回复",
        }


ToolRegistry.register(EndTurn)
