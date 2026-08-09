"""
群类型系统服务 — 世界按类型分发群 + 群助手管理

设计（珑哥 2026-08-09 定稿）：
- 世界预设群类型（规则/绑定上限/助手模板），规则挂在类型上，不直接操作群聊
- 群绑定世界时选择类型（校验上限），按模板自动创建群助手（每群可多个，数量由世界决定）
- 群助手 = agent 实体，归属群（不属于用户 id、不占额度），出现在群聊成员中
- 群主可给助手填 API（自定义 key / 一键应用自己的全局 API，加密存储）；
  世界程序只能调用不能读 key（隐私），世界打包不含 key（打包性）
- 驱动：群里 @ / 私信（复用 agent 聊天机制）；世界程序主动调度暂不做
"""
from __future__ import annotations

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.world import World, WorldGroupType, WorldAgent

logger = logging.getLogger(__name__)

DEFAULT_ASSISTANT_SPEC = {"count": 1, "need_api": True, "default_name": "群助手"}


# ═══════════════════════════════════════════════════════════════
# 群类型 CRUD（世界作者）
# ═══════════════════════════════════════════════════════════════

async def _require_world_owner(db: AsyncSession, world_id: int, owner_id: int) -> World:
    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")
    if world.owner_id != owner_id:
        raise ValueError("仅世界创建者可操作")
    return world


async def create_group_type(
    db: AsyncSession, world_id: int, owner_id: int,
    name: str, description: str = "", rules: str = "",
    bind_limit: int = 3, assistant_spec: dict | None = None,
) -> WorldGroupType:
    """世界作者创建群类型。"""
    await _require_world_owner(db, world_id, owner_id)
    spec = {**DEFAULT_ASSISTANT_SPEC, **(assistant_spec or {})}
    gt = WorldGroupType(
        world_id=world_id, name=name.strip()[:50],
        description=description.strip(), rules=rules.strip(),
        bind_limit=max(1, int(bind_limit)), assistant_spec=spec,
    )
    db.add(gt)
    await db.commit()
    await db.refresh(gt)
    logger.info(f"🌐 世界 #{world_id} 创建群类型「{gt.name}」(上限 {gt.bind_limit})")
    return gt


async def list_group_types(db: AsyncSession, world_id: int) -> list[WorldGroupType]:
    rows = (await db.execute(
        select(WorldGroupType).where(WorldGroupType.world_id == world_id).order_by(WorldGroupType.id)
    )).scalars().all()
    return list(rows)


async def update_group_type(
    db: AsyncSession, world_id: int, owner_id: int, type_id: int,
    name: str | None = None, description: str | None = None, rules: str | None = None,
    bind_limit: int | None = None, assistant_spec: dict | None = None,
) -> WorldGroupType:
    await _require_world_owner(db, world_id, owner_id)
    gt = await db.get(WorldGroupType, type_id)
    if gt is None or gt.world_id != world_id:
        raise ValueError("群类型不存在")
    if name is not None:
        gt.name = name.strip()[:50]
    if description is not None:
        gt.description = description.strip()
    if rules is not None:
        gt.rules = rules.strip()
    if bind_limit is not None:
        gt.bind_limit = max(1, int(bind_limit))
    if assistant_spec is not None:
        gt.assistant_spec = {**DEFAULT_ASSISTANT_SPEC, **assistant_spec}
    await db.commit()
    await db.refresh(gt)
    return gt


async def delete_group_type(db: AsyncSession, world_id: int, owner_id: int, type_id: int) -> None:
    """删除类型。已绑定该类型的群自动解绑类型（保留世界绑定）。"""
    from app.models.world import WorldBinding
    await _require_world_owner(db, world_id, owner_id)
    gt = await db.get(WorldGroupType, type_id)
    if gt is None or gt.world_id != world_id:
        raise ValueError("群类型不存在")
    await db.execute(
        WorldBinding.__table__.update().where(WorldBinding.group_type_id == type_id).values(group_type_id=None)
    )
    await db.delete(gt)
    await db.commit()


# ═══════════════════════════════════════════════════════════════
# 绑定群到类型 + 自动创建群助手
# ═══════════════════════════════════════════════════════════════

