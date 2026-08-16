"""
统一插件模型 — 目录即插件（plugins/<id>/plugin.json）

两级开关：
- plugins.enabled      管理员全局开放/关闭（管理面板一键切换）
- user_plugin_prefs    用户个人启用/停用（设置页一键切换）
生效 = enabled AND 用户偏好（用户偏好默认开启，即"装好即可用"）。
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, Text, DateTime, ForeignKey, UniqueConstraint,
)
from app.database import Base


def _now() -> datetime:
    return datetime.utcnow()


class Plugin(Base):
    __tablename__ = "plugins"

    id = Column(String(80), primary_key=True, comment="插件 id（目录名，如 skin-aurora）")
    name = Column(String(120), nullable=False, comment="显示名称")
    description = Column(Text, default="", comment="描述")
    category = Column(String(20), default="other", comment="skin | skill | world | other")
    version = Column(String(20), default="1.0.0")
    author = Column(String(80), default="")
    icon = Column(String(40), default="", comment="lucide 图标名（前端渲染）")
    enabled = Column(Boolean, default=True, comment="管理员全局开关（false = 所有人不可用）")
    builtin = Column(Boolean, default=False, comment="是否随代码内置（backend/plugins）")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class UserPluginPref(Base):
    __tablename__ = "user_plugin_prefs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plugin_id = Column(String(80), ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False)
    enabled = Column(Boolean, default=True, comment="用户个人开关")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("user_id", "plugin_id", name="uq_user_plugin_pref"),)
