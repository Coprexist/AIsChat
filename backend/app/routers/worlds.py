"""
群视界 API — 世界 CRUD、入口绑定、唤醒/休眠、懒通知

设计文档：docs/group_world/design/group_world_design.md
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from pydantic import BaseModel, Field
from sqlalchemy import select
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
    entity_type: str = Field(..., description="group | dm | user")
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
    """世界 AI 对话（单条消息无长度上限）"""
    message: str = Field(..., min_length=1)


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
# 唤醒 / 休眠
# ═══════════════════════════════════════════════════════════════

@router.post("/{world_id}/wake")
async def wake_world(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动唤醒世界（应用离线时间补偿）"""
    from app.services.world.world_service import wake_world
    try:
        world = await wake_world(db, world_id)
        await db.commit()
        return world
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{world_id}/sleep")
async def sleep_world(
    world_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动休眠世界"""
    from app.services.world.world_service import sleep_world
    try:
        world = await sleep_world(db, world_id)
        await db.commit()
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
    """世界 AI 对话历史（仅创建者；before_id 翻更早，has_more 判断是否还有）"""
    await _require_owner(db, world_id, current_user["user_id"])
    # 2.3：活跃埋点（动态限流按人数加成）
    from app.routers.world_proxy import record_world_activity
    record_world_activity(world_id, current_user["user_id"])
    from app.services.world.world_service import get_chat_history
    limit = max(1, min(limit, 100))
    # 多取一条判断是否还有更早
    msgs = await get_chat_history(db, world_id, limit=limit + 1, before_id=before_id)
    has_more = len(msgs) > limit
    return {"messages": msgs[-limit:], "has_more": has_more}


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
    from app.services.world.world_turn import get_world_worker
    worker = get_world_worker(world_id)
    turn_id = worker.enqueue(current_user["user_id"], req.message)
    return {
        "turn_id": turn_id,
        "queued": worker.queue_size > 1,
        "position": max(0, worker.queue_size - 1),
    }


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
    # 正在处理 = 队列有消息，或最后一条消息不是 ai 回复（轮次未闭合）
    processing = queue_size > 0
    if not processing:
        last = (await db.execute(
            select(WorldChatMessage)
            .where(WorldChatMessage.world_id == world_id)
            .order_by(WorldChatMessage.id.desc())
            .limit(1)
        )).scalar_one_or_none()
        if last is not None and last.role != "ai":
            processing = True
    return {"processing": processing, "queue_size": queue_size}



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


@router.get("/{world_id}/export")
async def export_zip(
    world_id: int,
    current_user: dict = Depends(get_current_user),
):
    """一键打包下载（代码+数据）"""

    await _require_owner(db, world_id, current_user["user_id"])
    from fastapi.responses import Response
    from app.services.world.world_file_service import export_zip as fs_export
    data = fs_export(world_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=world_{world_id}.zip"},
    )
