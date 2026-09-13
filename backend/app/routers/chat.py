"""
社交路由 — 用户信息与好友

群聊消息见 routers/gm.py，私信见 routers/dm.py，群管理见 routers/groups.py。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import chat_api
from app.database import get_db
from app.utils.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


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


class FriendRequestSend(BaseModel):
    """发送好友请求"""
    target_type: str
    target_id: int
    message: str | None = None


@router.post("/friend/request")
async def chat_friend_request(
    req: FriendRequestSend,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发送好友请求（统一入口）"""
    from app.services.social.friend_service import send_friend_request

    try:
        result = await send_friend_request(
            db,
            requester_id=current_user["user_id"],
            target_type=req.target_type,
            target_id=req.target_id,
            message=req.message,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
