"""
思维 Skill 服务
提供 Skill 的 CRUD 操作，供工具 handler 和（未来的）REST API 调用
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def list_skills(db: AsyncSession, agent_id: int) -> list[dict]:
    """获取某个 AI 的所有技能（按 priority 升序）"""
    from app.models.agent_skill import AgentSkill

    result = await db.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .order_by(AgentSkill.priority.asc())
    )
    skills = result.scalars().all()
    return [_skill_to_dict(s) for s in skills]


async def add_skill(
    db: AsyncSession,
    agent_id: int,
    name: str,
    skill_type: str,
    config: dict | None = None,
    is_enabled: bool = True,
    priority: int = 0,
) -> dict:
    """添加一个技能"""
    from app.models.agent_skill import AgentSkill
    from app.utils.pure.skill_registry import SkillRegistry

    if not SkillRegistry.is_valid_type(skill_type):
        valid = "、".join(SkillRegistry.get_type_names())
        return {"error": True, "message": f"未知技能类型「{skill_type}」，可用类型：{valid}"}

    skill = AgentSkill(
        agent_id=agent_id,
        name=name,
        skill_type=skill_type,
        config=config or {},
        is_enabled=is_enabled,
        priority=priority,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)

    logger.info(f"🧠 AI agent_id={agent_id} 添加技能: {name} (type={skill_type})")
    return {"success": True, "skill": _skill_to_dict(skill)}


async def update_skill(
    db: AsyncSession,
    agent_id: int,
    skill_id: int,
    name: str | None = None,
    config: dict | None = None,
    is_enabled: bool | None = None,
    priority: int | None = None,
) -> dict:
    """更新一个技能（仅 owner AI 可修改）"""
    from app.models.agent_skill import AgentSkill

    result = await db.execute(
        select(AgentSkill).where(AgentSkill.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        return {"error": True, "message": "技能不存在"}
    if skill.agent_id != agent_id:
        return {"error": True, "message": "无权修改此技能（不是你自己的）"}

    if name is not None:
        skill.name = name
    if config is not None:
        skill.config = config
    if is_enabled is not None:
        skill.is_enabled = is_enabled
    if priority is not None:
        skill.priority = priority

    skill.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(skill)

    logger.info(f"🧠 AI agent_id={agent_id} 更新技能 #{skill_id}: {skill.name}")
    return {"success": True, "skill": _skill_to_dict(skill)}


async def delete_skill(db: AsyncSession, agent_id: int, skill_id: int) -> dict:
    """删除一个技能"""
    from app.models.agent_skill import AgentSkill

    result = await db.execute(
        select(AgentSkill).where(AgentSkill.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        return {"error": True, "message": "技能不存在"}
    if skill.agent_id != agent_id:
        return {"error": True, "message": "无权删除此技能"}

    skill_name = skill.name
    await db.delete(skill)
    await db.commit()

    logger.info(f"🧠 AI agent_id={agent_id} 删除技能 #{skill_id}: {skill_name}")
    return {"success": True, "message": f"技能「{skill_name}」已删除"}


async def toggle_skill(
    db: AsyncSession,
    agent_id: int,
    skill_id: int,
    is_enabled: bool | None = None,
) -> dict:
    """启用/禁用技能（不传 is_enabled 则翻转）"""
    from app.models.agent_skill import AgentSkill

    result = await db.execute(
        select(AgentSkill).where(AgentSkill.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        return {"error": True, "message": "技能不存在"}
    if skill.agent_id != agent_id:
        return {"error": True, "message": "无权操作此技能"}

    if is_enabled is None:
        skill.is_enabled = not skill.is_enabled
    else:
        skill.is_enabled = is_enabled

    skill.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()

    status = "启用" if skill.is_enabled else "禁用"
    logger.info(f"🧠 AI agent_id={agent_id} {status}技能 #{skill_id}: {skill.name}")
    return {"success": True, "skill": _skill_to_dict(skill), "message": f"技能「{skill.name}」已{status}"}


def _skill_to_dict(skill) -> dict:
    """ORM → dict"""
    return {
        "id": skill.id,
        "agent_id": skill.agent_id,
        "name": skill.name,
        "skill_type": skill.skill_type,
        "is_enabled": skill.is_enabled,
        "config": skill.config or {},
        "priority": skill.priority,
        "created_at": str(skill.created_at) if skill.created_at else None,
        "updated_at": str(skill.updated_at) if skill.updated_at else None,
    }
