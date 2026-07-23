"""
ChatApi REST 路由 — 聊天服务的统一 HTTP 接口

人类和 AI 通过同一套接口操作聊天世界。
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import chat_api
from app.database import get_db
from app.schemas.group import (
    SetDndRequest,
    GroupResponse,
    GroupMemberResponse,
)
from app.schemas.message import MessageResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/message")
async def create_message(
    sender_type: str,
    sender_id: int,
    content: str,
    group_id: Optional[int] = None,
    dm_session_id: Optional[str] = None,
    reply_to: Optional[int] = None,
    attachments: Optional[list[str]] = None,
    db: AsyncSession = Depends(get_db),
):
    """创建消息"""
    try:
        message = await chat_api.create_message(
            db,
            sender_type=sender_type,
            sender_id=sender_id,
            group_id=group_id,
            dm_session_id=dm_session_id,
            content=content,
            reply_to=reply_to,
            attachments=attachments,
        )
        return message
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages")
async def list_messages(
    group_id: Optional[int] = None,
    dm_session_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """获取消息列表"""
    try:
        messages = await chat_api.list_messages(
            db,
            group_id=group_id,
            dm_session_id=dm_session_id,
            limit=limit,
            offset=offset,
        )
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group/dnd")
async def set_group_dnd(
    request: SetDndRequest,
    db: AsyncSession = Depends(get_db),
):
    """设置群 DND"""
    try:
        until = None
        if request.duration_minutes is not None and request.duration_minutes > 0:
            until = datetime.utcnow() + timedelta(minutes=request.duration_minutes)
        
        result = await chat_api.set_member_dnd(
            db,
            member_id=0,
            group_id=request.group_id,
            until=until,
            member_type="human",
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/{group_id}")
async def get_group_info(
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取群信息"""
    try:
        group = await chat_api.get_group(db, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        return group
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/{group_id}/members")
async def get_group_members(
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取群成员列表"""
    try:
        members = await chat_api.get_group_members(db, group_id)
        return {"members": members}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}")
async def get_user_info(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取用户信息"""
    try:
        user = await chat_api.get_user_info(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}/friends")
async def get_friend_list(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取好友列表"""
    try:
        friends = await chat_api.get_friend_list(db, user_id)
        return {"friends": friends}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))