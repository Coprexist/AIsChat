"""
世界入口路由代理 — 世界标识规范（设计文档 7.3）

  GET /world/{world_id}/files/*   静态资源（路由到世界文件目录）
  GET /world/{world_id}/preview   沉浸界面入口（注入 WORLD_ID）

世界编号由前端注入为变量（window.WORLD_ID），AI/人类代码只管写变量名。
"""
import asyncio
import json
import logging
import secrets
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/world", tags=["群视界入口"])


# ═══════════════════════════════════════════════════════════════
# 2.3 受控数据 API + 2.4 群聊写 API — 世界代码经代理访问世界数据/对话/群聊
#
#   读：
#     GET    /world/{id}/api/world      世界信息（不含敏感配置）
#     GET    /world/{id}/api/chat       对话历史（复用世界 AI 会话）
#     GET    /world/{id}/api/memories   记忆检索（向量 → 文本回退）
#     POST   /world/{id}/api/memories   存记忆
#     GET    /world/{id}/api/usage      LLM 用量与缓存命中率
#     GET    /world/{id}/api/groups     绑定群列表
#     GET    /world/{id}/api/group/messages   读群消息（仅绑定群）
#     GET    /world/{id}/api/group/members    群成员列表（仅绑定群）
#   写（身份=世界自身；作用域=仅本世界绑定群；独立写限流）：
#     POST   /world/{id}/api/group/messages   发群消息
#     POST   /world/{id}/api/group/roles      改成员角色（群主/管理员）
#     POST   /world/{id}/api/group/kick       移出成员（群主/管理员）
#
# 鉴权：每个世界一个 API token（懒生成存 worlds.config.api_token，update_world
# 是 merge 不会被覆盖）。沙箱启动时经 env 注入 WORLD_API_TOKEN / WORLD_API_BASE，
# 世界代码请求带 `Authorization: Bearer <token>` 或 `X-World-Token: <token>`。
# token 只对本世界数据有效——不暴露后端真实结构/JWT/密钥。
# 限流（10 秒窗口，worlds.config 可配，见 09 分区文档）：
#   读/总配额  = api_rate_limit（默认 120） + api_rate_limit_per_user（默认 60）× 活跃人数
#   写配额     = api_group_msg_limit（默认 20） + api_group_msg_limit_per_user（默认 10）× 活跃人数
# 活跃人数 = 最近 10 分钟内在该世界有操作（对话/打开设计页）的不同用户数。
# ═══════════════════════════════════════════════════════════════

RATE_LIMIT_WINDOW = 10.0        # 秒
RATE_LIMIT_MAX = 120            # 读/总配额基础值（10 秒）
RATE_LIMIT_PER_USER = 60        # 每人加成（10 秒）
GROUP_MSG_LIMIT = 20            # 写操作基础配额（10 秒）
GROUP_MSG_LIMIT_PER_USER = 10   # 写操作每人加成（10 秒）
ACTIVE_WINDOW = 600.0           # 活跃判定窗口（10 分钟）
_rate_buckets: dict[int, deque] = {}
# 世界活跃用户（world_id → {user_id: 最近活跃时刻}），供动态限流按人数加成
_ACTIVE_USERS: dict[int, dict[int, float]] = {}

# ── 世界状态实时推送（2.5：世界代码发布 → 页面 SSE 订阅，零轮询） ──
# 世界代码经受控 API POST /api/state 发布状态快照：后端存最新 + 广播给 SSE 订阅者
_state_latest: dict[int, dict] = {}
_state_subs: dict[int, set] = {}


def _publish_state(world_id: int, state: dict) -> None:
    """发布世界状态：更新最新快照 + 广播所有 SSE 订阅者（慢消费者只保留最新）"""
    _state_latest[world_id] = state
    for q in list(_state_subs.get(world_id, ())):
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            q.put_nowait(state)
        except asyncio.QueueFull:
            pass


