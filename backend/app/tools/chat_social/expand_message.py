"""
expand_message 工具 — AI 展开被折叠的消息完整内容
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class ExpandMessage(ToolPlugin):
    name = "expand_message"
    description = (
        "展开被折叠的群聊消息完整内容。群聊消息默认超过一定长度会被截断显示为 [展开 id=N]，"
        "如果确实需要看完整内容，用此工具展开。可一次展开多条。"
        "展开的内容不计入上下文限制，会追加在当前消息末尾。"
    )
    segment = "chat_social"
    parameters = {
        "group_id": {"type": "integer", "description": "目标群聊 ID"},
        "msg_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "要展开的消息 ID 列表",
        },
    }
    required = ["group_id", "msg_ids"]
    states = ["active", "dnd"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.models.message import Message
        from sqlalchemy import select

        target_group = arguments.get("group_id", group_id)
        msg_ids = arguments["msg_ids"]

        if not msg_ids:
            return {"error": True, "message": "请指定要展开的消息 ID"}

        result = await db.execute(
            select(Message.id, Message.content, Message.sender_type, Message.sender_id)
            .where(Message.id.in_(msg_ids), Message.group_id == target_group)
        )
        rows = {r[0]: r for r in result.all()}

        expanded = {}
        for mid in msg_ids:
            row = rows.get(mid)
            if row:
                expanded[str(mid)] = row[1]  # full content
            else:
                expanded[str(mid)] = f"[消息 {mid} 不存在或不属于此群]"

        return {"success": True, "expanded": expanded}


ToolRegistry.register(ExpandMessage)
