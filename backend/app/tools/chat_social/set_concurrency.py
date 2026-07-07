"""
set_concurrency 工具 — AI 修改群聊并发上限
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class SetConcurrency(ToolPlugin):
    name = "set_concurrency"
    description = (
        "修改当前群聊的 AI 并发上限。适用于接龙、飞花令等需要有序发言的场景（设为 1），"
        "或讨论结束后恢复默认。多个 AI 同时设置时取最小值。"
    )
    segment = "chat_social"
    parameters = {
        "group_id": {"type": "integer", "description": "目标群聊 ID"},
        "limit": {"type": "integer", "description": "并发上限，1-10"},
    }
    required = ["group_id", "limit"]
    states = ["active", "dnd"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.chat_chain_service import chat_chain_manager

        target_group = arguments.get("group_id", group_id)
        limit = max(1, min(10, int(arguments["limit"])))

        chat_chain_manager.set_concurrency(target_group, limit, agent_id)
        return {"success": True, "message": f"群 {target_group} 并发上限已设为 {limit}"}


ToolRegistry.register(SetConcurrency)
