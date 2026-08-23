"""
统一错误处理模块
提供标准化工具调用错误格式、WebSocket 错误事件、系统日志记录
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system_log import SystemLog

logger = logging.getLogger(__name__)


def build_tool_error(code: str, message: str) -> dict:
    """
    构建工具调用错误返回格式（用于 LLM function calling 的 tool 角色响应）。
    返回: {"error": true, "code": "ERROR_CODE", "message": "可读描述"}
    """
    return {
        "error": True,
        "code": code,
        "message": message,
    }


def build_ws_error(code: str, message: str, tool_call_id: str | None = None) -> dict:
    """
    构建 WebSocket 异步错误事件。
    返回: {"type": "error", "code": "...", "message": "...", "tool_call_id": "..."}
    """
    event = {
        "type": "error",
        "code": code,
        "message": message,
    }
    if tool_call_id:
        event["tool_call_id"] = tool_call_id
    return event


async def log_error(
    db: AsyncSession,
    log_type: str,
    operator_type: str,
    operator_id: int,
    target_type: str | None = None,
    target_id: int | None = None,
    details: dict | None = None,
    level: str = "ERROR",
):
    """
    将错误/警告写入 system_logs 表。

    Args:
        db: 数据库会话
        log_type: 日志类型（如 "tool_call_error", "ws_error", "dnd_auto_triggered"）
        operator_type: 操作者类型（"ai" / "human" / "system"）
        operator_id: 操作者 ID
        target_type: 目标类型（可选）
        target_id: 目标 ID（可选）
        details: 详细信息 dict（可选）
        level: 级别 "ERROR" | "WARNING" | "INFO"
    """
    merged_details = details or {}
    merged_details["level"] = level

    from app.repositories.audit_repo import SQLAlchemyAuditRepository
    from app.services.audit_service import create_audit_log
    await create_audit_log(
        SQLAlchemyAuditRepository(db), log_type=log_type, operator_type=operator_type,
        operator_id=operator_id, target_type=target_type or "system",
        target_id=target_id or 0,
        success=level != "ERROR",
        error_message=str(details) if level == "ERROR" else None,
        details=merged_details,
    )

    log_msg = f"[{level}] {log_type}"
    if details:
        log_msg += f" | {details}"
    if level == "ERROR":
        logger.error(log_msg)
    elif level == "WARNING":
        logger.warning(log_msg)
    else:
        logger.info(log_msg)
