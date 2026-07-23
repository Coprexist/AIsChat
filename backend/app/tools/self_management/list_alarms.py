"""
list_alarms 工具 — AI 查看闹钟列表
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class ListAlarms(ToolPlugin):
    name = "list_alarms"
    description = "查看你当前所有未触发的闹钟列表。"
    segment = "self_management"
    parameters = {}
    required = []
    states = ["active", "dnd", "offline"]
    admin_description = "查看自己设置的所有闹钟列表。AI 检查待执行的定时任务及其状态。"
    trigger_condition = "AI 检查待办定时任务时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.ai.alarm import list_alarms as svc_list_alarms

        try:
            result = await svc_list_alarms(db, agent_id)
            return result
        except Exception as e:
            logger.error(f"list_alarms 失败 (agent={agent_id}): {e}", exc_info=True)
            return {"error": True, "message": f"获取闹钟列表失败: {e}"}


ToolRegistry.register(ListAlarms)
