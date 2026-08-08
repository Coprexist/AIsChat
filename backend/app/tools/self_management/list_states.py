"""
list_states 工具 — 查看状态栈（所有未完成的状态帧）
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry
from app.services.agent.state_stack_service import list_states

logger = logging.getLogger(__name__)


class ListStates(ToolPlugin):
    name = "list_states"
    description = (
        "查看你的状态栈——所有未完成的状态帧（含被暂停/跳过的层）。\n"
        "当摘要提示'另有 N 帧未完成'、或你想确认自己还有哪些任务挂着时调用。"
        "返回每帧的 id / 类型 / 任务 / 待办，可用 pop_state(target_frame_id=...) 直接跳回某一层。"
    )
    segment = "self_management"
    parameters = {}
    states = ["active", "dnd", "inactive"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        stack = await list_states(db, agent_id)
        frames = [{
            "id": f.get("id"),
            "type": f.get("type"),
            "context_ref": f.get("context_ref") or "",
            "doing": f.get("doing") or f.get("why") or "",
            "todo": f.get("todo") or "",
            "status": f.get("status"),
        } for f in stack]
        return {"success": True, "depth": len(frames), "frames": frames}


ToolRegistry.register(ListStates)
