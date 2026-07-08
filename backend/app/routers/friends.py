"""
好友系统路由
搜索、好友申请、好友列表管理
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.schemas.friendship import (
    FriendRequestCreate, FriendRequestResponse,
    FriendResponse, SearchResponse, SearchResult,
)
from app.services.friend_service import (
    send_friend_request, accept_friend_request, reject_friend_request,
    remove_friend, list_friends, list_friend_requests, search_entities,
)
from app.utils.auth import get_current_user
from app.routers.ws import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["好友"])


async def _notify_friend_request(db: AsyncSession, event_type: str, data: dict, target_user_id: int):
    """通过 WebSocket 向目标用户推送好友相关通知"""
    try:
        await manager.send_to_user(target_user_id, {
            "type": "friend_notification",
            "data": {
                "event": event_type,
                **data,
            },
        })
    except Exception as e:
        logger.warning(f"推送好友通知给用户 {target_user_id} 失败: {e}")


async def _resolve_target_user_id(db: AsyncSession, target_type: str, target_id: int) -> int | None:
    """target_id 统一为 users.id（human 和 AI 都走统一 ID 空间），直接返回"""
    return target_id


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """搜索用户和 AI（支持按用户名/AI名搜索）"""
    results = await search_entities(db, q, current_user["user_id"])
    return {"results": results, "query": q}


@router.get("/friends", response_model=list[FriendResponse])
async def list_my_friends(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取我的好友列表"""
    friends = await list_friends(db, current_user["user_id"], limit=limit, offset=offset)
    # 注入在线状态：人类好友通过 WebSocket 连接判断，AI 好友保留 agent.state
    from app.routers.ws import manager
    online_ids = manager.get_online_user_ids()
    for f in friends:
        friend_uid = f.get("friend_user_id")
        if friend_uid and friend_uid in online_ids:
            # 在线：人类好友显示 online，AI 好友保留原有 state（active/dnd/offline）
            if f["friend_type"] == "human":
                f["state"] = "online"
            # AI 好友的 state 已经在 list_friends 中从 agent 表获取，保持不变
            # 但如果 AI 不在线（无 WebSocket 连接），且 agent.state 为 active，改为 offline
            elif f["friend_type"] == "ai" and f["state"] == "active" and friend_uid not in online_ids:
                pass  # AI 的 state 是其主动设置的状态，不根据连接状态覆盖
    return friends


