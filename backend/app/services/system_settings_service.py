"""
系统设置服务
单行表模式（id=1），懒初始化
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.system_settings import SystemSettings

logger = logging.getLogger(__name__)


async def _get_or_create(db: AsyncSession) -> SystemSettings:
    """获取系统设置行，不存在则创建（懒初始化）"""
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = SystemSettings(id=1, default_language="en")
        db.add(row)
        await db.flush()
        await db.refresh(row)
        logger.info("已初始化 system_settings（默认语言=en）")
    return row


async def get_provider_config(db: AsyncSession) -> dict:
    """[兼容旧代码] 获取默认 LLM 厂商配置（provider_config 数组的第一项，或空 dict）"""
    providers = await get_providers(db)
    if not providers:
        return {}
    # 返回第一个标记为 is_default 的，或第一个
    default = next((p for p in providers if p.get("is_default")), providers[0])
    return default


async def get_providers(db: AsyncSession) -> list[dict]:
    """获取所有 LLM 厂商配置数组"""
    from app.models.system_settings import SystemSettings
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        return []
    raw = row.provider_config
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    # 兼容旧单对象
    if isinstance(raw, dict):
        raw.setdefault("name", raw.get("provider", "default"))
        raw.setdefault("is_default", True)
        return [raw]
    return []


async def get_provider_by_name(db: AsyncSession, name: str) -> dict | None:
    """按名称查找单个供应商配置"""
    providers = await get_providers(db)
    for p in providers:
        if p.get("name") == name:
            return p
    return None


async def get_provider_for_pool_key(db: AsyncSession, pool_key) -> dict:
    """根据池 Key 获取对应的供应商配置"""
    from app.models.api_key_pool import ApiKeyPool
    # 如果 pool_key 有 provider_name，使用它
    provider_name = getattr(pool_key, "provider_name", None)
    if provider_name:
        provider = await get_provider_by_name(db, provider_name)
        if provider:
            return provider
    # 回退：用池 Key 的 api_base_url 匹配
    key_base = (getattr(pool_key, "api_base_url", None) or "").rstrip("/")
    if key_base:
        providers = await get_providers(db)
        for p in providers:
            if (p.get("base_url", "") or "").rstrip("/") == key_base:
                return p
    # 最终回退：默认供应商
    providers = await get_providers(db)
    if providers:
        default = next((p for p in providers if p.get("is_default")), providers[0])
        return default
    return {}


async def get_settings(db: AsyncSession) -> dict:
    """获取系统设置"""
    row = await _get_or_create(db)
    return {
        "id": row.id,
        "default_language": row.default_language,
        "default_platform_credit": row.default_platform_credit or 0,
        "system_prompt_overrides": row.system_prompt_overrides,
        "system_prompt_order": row.system_prompt_order,
        "federation_sync_interval_minutes": row.federation_sync_interval_minutes,
        "default_file_quota_mb": row.default_file_quota_mb,
        "updated_by": row.updated_by,
        "updated_at": str(row.updated_at) if row.updated_at else None,
        # v1.0.0 邮箱认证（公开字段）
        "login_providers": getattr(row, "login_providers", ["direct"]) or ["direct"],
        "require_email_verification": getattr(row, "require_email_verification", False) or False,
        "smtp_config": getattr(row, "smtp_config", None),
        "email_templates": getattr(row, "email_templates", None),
        "provider_config": getattr(row, "provider_config", None),
    }


async def update_settings(
    db: AsyncSession,
    default_language: str | None = None,
    default_platform_credit: int | None = None,
    default_file_quota_mb: int | None = None,
    updated_by: int | None = None,
) -> dict:
    """
    更新系统设置（仅更新传入的非空字段）。

    若设置 default_platform_credit > 0，需验证池中至少有一个 active Key。
    修改 default_platform_credit 会批量更新所有用户的 platform_gifted_credit。
    修改 default_file_quota_mb 会同步调整所有用户的 file_quota_mb（保留兑换码加成）。
    """
    row = await _get_or_create(db)

    if default_language is not None:
        if default_language not in ("zh", "en", "ja"):
            raise ValueError("不支持的语言，仅支持 zh / en / ja")
        row.default_language = default_language

    if default_platform_credit is not None:
        # 验证：若 > 0，池中必须有 active Key
        if default_platform_credit > 0:
            from app.models.api_key_pool import ApiKeyPool
            key_result = await db.execute(
                select(ApiKeyPool).where(ApiKeyPool.is_active == True).limit(1)
            )
            if key_result.scalar_one_or_none() is None:
                raise ValueError("API Key 池中没有可用的 Key，无法启用平台赠送额度")

        # 计算 delta → 批量更新所有用户
        old_value = row.default_platform_credit or 0
        delta = default_platform_credit - old_value
        row.default_platform_credit = default_platform_credit

        if delta != 0:
            from app.models.user import User as UserModel
            from sqlalchemy import text
            await db.execute(
                text(
                    "UPDATE users SET platform_gifted_credit = platform_gifted_credit + :delta"
                ),
                {"delta": delta},
            )
            logger.info(
                f"  平台赠送额度变更: {old_value} → {default_platform_credit} "
                f"(delta={delta:+d})，已批量更新所有用户"
            )

    if default_file_quota_mb is not None:
        old_value = row.default_file_quota_mb or 100
        delta = default_file_quota_mb - old_value
        row.default_file_quota_mb = default_file_quota_mb

        if delta != 0:
            from app.models.user import User as UserModel
            from sqlalchemy import text
            # 调整所有用户的 file_quota_mb（基数额度），兑换码加成部分不变
            await db.execute(
                text(
                    "UPDATE users SET file_quota_mb = file_quota_mb + :delta "
                    "WHERE type = 'human'"
                ),
                {"delta": delta},
            )
            logger.info(
                f"  文件配额基数变更: {old_value}MB → {default_file_quota_mb}MB "
                f"(delta={delta:+d})，已批量更新所有人类用户"
            )

    if updated_by is not None:
        row.updated_by = updated_by

    await db.flush()
    await db.refresh(row)
    logger.info(f"系统设置已更新: default_language={row.default_language}, "
                f"default_platform_credit={row.default_platform_credit}")
    return await get_settings(db)
