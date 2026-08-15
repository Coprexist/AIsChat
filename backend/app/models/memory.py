"""
两层记忆模型
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, func,
    CheckConstraint,
)
from app.config import settings
from app.db_providers import vector_column
from app.database import Base

class RoughMemory(Base):
    """粗略记忆（标题层）"""
    __tablename__ = "rough_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_type = Column(String(10), nullable=False)  # 'ai' | 'group'
    owner_id = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    embedding = Column(vector_column(settings.embedding_dimension))  # 标题向量（维度随配置）
    scope = Column(String(10), default="private")  # private | group | cross_user
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    # v0.1.3: per-user 记忆隔离（共振 AI 为 NULL，通用/半通用填触发用户 ID）
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # v0.1.4: 延迟归档字段
    status = Column(String(20), default="active", comment="active | pending_archive | discarded")
    value_score = Column(Integer, default=5, comment="记忆价值评分: 1=低价值(自动提取), 5=正常, 10=高价值")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "owner_type IN ('ai', 'group')",
            name="ck_rough_owner_type",
        ),
        CheckConstraint(
            "status IN ('active', 'pending_archive', 'discarded')",
            name="ck_rough_status",
        ),
    )


class DetailMemory(Base):
    """详细记忆（内容层）"""
    __tablename__ = "detail_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rough_id = Column(Integer, ForeignKey("rough_memories.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(vector_column(settings.embedding_dimension))  # 可选，用于深度检索
    created_at = Column(DateTime, server_default=func.now())
