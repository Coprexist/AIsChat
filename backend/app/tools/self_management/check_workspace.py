"""
check_workspace 工具 — AI 查看当前工作区状态
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class CheckWorkspace(ToolPlugin):
    name = "check_workspace"
    description = "查看你当前的工作区状态——你现在在做什么任务、是否被打断过。这就像你的「内心待办条」，可以随时查看自己手头有什么事。"
    segment = "self_management"
    parameters = {}
    required = []
    states = ["active", "dnd", "offline"]
    admin_description = "查看自己的工作区状态：当前任务、文件数量、待处理事项概览。AI 启动或回归时了解自身状态。"
    trigger_condition = "AI 启动、回归或需要了解自身状态时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.agent.workspace_service import get_workspace_status

        try:
            status = await get_workspace_status(db, agent_id)
            return status
        except Exception as e:
            logger.error(f"check_workspace 失败 (agent={agent_id}): {e}", exc_info=True)
            return {"error": True, "message": f"获取工作区状态失败: {e}"}


ToolRegistry.register(CheckWorkspace)
