""""
思维 Skill 引擎
在 AI 回复 pipeline 中评估触发条件，收集延迟/打字/注入信号。

设计：注册式分发 — 每种 skill_type 对应一个处理器函数，
通过 _ACTION_HANDLERS / _INJECT_HANDLERS 字典调度，
新增技能类型只需注册处理器，无需改 if/elif。
"""
import re
import logging
from typing import Any, Callable
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class SkillEvaluationResult:
    """一次 skill 评估的结果"""
    delay_seconds: float = 0.0
    show_typing: bool = False
    typing_config: dict | None = None
    inject_prompts: list[str] = field(default_factory=list)
    matched_skills: list[dict] = field(default_factory=list)


# ── 注册式分发：action 类（影响回复行为） ──

_ACTION_HANDLERS: dict[str, Callable] = {}


def register_action_handler(skill_type: str):
    """装饰器：注册 action 类技能处理器"""
    def wrapper(func: Callable):
        _ACTION_HANDLERS[skill_type] = func
        logger.debug(f"Action 技能处理器已注册: {skill_type} -> {func.__name__}")
        return func
    return wrapper


async def _handle_delay_reply(
    db: AsyncSession, agent, skill, config: dict,
    result: SkillEvaluationResult, context: dict | None,
    delay_allowed: bool,
) -> None:
    """处理 delay_reply 技能"""
    if not delay_allowed:
        logger.info(f"⏱️ AI agent_id={agent.id} 延迟回复已关闭，跳过 skill #{skill.id}")
        return
    delay = config.get("delay_seconds", 0)
    max_delay = config.get("max_delay_seconds", 30)
    if delay > 0:
        result.delay_seconds = min(max(result.delay_seconds, delay), max_delay)
        result.matched_skills.append({
            "id": skill.id, "name": skill.name,
            "skill_type": skill.skill_type, "action": f"延迟 {delay}s",
        })


async def _handle_typing_indicator(
    db: AsyncSession, agent, skill, config: dict,
    result: SkillEvaluationResult, context: dict | None,
    delay_allowed: bool,
) -> None:
    """处理 typing_indicator 技能"""
    if not delay_allowed:
        logger.info(f"⏱️ AI agent_id={agent.id} 延迟回复已关闭，跳过 typing_indicator skill #{skill.id}")
        return
    result.show_typing = True
    result.typing_config = config
    result.matched_skills.append({
        "id": skill.id, "name": skill.name,
        "skill_type": skill.skill_type, "action": "显示打字指示器",
    })


# ── 注册式分发：inject 类（注入提示词） ──

_INJECT_HANDLERS: dict[str, Callable] = {}


def register_inject_handler(skill_type: str):
    """装饰器：注册 inject 类技能处理器"""
    def wrapper(func: Callable):
        _INJECT_HANDLERS[skill_type] = func
        logger.debug(f"Inject 技能处理器已注册: {skill_type} -> {func.__name__}")
        return func
    return wrapper


async def _handle_inject_prompt(
    db: AsyncSession, agent, skill, config: dict,
    prompts: list[str], now: datetime,
) -> None:
    """处理 inject_prompt 技能"""
    insert_text = config.get("insert_text", "")
    if not insert_text:
        return

    # 检查过期
    duration = config.get("duration_seconds")
    one_shot = config.get("one_shot", False)
    updated_at = skill.updated_at

    if duration and updated_at:
        expires_at = updated_at.replace(tzinfo=None) + timedelta(seconds=duration)
        if now > expires_at:
            skill.is_enabled = False
            await db.commit()
            logger.info(f"🧠 技能 #{skill.id}「{skill.name}」已过期，自动禁用")
            return

    if one_shot and updated_at:
        skill.is_enabled = False
        await db.commit()
        logger.info(f"🧠 一次性技能 #{skill.id}「{skill.name}」已消耗，自动禁用")

    prompts.append(insert_text)


async def _handle_scene_trigger(
    db: AsyncSession, agent, skill, config: dict,
    prompts: list[str], now: datetime,
) -> None:
    """处理 scene_trigger 技能"""
    inject_text = config.get("inject_text", "")
    if inject_text:
        prompts.append(inject_text)


async def _load_enabled_skills(db: AsyncSession, agent_id: int) -> list:
    """加载某个 agent 的所有启用技能（按 priority 升序）"""
    from app.models.agent_skill import AgentSkill

    result = await db.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id, AgentSkill.is_enabled == True)
        .order_by(AgentSkill.priority.asc())
    )
    return result.scalars().all()


