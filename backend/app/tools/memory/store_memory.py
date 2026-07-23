"""
store_memory 工具 — AI 存储长期记忆
"""
import logging
from sqlalchemy import select as _sel
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class StoreMemory(ToolPlugin):
    name = "store_memory"
    description = "存储一条记忆（用于以后回忆）"
    segment = "memory"
    parameters = {
        "title": {"type": "string", "description": "记忆标题（简短概括）"},
        "content": {"type": "string", "description": "记忆详细内容"},
        "scope": {
            "type": "string", "enum": ["private", "group"],
            "description": "记忆范围：private 仅自己可见，group 群内成员可见",
        },
        "group_id": {
            "type": "integer", "nullable": True,
            "description": "群聊 ID（scope=group 时需要）",
        },
    }
    required = ["title", "content", "scope"]
    states = ["active"]
    admin_description = "将重要信息存入长期记忆（向量数据库）。记忆按用户隔离存储，构成 AI 的「人生经历」，影响未来决策。"
    trigger_condition = "AI 认为信息值得长期记忆时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.memory.memory_buffer import enqueue_memory
        from app.models.agent import Agent

        title = arguments["title"]
        content = arguments["content"]
        scope = arguments["scope"]
        mem_group_id = arguments.get("group_id", group_id if scope == "group" else None)

        agent_row = await db.execute(_sel(Agent).where(Agent.id == agent_id))
        agent_obj = agent_row.scalar_one_or_none()
        ai_type = agent_obj.ai_type if agent_obj else "resonance"
        trigger_user_id = context.get("trigger_user_id")

        api_key = context.get("api_key")
        api_base = context.get("api_base_url", "https://api.deepseek.com")

        await enqueue_memory(
            agent_id=agent_id, title=title, content=content,
            scope=scope, group_id=mem_group_id,
            api_base_url=api_base, api_key=api_key,
            trigger_user_id=trigger_user_id, ai_type=ai_type,
            source="tool", low_value=False,
        )
        return {"success": True, "title": title, "queued": True}


ToolRegistry.register(StoreMemory)
