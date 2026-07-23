"""
额度服务：API Key 池选择、额度扣除、用量记录

核心职责：
  1. find_best_pool_key() — 为用户选择最优池 Key（优先缓存命中）
  2. deduct_credit() — LLM 调用后按 token 数扣除 api_credit
  3. record_api_usage() — 写入 api_usage_log 审计记录
  4. auto_assign_pool_key() — 自动绑定用户→池 Key

额度规则：
  - 1 credit = 10,000 tokens（可通过 Settings.credit_per_10k_tokens 配置）
  - 最低单次扣除 0.01 credit
  - 使用池 Key 时扣 api_credit；使用自有 Key 时不扣
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 池 Key 选择
# ══════════════════════════════════════════════════════════════

async def find_best_pool_key(db: AsyncSession, user_id: int, exclude_pool_key_id: int | None = None):
    """
    为用户选择最优可用池 Key（考虑并发负载）。

    策略：
    1. 查用户已有绑定（user_api_assignments）→ 缓存命中
    2. 绑定的 Key 仍 active 且未排除 → 直接返回
    3. 绑定失效或被排除 → 按并发负载 + priority 选最优 active Key → 自动重新绑定
    4. 无可用 Key → 返回 None

    返回: ApiKeyPool | None
    """
    from app.models.api_key_pool import ApiKeyPool, UserApiAssignment
    from app.services.api_key_concurrency import concurrency_mgr

    # Step 1: 查缓存绑定
    assign_result = await db.execute(
        select(UserApiAssignment).where(UserApiAssignment.user_id == user_id)
    )
    assignment = assign_result.scalar_one_or_none()

    if assignment and assignment.pool_key_id != exclude_pool_key_id:
        # Step 2: 验证绑定 Key 仍有效
        key_result = await db.execute(
            select(ApiKeyPool).where(
                ApiKeyPool.id == assignment.pool_key_id,
                ApiKeyPool.is_active == True,
            )
        )
        cached_key = key_result.scalar_one_or_none()
        if cached_key:
            # 更新 last_used_at
            assignment.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.flush()
            return cached_key
        else:
            # Key 已失效，清除绑定
            logger.info(f"  🔄 用户 {user_id} 的池 Key {assignment.pool_key_id} 已失效，自动重新选择")
            await db.delete(assignment)
            await db.flush()

    # Step 3: 查询所有 active Key（排除指定 Key）
    query = select(ApiKeyPool).where(ApiKeyPool.is_active == True)
    if exclude_pool_key_id is not None:
        query = query.where(ApiKeyPool.id != exclude_pool_key_id)
    query = query.order_by(desc(ApiKeyPool.priority))
    key_result = await db.execute(query)
    all_keys = key_result.scalars().all()

    if not all_keys:
        return None

    # Step 4: 用并发管理器选负载最低的 Key
    best_key_id = await concurrency_mgr.get_least_loaded(all_keys)
    if best_key_id:
        # 找到对应 ORM 对象
        best_key = next((k for k in all_keys if k.id == best_key_id), None)
        if best_key:
            await auto_assign_pool_key(db, user_id, best_key.id)
            return best_key

    # 所有 Key 都冷却/满 → fallback 到 priority 最高的
    best_key = all_keys[0]
    await auto_assign_pool_key(db, user_id, best_key.id)
    return best_key


async def auto_assign_pool_key(db: AsyncSession, user_id: int, pool_key_id: int):
    """创建或更新用户→池 Key 绑定"""
    from app.models.api_key_pool import UserApiAssignment

    assign_result = await db.execute(
        select(UserApiAssignment).where(UserApiAssignment.user_id == user_id)
    )
    existing = assign_result.scalar_one_or_none()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if existing:
        existing.pool_key_id = pool_key_id
        existing.assigned_at = now
        existing.last_used_at = now
    else:
        db.add(UserApiAssignment(
            user_id=user_id,
            pool_key_id=pool_key_id,
            assigned_at=now,
            last_used_at=now,
        ))
    await db.flush()


# ══════════════════════════════════════════════════════════════
# 额度扣除
# ══════════════════════════════════════════════════════════════

async def deduct_credit(
    db: AsyncSession,
    user_id: int,
    tokens_used: int,
    source: str = "user_key",
    pool_key_id: int | None = None,
    agent_id: int | None = None,
    model: str | None = None,
) -> float:
    """
    按 token 数扣除额度（平台赠送优先 → api_credit）。

    规则：
    - source='pool_key': 先扣 platform_gifted_credit（>0 部分），再扣 api_credit
    - source='user_key': 仅记录，不扣除（用户用自己的 Key）
    - api_credit 允许超支变负数（前端标红）

    返回实际扣除的 credit 数（pool_key 模式下），或 0（user_key 模式下）。
    """
    from app.config import settings

    if tokens_used <= 0:
        return 0.0

    # 计算应扣 credit：1 credit = N tokens
    tokens_per_credit = getattr(settings, 'credit_per_10k_tokens', 10000)
    credit_to_spend = max(0.01, round(tokens_used / tokens_per_credit, 2))

    if source == "pool_key":
        from app.models.user import User
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            logger.warning(f"  扣除额度失败：用户 {user_id} 不存在")
            return 0.0

        remaining = credit_to_spend
        platform_deducted = 0.0
        api_deducted = 0.0

        # Step 1: 先扣平台赠送额度（仅 > 0 部分）
        platform_available = max(0, float(user.platform_gifted_credit or 0))
        if platform_available > 0:
            platform_deducted = min(remaining, platform_available)
            user.platform_gifted_credit = float(user.platform_gifted_credit or 0) - platform_deducted
            remaining -= platform_deducted

        # Step 2: 再扣 api_credit（允许超支变负数）
        if remaining > 0:
            api_deducted = remaining
            user.api_credit = float(user.api_credit or 0) - api_deducted

        await db.flush()

        # 记录日志
        total_deducted = platform_deducted + api_deducted
        await record_api_usage(
            db, user_id=user_id, agent_id=agent_id,
            pool_key_id=pool_key_id, source=source,
            tokens_used=tokens_used, credit_spent=total_deducted, model=model,
        )

        effective_remaining = max(0, float(user.platform_gifted_credit or 0)) + float(user.api_credit or 0)
        logger.info(
            f"  💰 扣除用户 {user_id} 额度 {total_deducted:.2f} credit "
            f"(平台赠送 -{platform_deducted:.2f}, api_credit -{api_deducted:.2f}, "
            f"本次 {tokens_used} tokens, 有效剩余 {effective_remaining:.2f})"
        )
        return total_deducted
    else:
        # 用户自有 Key：仅记录，不扣除
        await record_api_usage(
            db, user_id=user_id, agent_id=agent_id,
            pool_key_id=None, source="user_key",
            tokens_used=tokens_used, credit_spent=0.0, model=model,
        )
        return 0.0


# ══════════════════════════════════════════════════════════════
# 用量记录
# ══════════════════════════════════════════════════════════════

async def record_api_usage(
    db: AsyncSession,
    user_id: int,
    tokens_used: int,
    credit_spent: float = 0.0,
    source: str = "user_key",
    pool_key_id: int | None = None,
    agent_id: int | None = None,
    model: str | None = None,
):
    """写入 api_usage_log"""
    from app.models.api_usage_log import ApiUsageLog

    log_entry = ApiUsageLog(
        user_id=user_id,
        agent_id=agent_id,
        pool_key_id=pool_key_id,
        source=source,
        tokens_used=tokens_used,
        credit_spent=credit_spent,
        model=model,
    )
    db.add(log_entry)


# ══════════════════════════════════════════════════════════════
# 用户查询
# ══════════════════════════════════════════════════════════════

async def get_user_credit_status(db: AsyncSession, user_id: int) -> dict:
    """
    获取用户的额度状态摘要。

    返回:
        api_credit: 兑换码额度
        platform_gifted_credit: 平台赠送额度（原始值）
        platform_gifted_credit_effective: 平台赠送额度有效值（≥0 截断）
        total_effective: 有效总额度
        estimated_tokens: 估算剩余 Token 数（total_effective × 10000）
        monthly_consumed: 近 30 天已消费 credit
        assigned_key_name: 绑定的池 Key 名（或 None）
    """
    from app.models.user import User
    from app.models.api_key_pool import ApiKeyPool, UserApiAssignment

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return {
            "api_credit": 0, "platform_gifted_credit": 0,
            "platform_gifted_credit_effective": 0, "total_effective": 0,
            "estimated_tokens": 0, "monthly_consumed": 0, "assigned_key_name": None,
        }

    # 绑定 Key 名
    assigned_key_name = None
    assign_result = await db.execute(
        select(UserApiAssignment).where(UserApiAssignment.user_id == user_id)
    )
    assignment = assign_result.scalar_one_or_none()
    if assignment:
        key_result = await db.execute(
            select(ApiKeyPool.name).where(ApiKeyPool.id == assignment.pool_key_id)
        )
        assigned_key_name = key_result.scalar()

    # 月度消费
    from sqlalchemy import func
    month_start = datetime.now(timezone.utc).replace(tzinfo=None, day=1, hour=0, minute=0, second=0, microsecond=0)
    from app.models.api_usage_log import ApiUsageLog
    monthly_result = await db.execute(
        select(func.coalesce(func.sum(ApiUsageLog.credit_spent), 0)).where(
            ApiUsageLog.user_id == user_id,
            ApiUsageLog.created_at >= month_start,
            ApiUsageLog.source == "pool_key",
        )
    )
    monthly_consumed = float(monthly_result.scalar() or 0)

    from app.config import settings
    tokens_per_credit = getattr(settings, 'credit_per_10k_tokens', 10000)

    platform_raw = float(user.platform_gifted_credit or 0)
    platform_effective = max(0, platform_raw)
    api_credit = float(user.api_credit or 0)
    total_effective = platform_effective + api_credit

    return {
        "api_credit": api_credit,
        "platform_gifted_credit": platform_raw,
        "platform_gifted_credit_effective": platform_effective,
        "total_effective": total_effective,
        "estimated_tokens": int(total_effective) * tokens_per_credit,
        "monthly_consumed": monthly_consumed,
        "assigned_key_name": assigned_key_name,
    }
