"""
认证工具模块
- 密码哈希/验证
- JWT 令牌生成/验证
"""
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.utils.result import Result
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer 安全方案
security = HTTPBearer(auto_error=False)


def _truncate_password(password: str) -> str:
    """bcrypt 限制密码最大 72 字节，逐字符截断以确保不切割多字节 Unicode"""
    while len(password.encode("utf-8")) > 72:
        password = password[:-1]
    return password


def hash_password(password: str) -> str:
    """对密码进行哈希"""
    return pwd_context.hash(_truncate_password(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(_truncate_password(plain_password), hashed_password)


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """创建 JWT 访问令牌"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.jwt_expire_days)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Result[dict, str]:
    """解码 JWT 令牌，返回 Result[dict, str]"""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return Result.success(payload)
    except jwt.ExpiredSignatureError:
        return Result.failure("token 已过期")
    except JWTError as e:
        return Result.failure(f"token 无效: {e}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    token: str | None = Query(None, description="JWT 令牌（URL 参数兼容，用于 img/link 场景）"),
) -> dict:
    """
    FastAPI 依赖：从 JWT 中获取当前用户信息。
    支持 Authorization: Bearer <token> 头部或 ?token=<token> 查询参数。
    返回 {"user_id": int, "username": str, "role": str}
    """
    raw = None
    if credentials is not None:
        raw = credentials.credentials
    elif token:
        raw = token

    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证令牌",
        )

    payload_result = decode_access_token(raw)
    if payload_result.is_err():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=payload_result.error,
        )
    payload = payload_result.ok

    user_id = payload.get("user_id")
    username = payload.get("username")
    role = payload.get("role", "user")

    if user_id is None or username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌数据不完整",
        )

    # 记录活动时间戳（用于在线状态判断）
    from app.services.infrastructure.online_tracker import record_activity
    record_activity(int(user_id))

    return {"user_id": int(user_id), "username": username, "role": role}


async def require_admin(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    FastAPI 依赖：要求管理员权限。
    注意：必须从 DB 重新读取角色，因为 JWT 中的 role 可能是提权前的旧值。
    """
    from app.models.user import User as UserModel
    result = await db.execute(
        select(UserModel).where(UserModel.id == current_user["user_id"])
    )
    db_user = result.scalar_one_or_none()
    if db_user is None or db_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user
