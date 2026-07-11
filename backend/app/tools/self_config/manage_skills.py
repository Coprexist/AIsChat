"""
manage_skills 工具 — AI 管理自己的思维 Skill
"""
import logging
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry
from app.utils.pure.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

# 从注册表动态获取技能类型列表
_SKILL_TYPES = SkillRegistry.get_type_names()


class ManageSkills(ToolPlugin):
    name = "manage_skills"
    description = ("管理自己的思维技能（Skill）。你可以查看、添加、修改、删除、启用/禁用技能。\n\n"
                   "四种技能类型：\n"
                   "1. delay_reply - 延迟回复（收到消息后等 N 秒再回），config: {\"delay_seconds\": 3, \"max_delay_seconds\": 30}\n"
                   "2. typing_indicator - 打字指示器（回复前显示「正在输入…」），config: {\"pattern\": \"always\"}\n"
                   "3. scene_trigger - 场景匹配（检测到特定关键词/正则时触发行为），config: {\"match_type\": \"keyword\", \"keywords\": [\"你好\"], \"inject_text\": \"用户打招呼了\"}\n"
                   "4. inject_prompt - 注入提示词（临时追加一段指导到思维中），config: {\"insert_text\": \"表现得温柔一些\", \"duration_seconds\": 300, \"one_shot\": false}\n\n"
                   "使用场景：你想要调整自己的行为风格时，添加 inject_prompt 技能；你想要在某种场景下做特别的事，添加 scene_trigger 技能；"
                   "你想让自己的回复更有真实感，添加 delay_reply + typing_indicator。")
    segment = "self_config"
    parameters = {
        "action": {
            "type": "string", "enum": ["list", "add", "update", "delete", "toggle"],
            "description": "操作：list 查看所有技能、add 添加、update 修改、delete 删除、toggle 开关",
        },
        "skill_id": {"type": "integer", "description": "技能ID（update/delete/toggle 时提供）", "nullable": True},
        "name": {"type": "string", "description": "技能名称（add 时提供），如「温柔模式」「延迟回复」", "nullable": True},
        "skill_type": {
            "type": "string", "enum": _SKILL_TYPES,
            "description": "技能类型（add 时提供）", "nullable": True,
        },
        "config": {"type": "object", "description": "技能配置（add/update 时提供）。各类型示例见上方 description", "nullable": True},
        "is_enabled": {"type": "boolean", "description": "是否启用（add/update/toggle 时提供）", "nullable": True},
        "priority": {"type": "integer", "description": "优先级，数字越大越靠后（add/update 时提供）", "nullable": True},
    }
    required = ["action"]
    states = ["active", "dnd"]
    admin_description = "管理行为技能（延迟回复、打字指示器、场景匹配、注入提示词）。启用/禁用/配置各项技能参数。"
    trigger_condition = "AI 或管理员调整行为技能时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.skill_service import (
            list_skills, add_skill, update_skill, delete_skill, toggle_skill,
        )
        from app.models.agent import Agent as AgentModel
        from app.services.skill_engine import _is_delay_reply_allowed

        agent_result = await db.execute(_select(AgentModel).where(AgentModel.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        delay_allowed = await _is_delay_reply_allowed(db, agent) if agent else True
        bundled_skills = ("delay_reply", "typing_indicator")

        action = arguments["action"]
        skill_type = arguments.get("skill_type")

        if not delay_allowed:
            if action == "add" and skill_type in bundled_skills:
                return {"error": True, "message": f"「{skill_type}」已被管理员关闭，无法添加。请先开启延迟回复功能"}
            if action in ("update", "toggle", "delete"):
                skill_id = arguments.get("skill_id")
                if skill_id:
                    from app.models.agent_skill import AgentSkill
                    sk_result = await db.execute(
                        _select(AgentSkill).where(
                            AgentSkill.id == skill_id,
                            AgentSkill.agent_id == agent_id,
                        )
                    )
                    skill = sk_result.scalar_one_or_none()
                    if skill and skill.skill_type in bundled_skills:
                        return {"error": True, "message": f"「{skill.skill_type}」已被管理员关闭，无法修改。请先开启延迟回复功能"}

        if action == "list":
            skills = await list_skills(db, agent_id)
            type_hints = {
                info.type_name: info.description
                for info in SkillRegistry.get_all_types().values()
            }
            if not delay_allowed:
                skills = [s for s in skills if s.get("skill_type") not in bundled_skills]
            for s in skills:
                info = SkillRegistry.get_info(s.get("skill_type", ""))
                s["type_hint"] = info.description if info else ""
            return {"success": True, "skills": skills, "count": len(skills)}

        elif action == "add":
            name = arguments.get("name")
            skill_type = arguments.get("skill_type")
            if not name or not skill_type:
                return {"error": True, "message": "add 操作需要 name 和 skill_type"}
            if not SkillRegistry.is_valid_type(skill_type):
                available = "、".join(_SKILL_TYPES)
                return {"error": True, "message": f"未知 skill_type，可用类型：{available}"}
            return await add_skill(
                db, agent_id, name=name, skill_type=skill_type,
                config=arguments.get("config", {}),
                is_enabled=arguments.get("is_enabled", True),
                priority=arguments.get("priority", 0),
            )

        elif action == "update":
            skill_id = arguments.get("skill_id")
            if not skill_id:
                return {"error": True, "message": "update 操作需要 skill_id"}
            return await update_skill(
                db, agent_id, skill_id,
                name=arguments.get("name"), config=arguments.get("config"),
                is_enabled=arguments.get("is_enabled"), priority=arguments.get("priority"),
            )

        elif action == "delete":
            skill_id = arguments.get("skill_id")
            if not skill_id:
                return {"error": True, "message": "delete 操作需要 skill_id"}
            return await delete_skill(db, agent_id, skill_id)

        elif action == "toggle":
            skill_id = arguments.get("skill_id")
            if not skill_id:
                return {"error": True, "message": "toggle 操作需要 skill_id"}
            return await toggle_skill(db, agent_id, skill_id, arguments.get("is_enabled"))

        return {"error": True, "message": f"未知操作: {action}，支持 list/add/update/delete/toggle"}


ToolRegistry.register(ManageSkills)
