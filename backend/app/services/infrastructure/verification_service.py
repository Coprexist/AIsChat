"""
验证码服务
生成 / 发送 / 校验验证码 + 频率限制
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.verification_code import VerificationCode

logger = logging.getLogger(__name__)

CODE_EXPIRY_MINUTES = 5
CODE_LENGTH = 6
RATE_LIMIT_PER_MINUTE = 1
RATE_LIMIT_PER_HOUR = 5


def _generate_code() -> str:
    """生成 6 位数字验证码"""
    return str(secrets.randbelow(1_000_000)).zfill(CODE_LENGTH)


async def generate_and_send_code(
    db: AsyncSession,
    email: str,
    purpose: str,
    ip_address: str | None = None,
    lang: str = "zh",
) -> str:
    """生成验证码并发送邮件。返回生成的验证码（用于日志），失败抛 ValueError。"""
    # 频率限制（先查后插）
    await _check_rate_limit(db, email, ip_address)

    # 使同 email+purpose 的旧未使用码失效
    await db.execute(
        select(VerificationCode).where(
            VerificationCode.email == email,
            VerificationCode.purpose == purpose,
            VerificationCode.used == False,
        )
    )
    old_codes = (await db.execute(
        select(VerificationCode).where(
            VerificationCode.email == email,
            VerificationCode.purpose == purpose,
            VerificationCode.used == False,
        )
    )).scalars().all()
    for old in old_codes:
        old.used = True  # 标记旧码已失效

    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRY_MINUTES)

    vc = VerificationCode(
        email=email,
        code=code,
        purpose=purpose,
        expires_at=expires_at,
        ip_address=ip_address,
    )
    db.add(vc)
    await db.flush()

    # 发送邮件
    from app.services.email_service import send_verification_code_email
    await send_verification_code_email(db, email, code, purpose, lang)

    logger.info(f"验证码已生成并发送: email={email}, purpose={purpose}")
    return code


async def verify_code(
    db: AsyncSession,
    email: str,
    code: str,
    purpose: str,
) -> bool:
    """校验验证码。成功标记已使用并返回 True，失败返回 False。"""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.email == email,
            VerificationCode.code == code,
            VerificationCode.purpose == purpose,
            VerificationCode.used == False,
            VerificationCode.expires_at > now,
        )
    )
    vc = result.scalar_one_or_none()
    if vc is None:
        return False

    vc.used = True
    await db.flush()
    return True


async def _check_rate_limit(
    db: AsyncSession,
    email: str,
    ip_address: str | None = None,
) -> None:
    """检查频率限制：每邮箱+IP 每分钟 1 次，每小时 5 次。超限抛 HTTPException(429)。"""
    from fastapi import HTTPException
    from starlette import status

    now = datetime.now(timezone.utc)

    # 按邮箱检查
    one_min_ago = now - timedelta(minutes=1)
    one_hour_ago = now - timedelta(hours=1)

    minute_count = await db.execute(
        select(func.count(VerificationCode.id)).where(
            VerificationCode.email == email,
            VerificationCode.created_at > one_min_ago,
        )
    )
    if (minute_count.scalar() or 0) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="验证码发送太频繁，请稍后再试",
        )

    hour_count = await db.execute(
        select(func.count(VerificationCode.id)).where(
            VerificationCode.email == email,
            VerificationCode.created_at > one_hour_ago,
        )
    )
    if (hour_count.scalar() or 0) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="验证码发送次数超限，请一小时后重试",
        )

    # 按 IP 检查
    if ip_address:
        ip_minute = await db.execute(
            select(func.count(VerificationCode.id)).where(
                VerificationCode.ip_address == ip_address,
                VerificationCode.created_at > one_min_ago,
            )
        )
        if (ip_minute.scalar() or 0) >= RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="验证码发送太频繁，请稍后再试",
            )

        ip_hour = await db.execute(
            select(func.count(VerificationCode.id)).where(
                VerificationCode.ip_address == ip_address,
                VerificationCode.created_at > one_hour_ago,
            )
        )
        if (ip_hour.scalar() or 0) >= RATE_LIMIT_PER_HOUR:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="验证码发送次数超限，请一小时后重试",
            )