@router.post("/friends/{friendship_id}/toggle-priority")
async def toggle_friend_priority(
    friendship_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """切换特别关心状态"""
    from app.models.friendship import Friendship
    result = await db.execute(
        select(Friendship).where(
            Friendship.id == friendship_id,
            Friendship.user_id == current_user["user_id"],
        )
    )
    friendship = result.scalar_one_or_none()
    if friendship is None:
        raise HTTPException(status_code=404, detail="好友关系不存在")
    friendship.is_priority = not friendship.is_priority
    await db.commit()
    return {"is_priority": friendship.is_priority}


@router.post("/friends/requests", status_code=status.HTTP_201_CREATED)
async def create_friend_request(
    req: FriendRequestCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发送好友申请"""
    try:
        result = await send_friend_request(
            db,
            requester_id=current_user["user_id"],
            target_type=req.target_type,
            target_id=req.target_id,
            message=req.message,
        )
        # WebSocket 通知目标用户
        target_uid = await _resolve_target_user_id(db, req.target_type, req.target_id)
        if target_uid:
            await _notify_friend_request(db, "request_received", {
                "request_id": result.get("request_id"),
                "requester_id": current_user["user_id"],
                "requester_name": current_user.get("username", ""),
                "target_type": req.target_type,
                "target_id": req.target_id,
                "message": req.message,
                "status": result.get("status", "pending"),
                "auto_respond": result.get("auto_respond", False),
            }, target_uid)

        # 双向自动接受：注入双方附言到 DM
        if result.get("auto") and target_uid:
            greeting = "你们互相发送了好友申请，已自动成为好友"
            if req.message:
                greeting += f"\n{current_user.get('username', '对方')}：{req.message}"
            # 获取对方的附言（从反向申请中）
            if result.get("reverse_message"):
                greeting += f"\n{result.get('reverse_target_name', '对方')}：{result['reverse_message']}"
            await _inject_friend_greeting(
                db, current_user["user_id"], target_uid,
                greeting,
            )

        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/friends/requests", response_model=list[FriendRequestResponse])
async def list_requests(
    status_filter: str = Query("pending", description="pending | accepted | rejected"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取我的好友申请（收到 + 发出的）"""
    return await list_friend_requests(db, current_user["user_id"], status=status_filter)


@router.post("/friends/requests/{request_id}/accept")
async def accept_request(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """接受好友申请"""
    try:
        # 先获取请求详情（用于后续 DM 附言注入）
        f_req = await _get_friend_request(db, request_id)
        req_message = f_req.message if f_req else None
        req_created_at = f_req.created_at if f_req else None
        req_requester_id = f_req.requester_id if f_req else None
        req_target_type = f_req.target_type if f_req else None
        req_target_id = f_req.target_id if f_req else None

        result = await accept_friend_request(db, request_id, current_user["user_id"])

        # 通知发起者：申请已被接受
        if req_requester_id:
            await _notify_friend_request(db, "request_accepted", {
                "request_id": request_id,
                "accepter_name": current_user.get("username", ""),
            }, req_requester_id)

        # 将附言注入 DM 对话（使用申请发起时间戳）
        if req_requester_id and req_target_type:
            accepter_uid = current_user["user_id"]
            requester_uid = req_requester_id if req_target_type == "human" else req_requester_id
            # requester_uid 始终是 users.id
            greeting = "好友申请已通过"
            if req_message:
                greeting += f"\n附言：{req_message}"
            await _inject_friend_greeting(
                db, accepter_uid, requester_uid,
                greeting, created_at=req_created_at,
            )

        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/friends/requests/{request_id}/reject")
async def reject_request(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """拒绝好友申请"""
    try:
        result = await reject_friend_request(db, request_id, current_user["user_id"])
        # 通知发起者：申请已被拒绝
        req = await _get_friend_request(db, request_id)
        if req:
            await _notify_friend_request(db, "request_rejected", {
                "request_id": request_id,
                "rejecter_name": current_user.get("username", ""),
            }, req.requester_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/friends/{friend_type}/{friend_id}")
async def delete_friend(
    friend_type: str,
    friend_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除好友"""
    if friend_type not in ("human", "ai"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的好友类型")
    try:
        return await remove_friend(db, current_user["user_id"], friend_type, friend_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def _get_friend_request(db: AsyncSession, request_id: int):
    """获取好友申请（用于获取 requester_id 发送通知）"""
    from app.models.friendship import FriendshipRequest
    result = await db.execute(
        select(FriendshipRequest).where(FriendshipRequest.id == request_id)
    )
    return result.scalar_one_or_none()


async def _inject_friend_greeting(
    db: AsyncSession,
    from_user_id: int,
    to_user_id: int,
    greeting: str,
    created_at=None,
):
    """好友通过后，将附言注入 DM 对话开头（使用申请时间戳）"""
    from app.services.dm_service import (
        get_or_create_dm_session, send_dm_message,
    )
    try:
        dm = await get_or_create_dm_session(db, from_user_id, to_user_id)
        await send_dm_message(
            db, dm["session_id"],
            sender_id=from_user_id,
            content=f"🤝 {greeting}",
            created_at=created_at,
        )
    except Exception as e:
        logger.warning(f"注入好友附言到 DM 失败: {e}")


# ⚠️ 旧版 POST /dm/{friend_type}/{friend_id} 已移除（v0.2.0 统一 ID 后不再使用）。
# 移除原因：该路由与 dm.py 的 POST /dm/{session_id}/dnd 冲突——
#   FastAPI 将 "dnd" 当作 friend_id 的 int 参数解析，导致 422 错误。
# 私信请使用 POST /dm/{target_user_id}（见 dm.py）。
# 新增 /dm/ 子路由时注意：friends.router 先于 dm.router 注册，任何模糊匹配都会优先命中 friends 的路由。
