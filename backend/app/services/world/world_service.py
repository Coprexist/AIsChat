"""
世界服务 — 世界 CRUD、入口绑定、唤醒/休眠、懒通知、世界 AI 对话

设计文档：docs/group_world/design/group_world_design.md
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VALID_BIND_TYPES = {"group", "dm", "user", "agent"}  # agent = AI 直接绑定世界（个人专属能力）
DEFAULT_SLEEP_MEMORY_MB = 48  # 休眠配额（无人时默认 48MB/世界；24MB 连解释器都起不来，2026-08-05 实测）

# 群视界机器人（世界 AI）默认配置 —— 建世界时自动初始化，就是世界的一份配置（非 agent、无账号）
CREATOR_DEFAULT_CONFIG = {
    "name": "群视界机器人",
    "system_prompt": (
        "你是这个世界的「群视界机器人」——群聊世界视觉界面创造者。\n"
        "职责：\n"
        "1. 根据群聊需求创建/修改世界的界面与代码（HTML/CSS/JS/数据文件）\n"
        "2. 用世界文件 API 读写世界文件夹，用懒通知感知用户手动改动\n"
        "3. 遵守接口文档 docs/group_world/api/world_api_docs.md 的约定\n"
        "你的身份是世界的：对外标识 world-{world_id}，世界编号由前端注入 window.WORLD_ID，不需要关心具体数值。"
    ),
    "model": None,          # None = 继承全局默认模型
    "temperature": 0.8,
    "top_p": 0.9,
    "thinking": False,      # 深度思考（推理 token 单独计费，费用显著增加）
    "max_tool_rounds": 50,  # 工具循环上限（默认 50，设计页可改）
    "tools": ["world_files", "world_config"],  # 世界文件读写/配置（tool_registry 注册，阶段 2 完整注入）
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def apply_time_compensation(world, now: datetime | None = None):
    """离线时间补偿 + 唤醒：world_time += (now - last_active_at) × 流速；标记 active"""
    now = now or _now()
    if world.status == "sleeping" and world.last_active_at:
        delta = now - world.last_active_at
        if delta.total_seconds() > 0:
            base = world.world_time or world.last_active_at
            world.world_time = base + delta * (world.time_flow_rate or 1.0)
    world.last_active_at = now
    world.status = "active"

async def create_world(
    db: AsyncSession,
    owner_id: int,
    name: str,
    description: str = "",
    time_flow_rate: float = 1.0,
    config: dict | None = None,
) -> dict:
    """创建世界（默认 sleeping 状态，懒加载）

    群视界机器人 = 世界配置（worlds.creator_config），建世界即初始化，无需创建 agent/账号。
    """
    from app.models.world import World

    world = World(
        name=name,
        description=description,
        owner_id=owner_id,
        status="sleeping",
        time_flow_rate=time_flow_rate,
        world_time=_now(),
        last_active_at=_now(),
        config=config or {"sleep_memory_mb": DEFAULT_SLEEP_MEMORY_MB},
    )
    db.add(world)
    await db.flush()
    await db.refresh(world)

    # 群视界机器人：默认就位（独立表 world_ais，身份 = world-{id}）
    await ensure_world_ai(db, world.id)

    logger.info(f"🌐 世界创建: #{world.id} {name} (owner={owner_id}) + 世界 AI world-{world.id}")
    return world_to_dict(world)


async def ensure_world_ai(db: AsyncSession, world_id: int):
    """确保世界 AI 实体存在（幂等，独立表 world_ais），返回行"""
    from app.models.world import WorldAI
    row = await db.execute(select(WorldAI).where(WorldAI.world_id == world_id))
    wai = row.scalar_one_or_none()
    if wai is None:
        wai = WorldAI(
            world_id=world_id,
            name="群视界机器人",
            system_prompt=CREATOR_DEFAULT_CONFIG["system_prompt"].replace("{world_id}", str(world_id)),
            temperature=0.8,
            top_p=0.9,
            thinking=False,
            max_tool_rounds=50,
        )
        db.add(wai)
        await db.flush()
    return wai


# ═══════════════════════════════════════════════════════════════
# 世界详情 / 列表
# ═══════════════════════════════════════════════════════════════

async def get_world(db: AsyncSession, world_id: int) -> dict | None:
    """世界详情（含绑定入口、居民 AI、群视界机器人配置）"""
    from app.models.world import World, WorldBinding, WorldAgent

    world = await db.get(World, world_id)
    if world is None:
        return None

    result = world_to_dict(world)
    wai = await ensure_world_ai(db, world_id)  # 老世界自动补默认实体（幂等）

    bindings = await db.execute(
        select(WorldBinding).where(WorldBinding.world_id == world_id)
    )
    result["bindings"] = [
        {"entity_type": b.entity_type, "entity_id": b.entity_id}
        for b in bindings.scalars()
    ]

    # 居民 AI（真 agent 入驻世界；群视界机器人不在这个列表里）
    agents = await db.execute(
        select(WorldAgent).where(WorldAgent.world_id == world_id)
    )
    result["agents"] = [
        {
            "agent_id": a.agent_id,
            "role": a.role,
            "pending_notices": a.pending_notices or [],
        }
        for a in agents.scalars()
    ]

    # 群视界机器人：身份 = 世界（world-{id}），实体在 world_ais 表
    result["creator"] = world_ai_to_dict(world_id, wai)
    return result


def world_ai_to_dict(world_id: int, wai) -> dict:
    """世界 AI 摘要（无 agent_id/user_id——它不是 agent）"""
    from app.services.world.world_chat_service import build_forced_prompt
    return {
        "id": f"world-{world_id}",
        "name": wai.name or "群视界机器人",
        "system_prompt": wai.system_prompt or "",
        "forced_prompt": build_forced_prompt(),  # 强注入段（只读展示，不可改）
        "model": wai.model,
        "temperature": wai.temperature if wai.temperature is not None else 0.8,
        "top_p": wai.top_p if wai.top_p is not None else 0.9,
        "thinking": bool(wai.thinking),
        "max_tool_rounds": wai.max_tool_rounds or 50,
        "tools": ["world_files", "world_config"],
    }


async def list_worlds(db: AsyncSession, owner_id: int) -> list[dict]:
    """我的世界列表（含绑定入口）"""
    from app.models.world import World, WorldBinding

    result = await db.execute(
        select(World).where(World.owner_id == owner_id).order_by(World.id.desc())
    )
    worlds = result.scalars().all()
    if not worlds:
        return []

    # 批量查询绑定入口 + 世界 AI 实体，避免 N+1
    world_ids = [w.id for w in worlds]
    bind_result = await db.execute(
        select(WorldBinding).where(WorldBinding.world_id.in_(world_ids))
    )
    by_world: dict[int, list[dict]] = {}
    for b in bind_result.scalars():
        by_world.setdefault(b.world_id, []).append(
            {"entity_type": b.entity_type, "entity_id": b.entity_id}
        )
    from app.models.world import WorldAI
    wai_result = await db.execute(select(WorldAI).where(WorldAI.world_id.in_(world_ids)))
    wai_by_world = {w.world_id: w for w in wai_result.scalars()}

    out = []
    for w in worlds:
        d = world_to_dict(w)
        d["bindings"] = by_world.get(w.id, [])
        wai = wai_by_world.get(w.id)
        d["creator"] = world_ai_to_dict(w.id, wai) if wai else None
        out.append(d)
    return out


async def update_world(
    db: AsyncSession,
    world_id: int,
    owner_id: int,
    name: str | None = None,
    description: str | None = None,
    time_flow_rate: float | None = None,
    config: dict | None = None,
) -> dict:
    """更新世界（仅创建者）"""
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")
    if world.owner_id != owner_id:
        raise ValueError("仅创建者可修改世界")

    if name is not None:
        world.name = name
    if description is not None:
        world.description = description
    if time_flow_rate is not None:
        world.time_flow_rate = time_flow_rate
    if config is not None:
        world.config = {**(world.config or {}), **config}
    await db.flush()
    return world_to_dict(world)


async def update_creator_config(
    db: AsyncSession,
    world_id: int,
    owner_id: int,
    patch: dict,
) -> dict:
    """更新群视界机器人配置（世界 AI 表单提交；仅创建者）"""
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")
    if world.owner_id != owner_id:
        raise ValueError("仅创建者可配置世界 AI")

    wai = await ensure_world_ai(db, world_id)
    allowed = {"name", "system_prompt", "model", "temperature", "top_p", "thinking", "max_tool_rounds", "tools"}
    for k, v in patch.items():
        if k in allowed and k != "tools":  # tools 是派生字段，不落库
            setattr(wai, k, v)
    await db.flush()
    return world_ai_to_dict(world_id, wai)


async def delete_world(db: AsyncSession, world_id: int, owner_id: int) -> None:
    """删除世界（仅创建者）；世界 AI 是世界的配置，随世界一起消失"""
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")
    if world.owner_id != owner_id:
        raise ValueError("仅创建者可删除世界")

    await db.delete(world)
    await db.flush()
    logger.info(f"🗑️ 世界删除: #{world_id}（世界 AI 随世界销毁）")


# ═══════════════════════════════════════════════════════════════
# 入口绑定
# ═══════════════════════════════════════════════════════════════

async def bind_entity(
    db: AsyncSession,
    world_id: int,
    owner_id: int,
    entity_type: str,
    entity_id: int,
) -> dict:
    """绑定入口（群聊/私信/用户 ↔ 世界）"""
    from app.models.world import World, WorldBinding

    if entity_type not in VALID_BIND_TYPES:
        raise ValueError(f"无效入口类型: {entity_type}")

    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")
    if world.owner_id != owner_id:
        raise ValueError("仅创建者可绑定入口")

    existing = await db.execute(
        select(WorldBinding).where(
            WorldBinding.world_id == world_id,
            WorldBinding.entity_type == entity_type,
            WorldBinding.entity_id == entity_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(WorldBinding(world_id=world_id, entity_type=entity_type, entity_id=entity_id))
        await db.flush()
        logger.info(f"🔗 世界 #{world_id} 绑定 {entity_type}:{entity_id}")
    return {"success": True}


async def unbind_entity(
    db: AsyncSession,
    world_id: int,
    owner_id: int,
    entity_type: str,
    entity_id: int,
) -> None:
    """解绑入口"""
    from app.models.world import World, WorldBinding

    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")
    if world.owner_id != owner_id:
        raise ValueError("仅创建者可解绑入口")

    await db.execute(
        WorldBinding.__table__.delete().where(
            WorldBinding.world_id == world_id,
            WorldBinding.entity_type == entity_type,
            WorldBinding.entity_id == entity_id,
        )
    )
    await db.flush()


async def find_world_by_entity(db: AsyncSession, entity_type: str, entity_id: int) -> int | None:
    """按入口反查世界 id（群聊 id / 用户 id → 世界）"""
    from app.models.world import WorldBinding

    result = await db.execute(
        select(WorldBinding.world_id).where(
            WorldBinding.entity_type == entity_type,
            WorldBinding.entity_id == entity_id,
        )
    )
    return result.scalar_one_or_none()


async def find_worlds_by_entity(db: AsyncSession, entity_type: str, entity_id: int) -> list:
    """按入口反查多个世界（群/agent 可绑多个世界）"""
    from app.models.world import World, WorldBinding

    rows = (await db.execute(
        select(World).join(WorldBinding, WorldBinding.world_id == World.id).where(
            WorldBinding.entity_type == entity_type,
            WorldBinding.entity_id == entity_id,
        )
    )).scalars().all()
    return list(rows)


# ═══════════════════════════════════════════════════════════════
# 唤醒 / 休眠 / 世界时间
# ═══════════════════════════════════════════════════════════════

async def wake_world(db: AsyncSession, world_id: int) -> dict:
    """唤醒世界：应用离线时间补偿（世界时间 = 上次活跃 + 真实时间差 × 流速）"""
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")

    now = _now()
    if world.last_active_at:
        delta = now - world.last_active_at
        if world.world_time:
            world.world_time = world.world_time + delta * world.time_flow_rate
        else:
            world.world_time = now
    else:
        world.world_time = now
    world.last_active_at = now
    world.status = "active"
    await db.flush()
    logger.info(f"⏰ 世界 #{world_id} 唤醒，离线补偿 {delta.total_seconds() if 'delta' in dir() else 0:.0f}s")
    return world_to_dict(world)


async def sleep_world(db: AsyncSession, world_id: int) -> dict:
    """休眠世界"""
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")
    world.status = "sleeping"
    world.last_active_at = _now()
    await db.flush()
    return world_to_dict(world)


# ═══════════════════════════════════════════════════════════════
# 懒通知（用户改代码 → 下次对话附送给世界 AI；属世界配置的一部分）
# ═══════════════════════════════════════════════════════════════

async def add_pending_notice(
    db: AsyncSession,
    world_id: int,
    file_path: str,
    location: str,
    summary: str,
) -> None:
    """记录代码改动懒通知（不实时打扰，下次对话时附送）"""
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")

    notices = list(world.creator_notices or [])
    notices.append({
        "file": file_path,
        "location": location,
        "summary": summary,
        "at": _now().isoformat(),
    })
    world.creator_notices = notices[-50:]  # 最多保留 50 条
    await db.flush()


async def take_pending_notices(db: AsyncSession, world_id: int) -> list[dict]:
    """取出并清空懒通知（对话开始时调用，附送给世界 AI）"""
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        return []
    notices = list(world.creator_notices or [])
    world.creator_notices = []
    await db.flush()
    return notices


# ═══════════════════════════════════════════════════════════════
# 世界 AI 对话（世界级会话，非 DM/agent）
# ═══════════════════════════════════════════════════════════════
def world_to_dict(w) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "description": w.description,
        "owner_id": w.owner_id,
        "status": w.status,
        "time_flow_rate": w.time_flow_rate,
        "world_time": w.world_time.isoformat() if w.world_time else None,
        "last_active_at": w.last_active_at.isoformat() if w.last_active_at else None,
        "config": w.config or {},
        "creator_config": w.creator_config or {},
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════
# 世界数据（world_data）— 每世界 key-value，只经 API/skill ctx 读写
# ═══════════════════════════════════════════════════════════════

async def get_world_data(db: AsyncSession, world_id: int, key: str) -> dict | None:
    """读世界数据；不存在返回 None"""
    from app.models.world import WorldData
    row = (await db.execute(
        select(WorldData).where(WorldData.world_id == world_id, WorldData.key == key)
    )).scalar_one_or_none()
    if row is None:
        return None
    return {"key": row.key, "value": row.value}


async def set_world_data(db: AsyncSession, world_id: int, key: str, value) -> dict:
    """写世界数据（upsert）"""
    from app.models.world import WorldData
    row = (await db.execute(
        select(WorldData).where(WorldData.world_id == world_id, WorldData.key == key)
    )).scalar_one_or_none()
    if row is None:
        row = WorldData(world_id=world_id, key=key, value=value)
        db.add(row)
    else:
        row.value = value
    await db.commit()
    await db.refresh(row)
    return {"key": row.key, "value": row.value}


async def delete_world_data(db: AsyncSession, world_id: int, key: str) -> bool:
    """删世界数据；返回是否存在"""
    from app.models.world import WorldData
    row = (await db.execute(
        select(WorldData).where(WorldData.world_id == world_id, WorldData.key == key)
    )).scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


# ═══════════════════════════════════════════════════════════════
# 拆分模块再导出（世界 AI 对话 → world_chat_service；工具 → world_tools）
# 路由等外部引用保持不变
# ═══════════════════════════════════════════════════════════════

from app.services.world.world_chat_service import (  # noqa: E402
    CHAT_HISTORY_LIMIT,
    WORLD_CHAT_KEEP_LAST,
    WORLD_CONTEXT_MIN_MESSAGES,
    world_context_block,
    get_chat_history,
    _resolve_world_credentials,
    stream_world_chat,
)
from app.services.world.world_tools import (  # noqa: E402
    WORLD_TOOLS,
    _execute_world_tool,
    _tool_result_summary,
)
