"""
set_status 工具 — AI 设置自己的自定义状态文本
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry
from app.utils.text import validate_status_text

logger = logging.getLogger(__name__)


class SetStatus(ToolPlugin):
    name = "set_status"
    description = (
        "设置你的自定义状态文本，展示在你的资料卡中。"
        "可以随时更新，用来表达你当前在做什么、心情如何等。"
        "中文最多 10 字，英文最多 30 字符。"
        "设置为空字符串可清除状态。"
    )
    segment = "self_config"
    parameters = {
        "status_text": {
            "type": "string",
            "description": "自定义状态文本。中文至少 10 字，英文至少 20 字符，最多 100 字。设为空字符串 '' 可清除状态。",
        },
    }
    required = ["status_text"]
    states = ["active", "dnd", "inactive"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.models.agent import Agent as AgentModel

        status_text = arguments.get("status_text", "")

        # 校验长度
        try:
            status_text = validate_status_text(status_text if status_text else None)
        except ValueError as e:
            return {"error": True, "message": str(e)}

        result = await db.execute(select(AgentModel).where(AgentModel.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            return {"error": True, "message": "AI 代理不存在"}

        agent.status_text = status_text if status_text else None
        await db.commit()

        if status_text:
            return {
                "success": True,
                "status_text": status_text,
                "message": f"状态已更新为「{status_text}」",
            }
        else:
            return {
                "success": True,
                "status_text": None,
                "message": "状态已清除",
            }


ToolRegistry.register(SetStatus)
