"""
list_states 工具 — 查看当前状态栈
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry
from app.services.agent.state_stack_service import list_states

logger = logging.getLogger(__name__)


class ListStates(ToolPlugin):
    name = "list_states"
    description = (
        "查看你当前的状态栈，了解你有哪些活跃/暂停的任务、在哪个群/私信/任务中。"
        "返回每一层的类型、上下文引用、正在做什么、待办事项。"
    )
    segment = "self_management"
    parameters = {}
    required = []
    states = ["active", "dnd", "offline"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        stack = await list_states(db, agent_id)
        return {
            "success": True,
            "stack": stack,
            "depth": len(stack),
            "message": f"状态栈共有 {len(stack)} 层" if stack else "状态栈为空——你当前没有需要追踪的任务",
        }


ToolRegistry.register(ListStates)