async def bind_group_with_type(
    db: AsyncSession, world_id: int, owner_id: int, group_id: int, type_id: int,
) -> dict:
    """把群绑定到某群类型：校验上限 → 更新绑定 → 按模板自动创建群助手。"""
    from app.models.world import WorldBinding
    world = await _require_world_owner(db, world_id, owner_id)
    gt = await db.get(WorldGroupType, type_id)
    if gt is None or gt.world_id != world_id:
        raise ValueError("群类型不存在")

    # 上限校验：该类型已绑定群数
    bound = (await db.execute(
        select(func.count()).select_from(WorldBinding).where(
            WorldBinding.world_id == world_id,
            WorldBinding.entity_type == "group",
            WorldBinding.group_type_id == type_id,
        )
    )).scalar() or 0
    binding = (await db.execute(
        select(WorldBinding).where(
            WorldBinding.world_id == world_id,
            WorldBinding.entity_type == "group",
            WorldBinding.entity_id == group_id,
        )
    )).scalar_one_or_none()
    if binding is None:
        # 群未绑定世界 → 先绑定（群主已校验，此处直接建）
        binding = WorldBinding(world_id=world_id, entity_type="group", entity_id=group_id)
        db.add(binding)
    elif binding.group_type_id == type_id:
        return {"success": True, "assistants": [], "already": True}
    if bound >= gt.bind_limit:
        raise ValueError(f"群类型「{gt.name}」已达绑定上限（{gt.bind_limit}），无法再绑定")
    binding.group_type_id = type_id
    await db.flush()

    # 按模板自动创建群助手（幂等：该群已有该类型助手则不重复建）
    spec = {**DEFAULT_ASSISTANT_SPEC, **(gt.assistant_spec or {})}
    count = max(1, int(spec.get("count") or 1))
    existing = (await db.execute(
        select(WorldAgent).where(
            WorldAgent.world_id == world_id,
            WorldAgent.group_id == group_id,
            WorldAgent.group_type_id == type_id,
        )
    )).scalars().all()
    created = []
    for i in range(len(existing), count):
        agent_id = await _create_group_assistant(
            db, world, group_id, type_id, spec, i,
        )
        if agent_id:
            created.append(agent_id)
    await db.commit()
    logger.info(f"🔗 世界 #{world_id} 群 {group_id} 绑定类型「{gt.name}」，创建 {len(created)} 个群助手")
    return {"success": True, "assistants": created}


async def _create_group_assistant(
    db: AsyncSession, world: World, group_id: int, type_id: int,
    spec: dict, index: int,
) -> int | None:
    """创建单个群助手：agent + 入群 + 世界登记。"""
    try:
        from app.services.agent.agent_service import create_agent
        from app.chat.message import add_member

        # 群主（owner）作为 agent 的 owner（创建者身份；助手归属群不占个人额度）
        from sqlalchemy import text as _t
        owner_row = (await db.execute(_t(
            "SELECT member_id FROM group_members WHERE group_id=:g AND member_type='human' AND role='owner' LIMIT 1"
        ), {"g": group_id})).first()
        owner_id = int(owner_row[0]) if owner_row else world.owner_id

        base_name = str(spec.get("default_name") or "群助手").strip()[:30]
        name = f"{base_name}{index + 1}" if count_gt_1(spec) else base_name
        agent = await create_agent(
            db, owner_id=owner_id, name=name,
            system_prompt=f"你是群「{group_id}」的助手，由世界「{world.name}」统一调度管理。\n\n世界规则：\n{spec.get('rules_hint') or ''}",
            hide_ai_identity=False, is_ai_editable=False,
        )
        await add_member(db, group_id, "ai", agent.id, role="member")
        db.add(WorldAgent(world_id=world.id, agent_id=agent.id, role="assistant",
                          group_id=group_id, group_type_id=type_id,
                          config={"name": name, "spec": spec}))
        await db.flush()
        logger.info(f"🤖 群 {group_id} 创建群助手「{name}」(agent {agent.id})")
        return agent.id
    except Exception as e:
        logger.warning(f"创建群助手失败（group {group_id}）: {e}")
        return None


def count_gt_1(spec: dict) -> bool:
    return int(spec.get("count") or 1) > 1


# ═══════════════════════════════════════════════════════════════
# 群助手 API 配置（群主）
# ═══════════════════════════════════════════════════════════════

async def _get_assistant(db: AsyncSession, world_id: int, agent_id: int) -> WorldAgent:
    wa = (await db.execute(
        select(WorldAgent).where(WorldAgent.world_id == world_id, WorldAgent.agent_id == agent_id)
    )).scalar_one_or_none()
    if wa is None:
        raise ValueError("群助手不存在")
    return wa


