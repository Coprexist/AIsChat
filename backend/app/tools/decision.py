"""
决策技能工具 — AI 自配置「什么情景程序处理、什么情景才唤醒我本体」

产品 2026-08-13 定稿（world_decision_skill.md 阶段二）：
- 世界体系给 AI 提供配置自己决策技能的能力（list/write/delete_decision_skill）
- 存储：agent_skills(skill_type='decision')，config 即技能对象 {name, when, do, notify}
- 执行：决策引擎（decision_skill.run_decision_engine）在群触发链路优先匹配
- 群助手（非 agent 实体）由世界链路单独处理同三个工具（kind=group_assistant）
"""
import logging
import json

from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)

_RULE_SCHEMA_DESC = (
    "决策技能对象：{name, when:{event, conditions}, do:{action,...}, notify}。"
    "event 支持 group_message（字段：content/sender_id/sender_name/sender_type/group_id/is_mention/is_at_all/group_type）。"
    "conditions 递归条件树：{\"and\":[...]}/{\"or\":[...]}/{\"not\":{...}} 自由组装；"
    "叶子 {\"字段\":值}=等于，{\"字段_contains\":\"子串\"}、{\"字段_starts_with\":\"前缀\"}、"
    "{\"字段_matches\":\"正则\"}、{\"字段_gt/gte/lt/lte\":数值}。"
    "do 三选一：reply_template（{action,reply}固定回复，零成本）/ call_tool（{action,name,arguments}调平台工具）/ "
    "run_script（{action,code}沙箱脚本）。"
    "notify=true=命中后仍唤醒本体（关键时刻必须你来）；false=程序处理完即止（省调用）。同名覆盖，上限 20 条。"
    "示例：签到自动回复={\"name\":\"签到\",\"when\":{\"event\":\"group_message\",\"conditions\":{\"and\":[{\"content_contains\":\"签到\"},{\"not\":{\"is_mention\":true}}]}},\"do\":{\"action\":\"reply_template\",\"reply\":\"已记录签到 ✅\"},\"notify\":false}"
)


class ListDecisionSkills(ToolPlugin):
    name = "list_decision_skills"
    description = "查看你自己的决策技能列表（什么情景由程序自动处理、什么情景才触发你本体）。"
    parameters: dict = {}
    required: list = []

    async def execute(
        self, db: AsyncSession, agent_id: int, group_id: int | None,
        arguments: dict, context: dict,
    ) -> dict:
        from app.services.world.decision_skill import get_decision_rules
        rules = await get_decision_rules(db, "agent", agent_id)
        return {"success": True, "rules": rules, "count": len(rules)}


class WriteDecisionSkill(ToolPlugin):
    name = "write_decision_skill"
    description = (
        "配置你自己的决策技能：声明「遇到什么情景我干什么、是否必须唤醒我本体」。"
        + _RULE_SCHEMA_DESC
    )
    parameters: dict = {
        "rule": {"type": "object", "description": "完整决策技能对象（见描述）"},
    }
    required: list = ["rule"]

    async def execute(
        self, db: AsyncSession, agent_id: int, group_id: int | None,
        arguments: dict, context: dict,
    ) -> dict:
        from app.services.world.decision_skill import save_decision_rule
        rule = arguments.get("rule") or {}
        ok, err = await save_decision_rule(db, "agent", agent_id, rule)
        if not ok:
            return {"success": False, "error": err}
        return {"success": True, "name": str(rule.get("name") or "").strip()}


class DeleteDecisionSkill(ToolPlugin):
    name = "delete_decision_skill"
    description = "删除你自己的一个决策技能（按 name）。"
    parameters: dict = {
        "name": {"type": "string", "description": "要删除的技能名"},
    }
    required: list = ["name"]

    async def execute(
        self, db: AsyncSession, agent_id: int, group_id: int | None,
        arguments: dict, context: dict,
    ) -> dict:
        from app.services.world.decision_skill import delete_decision_rule
        await delete_decision_rule(db, "agent", agent_id, str(arguments.get("name") or ""))
        return {"success": True}


async def handle_decision_tool(
    db, kind: str, entity_id: int, name: str, arguments_json: str,
) -> dict:
    """群助手等非 agent 实体的决策工具执行入口（同三个工具语义）。"""
    try:
        args = json.loads(arguments_json or "{}") if isinstance(arguments_json, str) else (arguments_json or {})
    except json.JSONDecodeError:
        return {"success": False, "error": "参数解析失败"}
    from app.services.world.decision_skill import (
        get_decision_rules, save_decision_rule, delete_decision_rule,
    )
    if name == "list_decision_skills":
        rules = await get_decision_rules(db, kind, entity_id)
        return {"success": True, "rules": rules, "count": len(rules)}
    if name == "write_decision_skill":
        rule = args.get("rule") or {}
        ok, err = await save_decision_rule(db, kind, entity_id, rule)
        return {"success": ok, "name": str(rule.get("name") or "").strip()} if ok else {"success": False, "error": err}
    if name == "delete_decision_skill":
        await delete_decision_rule(db, kind, entity_id, str(args.get("name") or ""))
        return {"success": True}
    return {"success": False, "error": f"未知决策工具 {name}"}
