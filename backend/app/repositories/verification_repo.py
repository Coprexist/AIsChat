"""
验证码仓库接口（Protocol）+ SQLAlchemy 实现。
"""
from datetime import datetime, timezone
from typing import Protocol
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.verification_code import VerificationCode


class VerificationRepository(Protocol):
    async def verify_code(self, email: str, code: str, purpose: str) -> bool: ...


class SQLAlchemyVerificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def verify_code(self, email: str, code: str, purpose: str) -> bool:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
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
        await self.session.flush()
        return True