def _cfg_int(cfg: dict, key: str, default: int, lo: int, hi: int) -> int:
    """worlds.config 配额读取（非法值回退默认，钳制在 [lo, hi]）"""
    try:
        v = int(cfg.get(key) or default)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(v, hi))


def _prune_active(world_id: int, now: float) -> None:
    users = _ACTIVE_USERS.get(world_id)
    if not users:
        return
    stale = [u for u, ts in users.items() if now - ts > ACTIVE_WINDOW]
    for u in stale:
        del users[u]


def record_world_activity(world_id: int, user_id: int | None) -> None:
    """世界活跃埋点：带身份的入口（世界 AI 对话/设计页）调用，供动态限流按人数加成"""
    if not user_id:
        return
    now = time.monotonic()
    _prune_active(world_id, now)
    _ACTIVE_USERS.setdefault(world_id, {})[user_id] = now


def _active_user_count(world_id: int) -> int:
    _prune_active(world_id, time.monotonic())
    return len(_ACTIVE_USERS.get(world_id, {}))


def _consume(world_id: int, quota: int, what: str) -> None:
    """内存滑动窗口限流（世界代码死循环打爆代理的最后防线）"""
    now = time.monotonic()
    dq = _rate_buckets.setdefault(world_id, deque())
    while dq and now - dq[0] > RATE_LIMIT_WINDOW:
        dq.popleft()
    if len(dq) >= quota:
        raise HTTPException(status_code=429, detail=f"请求过于频繁（{what}：{quota} 次/10 秒）")
    dq.append(now)


def _rate_limit(world) -> None:
    """读/总配额：基础 + 每人加成 × 活跃人数（worlds.config 可配）"""
    cfg = world.config or {}
    base = _cfg_int(cfg, "api_rate_limit", RATE_LIMIT_MAX, 10, 10000)
    per_user = _cfg_int(cfg, "api_rate_limit_per_user", RATE_LIMIT_PER_USER, 0, 1000)
    _consume(world.id, base + per_user * _active_user_count(world.id), "受控 API 限流")


def _rate_limit_write(world) -> None:
    """写操作（发群消息/管理）独立配额：基础 + 每人加成（worlds.config 可配）"""
    cfg = world.config or {}
    base = _cfg_int(cfg, "api_group_msg_limit", GROUP_MSG_LIMIT, 1, 1000)
    per_user = _cfg_int(cfg, "api_group_msg_limit_per_user", GROUP_MSG_LIMIT_PER_USER, 0, 100)
    _consume(world.id, base + per_user * _active_user_count(world.id), "群消息写限流")


async def ensure_world_api_token(db: AsyncSession, world) -> str:
    """懒生成世界 API token（存 worlds.config.api_token）。

    调用方负责 commit（沙箱端点进入前调一次，确保 env 注入时 token 已落库）。
    """
    cfg = dict(world.config or {})
    token = cfg.get("api_token")
    if not token or not isinstance(token, str) or len(token) < 16:
        token = secrets.token_urlsafe(32)
        cfg["api_token"] = token
        world.config = cfg
    return token


async def _authorize_world_api(db: AsyncSession, world_id: int, request: Request):
    """校验世界 API token（Bearer 或 X-World-Token），返回世界 ORM（未授权抛 401/404）"""
    from app.models.world import World

    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else request.headers.get("X-World-Token", "")
    if not token:
        raise HTTPException(status_code=401, detail="缺少世界 API token（沙箱环境变量 WORLD_API_TOKEN）")
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    expected = (world.config or {}).get("api_token")
    if not expected or not secrets.compare_digest(str(expected), token):
        raise HTTPException(status_code=401, detail="世界 API token 无效")
    _rate_limit(world)
    return world


