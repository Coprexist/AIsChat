"""
好友系统 ORM 模型
支持用户与用户、用户与 AI 之间的好友关系
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, CheckConstraint, UniqueConstraint,
)
from sqlalchemy.sql import func
from app.database import Base


class Friendship(Base):
    """好友关系表"""
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)  # 用户 ID（外键见迁移）
    friend_type = Column(String(10), nullable=False)       # 'human' 或 'ai'
    friend_id = Column(Integer, nullable=False)             # 好友的 ID
    created_at = Column(DateTime, server_default=func.now())
    is_priority = Column(Boolean, default=False)  # 特别关心，消息可穿透 DND

    __table_args__ = (
        CheckConstraint(
            "friend_type IN ('human', 'ai')",
            name="ck_friendships_friend_type",
        ),
        UniqueConstraint("user_id", "friend_type", "friend_id", name="uq_friendship"),
    )


class FriendshipRequest(Base):
    """好友申请表"""
    __tablename__ = "friendship_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requester_id = Column(Integer, nullable=False, index=True)  # 发起方用户 ID
    target_type = Column(String(10), nullable=False)            # 'human' 或 'ai'
    target_id = Column(Integer, nullable=False)                  # 目标 ID
    status = Column(String(20), default="pending")              # pending / accepted / rejected
    message = Column(Text, nullable=True)                        # 申请附言
    created_at = Column(DateTime, server_default=func.now())
    is_priority = Column(Boolean, default=False)  # 特别关心，消息可穿透 DND
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('human', 'ai')",
            name="ck_fr_target_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_fr_status",
        ),
    )
