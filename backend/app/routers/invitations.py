"""
群邀请路由：接受/拒绝/列表
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.utils.auth import get_current_user

router = APIRouter(tags=["群邀请"])


@router.get("/group-invitations")
async def list_invitations(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的待处理群邀请"""
    from app.services.invitation_service import list_pending_invitations
    invitations = await list_pending_invitations(db, current_user["user_id"])
    return {"invitations": invitations}


@router.post("/group-invitations/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """接受群邀请"""
    from app.services.invitation_service import accept_invitation as accept_inv
    try:
        result = await accept_inv(db, invitation_id, current_user["user_id"])
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/group-invitations/{invitation_id}/reject")
async def reject_invitation(
    invitation_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """拒绝群邀请"""
    from app.services.invitation_service import reject_invitation as reject_inv
    try:
        result = await reject_inv(db, invitation_id, current_user["user_id"])
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
