"""
对话日志用户端路由
用户的日志设置 + 查看授权 AI 的对话日志 + 导出
"""
import json
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.utils.auth import get_current_user
from app.utils.pure.formatting import format_log_as_markdown
from app.models.user import User

router = APIRouter(tags=["对话日志"])


class UserConvLogLimitBody(BaseModel):
    limit: int = Field(..., ge=1, le=500, description="保留数")


@router.get("/conversation-log/settings")
async def get_my_log_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的对话日志保留设置"""
    from app.services.content.conversation_log_service import get_user_log_limit
    return await get_user_log_limit(db, current_user["user_id"])


@router.put("/conversation-log/settings")
async def update_my_log_settings(
    req: UserConvLogLimitBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户的对话日志保留数"""
    from app.services.content.conversation_log_service import update_user_log_limit
    try:
        return await update_user_log_limit(db, current_user["user_id"], req.limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/conversation-log/agents/{agent_id}/logs")
async def get_agent_logs_user(
    agent_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看某 AI 的对话日志（需授权）"""
    from app.services.content.conversation_log_service import get_agent_logs
    # 从 DB 读取角色而非信任 JWT（提权后 JWT 可能过时）
    user_result = await db.execute(select(User.role).where(User.id == current_user["user_id"]))
    db_role = user_result.scalar_one_or_none()
    is_admin = db_role == "admin"
    try:
        return await get_agent_logs(
            db, agent_id,
            user_id=current_user["user_id"],
            is_admin=is_admin,
            limit=limit, offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/conversation-log/agents/{agent_id}/logs/{log_id}")
async def get_agent_log_detail_user(
    agent_id: int,
    log_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看单条对话日志详情（需授权）"""
    from app.services.content.conversation_log_service import get_log_detail
    user_result = await db.execute(select(User.role).where(User.id == current_user["user_id"]))
    db_role = user_result.scalar_one_or_none()
    is_admin = db_role == "admin"
    try:
        detail = await get_log_detail(
            db, log_id,
            user_id=current_user["user_id"],
            is_admin=is_admin,
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="日志不存在")
        return detail
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# 导出端点
# ============================================================

@router.get("/conversation-log/agents/{agent_id}/logs/{log_id}/export")
async def export_log_detail(
    agent_id: int,
    log_id: int,
    format: str = Query("json", pattern=r"^(json|md|markdown)$"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出单条对话日志（JSON 或 Markdown）"""
    from app.services.content.conversation_log_service import get_log_detail
    user_result = await db.execute(select(User.role).where(User.id == current_user["user_id"]))
    db_role = user_result.scalar_one_or_none()
    is_admin = db_role == "admin"
    try:
        detail = await get_log_detail(
            db, log_id,
            user_id=current_user["user_id"],
            is_admin=is_admin,
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="日志不存在")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if format in ('md', 'markdown'):
        md = format_log_as_markdown(detail)
        return PlainTextResponse(md, media_type="text/markdown; charset=utf-8",
                                 headers={"Content-Disposition": f"attachment; filename=log-{log_id}.md"})
    else:
        return PlainTextResponse(
            json.dumps(detail, ensure_ascii=False, indent=2, default=str),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=log-{log_id}.json"},
        )


# ============================================================
# Token 用量端点
# ============================================================

from datetime import datetime, timedelta, timezone as tz


@router.get("/conversation-log/usage/overview")
async def get_usage_overview(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户所有 AI 的 token 消耗汇总（近 N 天）"""
    from app.services.content.conversation_log_service import get_user_agents_token_summary
    end_date = datetime.now(tz.utc).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    return await get_user_agents_token_summary(db, current_user["user_id"], start_date, end_date)


@router.get("/conversation-log/usage/agents/{agent_id}/daily")
async def get_agent_daily_usage(
    agent_id: int,
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个 AI 每日 token 消耗分布"""
    from app.services.content.conversation_log_service import get_agent_token_daily
    # 权限：用户只能看自己拥有的 AI
    from app.models.agent import Agent
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar()
    if not agent or agent.owner_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="无权查看此 AI 的用量数据")
    end_date = datetime.now(tz.utc).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    return await get_agent_token_daily(db, agent_id, start_date, end_date)
