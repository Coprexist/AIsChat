"""
群类型系统服务 — 配置在文件（随世界打包），状态在 DB

设计（珑哥 2026-08-09 定稿）：
- 类型定义（规则/绑定上限/助手模板）存世界文件夹 `group_types.json`，
  随世界打包分发（发布商城/导入自动带上）；世界作者可在设置 UI 或
  通过群视界机器人对话修改（像改世界名/简介一样）
- 类型用字符串 slug 作稳定 id（打包分发后不变），DB 只存绑定状态
  （world_bindings.group_type_slug / world_agents.group_type_slug）
- 群绑定类型时按模板自动创建群助手（每群可多个，数量由世界决定）；
  助手归属群（不属于用户 id、不占额度），出现在群聊成员中
- 群主可给助手填 API（自定义 key / 一键应用自己的全局 API，加密存储）；
  世界程序只能调用不能读 key（隐私），世界打包不含 key（打包性）
- 驱动：群里 @ / 私信；世界程序主动调度暂不做
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.world import World, WorldAgent, WorldBinding

logger = logging.getLogger(__name__)

GROUP_TYPES_FILE = "group_types.json"          # 世界文件夹内（相对世界根目录）
DEFAULT_ASSISTANT_SPEC = {"count": 1, "need_api": True, "default_name": "群助手"}

# 默认群类型：世界还没配置 group_types.json 时兜底（开箱即用，群/AI 都可绑定；用户自定义后覆盖）
# slug=稳定 id（绑定存 slug，改名只改 name 不影响存量绑定）
# bind_limit=-1 = 无限（珑哥 2026-08-12 定：默认类型群聊和 AI 数目都是无限）
DEFAULT_GROUP_TYPES = [
    {"slug": "default", "name": "默认类型", "description": "未配置群类型时的兜底类型",
     "rules": "", "bind_limit": -1, "assistant_spec": {"count": 1, "need_api": False, "default_name": "群助手"}},
]


# ═══════════════════════════════════════════════════════════════
# 文件读写（定义层）
# ═══════════════════════════════════════════════════════════════

def _types_path(world_id: int) -> Path:
    # 支持环境变量覆盖根目录（可测试性；生产默认 data/worlds）
    root = Path(os.environ.get("WORLD_TYPES_ROOT", "data/worlds"))
    return root / str(world_id) / GROUP_TYPES_FILE


def load_group_types(world_id: int) -> list[dict]:
    """读世界文件夹的 group_types.json（定义层）。缺失/损坏/为空 → 返回内置默认类型（开箱即用）。"""
    import copy
    try:
        data = json.loads(_types_path(world_id).read_text(encoding="utf-8"))
        types = data.get("types", []) if isinstance(data, dict) else []
        types = [t for t in types if isinstance(t, dict) and t.get("slug")]
        if types:
            return types
    except (OSError, json.JSONDecodeError):
        pass
    return copy.deepcopy(DEFAULT_GROUP_TYPES)


def save_group_types(world_id: int, types: list[dict]) -> None:
    """写 group_types.json（原子写）。"""
    path = _types_path(world_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"types": types}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _normalize_type(t: dict) -> dict:
    """清洗单个类型定义：slug 从 name 生成（稳定 id），字段齐全。

    bind_limit：-1 = 无限（珑哥 2026-08-12 定：不是极大值，用 -1 表达无限）；
    0/负数（除 -1）→ 归 1（至少允许一个）；正整数 = 上限。
    """
    name = str(t.get("name") or "").strip()[:50]
    slug = str(t.get("slug") or _slugify(name)).strip()[:50]
    spec = {**DEFAULT_ASSISTANT_SPEC, **(t.get("assistant_spec") or {})}
    raw_limit = t.get("bind_limit")
    try:
        limit = int(raw_limit) if raw_limit is not None else 3
    except (TypeError, ValueError):
        limit = 3
    if limit == -1:
        limit = -1  # 无限
    elif limit < 1:
        limit = 1
    return {
        "slug": slug,
        "name": name,
        "description": str(t.get("description") or ""),
        "rules": str(t.get("rules") or ""),
        "bind_limit": limit,
        "assistant_spec": {
            "count": max(1, int(spec.get("count") or 1)),
            "need_api": bool(spec.get("need_api", True)),
            "default_name": str(spec.get("default_name") or "群助手")[:30],
        },
    }


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", name.lower()).strip("-")
    return slug or "type"


# ═══════════════════════════════════════════════════════════════
# 类型 CRUD（读文件 + 写文件；世界作者/群视界机器人）
# ═══════════════════════════════════════════════════════════════

async def _require_world_owner(db: AsyncSession, world_id: int, owner_id: int) -> World:
    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")
    if world.owner_id != owner_id:
        raise ValueError("仅世界创建者可操作")
    return world


async def list_group_types(db: AsyncSession, world_id: int, entity_type: str = "group") -> list[dict]:
    """类型定义 + 每类型已绑定数（bound_count 按 entity_type 区分：group=群 / agent=AI）。"""
    types = load_group_types(world_id)
    result = []
    for t in types:
        bound = (await db.execute(
            select(func.count()).select_from(WorldBinding).where(
                WorldBinding.world_id == world_id,
                WorldBinding.entity_type == entity_type,
                WorldBinding.group_type_slug == t["slug"],
            )
        )).scalar() or 0
        result.append({**t, "bound_count": bound})
    return result


async def save_group_types_config(
    db: AsyncSession, world_id: int, owner_id: int, types: list[dict],
) -> list[dict]:
    """世界作者（或群视界机器人）整体保存类型定义（全量替换，slug 幂等）。"""
    await _require_world_owner(db, world_id, owner_id)
    normalized = [_normalize_type(t) for t in types if t.get("name")]
    # slug 去重（保留后者）
    seen: dict[str, dict] = {}
    for t in normalized:
        seen[t["slug"]] = t
    save_group_types(world_id, list(seen.values()))
    logger.info(f"🌐 世界 #{world_id} 保存 {len(seen)} 个群类型定义")
    return list(seen.values())


# ═══════════════════════════════════════════════════════════════
# 绑定群到类型 + 自动创建群助手
# ═══════════════════════════════════════════════════════════════

async def bind_entry_with_type(
    db: AsyncSession, world_id: int, owner_id: int, entity_type: str, entity_id: int, type_slug: str,
) -> dict:
    """把入口（群聊 group / AI agent）绑定到某类型（slug）：校验定义/上限 → 更新绑定。

    - group：按模板自动创建群助手（幂等）
    - agent：AI 直接绑定世界（个人专属能力），只绑定 + 类型标记，不建助手
    - ⚠️ AI 一律按 user_id 存（2026-08-12 珑哥定：全平台 AI 对外标识统一 user_id，
      杜绝 agent.id 与另一 agent 的 user_id 撞车）——传入 agent.id 自动转 user_id
    """
    from app.models.agent import Agent as AgentModel
    if entity_type == "agent":
        agent_row = (await db.execute(
            select(AgentModel).where(AgentModel.user_id == entity_id)
        )).scalar_one_or_none()
        if agent_row is None:
            agent_row = await db.get(AgentModel, entity_id)
        if agent_row is None or not agent_row.user_id:
            raise ValueError(f"AI 不存在（{entity_id}）")
        entity_id = agent_row.user_id
    if entity_type not in ("group", "agent"):
        raise ValueError(f"仅支持绑定 group/agent，收到 {entity_type}")
    await _require_world_owner(db, world_id, owner_id)
    type_def = next((t for t in load_group_types(world_id) if t["slug"] == type_slug), None)
    if type_def is None:
        raise ValueError(f"群类型不存在（{type_slug}）")

    bound = (await db.execute(
        select(func.count()).select_from(WorldBinding).where(
            WorldBinding.world_id == world_id,
            WorldBinding.entity_type == entity_type,
            WorldBinding.group_type_slug == type_slug,
        )
    )).scalar() or 0
    binding = (await db.execute(
        select(WorldBinding).where(
            WorldBinding.world_id == world_id,
            WorldBinding.entity_type == entity_type,
            WorldBinding.entity_id == entity_id,
        )
    )).scalar_one_or_none()
    if binding is None:
        binding = WorldBinding(world_id=world_id, entity_type=entity_type, entity_id=entity_id)
        db.add(binding)
    elif binding.group_type_slug == type_slug:
        return {"success": True, "assistants": [], "already": True}
    limit = int(type_def["bind_limit"])
    if limit != -1 and bound >= limit:
        raise ValueError(f"群类型「{type_def['name']}」已达绑定上限（{limit}）")
    binding.group_type_slug = type_slug
    await db.flush()

    created = []
    if entity_type == "group":
        # 按模板自动创建群助手（幂等：该群该类型已有助手则不重复建）
        spec = type_def["assistant_spec"]
        count = int(spec["count"])
        existing = (await db.execute(
            select(WorldAgent).where(
                WorldAgent.world_id == world_id,
                WorldAgent.group_id == entity_id,
                WorldAgent.group_type_slug == type_slug,
            )
        )).scalars().all()
        world = await db.get(World, world_id)
        for i in range(len(existing), count):
            agent_id = await _create_group_assistant(db, world, entity_id, type_slug, spec, i)
            if agent_id:
                created.append(agent_id)
    await db.commit()
    logger.info(f"🔗 世界 #{world_id} {entity_type} {entity_id} 绑定类型「{type_def['name']}」，创建 {len(created)} 个群助手")
    return {"success": True, "assistants": created}


async def bind_entries_with_type(
    db: AsyncSession, world_id: int, owner_id: int, entity_type: str, entity_ids: list[int], type_slug: str,
) -> dict:
    """批量把多个入口（群/AI）绑定到同一类型（逐个复用 bind_entry_with_type，互不影响；返回逐条结果）"""
    results = []
    for eid in entity_ids:
        try:
            r = await bind_entry_with_type(db, world_id, owner_id, entity_type, eid, type_slug)
            results.append({"entity_id": eid, "success": True, "assistants": r.get("assistants", []), "already": r.get("already", False)})
        except ValueError as e:
            results.append({"entity_id": eid, "success": False, "error": str(e)})
    ok = sum(1 for r in results if r["success"])
    return {"success": True, "bound": ok, "failed": len(results) - ok, "results": results}


async def _create_group_assistant(
    db: AsyncSession, world: World, group_id: int, type_slug: str,
    spec: dict, index: int,
) -> int | None:
    """创建单个群助手：agent + 入群 + 世界登记（嵌套事务，失败不影响外层）。"""
    try:
        async with db.begin_nested():
            from app.services.agent.agent_service import create_agent
            from app.chat.message import add_member
            from sqlalchemy import text as _t

            owner_row = (await db.execute(_t(
                "SELECT member_id FROM group_members WHERE group_id=:g AND member_type='human' AND role='owner' LIMIT 1"
            ), {"g": group_id})).first()
            owner_id = int(owner_row[0]) if owner_row else world.owner_id

            base_name = str(spec.get("default_name") or "群助手").strip()[:30]
            name = f"{base_name}{index + 1}" if int(spec.get("count") or 1) > 1 else base_name
            agent = await create_agent(
                db, owner_id=owner_id, name=name,
                system_prompt=f"你是群「{group_id}」的助手，由世界「{world.name}」统一调度管理。\n\n类型：{type_slug}",
                hide_ai_identity=False, is_ai_editable=False,
            )
            await add_member(db, group_id, "ai", agent.id, role="member")
            db.add(WorldAgent(world_id=world.id, agent_id=agent.id, role="assistant",
                              group_id=group_id, group_type_slug=type_slug,
                              config={"name": name}))
            await db.flush()
            logger.info(f"🤖 群 {group_id} 创建群助手「{name}」(agent {agent.id})")
            return agent.id
    except Exception as e:
        logger.warning(f"创建群助手失败（group {group_id}）: {e}")
        return None


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


async def _require_group_owner(db: AsyncSession, world_id: int, operator_id: int, agent_id: int) -> WorldAgent:
    wa = await _get_assistant(db, world_id, agent_id)
    from sqlalchemy import text as _t
    owner_row = (await db.execute(_t(
        "SELECT member_id FROM group_members WHERE group_id=:g AND member_type='human' AND role='owner' LIMIT 1"
    ), {"g": wa.group_id})).first()
    group_owner = int(owner_row[0]) if owner_row else 0
    if operator_id != group_owner:
        raise ValueError("仅群主可配置群助手 API")
    return wa


async def set_assistant_api(
    db: AsyncSession, world_id: int, operator_id: int, agent_id: int,
    api_key: str | None = None, api_base_url: str | None = None,
) -> dict:
    """群主为群助手设置 API（自定义 key，加密存储）。"""
    await _require_group_owner(db, world_id, operator_id, agent_id)
    from app.utils.crypto import encrypt_api_key
    from sqlalchemy import text as _u
    if api_key:
        await db.execute(_u("UPDATE agents SET api_key_encrypted=:k, api_base_url=:b WHERE id=:aid"),
                         {"k": encrypt_api_key(api_key), "b": api_base_url, "aid": agent_id})
    elif api_base_url:
        await db.execute(_u("UPDATE agents SET api_base_url=:b WHERE id=:aid"),
                         {"b": api_base_url, "aid": agent_id})
    await db.commit()
    return {"success": True, "agent_id": agent_id, "configured": bool(api_key)}


async def apply_global_api(db: AsyncSession, world_id: int, operator_id: int, agent_id: int) -> dict:
    """一键应用群主的默认全局 API。"""
    wa = await _require_group_owner(db, world_id, operator_id, agent_id)
    from sqlalchemy import text as _t
    owner_row = (await db.execute(_t(
        "SELECT member_id FROM group_members WHERE group_id=:g AND member_type='human' AND role='owner' LIMIT 1"
    ), {"g": wa.group_id})).first()
    group_owner = int(owner_row[0]) if owner_row else 0
    from app.models.user import User
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
    await _require_group_owner(db, world_id, operator_id, agent_id)
    from sqlalchemy import text as _u
    await db.execute(_u("UPDATE agents SET api_key_encrypted=NULL, api_base_url=NULL WHERE id=:aid"),
                     {"aid": agent_id})
    await db.commit()
    return {"success": True, "agent_id": agent_id, "configured": False}


async def assistant_api_status(db: AsyncSession, world_id: int, agent_id: int) -> dict:
    """群助手 API 状态（不回显 key）。"""
    wa = await _get_assistant(db, world_id, agent_id)
    from app.models.agent import Agent
    from app.models.user import User
    from sqlalchemy import text as _t
    agent = await db.get(Agent, agent_id)
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


# ═══════════════════════════════════════════════════════════════
# 事件注入（群消息 → group_type 轻量字段）
# ═══════════════════════════════════════════════════════════════

async def get_group_type_for_group(db: AsyncSession, world_id: int, group_id: int) -> dict | None:
    """群消息事件注入用：查绑定 → 返回 {slug, name}（未绑定返回 None）。"""
    binding = (await db.execute(
        select(WorldBinding).where(
            WorldBinding.world_id == world_id,
            WorldBinding.entity_type == "group",
            WorldBinding.entity_id == group_id,
        )
    )).scalar_one_or_none()
    if binding is None or not binding.group_type_slug:
        return None
    type_def = next((t for t in load_group_types(world_id) if t["slug"] == binding.group_type_slug), None)
    if type_def is None:
        return {"slug": binding.group_type_slug, "name": binding.group_type_slug}
    return {"slug": type_def["slug"], "name": type_def["name"]}
