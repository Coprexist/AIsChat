"""
群聊模型
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, CheckConstraint, func, Text,
    ForeignKey, PrimaryKeyConstraint,
)
from app.database import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    owner_type = Column(String(10), nullable=False)  # 'human' | 'ai'
    owner_id = Column(Integer, nullable=False)
    is_vector_accelerated = Column(Boolean, default=False)
    announcement = Column(Text, nullable=True)
    announcement_updated_at = Column(DateTime, nullable=True)
    speak_limit_per_minute = Column(Integer, default=0)  # 0 = 不限制
    speak_limit_window_seconds = Column(Integer, default=120)  # 时间窗口（秒）
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "owner_type IN ('human', 'ai')",
            name="ck_group_owner_type",
        ),
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    member_type = Column(String(10), nullable=False)  # 'human' | 'ai'
    member_id = Column(Integer, nullable=False)
    role = Column(String(20), default="member")  # owner|admin|member
    dnd_until = Column(DateTime, nullable=True)  # NULL=永久免打扰; 有值=临时截止时间
    muted_until = Column(DateTime, nullable=True)  # 屏蔽截止时间，期间 @/公告也不穿透
    last_read_at = Column(DateTime, nullable=True)  # 用户上次查看群聊的时间
    joined_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("group_id", "member_type", "member_id"),
        CheckConstraint(
            "member_type IN ('human', 'ai')",
            name="ck_group_member_type",
        ),
    )


class GroupInvitation(Base):
    """群邀请记录（仅人类走邀请流程，AI 直接入群）"""
    __tablename__ = "group_invitations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    inviter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invitee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending | accepted | rejected
    message = Column(Text, nullable=True)  # 附言
    dm_session_id = Column(String(64), nullable=True)  # 关联的 DM 会话
    dm_message_id = Column(Integer, nullable=True)     # 关联的卡片消息 ID
    created_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_group_invitation_status",
        ),
    )