@router.get("/{world_id}/api/world")
async def world_api_info(
    world_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：世界信息（不含 api_token 等敏感配置）"""
    world = await _authorize_world_api(db, world_id, request)
    from app.models.world import WorldBinding

    bindings = (await db.execute(
        select(WorldBinding).where(WorldBinding.world_id == world_id)
    )).scalars().all()
    cfg = world.config or {}
    return {
        "id": world.id,
        "name": world.name,
        "description": world.description,
        "status": world.status,
        "time_flow_rate": world.time_flow_rate,
        "world_time": world.world_time.isoformat() if world.world_time else None,
        "last_active_at": world.last_active_at.isoformat() if world.last_active_at else None,
        "bindings": [{"entity_type": b.entity_type, "entity_id": b.entity_id} for b in bindings],
        "creator_name": (world.creator_config or {}).get("name") or "群视界机器人",
        "quota": {k: cfg[k] for k in ("sandbox_timeout_seconds", "cpu_quota", "runtime_memory_mb", "sleep_memory_mb") if k in cfg},
    }


@router.get("/{world_id}/api/chat")
async def world_api_chat(
    world_id: int,
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
    before_id: int | None = Query(default=None, description="翻更早：传最旧消息 id"),
    db: AsyncSession = Depends(get_db),
):
    """受控 API：世界 AI 对话历史（与设计页同一份查询）"""
    await _authorize_world_api(db, world_id, request)
    from app.services.world.world_chat_service import get_chat_history
    return {"messages": await get_chat_history(db, world_id, limit=limit, before_id=before_id)}


@router.get("/{world_id}/api/memories")
async def world_api_recall_memory(
    world_id: int,
    request: Request,
    query: str = Query(..., description="检索关键词"),
    top_k: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """受控 API：记忆检索（复用世界 AI 的 recall_memory 同一份逻辑）"""
    world = await _authorize_world_api(db, world_id, request)
    from app.services.world.world_tools import _do_execute
    result = await _do_execute(db, world, "recall_memory", json.dumps({"query": query, "top_k": top_k}))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "记忆检索失败"))
    return {"memories": result.get("memories", [])}


@router.post("/{world_id}/api/memories")
async def world_api_store_memory(
    world_id: int,
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：存记忆（复用世界 AI 的 store_memory 同一份逻辑）"""
    world = await _authorize_world_api(db, world_id, request)
    title = str(body.get("title", "")).strip()
    content = str(body.get("content", "")).strip()
    if not title or not content:
        raise HTTPException(status_code=422, detail="title 和 content 不能为空")
    from app.services.world.world_tools import _do_execute
    result = await _do_execute(db, world, "store_memory", json.dumps({"title": title, "content": content}))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "记忆存储失败"))
    await db.commit()
    return {"ok": True, "title": title, "embedded": result.get("embedded", False)}


