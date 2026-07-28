"""
audit_service — 审计日志服务

企业级操作记录，包含：
- 统一写入接口（create_audit_log）
- 哈希链防篡改（SHA256）
- 自动清理策略
- 哈希链完整性验证
"""
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 日志保留天数
LOG_RETENTION_DAYS = 180
# 每次清理最大删除条数（分批防锁表）
CLEANUP_BATCH_SIZE = 5000


def _compute_hash(
    prev_hash: Optional[str],
    created_at: datetime,
    log_type: str,
    operator_type: str,
    operator_id: int,
    target_type: str,
    target_id: Optional[int],
    success: bool,
    old_value: Any,
    new_value: Any,
    ip_address: Optional[str],
) -> str:
    """计算日志条目的 SHA256 哈希。

    包含所有关键字段 + 上一条哈希，修改任一字段会破坏链。
    """
    parts = [
        prev_hash or "",
        created_at.isoformat() if created_at else "",
        log_type,
        operator_type,
        str(operator_id),
        target_type,
        str(target_id or ""),
        "1" if success else "0",
        str(old_value or ""),
        str(new_value or ""),
        ip_address or "",
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    """创建审计日志条目。

    自动计算哈希链：读取上一条日志的 hash 作为 prev_hash。
    """
    from app.models.system_log import SystemLog

    # 读上一条 hash（以 id 降序取第一条）
    prev = (
        await db.execute(
            select(SystemLog.hash)
            .order_by(SystemLog.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    current_hash = _compute_hash(
        prev_hash=prev,
        created_at=now,
        log_type=log_type,
        operator_type=operator_type,
        operator_id=operator_id,
        target_type=target_type,
        target_id=target_id,
        success=success,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )

    entry = SystemLog(
        log_type=log_type,
        operator_type=operator_type,
        operator_id=operator_id,
        target_type=target_type,
        target_id=target_id,
        success=success,
        error_message=error_message,
        ip_address=ip_address,
        old_value=old_value,
        new_value=new_value,
        details=details or {},
        prev_hash=prev,
        hash=current_hash,
        created_at=now,
    )
    db.add(entry)
    await db.flush()

    return entry.to_dict()


async def verify_audit_chain(db: AsyncSession, limit: int = 1000) -> dict:
    """验证最近 N 条日志的哈希链完整性。

    返回: { "valid": bool, "checked": int, "first_broken": int | None }
    """
    from app.models.system_log import SystemLog

    result = await db.execute(
        select(SystemLog).order_by(SystemLog.id.asc()).limit(limit)
    )
    logs = result.scalars().all()

    broken = None
    for i, entry in enumerate(logs):
        expected = _compute_hash(
            prev_hash=entry.prev_hash,
            created_at=entry.created_at,
            log_type=entry.log_type,
            operator_type=entry.operator_type,
            operator_id=entry.operator_id,
            target_type=entry.target_type,
            target_id=entry.target_id,
            success=entry.success,
            old_value=entry.old_value,
            new_value=entry.new_value,
            ip_address=entry.ip_address,
        )
        if expected != entry.hash:
            broken = entry.id
            break

    return {
        "valid": broken is None,
        "checked": len(logs),
        "first_broken": broken,
    }


async def cleanup_old_logs(db: AsyncSession, days: int = LOG_RETENTION_DAYS) -> dict:
    """删除超过保留天数的日志。分批执行，避免锁表。"""
    from app.models.system_log import SystemLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total_deleted = 0

    while True:
        result = await db.execute(
            delete(SystemLog)
            .where(SystemLog.created_at < cutoff)
            .limit(CLEANUP_BATCH_SIZE)
        )
        deleted = result.rowcount
        total_deleted += deleted
        if deleted < CLEANUP_BATCH_SIZE:
            break
        await db.commit()

    return {"deleted": total_deleted, "cutoff": cutoff.isoformat()}


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