def _match_trigger(skill, context: dict | None) -> bool:
    """
    检查技能是否匹配触发条件。

    规则：
    - 无 trigger 配置 → 始终触发（always-on 技能，如 inject_prompt）
    - 有 trigger.match_type == "keyword" → 检查 keywords 是否在消息内容中出现
    - 有 trigger.match_type == "regex" → 检查正则是否匹配
    - 有 trigger → 但 context 为 None → 不匹配
    """
    config = skill.config or {}
    trigger = config.get("trigger")
    if not trigger:
        return True  # 无触发条件 = 始终激活

    if not context:
        return False

    content = context.get("content", "") or ""
    match_type = trigger.get("match_type", "keyword")

    if match_type == "keyword":
        keywords = trigger.get("keywords", [])
        if not keywords:
            return True
        content_lower = content.lower()
        return any(kw.lower() in content_lower for kw in keywords)

    elif match_type == "regex":
        pattern = trigger.get("pattern_regex")
        if not pattern:
            return True
        try:
            return bool(re.search(pattern, content))
        except re.error:
            logger.warning(f"技能 #{skill.id} 正则错误: {pattern}")
            return False

    return True


async def _is_delay_reply_allowed(db: AsyncSession, agent) -> bool:
    """
    检查 agent 级别是否允许延迟回复。
    agent.delay_reply_enabled: True=允许, False=禁止, NULL=继承全局默认。
    """
    if agent.delay_reply_enabled is not None:
        return agent.delay_reply_enabled

    # NULL → 查全局默认
    try:
        from app.models.conversation_log import ConversationLogConfig
        result = await db.execute(select(ConversationLogConfig).limit(1))
        cfg = result.scalar_one_or_none()
        return cfg.default_delay_reply_enabled if cfg else False
    except Exception:
        return False


async def evaluate_action_skills(
    db: AsyncSession,
    agent,
    group_id: int,
    context: dict | None = None,
) -> SkillEvaluationResult:
    """
    评估 action 类技能（延迟回复、打字指示器）。

    在 ai_response_worker 中调用（build_messages 之前），
    用于控制回复时序和 WebSocket 事件。
    """
    from app.models.agent_skill import AgentSkill

    result = SkillEvaluationResult()

    try:
        skills = await _load_enabled_skills(db, agent.id)
    except Exception as e:
        logger.warning(f"加载技能失败: {e}")
        return result

    # 检查 agent 级别的延迟回复开关
    delay_allowed = await _is_delay_reply_allowed(db, agent)

    for skill in skills:
        if not _match_trigger(skill, context):
            continue

        config = skill.config or {}

        # 用 SkillRegistry 判断是否为 action 类技能
        from app.utils.pure.skill_registry import SkillRegistry
        type_info = SkillRegistry.get_info(skill.skill_type)
        if not type_info or type_info.category != "action":
            continue

        # 注册式分发：从 _ACTION_HANDLERS 查找处理器
        handler = _ACTION_HANDLERS.get(skill.skill_type)
        if handler and skill.is_enabled:
            await handler(db, agent, skill, config, result, context, delay_allowed)

    if result.matched_skills:
        logger.info(
            f"🧠 AI agent_id={agent.id} 技能触发: "
            f"delay={result.delay_seconds}s typing={result.show_typing}"
        )

    return result


async def evaluate_inject_skills(
    db: AsyncSession,
    agent,
    group_id: int,
    context: dict | None = None,
) -> list[str]:
    """
    评估 inject 类技能（inject_prompt、scene_trigger 的 inject_text）。

    在 _build_injected_skills 中调用，返回注入到系统提示词中的文本列表。
    """
    prompts: list[str] = []

    try:
        skills = await _load_enabled_skills(db, agent.id)
    except Exception as e:
        logger.warning(f"加载注入技能失败: {e}")
        return prompts

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for skill in skills:
        if not _match_trigger(skill, context):
            continue

        config = skill.config or {}

        # 用 SkillRegistry 判断是否为 inject 类技能
        from app.utils.pure.skill_registry import SkillRegistry
        type_info = SkillRegistry.get_info(skill.skill_type)
        if not type_info or type_info.category != "inject":
            continue

        # 注册式分发：从 _INJECT_HANDLERS 查找处理器
        handler = _INJECT_HANDLERS.get(skill.skill_type)
        if handler and skill.is_enabled:
            await handler(db, agent, skill, config, prompts, now)

    if prompts:
        logger.info(f"🧠 AI agent_id={agent.id} 注入 {len(prompts)} 条技能提示")

    return prompts


# --- auto-register built-in skill handlers ---

register_action_handler("delay_reply")(_handle_delay_reply)
register_action_handler("typing_indicator")(_handle_typing_indicator)
register_inject_handler("inject_prompt")(_handle_inject_prompt)
register_inject_handler("scene_trigger")(_handle_scene_trigger)