@router.post("/{world_id}/api/event")
async def world_api_event(
    world_id: int,
    body: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """页面 → 世界程序静默命令通道（产品 2026-08-13 定）。

    页面操作（移动/攻击/开宝箱等）直接触发世界程序 handle(event)，
    **不产生群消息、不进群聊**（解决页面操作刷屏群聊问题）。
    鉴权：主站登录用户（页面宿主注入的 user token）+ 群绑定/成员校验；
    事件结构：{type, payload, group_id?}，source=page 标记，
    服务端注入 user_id/user_name（不信任页面自报身份）。
    """
    from app.models.world import World, WorldBinding
    from sqlalchemy import text as _t

    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    _rate_limit_write(world)

    # 群作用域：缺省第一个绑定群；显式传的必须属于本世界绑定
    gid = await _check_bound_group(db, world, body.get("group_id"))
    # 成员校验：世界 owner 或群成员（human）
    uid = current_user["user_id"]
    is_owner = world.owner_id == uid
    if not is_owner:
        row = (await db.execute(_t(
            "SELECT 1 FROM group_members WHERE group_id=:g AND member_id=:u AND member_type='human' LIMIT 1"
        ), {"g": gid, "u": uid})).first()
        if row is None:
            raise HTTPException(status_code=403, detail="你不在该群成员中，无法向世界发命令")

    event_type = str(body.get("type") or "").strip()
    payload = dict(body.get("payload") or {})
    if not event_type:
        raise HTTPException(status_code=422, detail="type 必填（如 page_command）")
    # 服务端注入身份（不信任页面自报）
    payload.setdefault("user_id", uid)
    payload.setdefault("user_name", current_user.get("username") or f"#{uid}")

    event = {"type": event_type, "source": "page", "payload": payload, "group_id": gid}
    try:
        from app.services.world.group_type_service import get_group_type_for_group
        event["group_type"] = await get_group_type_for_group(db, world_id, gid)
    except Exception:
        pass

    # 常驻世界 → 投递常驻进程；否则临时触发（同步等结果，handle 返回可回页面）
    from app.services.world.world_resident import manager
    if manager.is_resident(world) and await manager.dispatch(world.id, event):
        return {"success": True, "queued": True, "event_type": event_type}
    from app.services.world.world_sandbox import run_world_trigger
    from app.routers.world_proxy import ensure_world_api_token
    await ensure_world_api_token(db, world)
    await db.commit()
    result = await run_world_trigger(world, event=event, background=False)
    if not result.get("success"):
        return {"success": False, "reason": result.get("reason", "世界程序未处理"),
                "stdout": (result.get("stdout") or "")[-200:]}
    return {"success": True, "result": result.get("result")}


@router.get("/{world_id}/api/usage")
async def world_api_usage(
    world_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：LLM 用量与缓存命中率（与设计页 /worlds/{id}/usage 同一口径）"""
    await _authorize_world_api(db, world_id, request)
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


@router.post("/{world_id}/api/state")
async def world_api_publish_state(
    world_id: int,
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：世界代码发布状态快照（NPC 对话/移动/事件 → 页面 SSE 实时收到）

    状态由世界代码全权定义（任意 JSON）；后端负责：内存最新快照 + 广播订阅者 + 落 state.json。
    """
    world = await _authorize_world_api(db, world_id, request)
    _rate_limit_write(world)
    if len(json.dumps(body, ensure_ascii=False)) > 100 * 1024:
        raise HTTPException(status_code=422, detail="状态过大（上限 100KB）")
    _publish_state(world_id, body)
    try:
        from app.services.world.world_file_service import write_file
        write_file(world_id, "state.json", json.dumps(body, ensure_ascii=False, indent=1))
    except Exception:
        pass  # 落盘失败不影响实时推送
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# 世界数据（world_data 表）— 世界代码经受控 API 读写结构化数据
# ═══════════════════════════════════════════════════════════════

@router.get("/{world_id}/api/data/{key}")
async def world_api_data_get(
    world_id: int,
    key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：读世界数据（world_data 表；不存在 value=null）"""
    await _authorize_world_api(db, world_id, request)
    from app.services.world.world_service import get_world_data
    row = await get_world_data(db, world_id, key)
    return {"key": key, "value": row["value"] if row else None}


@router.put("/{world_id}/api/data/{key}")
async def world_api_data_put(
    world_id: int,
    key: str,
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：写世界数据（upsert；key ≤200 字符）"""
    await _authorize_world_api(db, world_id, request)
    if len(key) > 200:
        raise HTTPException(status_code=400, detail="key 过长（≤200）")
    from app.services.world.world_service import set_world_data
    return await set_world_data(db, world_id, key, body.get("value"))


@router.delete("/{world_id}/api/data/{key}")
async def world_api_data_delete(
    world_id: int,
    key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：删世界数据"""
    await _authorize_world_api(db, world_id, request)
    from app.services.world.world_service import delete_world_data
    ok = await delete_world_data(db, world_id, key)
    if not ok:
        raise HTTPException(status_code=404, detail="数据不存在")
    return {"success": True}


@router.get("/{world_id}/events")
async def world_events(
    world_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """世界状态 SSE 订阅（页面 EventSource 用）：实时收到世界代码发布的状态

    - 公开端点（与静态资源同理）：只推世界自身发布的状态，不含敏感数据
    - 连接即发当前快照（刷新/新用户能拿到最新状态）；15s 心跳防代理超时
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    _state_subs.setdefault(world_id, set()).add(q)

    async def gen():
        try:
            latest = _state_latest.get(world_id)
            if latest is not None:
                yield f"data: {json.dumps(latest, ensure_ascii=False)}\n\n"
            while True:
                try:
                    state = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # 断连检测：客户端断开后及时结束连接（不占 worker，避免 reload 优雅退出死锁）
                    if await request.is_disconnected():
                        break
                    yield ": ping\n\n"  # 心跳
                    continue
                yield f"data: {json.dumps(state, ensure_ascii=False)}\n\n"
        finally:
            _state_subs.get(world_id, set()).discard(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 2.4 群聊写 API：身份 = 世界自身（与 AI 工具同身份，底层借世界主人权限并做群角色检查）；
#    作用域 = 仅本世界绑定群；限流 = 写操作独立配额 ──

async def _check_bound_group(db: AsyncSession, world, group_id: int | None) -> int:
    """群作用域校验：返回群 id（缺省取绑定第一个群；显式传的必须属于本世界绑定）"""
    from app.models.world import WorldBinding

    rows = (await db.execute(
        select(WorldBinding).where(
            WorldBinding.world_id == world.id,
            WorldBinding.entity_type == "group",
        ).order_by(WorldBinding.id)
    )).scalars().all()
    bound = [r.entity_id for r in rows]
    if not bound:
        raise HTTPException(status_code=403, detail="本世界未绑定任何群聊")
    if group_id is None:
        return bound[0]
    if group_id not in bound:
        raise HTTPException(status_code=403, detail=f"群 #{group_id} 不在本世界绑定范围（可操作：{bound}）")
    return group_id


def _tool_ok(result: dict, what: str) -> None:
    """工具结果统一错误提升（复用 world_tools 同一份实现）"""
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", what))


@router.get("/{world_id}/api/groups")
async def world_api_groups(
    world_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：绑定群列表（复用 get_bound_groups 同一份逻辑）"""
    world = await _authorize_world_api(db, world_id, request)
    from app.services.world.world_tools import _do_execute
    result = await _do_execute(db, world, "get_bound_groups", "{}")
    _tool_ok(result, "查绑定群失败")
    return {"groups": result.get("groups", [])}


@router.get("/{world_id}/api/group/messages")
async def world_api_group_messages(
    world_id: int,
    request: Request,
    group_id: int | None = Query(default=None, description="群 id（缺省 = 世界绑定的第一个群）"),
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """受控 API：读群消息（仅绑定群；复用 get_group_messages 同一份逻辑）"""
    world = await _authorize_world_api(db, world_id, request)
    gid = await _check_bound_group(db, world, group_id)
    from app.services.world.world_tools import _do_execute
    result = await _do_execute(db, world, "get_group_messages", json.dumps({"group_id": gid, "limit": limit}))
    _tool_ok(result, "读群消息失败")
    return {"group_id": gid, "messages": result.get("messages", [])}


@router.get("/{world_id}/api/group/members")
async def world_api_group_members(
    world_id: int,
    request: Request,
    group_id: int | None = Query(default=None, description="群 id（缺省 = 世界绑定的第一个群）"),
    db: AsyncSession = Depends(get_db),
):
    """受控 API：群成员列表（仅绑定群；复用 list_group_members 同一份逻辑）"""
    world = await _authorize_world_api(db, world_id, request)
    gid = await _check_bound_group(db, world, group_id)
    from app.services.world.world_tools import _do_execute
    result = await _do_execute(db, world, "list_group_members", json.dumps({"group_id": gid}))
    _tool_ok(result, "查成员失败")
    return {"group_id": gid, "members": result.get("members", [])}


@router.post("/{world_id}/api/group/messages")
async def world_api_group_send(
    world_id: int,
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：发群消息（世界自身身份；仅绑定群；写限流）"""
    world = await _authorize_world_api(db, world_id, request)
    try:
        gid = await _check_bound_group(db, world, body.get("group_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="group_id 不合法")
    _rate_limit_write(world)
    content = str(body.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=422, detail="消息内容不能为空")
    if len(content) > 2000:
        raise HTTPException(status_code=422, detail="消息内容过长（上限 2000 字）")
    from app.services.world.world_tools import _do_execute
    result = await _do_execute(db, world, "send_group_message", json.dumps({"group_id": gid, "content": content}))
    _tool_ok(result, "发送失败")
    await db.commit()
    return {"ok": True, "group_id": gid, "message_id": result.get("message_id")}


@router.post("/{world_id}/api/group/roles")
async def world_api_group_role(
    world_id: int,
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：改成员角色（群主/管理员；仅绑定群；写限流）"""
    world = await _authorize_world_api(db, world_id, request)
    try:
        gid = await _check_bound_group(db, world, body.get("group_id"))
        mid = int(body.get("member_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="group_id/member_id 不合法")
    mtype = str(body.get("member_type") or "")
    role = str(body.get("role") or "")
    if mtype not in ("human", "ai") or not mid or role not in ("owner", "admin", "member"):
        raise HTTPException(status_code=422, detail="参数不合法：member_type(human|ai) / member_id / role(owner|admin|member)")
    _rate_limit_write(world)
    from app.services.world.world_tools import _do_execute
    result = await _do_execute(db, world, "set_group_member_role",
                               json.dumps({"group_id": gid, "member_type": mtype, "member_id": mid, "role": role}))
    _tool_ok(result, "改角色失败")
    await db.commit()
    return {"ok": True, "group_id": gid, "member_id": mid, "role": role}


@router.post("/{world_id}/api/group/kick")
async def world_api_group_kick(
    world_id: int,
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """受控 API：移出成员（群主/管理员；仅绑定群；写限流）"""
    world = await _authorize_world_api(db, world_id, request)
    try:
        gid = await _check_bound_group(db, world, body.get("group_id"))
        mid = int(body.get("member_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="group_id/member_id 不合法")
    mtype = str(body.get("member_type") or "")
    if mtype not in ("human", "ai") or not mid:
        raise HTTPException(status_code=422, detail="参数不合法：member_type(human|ai) / member_id")
    _rate_limit_write(world)
    from app.services.world.world_tools import _do_execute
    result = await _do_execute(db, world, "kick_group_member",
                               json.dumps({"group_id": gid, "member_type": mtype, "member_id": mid}))
    _tool_ok(result, "移出失败")
    await db.commit()
    return {"ok": True, "group_id": gid, "member_id": mid}

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def _resolve_world_file(world_id: int, rel_path: str):
    """解析世界文件（防越界），返回 (Path, mime) 或抛 404"""
    from pathlib import Path
    from app.services.world.world_file_service import WORLDS_ROOT

    base = (WORLDS_ROOT / str(world_id)).resolve()
    rel_path = (rel_path or "").strip().lstrip("/")
    if not rel_path or ".." in rel_path.split("/"):
        raise HTTPException(status_code=404, detail="文件不存在")
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    mime = MIME_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return target, mime


async def _get_creator_name(db: AsyncSession, world_id: int) -> str:
    """群视界 AI 名字（worlds.creator_config.name，默认群视界机器人）"""
    from app.models.world import World
    world = await db.get(World, world_id)
    if world is None:
        return "群视界机器人"
    cfg = world.creator_config or {}
    return cfg.get("name") or "群视界机器人"


def _inject_world_vars(
    html: str, world_id: int, creator_name: str, group_id: int | None, world_name: str = "",
    entry: dict | None = None, api_prefix: str = "/api", ui_prefix: str = "",
) -> str:
    """向世界 HTML 注入环境变量（世界代码零硬编码，打包/换实例即插即用）。

    变量（world code 直接读 window.*）：
      WORLD_ID     世界编号
      WORLD_NAME   世界名
      WORLD_AI_ID  群视界 AI 身份（world-{id}）
      WORLD_AI_NAME 群视界 AI 名字
      GROUP_ID     入口群聊编号（无 = null）
      USER_ID      当前用户编号（无登录态 = null，客户端可补）
      WORLD_ENTRY  入口分流：{kind: 'group'|'dm'|'main', group_id, group_type_slug}
                   世界代码据此渲染不同界面（群类型→对应场景、私聊→对话地点、直进→主页）
      WORLD_API    API 前缀（独立部署 /api；宿主嵌入时由宿主代理注入 /aischat-api）
      WORLD_UI     主应用前端前缀（独立部署空串；宿主嵌入时 /aischat-ui）
    """
    script = (
        "<script>\n"
        f"window.WORLD_ID = {world_id};\n"
        f"window.WORLD_NAME = {json.dumps(world_name, ensure_ascii=False)};\n"
        f"window.WORLD_AI_ID = 'world-{world_id}';\n"
        f"window.WORLD_AI_NAME = {json.dumps(creator_name, ensure_ascii=False)};\n"
        f"window.GROUP_ID = {group_id if group_id is not None else 'null'};\n"
        f"window.WORLD_ENTRY = {json.dumps(entry or {'kind': 'main', 'group_id': None, 'group_type_slug': None}, ensure_ascii=False)};\n"
        f"window.WORLD_API = {json.dumps(api_prefix, ensure_ascii=False)};\n"
        f"window.WORLD_UI = {json.dumps(ui_prefix, ensure_ascii=False)};\n"
        "window.USER_ID = null; // 由宿主环境注入\n"
        "</script>\n"
        "<script>\n"
        "// 平台 UI 桥：世界代码可控制宿主侧边栏/悬浮图标（详见接口文档）\n"
        "window.WorldUI = {\n"
        "  toggleSidebar: function(){ _worldUi('toggle_sidebar') },\n"
        "  showSidebar: function(){ _worldUi('show_sidebar') },\n"
        "  hideSidebar: function(){ _worldUi('hide_sidebar') },\n"
        "  hideFloatingIcon: function(){ _worldUi('hide_floating_icon') },\n"
        "  showFloatingIcon: function(){ _worldUi('show_floating_icon') }\n"
        "};\n"
        "function _worldUi(action){ try{ window.parent.postMessage({type:'world_ui', action:action}, '*') }catch(e){} }\n"
        "</script>\n"
    )
    if "</head>" in html:
        return html.replace("</head>", script + "</head>", 1)
    if "<head" in html:
        # 有 <head> 但无闭合标签（不标准但常见），插在 head 标签后
        import re
        m = re.search(r"<head[^>]*>", html)
        return html[:m.end()] + script + html[m.end():]
    return script + html


@router.get("/{world_id}/files/{path:path}")
async def serve_world_file(
    world_id: int,
    path: str,
    request: Request,
    group_id: int | None = Query(default=None, description="入口群聊编号"),
    entry_from: str | None = Query(default=None, alias="from", description="入口类型：dm=私聊 / main=直进（群入口由 group_id 推断）"),
    db: AsyncSession = Depends(get_db),
):
    """静态资源路由：/world/{WORLD_ID}/files/<相对路径>（HTML 自动注入世界变量）"""
    target, mime = _resolve_world_file(world_id, path)
    if mime.startswith("text/html"):
        creator_name = await _get_creator_name(db, world_id)
        world_name = ""
        try:
            from app.models.world import World as _World
            _w = await db.get(_World, world_id)
            if _w is not None:
                world_name = _w.name or ""
        except Exception:
            pass
        # 变量注入：URL 没带 group_id 时，自动补世界绑定的第一个群（保持「编号一律变量」哲学）
        if group_id is None:
            try:
                from app.models.world import WorldBinding
                row = (await db.execute(
                    select(WorldBinding).where(
                        WorldBinding.world_id == world_id,
                        WorldBinding.entity_type == "group",
                    ).order_by(WorldBinding.id).limit(1)
                )).scalar_one_or_none()
                if row is not None:
                    group_id = row.entity_id
            except Exception:
                pass
        # 入口分流：WORLD_ENTRY（群入口查绑定类型；dm/main 由 from 参数指定）
        entry: dict = {"kind": "main", "group_id": None, "group_type_slug": None}
        if group_id is not None:
            entry["kind"] = "group"
            entry["group_id"] = group_id
            try:
                from app.models.world import WorldBinding as _WB
                _b = (await db.execute(select(_WB).where(
                    _WB.world_id == world_id, _WB.entity_type == "group", _WB.entity_id == group_id,
                ))).scalar_one_or_none()
                entry["group_type_slug"] = _b.group_type_slug if _b else None
            except Exception:
                pass
        elif entry_from in ("dm", "main"):
            entry["kind"] = entry_from
        html = target.read_text(encoding="utf-8", errors="replace")
        # 宿主嵌入（DSH）时由宿主代理注入 x-aischat-api-prefix / x-aischat-ui-prefix，
        # 世界代码据此拼 API/前端地址；独立部署无这些头，用默认值。
        api_prefix = request.headers.get("x-aischat-api-prefix", "/api")
        ui_prefix = request.headers.get("x-aischat-ui-prefix", "")
        return HTMLResponse(_inject_world_vars(html, world_id, creator_name, group_id, world_name, entry=entry, api_prefix=api_prefix, ui_prefix=ui_prefix))
    # 世界代码频繁变化：ETag 条件缓存——更新后自动拿新版（免强刷），
    # 未更新时浏览器 304 走缓存（不重复下载）（2026-08-05 产品）
    etag = f'"{target.stat().st_mtime_ns:x}-{target.stat().st_size:x}"'
    headers = {"ETag": etag}
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304)
    return FileResponse(target, media_type=mime, headers=headers)


@router.get("/{world_id}/preview")
async def world_preview(
    world_id: int,
    request: Request,
    group_id: int | None = Query(default=None, description="入口群聊编号"),
    db: AsyncSession = Depends(get_db),
):
    """沉浸界面入口：重定向到规范挂载点 /world/{id}/files/index.html

    页面内部一律用相对路径（打包即插即用）；/preview 与 /files/ 层级不同，
    相对路径在 /preview 下会解析错（style.css → /world/{id}/style.css 404），
    所以统一重定向到 files 挂载点，由 serve_world_file 注入世界变量。
    """
    try:
        _resolve_world_file(world_id, "index.html")
    except HTTPException:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;display:flex;align-items:center;"
            "justify-content:center;height:100vh;color:#888'>"
            "<div>这个世界还没有 index.html，让群视界机器人创建一个吧</div></body></html>"
        )
    # 打开过 = 活跃信号（调度器据此唤醒/延迟休眠）
    try:
        from app.models.world import World
        world = await db.get(World, world_id)
        if world is not None:
            world.last_active_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
    except Exception:
        pass
    url = f"/world/{world_id}/files/index.html"
    qs = []
    if group_id is not None:
        qs.append(f"group_id={group_id}")
    entry_from: str | None = None
    try:
        entry_from = request.query_params.get("from")
    except Exception:
        pass
    if entry_from in ("dm", "main"):
        qs.append(f"from={entry_from}")
    if qs:
        url += "?" + "&".join(qs)
    return RedirectResponse(url, status_code=307)
