"""
AI 底层服务 API — 设计文档 ai_service_design.md 九节

端点：
  GET  /ai/tools   获取可用工具列表（按状态过滤）
  POST /ai/chat    触发 AI 回复（无差别入口：人类与 AI 同一套接口）
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI 底层服务"])


class TriggerChatRequest(BaseModel):
    """触发 AI 回复请求"""
    agent_id: int = Field(..., description="目标 AI（agent.id 或 user_id）")
    group_id: int = Field(..., description="群聊 ID")
    content: str = Field(..., min_length=1, max_length=4000, description="触发消息内容")
    sender_type: str = Field(default="human", description="发送者类型 human|ai")
    sender_id: int | None = Field(default=None, description="发送者 ID；缺省=当前用户")
    message_type: str = Field(default="normal", description="normal|reminder|alarm")


@router.get("/tools")
async def list_tools(
    state: str = "active",
    current_user: dict = Depends(get_current_user),
):
    """获取可用工具列表（按 AI 状态过滤）"""
    from app.services.tool_registry import get_allowed_tools

    tools = get_allowed_tools(state)
    return {"tools": tools}


@router.post("/chat")
async def trigger_ai_chat(
    req: TriggerChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """触发 AI 回复 — 创建消息并入队 AI 回复（无差别入口）"""
    from app.chat import chat_api
    from app.ai.response_worker import _maybe_trigger_ai_reply

    sender_id = req.sender_id or current_user["user_id"]

    try:
        # 1. 创建消息（走统一消息管道）
        message = await chat_api.create_message(
            db,
            sender_type=req.sender_type,
            sender_id=sender_id,
            group_id=req.group_id,
            content=req.content,
        )
        await db.flush()

        # 2. 触发 AI 回复
        group = await chat_api.get_group(db, req.group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="群聊不存在")

        await _maybe_trigger_ai_reply(
            db,
            agent_id=req.agent_id,
            group_id=req.group_id,
            group=group,
            content=req.content,
            trigger_message_id=message.id,
            sender_type=req.sender_type,
            sender_id=sender_id,
            message_type=req.message_type,
        )
        await db.commit()
        return {"success": True, "message_id": message.id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("AI 触发回复失败")
        raise HTTPException(status_code=500, detail=str(e))
