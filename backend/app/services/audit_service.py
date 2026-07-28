"""
audit_service — 审计日志服务（外观层）

统一入口，委托给 AuditStorageBackend 实现。
新增存储后端只需在 `services/audit/` 下新建实现类，切换由系统设置控制。
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import get_backend, set_backend
from app.services.audit.postgres_backend import PostgresAuditBackend

logger = logging.getLogger(__name__)

LOG_RETENTION_DAYS = 90
CLEANUP_BATCH_SIZE = 5000

_backend_initialized = False


async def _ensure_backend() -> None:
    """确保后端已初始化"""
    global _backend_initialized
    if not _backend_initialized:
        set_backend(PostgresAuditBackend())
        _backend_initialized = True


async def create_audit_log(
    db: AsyncSession,
    log_type: str,
    operator_type: str,
    operator_id: int,
    target_type: str,
    target_id: Optional[int] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    ip_address: Optional[str] = None,
    old_value: Any = None,
    new_value: Any = None,
    details: Optional[dict] = None,
) -> dict:
    """创建审计日志条目（委托后端实现）"""
    await _ensure_backend()
    entry = {
        "log_type": log_type,
        "operator_type": operator_type,
        "operator_id": operator_id,
        "target_type": target_type,
        "target_id": target_id,
        "success": success,
        "error_message": error_message,
        "ip_address": ip_address,
        "old_value": old_value,
        "new_value": new_value,
        "details": details or {},
        "_flush": True,
    }
    await get_backend().write(entry, db=db)
    return entry


async def verify_audit_chain(db: AsyncSession, limit: int = 1000) -> dict:
    """验证哈希链完整性"""
    await _ensure_backend()
    return await get_backend().verify_chain(limit=limit, db=db)


async def cleanup_old_logs(db: AsyncSession, days: int = LOG_RETENTION_DAYS) -> dict:
    """删除超过保留天数的日志"""
    await _ensure_backend()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return await get_backend().cleanup(before=cutoff.isoformat(), db=db)


async def should_log_actions(db: AsyncSession) -> bool:
    """检查是否开启了用户行为日志记录"""
    from app.services.infrastructure.system_settings_service import get_settings
    try:
        s = await get_settings(db)
        return bool(s.get("audit_user_actions", False))
    except Exception:
        return False


async def log_user_action(
    db: AsyncSession,
    log_type: str,
    operator_id: int,
    target_type: str,
    target_id: int | None = None,
    details: dict | None = None,
    ip: str | None = None,
):
    """记录用户行为日志（仅当 audit_user_actions 开启时生效）"""
    if not await should_log_actions(db):
        return
    await create_audit_log(
        db=db, log_type=log_type, operator_type="human",
        operator_id=operator_id, target_type=target_type,
        target_id=target_id, details=details or {}, ip_address=ip,
    )
