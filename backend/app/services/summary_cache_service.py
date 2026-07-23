"""
摘要缓存服务
提供未读摘要的缓存查询、写入、过期检查
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.summary_cache import UnreadSummaryCache
from app.config import settings

logger = logging.getLogger(__name__)


async def get_cached_summary(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
) -> dict | None:
    """
    查询未过期的摘要缓存。
    返回 None 表示缓存未命中或已过期。
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UnreadSummaryCache)
        .where(
            and_(
                UnreadSummaryCache.agent_id == agent_id,
                UnreadSummaryCache.group_id == group_id,
                UnreadSummaryCache.expires_at > now,
            )
        )
        .order_by(UnreadSummaryCache.cached_at.desc())
        .limit(1)
    )
    cache = result.scalar_one_or_none()
    if cache is None:
        return None

    logger.debug(f"缓存命中: agent={agent_id}, group={group_id}")
    return {
        "id": cache.id,
        "summary_text": cache.summary_text,
        "message_count": cache.message_count,
        "last_message_at": str(cache.last_message_at) if cache.last_message_at else None,
        "cached_at": str(cache.cached_at) if cache.cached_at else None,
    }


async def set_cached_summary(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
    summary_text: str,
    message_count: int,
    last_message_at: datetime | None = None,
    ttl_seconds: int | None = None,
) -> UnreadSummaryCache:
    """
    写入摘要缓存。
    先删除同一 agent+group 的旧缓存，再写入新记录。
    """
    ttl = ttl_seconds or settings.summary_cache_ttl
    now = datetime.now(timezone.utc)

    # 删除旧缓存（同一 agent+group）
    old = await db.execute(
        select(UnreadSummaryCache)
        .where(
            and_(
                UnreadSummaryCache.agent_id == agent_id,
                UnreadSummaryCache.group_id == group_id,
            )
        )
    )
    for old_cache in old.scalars().all():
        await db.delete(old_cache)

    # 写入新缓存
    cache = UnreadSummaryCache(
        agent_id=agent_id,
        group_id=group_id,
        summary_text=summary_text,
        message_count=message_count,
        last_message_at=last_message_at or now,
        expires_at=now + timedelta(seconds=ttl),
    )
    db.add(cache)
    await db.flush()
    await db.refresh(cache)

    logger.debug(f"缓存写入: agent={agent_id}, group={group_id}, ttl={ttl}s")
    return cache


async def invalidate_cache(
    db: AsyncSession,
    agent_id: int,
    group_id: int | None = None,
):
    """使缓存失效（有新消息到达时调用）"""
    query = select(UnreadSummaryCache).where(
        UnreadSummaryCache.agent_id == agent_id
    )
    if group_id is not None:
        query = query.where(UnreadSummaryCache.group_id == group_id)

    result = await db.execute(query)
    for cache in result.scalars().all():
        await db.delete(cache)

    if group_id:
        logger.debug(f"缓存已失效: agent={agent_id}, group={group_id}")
    else:
        logger.debug(f"全部缓存已失效: agent={agent_id}")
