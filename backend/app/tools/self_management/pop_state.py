"""
pop_state 工具 — 结束当前状态帧，恢复上一层任务
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry
from app.services.state_stack_service import pop_state

logger = logging.getLogger(__name__)


class PopState(ToolPlugin):
    name = "pop_state"
    description = (
        "结束当前状态帧，自动恢复到上一个被打断的任务。"
        "调用后系统会告诉你应该回到什么任务继续。"
        "如果你完成了当前任务想回去，用这个；如果你不做了想放弃，用 close_state。"
    )
    segment = "self_management"
    parameters = {}
    required = []
    states = ["active", "dnd", "offline"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        stack, msg = await pop_state(db, agent_id)
        await db.commit()
        return {
            "success": True,
            "message": msg,
            "remaining_depth": len(stack),
            "next_frame": stack[-1] if stack else None,
        }


ToolRegistry.register(PopState)
