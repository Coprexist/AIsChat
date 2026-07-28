"""
搜索路由（v0.1.3: 独立于好友系统，搜索结果可直接发起 DM）
"""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.social.search_service import search_entities
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["搜索"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """搜索用户和 AI（支持按用户名/AI名搜索，可直接发起 DM）"""
    results = await search_entities(db, q, current_user["user_id"])
    return {"results": results, "query": q}
