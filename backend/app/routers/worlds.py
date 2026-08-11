"""
群视界 API — 世界 CRUD、入口绑定、唤醒/休眠、懒通知

设计文档：docs/group_world/design/group_world_design.md
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, Form
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/worlds", tags=["群视界"])


# ═══════════════════════════════════════════════════════════════
# 模型
# ═══════════════════════════════════════════════════════════════

class WorldCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    time_flow_rate: float = Field(default=1.0, ge=0.1, le=100.0)
    config: dict | None = None


class WorldUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    time_flow_rate: float | None = Field(default=None, ge=0.1, le=100.0)
    config: dict | None = None


class WorldRunRequest(BaseModel):
    """2.1 沙箱：运行世界 Python 代码（code 或 entry 二选一）"""
    code: str | None = Field(default=None, description="直接执行的脚本")
    entry: str | None = Field(default=None, description="世界文件夹内入口文件（相对路径）")


class WorldTriggerRequest(BaseModel):
    """2.2 触发文件：执行世界入口的 handle(event)"""
    event: dict = Field(default_factory=dict, description="触发事件")
    entry: str = Field(default="main.py", description="世界入口文件（默认 main.py）")


class BindRequest(BaseModel):
    entity_type: str = Field(..., description="group | dm | user | agent（AI 直接绑定）")
    entity_id: int


class NoticeRequest(BaseModel):
    """代码改动懒通知 — 世界 AI 的，无需 agent_id"""
    file: str = Field(..., description="改动文件")
    location: str = Field(default="", description="改动位置")
    summary: str = Field(..., description="改动摘要")


class CreatorConfigRequest(BaseModel):
    """群视界机器人（世界 AI）配置 — 单独表单，不属于 agent"""
    name: str | None = Field(default=None, max_length=50)
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2.0)
    top_p: float | None = Field(default=None, ge=0, le=1.0)
    thinking: bool | None = Field(default=None, description="深度思考（推理 token 单独计费，费用显著增加）")
    max_tool_rounds: int | None = Field(default=None, ge=1, le=200, description="工具循环上限（默认 50）")
    tools: list[str] | None = None


class ChatRequest(BaseModel):
    """世界 AI 对话：message 单条；messages 批量（排队消息一起发给 AI，多条气泡）"""
    message: str | None = Field(None, min_length=1)
    messages: list[str] | None = None


class ChatSessionRequest(BaseModel):
    """切换会话"""
    session_id: str


class ChatPinRequest(BaseModel):
    """收藏/取消收藏当前会话"""
    pin: bool = True


class ChatSettingsUpdate(BaseModel):
    """会话生命周期设置（0 = 关闭对应项）"""
    auto_new_enabled: bool | None = None
    auto_new_time: str | None = None
    compact_idle_hours: int | None = None
    retention_days: int | None = None


async def _require_owner(db: AsyncSession, world_id: int, user_id: int):
    """设计页/编辑接口：仅创建者可进入世界编辑界面"""
    from app.models.world import World
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    if world.owner_id != user_id:
        raise HTTPException(status_code=403, detail="仅创建者可进入世界编辑界面")
    return world


# ═══════════════════════════════════════════════════════════════
# 世界 CRUD
# ═══════════════════════════════════════════════════════════════

@router.post("")
async def create_world(
    req: WorldCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建世界"""
    from app.services.world.world_service import create_world
    world = await create_world(
        db, current_user["user_id"], req.name, req.description, req.time_flow_rate, req.config
    )
    await db.commit()
    return world