async def set_assistant_api(
    db: AsyncSession, world_id: int, operator_id: int, agent_id: int,
    api_key: str | None = None, api_base_url: str | None = None,
) -> dict:
    """群主为群助手设置 API（自定义 key）。加密存储，世界只能调用不能读。"""
    wa = await _get_assistant(db, world_id, agent_id)
    from sqlalchemy import text as _t
    owner_row = (await db.execute(_t(
        "SELECT member_id FROM group_members WHERE group_id=:g AND member_type='human' AND role='owner' LIMIT 1"
    ), {"g": wa.group_id})).first()
    group_owner = int(owner_row[0]) if owner_row else 0
    if operator_id != group_owner:
        raise ValueError("仅群主可配置群助手 API")

    from app.utils.crypto import encrypt_api_key
    from sqlalchemy import text as _u
    if api_key:
        await db.execute(_u("UPDATE agents SET api_key_encrypted=:k, api_base_url=:b WHERE id=:aid"),
                         {"k": encrypt_api_key(api_key), "b": api_base_url, "aid": agent_id})
    else:
        # 只改 base
        await db.execute(_u("UPDATE agents SET api_base_url=:b WHERE id=:aid"),
                         {"b": api_base_url, "aid": agent_id})
    await db.commit()
    return {"success": True, "agent_id": agent_id, "configured": bool(api_key)}


async def apply_global_api(db: AsyncSession, world_id: int, operator_id: int, agent_id: int) -> dict:
    """一键应用群主的默认全局 API（user 的 api_key_encrypted + api_base_url）。"""
    wa = await _get_assistant(db, world_id, agent_id)
    from sqlalchemy import text as _t
    owner_row = (await db.execute(_t(
        "SELECT member_id FROM group_members WHERE group_id=:g AND member_type='human' AND role='owner' LIMIT 1"
    ), {"g": wa.group_id})).first()
    group_owner = int(owner_row[0]) if owner_row else 0
    if operator_id != group_owner:
        raise ValueError("仅群主可配置群助手 API")

    from app.models.user import User
    from app.utils.crypto import encrypt_api_key
    user = await db.get(User, group_owner)
    if not user or not user.api_key_encrypted:
        raise ValueError("你还没有配置全局 API（在「我的」页设置）")
    from sqlalchemy import text as _u
    await db.execute(_u("UPDATE agents SET api_key_encrypted=:k, api_base_url=:b WHERE id=:aid"),
                     {"k": user.api_key_encrypted, "b": user.api_base_url, "aid": agent_id})
    await db.commit()
    return {"success": True, "agent_id": agent_id, "configured": True, "source": "global"}


async def clear_assistant_api(db: AsyncSession, world_id: int, operator_id: int, agent_id: int) -> dict:
    """清除群助手 API（回落系统默认）。"""
    wa = await _get_assistant(db, world_id, agent_id)
    from sqlalchemy import text as _t
    owner_row = (await db.execute(_t(
        "SELECT member_id FROM group_members WHERE group_id=:g AND member_type='human' AND role='owner' LIMIT 1"
    ), {"g": wa.group_id})).first()
    group_owner = int(owner_row[0]) if owner_row else 0
    if operator_id != group_owner:
        raise ValueError("仅群主可配置群助手 API")
    from sqlalchemy import text as _u
    await db.execute(_u("UPDATE agents SET api_key_encrypted=NULL, api_base_url=NULL WHERE id=:aid"),
                     {"aid": agent_id})
    await db.commit()
    return {"success": True, "agent_id": agent_id, "configured": False}


async def assistant_api_status(db: AsyncSession, world_id: int, agent_id: int) -> dict:
    """群助手 API 状态（不回显 key）：configured / source / has_global。"""
    wa = await _get_assistant(db, world_id, agent_id)
    from app.models.agent import Agent
    agent = await db.get(Agent, agent_id)
    from app.models.user import User
    from sqlalchemy import text as _t
    owner_row = (await db.execute(_t(
        "SELECT member_id FROM group_members WHERE group_id=:g AND member_type='human' AND role='owner' LIMIT 1"
    ), {"g": wa.group_id})).first()
    group_owner = int(owner_row[0]) if owner_row else 0
    user = await db.get(User, group_owner) if group_owner else None
    return {
        "success": True,
        "agent_id": agent_id,
        "configured": bool(agent and agent.api_key_encrypted),
        "has_global": bool(user and user.api_key_encrypted),
        "name": agent.name if agent else None,
    }
