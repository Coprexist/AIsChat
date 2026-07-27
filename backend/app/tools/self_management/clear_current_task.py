"""
clear_current_task 工具 — AI 清除当前任务
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class ClearCurrentTask(ToolPlugin):
    name = "clear_current_task"
    description = "清除当前任务——表示你完成了或放弃了手头的事。比如用户说「别写了」「不用管那个了」，你就该调用这个。清除后系统不会再提醒你恢复那个任务。"
    segment = "self_management"
    parameters = {
        "reason": {"type": "string", "nullable": True, "description": "可选：为什么清除（完成/放弃/被用户叫停/其他）"},
    }
    required = []
    states = ["active", "dnd", "inactive"]
    admin_description = "清除当前任务标记。完成或放弃手头任务时调用，释放工作区焦点。"
    trigger_condition = "任务完成或被放弃时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.agent.workspace_service import clear_task

        reason = arguments.get("reason", "手动清除")
        try:
            await clear_task(db, agent_id)
            await db.commit()
            return {"success": True, "message": f"已清除当前任务（原因：{reason}）"}
        except Exception as e:
            logger.error(f"clear_current_task 失败 (agent={agent_id}): {e}", exc_info=True)
            return {"error": True, "message": f"清除任务失败: {e}"}


ToolRegistry.register(ClearCurrentTask)
