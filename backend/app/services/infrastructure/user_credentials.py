"""用户级凭据读取 —— 唯一入口。

API Key 是**用户级**的：系统 provider_config 只存 base_url / 模型清单，不存 key。
所以任何"我要拿这个用户的 key 去调供应商"的地方都走这里，别各写一遍 select+decrypt。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def user_api_key(db: AsyncSession, user_id: int) -> str | None:
    """取用户自己保存的 API Key（解密后）。

    - 没配 → None
    - 解密失败（ENCRYPTION_KEY 换过 / 数据损坏）→ 记日志 + None：
      不该把一个"没填 key"的场景打成 500，但也不能静默（否则排查时无从下手）。
    """
    from app.models.user import User
    from app.utils.crypto import decrypt_api_key

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.api_key_encrypted:
        return None
    try:
        return decrypt_api_key(user.api_key_encrypted)
    except Exception as e:
        logger.warning(f"用户 #{user_id} 的 API Key 解密失败（检查 ENCRYPTION_KEY 是否变更）: {e}")
        return None
