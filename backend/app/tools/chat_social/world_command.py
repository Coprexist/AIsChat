"""
world_command 工具 — 群 AI 操作绑定世界（命令统一交给世界程序解析）

缓存友好：所有 AI 统一注入同一个稳定工具（定义与具体世界无关，前缀缓存不损）；
具体命令语法由系统提示末尾的【本群世界】能力清单（动态尾部）展示。

执行 = 以 AI 身份发群消息（source="user" 触发群消息钩子）→ 世界程序 main.py handle()
解析执行 → SSE 实时生效。命令在群里可见可审计，与用户共用同一套语法（零重复逻辑）。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import ToolPlugin

logger = logging.getLogger(__name__)


class WorldCommand(ToolPlugin):
    name = "world_command"
    description = "向当前群绑定的世界发送命令（操作世界：移动角色/触发事件/查询状态等，语法由世界程序定义）。仅群聊可用；具体命令清单见系统提示末尾的【本群世界】。"
    segment = "chat_social"
    parameters = {
        "command": {
            "type": "string",
            "description": "发送给世界程序的命令文本，如「旅人移动到 2,3」/「我去 2,3」/「身份 签到」",
        },
    }
    required = ["command"]
    states = ["active", "dnd", "inactive"]
    admin_description = "群 AI 通过命令操作本群绑定的世界（与用户共用世界程序语法）"
    trigger_condition = "本群绑定了世界，且需要操作世界时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        command = str(arguments.get("command", "")).strip()
        if not command:
            return {"error": True, "message": "command 不能为空"}
        if group_id is None:
            return {"error": True, "message": "world_command 仅群聊可用（需要群绑定世界）"}

        # 查本群绑定的世界
        from app.models.world import WorldBinding
        rows = (await db.execute(
            select(WorldBinding).where(
                WorldBinding.entity_type == "group",
                WorldBinding.entity_id == group_id,
            )
        )).scalars().all()
        if not rows:
            return {"error": True, "message": "本群未绑定世界（可在世界列表给群配置世界后使用）"}
        world_id = rows[0].world_id

        # 以 AI 身份发群消息 → 群消息钩子（source="user"）→ 世界程序 handle 解析执行
        from app.chat.message import create_message
        await create_message(db, group_id, "ai", agent_id, command, source="user")

        return {
            "success": True,
            "message": f"命令已交给世界程序处理（你以群里可见的方式发布了：{command}）",
            "world_id": world_id,
        }