@router.get("")
async def list_worlds(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的世界列表"""
    from app.services.world.world_service import list_worlds
    return await list_worlds(db, current_user["user_id"])


@router.get("/by-entity")
async def world_by_entity(
    entity_type: str,
    entity_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按入口反查世界（群聊/私信/用户 → 世界 id）"""
    from app.services.world.world_service import find_world_by_entity
    world_id = await find_world_by_entity(db, entity_type, entity_id)
    if world_id is None:
        raise HTTPException(status_code=404, detail="该入口未绑定世界")
    return {"world_id": world_id}


@router.get("/{world_id}")
async def get_world(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """世界详情（仅创建者；沉浸界面走静态路由不依赖此接口）"""
    from app.services.world.world_service import get_world as _get_world
    await _require_owner(db, world_id, current_user["user_id"])
    # 2.3：活跃埋点（动态限流按人数加成）
    from app.routers.world_proxy import record_world_activity
    record_world_activity(world_id, current_user["user_id"])
    world = await _get_world(db, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    return world


@router.put("/{world_id}")
async def update_world(
    world_id: int,
    req: WorldUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新世界"""
    from app.services.world.world_service import update_world
    try:
        world = await update_world(
            db, world_id, current_user["user_id"],
            name=req.name, description=req.description,
            time_flow_rate=req.time_flow_rate, config=req.config,
        )
        await db.commit()
        return world
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{world_id}")
async def delete_world(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除世界"""
    from app.services.world.world_service import delete_world
    try:
        await delete_world(db, world_id, current_user["user_id"])
        await db.commit()
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 入口绑定
# ═══════════════════════════════════════════════════════════════

@router.post("/{world_id}/bind")
async def bind_entity(
    world_id: int,
    req: BindRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """绑定入口（群聊/私信/用户 ↔ 世界）"""
    from app.services.world.world_service import bind_entity
    try:
        result = await bind_entity(db, world_id, current_user["user_id"], req.entity_type, req.entity_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{world_id}/unbind")
async def unbind_entity(
    world_id: int,
    req: BindRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解绑入口"""
    from app.services.world.world_service import unbind_entity
    try:
        await unbind_entity(db, world_id, current_user["user_id"], req.entity_type, req.entity_id)
        await db.commit()
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 群类型系统（世界按类型分发群 + 群助手）
# ═══════════════════════════════════════════════════════════════

@router.post("/{world_id}/group-types")
async def save_group_types(
    world_id: int,
    req: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """世界作者整体保存群类型定义（写 group_types.json，随世界打包）"""
    from app.services.world.group_type_service import save_group_types_config
    try:
        types = await save_group_types_config(
            db, world_id, current_user["user_id"], req.get("types") or [],
        )
        return {"success": True, "types": types}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{world_id}/group-types")
async def list_group_types(
    world_id: int,
    entity_type: str = Query("group", pattern="^(group|agent)$"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """类型列表（定义+已绑定数/上限；entity_type=group 看群绑定数，agent 看 AI 绑定数）"""
    from app.services.world.group_type_service import list_group_types as _list
    types = await _list(db, world_id, entity_type=entity_type)
    return {"types": types}


@router.delete("/{world_id}/group-types/{type_slug}")
async def delete_group_type(
    world_id: int, type_slug: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除类型定义（已绑定群解除类型，群助手保留）"""
    from app.services.world.group_type_service import (
        _require_world_owner, load_group_types, save_group_types,
    )
    from app.models.world import WorldBinding
    try:
        await _require_world_owner(db, world_id, current_user["user_id"])
        types = [t for t in load_group_types(world_id) if t["slug"] != type_slug]
        save_group_types(world_id, types)
        await db.execute(
            WorldBinding.__table__.update().where(
                WorldBinding.group_type_slug == type_slug).values(group_type_slug=None)
        )
        await db.commit()
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{world_id}/bind-group")
async def bind_group_to_type(
    world_id: int,
    req: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """群主把群绑定到某群类型（slug）：校验上限 → 自动创建群助手（按模板）"""
    from app.services.world.group_type_service import bind_entry_with_type
    try:
        result = await bind_entry_with_type(
            db, world_id, current_user["user_id"], "group",
            entity_id=int(req.get("group_id") or 0),
            type_slug=str(req.get("type_slug") or ""),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{world_id}/bind-groups")
async def bind_groups_to_type(
    world_id: int,
    req: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量把多个群绑定到某类型（勾选多群一次绑定；逐群校验，互不影响）"""
    from app.services.world.group_type_service import bind_entries_with_type
    try:
        return await bind_entries_with_type(
            db, world_id, current_user["user_id"], "group",
            entity_ids=[int(x) for x in (req.get("group_ids") or []) if int(x) > 0],
            type_slug=str(req.get("type_slug") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{world_id}/bind-entries")
async def bind_entries(
    world_id: int,
    req: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """通用批量绑定入口（entity_type: group=群聊 / agent=AI）：选类型 → 勾选多条 → 一次绑定"""
    from app.services.world.group_type_service import bind_entries_with_type
    entity_type = str(req.get("entity_type") or "group")
    if entity_type not in ("group", "agent"):
        raise HTTPException(status_code=400, detail="entity_type 仅支持 group/agent")
    try:
        return await bind_entries_with_type(
            db, world_id, current_user["user_id"], entity_type,
            entity_ids=[int(x) for x in (req.get("entity_ids") or []) if int(x) > 0],
            type_slug=str(req.get("type_slug") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{world_id}/assistants")
async def list_assistants(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """世界视角：列出该世界所有群助手（含 API 状态，不回显 key）"""
    from app.services.world.group_type_service import assistant_api_status
    from app.models.world import WorldAgent
    rows = (await db.execute(
        select(WorldAgent).where(
            WorldAgent.world_id == world_id, WorldAgent.role == "assistant")
        .order_by(WorldAgent.id)
    )).scalars().all()
    items = []
    for wa in rows:
        st = await assistant_api_status(db, world_id, wa.agent_id)
        items.append({"id": wa.agent_id, "group_id": wa.group_id,
                      "group_type_slug": wa.group_type_slug, **st})
    return {"assistants": items}


@router.put("/{world_id}/assistants/{agent_id}/api")
async def set_assistant_api(
    world_id: int, agent_id: int,
    req: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """群主为群助手设置自定义 API（加密存储）"""
    from app.services.world.group_type_service import set_assistant_api as _set
    try:
        return await _set(
            db, world_id, current_user["user_id"], agent_id,
            api_key=str(req.get("api_key") or "") or None,
            api_base_url=str(req.get("api_base_url") or "") or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{world_id}/assistants/{agent_id}/apply-global")
async def apply_global_api(
    world_id: int, agent_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """一键应用群主的默认全局 API"""
    from app.services.world.group_type_service import apply_global_api as _apply
    try:
        return await _apply(db, world_id, current_user["user_id"], agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{world_id}/assistants/{agent_id}/api")
async def clear_assistant_api(
    world_id: int, agent_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清除群助手 API（回落系统默认）"""
    from app.services.world.group_type_service import clear_assistant_api as _clear
    try:
        return await _clear(db, world_id, current_user["user_id"], agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{world_id}/wake")
async def wake_world(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动唤醒世界（应用离线时间补偿；resident 世界同时启动常驻进程）"""
    from app.services.world.world_service import wake_world
    try:
        world = await wake_world(db, world_id)
        await db.commit()
        # 2.5：常驻世界随唤醒启动（config.resident=true 且 main.py 存在）
        from app.models.world import World as _World
        w = await db.get(_World, world_id)
        if w is not None:
            from app.services.world.world_resident import manager
            await manager.start(db, w)
        return world
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{world_id}/sleep")
async def sleep_world(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动休眠世界（resident 世界同时优雅停止常驻进程）"""
    from app.services.world.world_service import sleep_world
    try:
        world = await sleep_world(db, world_id)
        await db.commit()
        from app.services.world.world_resident import manager
        await manager.stop(world_id)
        return world
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 世界编号变量（前端注入 window.WORLD_ID）
# ═══════════════════════════════════════════════════════════════

@router.get("/{world_id}/world-variable")
async def world_variable(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取世界编号（前端注入 window.WORLD_ID，AI/人类代码只管用变量）"""
    await _require_owner(db, world_id, current_user["user_id"])
    return {"world_id": world_id, "variable": "WORLD_ID", "value": world_id}


# ═══════════════════════════════════════════════════════════════
# 懒通知（用户改代码 → 下次对话附带给群视界 agent）
# ═══════════════════════════════════════════════════════════════

@router.post("/{world_id}/notices")
async def add_notice(
    world_id: int,
    req: NoticeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """记录代码改动懒通知（世界 AI 是默认收件人，无需 agent_id）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_service import add_pending_notice
    try:
        await add_pending_notice(db, world_id, req.file, req.location, req.summary)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"success": True}


@router.get("/{world_id}/notices")
async def take_creator_notices(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取出并清空世界 AI 的懒通知（对话开始时调用，身份 = 世界，无需 agent_id）"""

    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_service import take_pending_notices
    notices = await take_pending_notices(db, world_id)
    await db.commit()
    return {"notices": notices}


# ═══════════════════════════════════════════════════════════════
# 群视界机器人（世界 AI）— 单独表单，不属于 agent，无账号
# ═══════════════════════════════════════════════════════════════

@router.get("/{world_id}/creator")
async def get_creator(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取世界 AI 配置（就是世界配置的一部分）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_service import get_world
    world = await get_world(db, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    return world["creator"]


@router.put("/{world_id}/creator")
async def update_creator(
    world_id: int,
    req: CreatorConfigRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新世界 AI 配置（仅创建者）"""

    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_service import update_creator_config
    try:
        creator = await update_creator_config(
            db, world_id, current_user["user_id"], req.model_dump(exclude_none=True)
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=403 if "创建者" in str(e) else 404, detail=str(e))
    await db.commit()
    return creator


@router.get("/{world_id}/usage")
async def get_world_usage(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """世界 LLM 用量与缓存命中率（阶段 2.7，仅创建者）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from sqlalchemy import func as _func
    from app.models.world import WorldLLMUsage
    row = (await db.execute(
        select(
            _func.count(WorldLLMUsage.id),
            _func.coalesce(_func.sum(WorldLLMUsage.prompt_tokens), 0),
            _func.coalesce(_func.sum(WorldLLMUsage.completion_tokens), 0),
            _func.coalesce(_func.sum(WorldLLMUsage.cached_tokens), 0),
        ).where(WorldLLMUsage.world_id == world_id)
    )).one()
    calls, prompt, completion, cached = row
    hit_rate = round(cached / prompt * 100, 1) if prompt else 0.0
    return {
        "world_id": world_id,
        "total_calls": calls,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "cache_hit_rate_pct": hit_rate,
    }


@router.post("/{world_id}/run")
async def run_world_code(
    world_id: int,
    req: WorldRunRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """在沙箱中运行世界 Python 代码（阶段 2.1，仅创建者；配额：默认 24MB/10s，worlds.config 可配）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.models.world import World
    from app.services.world.world_sandbox import run_world_code as _run
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    # 2.3：确保受控 API token 已生成（沙箱 env 注入 WORLD_API_TOKEN 用）
    from app.routers.world_proxy import ensure_world_api_token
    await ensure_world_api_token(db, world)
    await db.commit()
    result = await _run(world, code=req.code, entry=req.entry)
    result["world_id"] = world_id
    return result


@router.post("/{world_id}/trigger")
async def trigger_world_code(
    world_id: int,
    req: WorldTriggerRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """2.2 触发文件：执行世界入口的 handle(event)，返回结果（仅创建者）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.models.world import World
    from app.services.world.world_sandbox import run_world_trigger as _trigger
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    # 2.3：确保受控 API token 已生成（沙箱 env 注入 WORLD_API_TOKEN 用）
    from app.routers.world_proxy import ensure_world_api_token
    await ensure_world_api_token(db, world)
    await db.commit()
    result = await _trigger(world, event=req.event, entry=req.entry)
    result["world_id"] = world_id
    return result


# ═══════════════════════════════════════════════════════════════
# 世界 AI 对话（世界级会话，非 DM/agent）
# ═══════════════════════════════════════════════════════════════

@router.get("/{world_id}/chat")
async def get_chat(
    world_id: int,
    before_id: int | None = None,
    limit: int = 30,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """世界 AI 对话历史（仅创建者；before_id 翻更早，has_more 判断是否还有；按当前会话过滤）"""
    await _require_owner(db, world_id, current_user["user_id"])
    # 2.3：活跃埋点（动态限流按人数加成）
    from app.routers.world_proxy import record_world_activity
    record_world_activity(world_id, current_user["user_id"])
    from app.models.world import World
    from app.services.world.world_chat_service import get_chat_history, ensure_session_lifecycle, session_id_for_db
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    # 懒加载会话生命周期（auto_new / 过期清理）
    await ensure_session_lifecycle(db, world)
    sid = session_id_for_db(world)
    limit = max(1, min(limit, 100))
    # 多取一条判断是否还有更早
    msgs = await get_chat_history(db, world_id, limit=limit + 1, before_id=before_id, session_id=sid)
    has_more = len(msgs) > limit
    cfg = world.config or {}
    sessions = [
        {"id": k, "created_at": (v or {}).get("created_at"), "last_active_at": (v or {}).get("last_active_at"),
         "pinned": bool((v or {}).get("pinned_by"))}
        for k, v in (cfg.get("sessions") or {}).items()
    ]
    # 默认会话（旧数据无 session_id）若还有消息，也进列表（否则点哪个都空、默认会话找不到）
    from sqlalchemy import func as _f
    from app.models.world import WorldChatMessage as _WCM
    has_default = (await db.execute(
        select(_f.count()).select_from(_WCM).where(
            _WCM.world_id == world_id, _WCM.session_id.is_(None),
        )
    )).scalar() or 0
    if has_default:
        sessions.insert(0, {"id": "default", "last_active_at": None, "pinned": bool((cfg.get("sessions") or {}).get("default", {}).get("pinned_by"))})
    return {
        "messages": msgs[-limit:],
        "has_more": has_more,
        "current_session": cfg.get("current_session") or "default",
        "sessions": sessions,
    }


@router.post("/{world_id}/chat")
async def post_chat(
    world_id: int,
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """世界 AI 对话：入队（服务器端全程执行，不依赖连接），返回 turn_id 用于订阅直播"""
    await _require_owner(db, world_id, current_user["user_id"])
    # 2.3：活跃埋点（动态限流按人数加成）
    from app.routers.world_proxy import record_world_activity
    record_world_activity(world_id, current_user["user_id"])
    # 懒加载会话生命周期（auto_new / 过期清理）+ 活跃时间
    from app.models.world import World
    from app.services.world.world_chat_service import ensure_session_lifecycle, touch_session
    world = await db.get(World, world_id)
    if world is not None:
        await ensure_session_lifecycle(db, world)
        touch_session(world)
        await db.commit()
    from app.services.world.world_turn import get_world_worker
    worker = get_world_worker(world_id)
    payload = req.messages if req.messages else ([req.message] if req.message else [])
    turn_id = worker.enqueue(current_user["user_id"], payload)
    return {
        "turn_id": turn_id,
        "queued": worker.queue_size > 1,
        "position": max(0, worker.queue_size - 1),
    }


@router.post("/{world_id}/chat/session")
async def switch_chat_session(
    world_id: int,
    req: ChatSessionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """切换当前会话（id 一致：切回旧会话继续对话，上下文按会话隔离）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.models.world import World
    from app.services.world.world_chat_service import get_chat_history, session_id_for_db
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    cfg = dict(world.config or {})
    sessions = cfg.get("sessions") or {}
    # default 会话始终可切（旧数据）；其他会话须存在于列表
    if req.session_id != "default" and req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    cfg["current_session"] = None if req.session_id == "default" else req.session_id
    world.config = cfg
    await db.commit()
    msgs = await get_chat_history(db, world_id, 30, session_id=session_id_for_db(world))
    from sqlalchemy import func as _f
    from app.models.world import WorldChatMessage as _WCM
    has_default = (await db.execute(
        select(_f.count()).select_from(_WCM).where(
            _WCM.world_id == world_id, _WCM.session_id.is_(None),
        )
    )).scalar() or 0
    out = [
        {"id": k, "created_at": (v or {}).get("created_at"), "last_active_at": (v or {}).get("last_active_at"),
         "pinned": bool((v or {}).get("pinned_by"))}
        for k, v in sessions.items()
    ]
    if has_default:
        out.insert(0, {"id": "default", "last_active_at": None, "pinned": bool(sessions.get("default", {}).get("pinned_by"))})
    return {
        "current_session": req.session_id,
        "messages": msgs,
        "sessions": out,
    }


@router.post("/{world_id}/chat/session/pin")
async def pin_chat_session(
    world_id: int,
    req: ChatPinRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """收藏/取消收藏当前会话（每用户最多 16 个；收藏的会话不被自动清理）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.models.world import World
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    cfg = dict(world.config or {})
    sessions = dict(cfg.get("sessions") or {})
    key = cfg.get("current_session") or "default"
    meta = dict(sessions.get(key) or {})
    pinned = list(meta.get("pinned_by") or [])
    uid = current_user["user_id"]
    if req.pin:
        if uid not in pinned:
            if len(pinned) >= 16:
                raise HTTPException(status_code=400, detail="收藏已达上限（16 个）")
            pinned.append(uid)
    else:
        if uid in pinned:
            pinned.remove(uid)
    meta["pinned_by"] = pinned
    sessions[key] = meta
    cfg["sessions"] = sessions
    world.config = cfg
    await db.commit()
    return {"pinned": bool(pinned), "count": len(pinned)}


@router.get("/{world_id}/chat/settings")
async def get_chat_settings(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会话生命周期设置（世界级；未配置时给默认值）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.models.world import World
    from app.services.world.world_chat_service import session_settings
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    return session_settings(world)


@router.put("/{world_id}/chat/settings")
async def update_chat_settings(
    world_id: int,
    req: ChatSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新会话生命周期设置（设计页配置面板用）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.models.world import World
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    cfg = dict(world.config or {})
    st = dict(cfg.get("session_settings") or {})
    patch = req.model_dump(exclude_none=True)
    if "auto_new_time" in patch:
        try:
            hh, mm = str(patch["auto_new_time"]).split(":")[:2]
            patch["auto_new_time"] = f"{int(hh):02d}:{int(mm):02d}"
        except Exception:
            raise HTTPException(status_code=400, detail="auto_new_time 格式应为 HH:MM")
    st.update(patch)
    cfg["session_settings"] = st
    world.config = cfg
    await db.commit()
    return st


@router.get("/{world_id}/chat/stream")
async def chat_stream(
    world_id: int,
    turn_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """世界 AI 对话直播（SSE）：订阅指定轮次；断开重连=重新订阅，轮次在服务器继续"""
    await _require_owner(db, world_id, current_user["user_id"])
    from fastapi.responses import StreamingResponse
    from app.services.world.world_turn import subscribe_turn
    return StreamingResponse(subscribe_turn(world_id, turn_id), media_type="text/event-stream")


@router.get("/{world_id}/chat/suggest")
async def chat_suggest(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """"你可以"建议：读取持久化的建议（AI 上次生成）；无存储且无对话历史 → 预设随机 4 个（首次进入/clear 后引导）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.models.world import WorldChatMessage
    from sqlalchemy import func as _f
    # 无对话历史（首次进入/clear 后）→ 总是预设引导（不被 AI 旧建议污染）
    cnt = (await db.execute(
        select(_f.count()).select_from(WorldChatMessage).where(WorldChatMessage.world_id == world_id)
    )).scalar() or 0
    if cnt == 0:
        from app.services.world.world_suggestions import load_preset_suggestions
        return {"suggestions": await load_preset_suggestions(db)}
    # 有对话历史 → 用持久化的 AI 建议；没有 → 空（等 AI 下次回复生成）
    from app.services.world.world_service import get_world_data
    row = await get_world_data(db, world_id, "ui.suggestions")
    if row and row.get("value"):
        return {"suggestions": row["value"]}
    return {"suggestions": []}


@router.get("/{world_id}/chat/status")
async def chat_status(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """世界 AI 对话状态：是否正在处理/排队（刷新页面后据此恢复「思考中」指示）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.models.world import WorldChatMessage
    from app.services.world.world_turn import get_world_worker
    worker = get_world_worker(world_id)
    queue_size = worker.queue_size
    # 正在处理 = 队列有消息，或有进行中的轮次（active_turn 标记；比"最后消息非 ai"准确，
    # worker 死后不会把排队消息永远误报为 processing，导致前端排队永不发送）
    processing = queue_size > 0
    turn_id = None
    if not processing:
        from app.models.world import World as _World
        world_row = await db.get(_World, world_id)
        act = (world_row.config or {}).get("active_turn") if world_row else None
        if act:
            processing = True
            turn_id = act.get("turn_id")  # 刷新后前端据此订阅 SSE 直播，而不是干等到整轮结束
    return {"processing": processing, "queue_size": queue_size, "turn_id": turn_id}



# ═══════════════════════════════════════════════════════════════
# 文件操作（群视界机器人 / 设计页用）
# ═══════════════════════════════════════════════════════════════

@router.get("/{world_id}/files")
async def list_files(
    world_id: int,
    prefix: str = "",
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """文件树（仅创建者）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_service import get_world
    from app.services.world.world_file_service import list_files as fs_list

    if await get_world(db, world_id) is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    return {"files": fs_list(world_id, prefix)}


@router.get("/{world_id}/files/content")
async def read_file(
    world_id: int,
    path: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读文件内容"""

    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_file_service import read_file as fs_read
    try:
        return fs_read(world_id, path)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))


class FileWriteRequest(BaseModel):
    path: str = Field(..., description="相对路径，如 index.html / css/style.css")
    content: str


@router.put("/{world_id}/files")
async def write_file(
    world_id: int,
    req: FileWriteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写入文件（仅创建者，群视界机器人调用，自动建目录）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_file_service import write_file as fs_write
    try:
        return fs_write(world_id, req.path, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{world_id}/files")
async def delete_file(
    world_id: int,
    path: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除文件"""

    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_file_service import delete_file as fs_delete
    try:
        fs_delete(world_id, path)
        return {"success": True}
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{world_id}/files/import")
async def import_zip(
    world_id: int,
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """zip 批量导入（仅创建者，文件夹导入接口）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_file_service import import_zip as fs_import
    try:
        data = await file.read()
        result = fs_import(world_id, data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{world_id}/files/upload")
async def upload_file(
    world_id: int,
    file: UploadFile,
    path: str = Form(..., description="目标相对路径（含文件名，如 img/logo.png）"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单文件上传（图片/音频/字体等二进制，仅创建者；先选目标位置再上传）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_file_service import write_file_bytes
    path = path.strip().lstrip("/")
    if not path:
        raise HTTPException(status_code=400, detail="目标路径不能为空")
    try:
        data = await file.read()
        result = write_file_bytes(world_id, path, data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 世界数据（world_data）— 结构化/操作数据，只经 API 读写
# （代码/数据分离：静态文字类产物放 data/worlds/{id}/content/，自由层级，发布不打包）
# ═══════════════════════════════════════════════════════════════

class WorldDataRequest(BaseModel):
    """世界数据写入请求：value 为任意 JSON"""
    value: dict | list | str | int | float | bool | None = None


@router.get("/{world_id}/data/{key}")
async def get_world_data(
    world_id: int,
    key: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读世界数据（不存在返回 value=null）"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_service import get_world_data
    row = await get_world_data(db, world_id, key)
    return {"key": key, "value": row["value"] if row else None}


@router.put("/{world_id}/data/{key}")
async def put_world_data(
    world_id: int,
    key: str,
    body: WorldDataRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写世界数据（upsert；key 长度限制 200）"""
    await _require_owner(db, world_id, current_user["user_id"])
    if len(key) > 200:
        raise HTTPException(status_code=400, detail="key 过长（≤200）")
    from app.services.world.world_service import set_world_data
    return await set_world_data(db, world_id, key, body.value)


@router.delete("/{world_id}/data/{key}")
async def delete_world_data(
    world_id: int,
    key: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删世界数据"""
    await _require_owner(db, world_id, current_user["user_id"])
    from app.services.world.world_service import delete_world_data
    ok = await delete_world_data(db, world_id, key)
    if not ok:
        raise HTTPException(status_code=404, detail="数据不存在")
    return {"success": True}


@router.get("/{world_id}/export")
async def export_zip(
    world_id: int,
    include_content: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """一键打包下载。include_content=true（默认）包含 content/ 产物区；false 只打包代码区（发布用）"""

    await _require_owner(db, world_id, current_user["user_id"])
    from fastapi.responses import Response
    from app.services.world.world_file_service import export_zip as fs_export
    data = fs_export(world_id, include_content=include_content)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=world_{world_id}.zip"},
    )
