"""
决策技能（Decision Skill）— 事件 → AI 自写规则 → 程序化处理 or 唤醒本体

产品 2026-08-13 定稿（world_decision_skill.md 阶段二）：
- AI 不可能一直触发——大量事件由 AI 自写的决策技能程序化处理，
  只有关键时刻（@AI / notify=true / 全部未命中）才唤醒 LLM 本体。
- 归属：**AI 个体**——群 AI（agent 居民）与群助手（group_assistant）
  各自持有自己的决策技能，通过平台工具（list/write/delete_decision_skill）自配置。
- 存储：群 AI → agent_skills(skill_type='decision')；群助手 → group_assistants.config['decision_rules']。
- 技能结构：
    {
      "name": "签到自动回复",
      "when": {"event": "group_message",
               "conditions": {"and": [{"content_contains": "签到"}, {"not": {"is_mention": true}}]}},
      "do": {"action": "reply_template", "reply": "已记录你的签到 ✅"},   # 或 call_tool / run_script
      "notify": false   # true = 命中后仍唤醒本体（do 结果带给 LLM）
    }
- 条件 DSL：递归逻辑树 and/or/not + 字段运算（等于 / _contains / _starts_with /
  _matches 正则 / _gt _gte _lt _lte 数值），字段引用事件上下文。
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# 条件 DSL 解析（递归逻辑树 + 字段运算）
# ═══════════════════════════════════════════════════════════

_OPS = ("_starts_with", "_contains", "_matches", "_gte", "_gt", "_lte", "_lt")


def _field_op(cond_key: str) -> tuple[str, str | None]:
    """叶子条件键拆成 (字段, 运算)。无运算后缀 = 等于。"""
    for op in _OPS:
        if cond_key.endswith(op):
            return cond_key[: -len(op)], op
    return cond_key, None


def _apply_op(value, op: str | None, expect) -> bool:
    try:
        if op is None:
            return value == expect
        if op == "_contains":
            return str(expect) in str(value)
        if op == "_starts_with":
            return str(value).startswith(str(expect))
        if op == "_matches":
            return re.search(str(expect), str(value)) is not None
        if op in ("_gt", "_gte", "_lt", "_lte"):
            v, e = float(value), float(expect)
            return {"_gt": v > e, "_gte": v >= e, "_lt": v < e, "_lte": v <= e}[op]
    except (TypeError, ValueError):
        return False
    return False


def match_conditions(conditions, ctx: dict) -> bool:
    """递归条件树求值。conditions 结构：
    - {"and": [cond...]} / {"or": [cond...]} 组合节点
    - {"not": cond} 取反节点
    - 叶子：{"字段": 值} 或 {"字段_运算": 值}（字段引用 ctx）
    """
    if not isinstance(conditions, dict) or not conditions:
        return False
    if "and" in conditions:
        return all(match_conditions(c, ctx) for c in conditions["and"])
    if "or" in conditions:
        return any(match_conditions(c, ctx) for c in conditions["or"])
    if "not" in conditions:
        return not match_conditions(conditions["not"], ctx)
    # 叶子：单键（多键叶子按 and 处理）
    results = []
    for key, expect in conditions.items():
        field, op = _field_op(str(key))
        results.append(_apply_op(ctx.get(field), op, expect))
    return all(results)


# ═══════════════════════════════════════════════════════════
# 技能校验
# ═══════════════════════════════════════════════════════════

_MAX_RULES = 20          # 每实体技能上限
_MAX_DO_SCRIPT = 4000    # run_script 脚本/回复文本上限（字符）

_DO_ACTIONS = ("reply_template", "call_tool", "run_script")


def validate_rule(rule: dict) -> tuple[bool, str]:
    """校验决策技能结构，返回 (ok, error)。"""
    if not isinstance(rule, dict):
        return False, "技能必须是对象"
    name = str(rule.get("name") or "").strip()
    if not name or len(name) > 50:
        return False, "name 必填且 ≤50 字"
    when = rule.get("when") or {}
    if not isinstance(when, dict) or not str(when.get("event") or "").strip():
        return False, "when.event 必填（如 group_message）"
    conditions = when.get("conditions")
    if conditions is not None and not isinstance(conditions, dict):
        return False, "when.conditions 必须是条件对象"
    do = rule.get("do") or {}
    action = str(do.get("action") or "")
    if action not in _DO_ACTIONS:
        return False, f"do.action 必须是 {_DO_ACTIONS} 之一"
    if action == "reply_template":
        if not str(do.get("reply") or "").strip():
            return False, "reply_template 需要 reply 文本"
        if len(str(do["reply"])) > _MAX_DO_SCRIPT:
            return False, f"reply 过长（≤{_MAX_DO_SCRIPT} 字）"
    if action == "call_tool":
        if not str(do.get("name") or "").strip():
            return False, "call_tool 需要 name（平台工具名）"
    if action == "run_script":
        code = str(do.get("code") or "")
        if not code.strip():
            return False, "run_script 需要 code（Python 脚本）"
        if len(code) > _MAX_DO_SCRIPT:
            return False, f"code 过长（≤{_MAX_DO_SCRIPT} 字）"
    return True, ""


# ═══════════════════════════════════════════════════════════
# 存储读写（群助手 / 群 AI 通用）
# ═══════════════════════════════════════════════════════════

async def get_decision_rules(db, kind: str, entity_id: int) -> list[dict]:
    """读某实体的决策技能列表。kind: group_assistant | agent"""
    if kind == "group_assistant":
        from app.models.world import GroupAssistant
        ga = await db.get(GroupAssistant, entity_id)
        return list((ga.config or {}).get("decision_rules") or []) if ga else []
    if kind == "agent":
        from app.models.agent_skill import AgentSkill
        from sqlalchemy import select
        rows = (await db.execute(
            select(AgentSkill).where(
                AgentSkill.agent_id == entity_id,
                AgentSkill.skill_type == "decision",
            ).order_by(AgentSkill.id)
        )).scalars().all()
        return [dict(r.config or {}) for r in rows]
    return []


async def save_decision_rule(db, kind: str, entity_id: int, rule: dict) -> tuple[bool, str]:
    """新增/更新（同名覆盖）一个决策技能。"""
    ok, err = validate_rule(rule)
    if not ok:
        return False, err
    name = str(rule["name"]).strip()
    if kind == "group_assistant":
        from app.models.world import GroupAssistant
        ga = await db.get(GroupAssistant, entity_id)
        if ga is None:
            return False, "群助手不存在"
        rules = list((ga.config or {}).get("decision_rules") or [])
        rules = [r for r in rules if r.get("name") != name]
        if len(rules) >= _MAX_RULES:
            return False, f"决策技能已达上限（{_MAX_RULES} 条）"
        rules.append(rule)
        cfg = dict(ga.config or {})
        cfg["decision_rules"] = rules
        ga.config = cfg
        await db.commit()
        return True, ""
    if kind == "agent":
        from app.models.agent_skill import AgentSkill
        from sqlalchemy import select
        row = (await db.execute(
            select(AgentSkill).where(
                AgentSkill.agent_id == entity_id,
                AgentSkill.skill_type == "decision",
                AgentSkill.name == name,
            )
        )).scalar_one_or_none()
        if row is not None:
            row.config = rule
        else:
            count = (await db.execute(
                select(AgentSkill).where(
                    AgentSkill.agent_id == entity_id,
                    AgentSkill.skill_type == "decision",
                )
            )).scalars().all()
            if len(count) >= _MAX_RULES:
                return False, f"决策技能已达上限（{_MAX_RULES} 条）"
            db.add(AgentSkill(agent_id=entity_id, name=name, skill_type="decision", config=rule))
        await db.commit()
        return True, ""
    return False, f"未知实体类型 {kind}"


async def delete_decision_rule(db, kind: str, entity_id: int, name: str) -> bool:
    """删除一个决策技能。"""
    if kind == "group_assistant":
        from app.models.world import GroupAssistant
        ga = await db.get(GroupAssistant, entity_id)
        if ga is None:
            return False
        rules = [r for r in (ga.config or {}).get("decision_rules") or [] if r.get("name") != name]
        cfg = dict(ga.config or {})
        cfg["decision_rules"] = rules
        ga.config = cfg
        await db.commit()
        return True
    if kind == "agent":
        from app.models.agent_skill import AgentSkill
        from sqlalchemy import select
        row = (await db.execute(
            select(AgentSkill).where(
                AgentSkill.agent_id == entity_id,
                AgentSkill.skill_type == "decision",
                AgentSkill.name == name,
            )
        )).scalar_one_or_none()
        if row is not None:
            await db.delete(row)
            await db.commit()
        return True
    return False


# ═══════════════════════════════════════════════════════════
# 决策引擎：事件上下文 → 技能匹配
# ═══════════════════════════════════════════════════════════

async def run_decision_engine(
    db, kind: str, entity_id: int, world, event_type: str, ctx: dict,
) -> dict:
    """高层决策入口（触发链路调用）：读实体决策技能 → 匹配 → 执行 do。

    返回：
      {"hit": False}                         未命中 → 走正常触发流程
      {"hit": True, "handled": True, "reply": str?}  已程序化处理（notify=false），
                                           reply 非空时调用方应代发到群；**不唤醒 LLM**
      {"hit": True, "handled": False, "result": ...}  do 已执行但 notify=true，
                                           调用方**继续唤醒 LLM**（可把 result 注入上下文）
    """
    try:
        rules = await get_decision_rules(db, kind, entity_id)
        if not rules:
            return {"hit": False}
        rule = find_hit(rules, event_type, ctx)
        if rule is None:
            return {"hit": False}
        do = rule.get("do") or {}
        result = await execute_do(db, world, do, ctx)
        notify = bool(rule.get("notify"))
        if notify:
            return {"hit": True, "handled": False, "result": result}
        return {"hit": True, "handled": True, "reply": result.get("reply") or ""}
    except Exception as e:
        logger.warning(f"🎲 决策引擎异常（{kind} {entity_id}）: {e}")
        return {"hit": False}


def build_group_message_ctx(
    content: str, sender_id: int | None, sender_name: str,
    sender_type: str, group_id: int | None, is_mention: bool = False,
    is_at_all: bool = False, group_type: dict | None = None,
) -> dict:
    """group_message 情景的事件上下文（条件 DSL 字段来源）。"""
    return {
        "event": "group_message",
        "content": content or "",
        "sender_id": sender_id,
        "sender_name": sender_name or "",
        "sender_type": sender_type or "human",
        "group_id": group_id,
        "is_mention": bool(is_mention),
        "is_at_all": bool(is_at_all),
        "group_type": (group_type or {}).get("slug") if group_type else None,
        "group_type_name": (group_type or {}).get("name") if group_type else None,
    }


def find_hit(rules: list[dict], event_type: str, ctx: dict) -> dict | None:
    """按序匹配：返回第一个 when.event 相符且 conditions 命中的技能（无 then 返回 None）。"""
    for rule in rules:
        when = rule.get("when") or {}
        if str(when.get("event") or "") != event_type:
            continue
        conditions = when.get("conditions")
        if conditions is None or match_conditions(conditions, ctx):
            return rule
    return None


# ═══════════════════════════════════════════════════════════
# do 执行
# ═══════════════════════════════════════════════════════════

async def execute_do(db, world, do: dict, ctx: dict) -> dict:
    """执行决策技能的动作。返回 {success, reply?, result?, error?}。

    - reply_template：返回 reply 文本（调用方决定发送渠道）
    - call_tool：调平台工具（world_tools._do_execute，世界身份）
    - run_script：沙箱执行 Python（复用 skill_sandbox，世界配额）
    """
    action = str(do.get("action") or "")
    try:
        if action == "reply_template":
            return {"success": True, "reply": str(do.get("reply") or "").strip()}
        if action == "call_tool":
            from app.repositories.world_repo import SQLAlchemyWorldRepository
            from app.services.world.world_tools import _do_execute
            import json as _json
            name = str(do.get("name") or "")
            arguments = do.get("arguments") or {}
            result = await _do_execute(
                SQLAlchemyWorldRepository(db), world, name,
                _json.dumps(arguments, ensure_ascii=False) if isinstance(arguments, dict) else str(arguments),
            )
            return {"success": bool(result.get("success")), "result": result}
        if action == "run_script":
            from app.services.world.skill_sandbox import run_skill_in_sandbox
            code = str(do.get("code") or "")
            # 沙箱协议：world 目录内建临时脚本 → 执行 → 返回结果
            result = await run_skill_in_sandbox(db, world, {"name": "_decision_script", "code": code}, {"ctx": ctx})
            return {"success": bool(result.get("success", result.get("ok"))), "result": result}
    except Exception as e:
        logger.warning(f"🎲 决策技能 do 执行失败（{action}）: {e}")
        return {"success": False, "error": str(e)[:200]}
    return {"success": False, "error": f"未知动作 {action}"}


# ═══════════════════════════════════════════════════════════
# 平台工具（AI 自配置决策技能，注入群 AI / 群助手）
# ═══════════════════════════════════════════════════════════

DECISION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_decision_skills",
            "description": "查看你自己的决策技能列表（什么情景由程序自动处理、什么情景才触发你本体）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_decision_skill",
            "description": (
                "配置你自己的决策技能：声明「遇到什么情景我干什么、是否必须唤醒我本体」。"
                "结构：{name, when:{event, conditions}, do:{action, ...}, notify}。"
                "event 支持 group_message（群消息；字段：content/sender_id/sender_name/sender_type/group_id/is_mention/is_at_all/group_type）。"
                "conditions 为递归条件树：{\"and\":[...]}/{\"or\":[...]}/{\"not\":{...}} 自由组装；"
                "叶子 {\"字段\":值}=等于，{\"字段_contains\":\"子串\"}、{\"字段_starts_with\":\"前缀\"}、"
                "{\"字段_matches\":\"正则\"}、{\"字段_gt/gte/lt/lte\":数值}。"
                "do 三选一：reply_template（{action, reply}固定回复，零成本）/ "
                "call_tool（{action, name, arguments}调平台工具）/ run_script（{action, code}沙箱脚本）。"
                "notify=true = 命中后仍唤醒本体（关键时刻必须你来）；false = 程序处理完即止（省调用）。"
                "同名覆盖更新，上限 20 条。示例：签到自动回复 = "
                "{\"name\":\"签到\",\"when\":{\"event\":\"group_message\",\"conditions\":{\"and\":[{\"content_contains\":\"签到\"},{\"not\":{\"is_mention\":true}}]}},\"do\":{\"action\":\"reply_template\",\"reply\":\"已记录签到 ✅\"},\"notify\":false}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rule": {"type": "object", "description": "完整决策技能对象（见 description）"},
                },
                "required": ["rule"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_decision_skill",
            "description": "删除你自己的一个决策技能（按 name）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "要删除的技能名"},
                },
                "required": ["name"],
            },
        },
    },
]
