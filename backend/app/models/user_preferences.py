from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from app.database import Base


class UserGroupPreference(Base):
    __tablename__ = "user_group_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    is_pinned = Column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_user_group_pref"),)


class UserDMPreference(Base):
    __tablename__ = "user_dm_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String(64), ForeignKey("dm_sessions.session_id", ondelete="CASCADE"), nullable=False)
    is_pinned = Column(Boolean, default=False)
    is_special_care = Column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_user_dm_pref"),)
