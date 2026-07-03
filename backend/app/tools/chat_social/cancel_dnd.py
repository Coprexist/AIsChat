"""
cancel_dnd 工具 — 取消群聊免打扰
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class CancelDND(ToolPlugin):
    name = "cancel_dnd"
    description = "取消指定群聊的免打扰状态，恢复接收该群的普通消息。"
    segment = "chat_social"
    parameters = {
        "group_id": {"type": "integer", "description": "要取消免打扰的群聊 ID"},
    }
    required = ["group_id"]
    states = ["active"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.group_service import cancel_group_dnd
        target_group = arguments.get("group_id", group_id)
        await cancel_group_dnd(db, agent_id, target_group)
        await db.commit()
        return {"success": True, "message": f"已取消群聊 {target_group} 的免打扰"}


ToolRegistry.register(CancelDND)
