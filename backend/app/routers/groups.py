"""
群聊与消息路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.group import (
    GroupCreateRequest, GroupInviteRequest, GroupResponse,
    GroupUpdateRequest, AnnouncementRequest, RoleChangeRequest,
    SetDndRequest, UnreadSummaryItem, UnreadSummaryResponse, UnreadResponse,
    FederationShareRequest, GroupFederationStatus,
)
from app.schemas.message import MessageResponse
from app.services.group_service import (
    create_group,
    get_group,
    list_user_groups,
    add_member,
    get_group_members,
    get_recent_messages,
    message_to_dict,
    set_group_dnd,
    cancel_group_dnd,
    is_member_in_dnd,
    update_group_settings,
    set_announcement,
    delete_announcement,
    change_member_role,
    remove_member,
    leave_group,
    disband_group,
    get_unread_info,
    update_last_read,
)
from app.utils.auth import get_current_user

router = APIRouter(tags=["群聊"])


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_new_group(
    req: GroupCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建群聊"""
    try:
        group = await create_group(
            db,
            name=req.name,
            owner_type="human",
            owner_id=current_user["user_id"],
            initial_members=req.initial_members,
        )
        return {
            "id": group.id,
            "name": group.name,
            "owner_type": group.owner_type,
            "owner_id": group.owner_id,
            "is_vector_accelerated": group.is_vector_accelerated,
            "created_at": str(group.created_at) if group.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/groups", response_model=list[GroupResponse])
async def list_my_groups(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取我的群聊列表"""
    groups = await list_user_groups(db, current_user["user_id"])
    return groups


@router.get("/groups/{group_id}", response_model=GroupResponse)
async def get_group_detail(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取群聊详情"""
    group = await get_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="群聊不存在")

    # 统计成员数量 & 在线人数（AI 成员中 state=active 的）
    from app.models.group import GroupMember
    from app.models.agent import Agent as AgentModel
    member_result = await db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id)
    )
    members = member_result.scalars().all()
    member_count = len(members)
    online_count = 0
    ai_member_ids = [m.member_id for m in members if m.member_type == "ai"]
    if ai_member_ids:
        ai_result = await db.execute(
            select(AgentModel).where(
                AgentModel.user_id.in_(ai_member_ids),  # v2.0.0: member_id 统一为 user_id
                AgentModel.state == "active",
            )
        )
        online_count = len(ai_result.scalars().all())

    return {
        "id": group.id,
        "name": group.name,
        "owner_type": group.owner_type,
        "owner_id": group.owner_id,
        "is_vector_accelerated": group.is_vector_accelerated,
        "created_at": str(group.created_at) if group.created_at else None,
        "member_count": member_count,
        "online_count": online_count,
    }


