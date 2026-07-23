"""
人格锚点模型 — AI 的核心身份和基本设定（只读）
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from app.database import Base


class PersonalityAnchor(Base):
    __tablename__ = "personality_anchors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(50), nullable=False)
    identity = Column(Text, nullable=False)
    personality = Column(Text, nullable=False)
    core_values = Column(Text, nullable=False)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())