@router.post("/groups/{group_id}/invite")
async def invite_member(
    group_id: int,
    req: GroupInviteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """邀请成员加入群聊"""
    try:
        member = await add_member(
            db,
            group_id=group_id,
            member_type=req.member_type,
            member_id=req.member_id,
        )
        return {"message": "邀请成功", "group_id": group_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/groups/{group_id}/members")
async def list_members(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取群成员列表（含名称和在线状态，用于 @提及自动补全）"""
    from app.models.user import User
    from app.models.agent import Agent as AgentModel
    members = await get_group_members(db, group_id)
    result = []
    for m in members:
        name = None
        state = None
        if m.member_type == "human":
            u = await db.get(User, m.member_id)
            if u:
                name = u.username
        elif m.member_type == "ai":
            a_res = await db.execute(
                select(AgentModel).where(AgentModel.user_id == m.member_id)
            )
            a = a_res.scalar_one_or_none()
            if a:
                name = a.name
                state = a.state
        result.append({
            "type": m.member_type,
            "id": m.member_id,
            "name": name or f"{m.member_type}:{m.member_id}",
            "state": state,
            "role": m.role,
            "dnd_until": str(m.dnd_until) if m.dnd_until else None,
        })
    return result


@router.get("/groups/{group_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    group_id: int,
    limit: int = 20,
    before_id: int | None = Query(None),
    after_id: int | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取群聊消息历史（游标分页）"""
    from app.models.user import User
    from app.models.agent import Agent

    messages = await get_recent_messages(db, group_id, limit, before_id=before_id, after_id=after_id)

    # 批量解析发送者名称 + 头像
    human_ids = {m.sender_id for m in messages if m.sender_type == "human"}
    ai_ids = {m.sender_id for m in messages if m.sender_type == "ai"}

    name_map: dict[tuple, str] = {}
    avatar_map: dict[tuple, str | None] = {}
    if human_ids:
        result = await db.execute(select(User).where(User.id.in_(human_ids)))
        for u in result.scalars().all():
            name_map[("human", u.id)] = u.username
            avatar_map[("human", u.id)] = u.avatar_url
    if ai_ids:
        result = await db.execute(select(Agent).where(Agent.id.in_(ai_ids)))
        for a in result.scalars().all():
            name_map[("ai", a.id)] = a.name
            avatar_map[("ai", a.id)] = a.avatar_url

    # messages 已由 service 层按时间升序排列
    return [
        message_to_dict(m, sender_name=name_map.get((m.sender_type, m.sender_id)), sender_avatar_url=avatar_map.get((m.sender_type, m.sender_id)))
        for m in messages
    ]


@router.post("/groups/{group_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_group_message(
    group_id: int,
    body: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发送群聊消息（含附件）"""
    from app.services.group_service import create_message as create_group_msg
    from app.models.user import User as UserModel
    from app.models.agent import Agent as AgentModel

    content = body.get("content", "")
    attachments = body.get("attachments")
    reply_to = body.get("reply_to")

    if not content.strip() and not attachments:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息内容或附件不能都为空")

    try:
        message = await create_group_msg(
            db, group_id=group_id, sender_type="human",
            sender_id=current_user["user_id"], content=content,
            reply_to=reply_to, attachments=attachments,
        )
        await db.flush()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 取发送者头像
    sender_avatar = None
    u_result = await db.execute(select(UserModel).where(UserModel.id == current_user["user_id"]))
    u = u_result.scalar_one_or_none()
    if u:
        sender_avatar = u.avatar_url

    msg_data = message_to_dict(message, sender_name=current_user["username"], sender_avatar_url=sender_avatar)

    # WebSocket 广播
    try:
        from app.routers.ws import manager
        await manager.broadcast_to_group(group_id, {"type": "message", "data": msg_data})
    except Exception:
        pass

    # 触发 AI 回复
    try:
        from app.services.ai_response_worker import message_queue
        import asyncio
        message_queue.put_nowait({
            "conversation_type": "group",
            "group_id": group_id,
            "message_id": message.id,
            "content": content,
            "sender_type": "human",
            "sender_id": current_user["user_id"],
            "chain_depth": 0,
        })
    except asyncio.QueueFull:
        pass

    return msg_data


@router.post("/groups/{group_id}/dnd")
async def set_dnd(
    group_id: int,
    req: SetDndRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    为当前用户（或其所拥有的 AI）在指定群聊设置免打扰。
    请求中的 group_id 会覆盖 body 中的 group_id。
    """
    try:
        actual_group_id = group_id
        # ⚠️ 必须显式传 member_type="human"，因为 set_group_dnd 默认是 "ai"
        #（向后兼容 AI worker/tool_registry）。如果漏传，human 用户查不到记录会报错。
        member = await set_group_dnd(
            db,
            agent_id=current_user["user_id"],
            group_id=actual_group_id,
            duration_minutes=req.duration_minutes,
            member_type="human",
        )
        return {
            "message": "免打扰已设置",
            "group_id": actual_group_id,
            "dnd_until": str(member.dnd_until) if member.dnd_until else "永久",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/groups/{group_id}/dnd/cancel")
async def cancel_dnd(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消指定群聊的免打扰"""
    try:
        await cancel_group_dnd(db, current_user["user_id"], group_id, member_type="human")
        return {"message": "免打扰已取消", "group_id": group_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/groups/{group_id}/dnd/status")
async def check_dnd(
    group_id: int,
    agent_id: int = Query(..., description="AI ID"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """检查指定 AI 在群聊中是否处于免打扰状态"""
    in_dnd = await is_member_in_dnd(db, agent_id, group_id)
    return {"agent_id": agent_id, "group_id": group_id, "in_dnd": in_dnd}


# ============================================================
# Phase 4: 群聊治理端点
# ============================================================


@router.patch("/groups/{group_id}")
async def update_group(
    group_id: int,
    req: GroupUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新群聊设置（名称、公告、发言限制等）。仅群主/管理员可操作。"""
    try:
        updates = req.model_dump(exclude_none=True)

        group = await update_group_settings(
            db, group_id, current_user["user_id"], updates,
        )
        return {
            "id": group.id,
            "name": group.name,
            "owner_type": group.owner_type,
            "owner_id": group.owner_id,
            "is_vector_accelerated": group.is_vector_accelerated,
            "announcement": group.announcement,
            "speak_limit_per_minute": group.speak_limit_per_minute or 0,
            "speak_limit_window_seconds": group.speak_limit_window_seconds or 120,
            "created_at": str(group.created_at) if group.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/groups/{group_id}/announcement")
async def create_announcement(
    group_id: int,
    req: AnnouncementRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """设置群公告。仅群主/管理员可操作。"""
    try:
        content = await set_announcement(
            db, group_id, req.content, current_user["user_id"],
        )
        # 广播公告到群聊（作为系统消息）
        from app.routers.ws import manager
        await manager.broadcast_to_group(
            group_id,
            {
                "type": "announcement",
                "data": {
                    "group_id": group_id,
                    "content": content[:200],
                    "operator": current_user["username"],
                },
            },
        )
        return {"message": "公告已更新", "content": content}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/groups/{group_id}/announcement")
async def remove_announcement(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除群公告。仅群主/管理员可操作。"""
    try:
        await delete_announcement(db, group_id, current_user["user_id"])
        return {"message": "公告已删除"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/groups/{group_id}/members/{member_type}/{member_id}/role")
async def update_member_role(
    group_id: int,
    member_type: str,
    member_id: int,
    req: RoleChangeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改成员角色（提拔/降级）。仅群主可操作。"""
    try:
        member = await change_member_role(
            db, group_id, current_user["user_id"],
            member_type, member_id, req.role,
        )
        return {
            "message": f"角色已更新为 {req.role}",
            "member_type": member.member_type,
            "member_id": member.member_id,
            "role": member.role,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/groups/{group_id}/members/{member_type}/{member_id}")
async def kick_member(
    group_id: int,
    member_type: str,
    member_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """将成员踢出群聊。仅群主/管理员可操作。"""
    try:
        await remove_member(
            db, group_id, current_user["user_id"],
            member_type, member_id,
        )
        return {"message": "成员已移出群聊"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/groups/{group_id}/leave")
async def leave(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """退出群聊。群主需先转让。"""
    try:
        await leave_group(db, group_id, "human", current_user["user_id"])
        return {"message": "已退出群聊"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解散群聊（仅群主可操作）"""
    try:
        await disband_group(db, group_id, current_user["user_id"])
        return {"message": "群聊已解散", "group_id": group_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/groups/{group_id}/unread")
async def unread_info(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户在该群的未读信息。"""
    return await get_unread_info(db, group_id, current_user["user_id"])


@router.post("/groups/{group_id}/read")
async def mark_read(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记当前用户已读该群消息（进入群聊时调用）。"""
    updated = await update_last_read(db, group_id, "human", current_user["user_id"])
    return {"ok": True, "updated": updated}
    return {"message": "已标记为已读"}


# ---------- 联邦共享控制（v1.0.0: 群主/AI制作者按群控制） ----------

@router.get("/groups/{group_id}/federation/peers")
async def get_federation_peers(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取群联邦共享状态：列出所有对等端及其共享状态。
    需要群主/AI制作者权限。
    """
    from app.services.federation_service import get_group_federation_peers
    result = await get_group_federation_peers(db, group_id, current_user["user_id"])
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result["message"])
    return result


@router.post("/groups/{group_id}/federation/share")
async def share_group_federation(
    group_id: int,
    req: FederationShareRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    将群共享到指定对等端。
    需要群主/AI制作者权限。
    """
    from app.services.federation_service import share_group_to_peers
    result = await share_group_to_peers(
        db, group_id, req.peer_ids, current_user["user_id"],
    )
    if result.get("error"):
        msg = result["message"]
        if "无权限" in msg:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return result


@router.post("/groups/{group_id}/federation/unshare")
async def unshare_group_federation(
    group_id: int,
    req: FederationShareRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    取消群对指定对等端的联邦共享。
    需要群主/AI制作者权限。
    """
    from app.services.federation_service import unshare_group_from_peers
    result = await unshare_group_from_peers(
        db, group_id, req.peer_ids, current_user["user_id"],
    )
    if result.get("error"):
        msg = result["message"]
        if "无权限" in msg:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return result


# ---------- 聊天记录导出 ----------

@router.get("/groups/{group_id}/export")
async def export_chat(
    group_id: int,
    fmt: str = Query("json", pattern="^(json|txt|html)$"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出群聊记录（json / txt / html）"""
    from app.services.export_service import export_chat_history

    # 校验群成员身份
    group = await get_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="群聊不存在")

    try:
        content, media_type, filename = await export_chat_history(
            db, group_id, fmt, date_from, date_to
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
