"""
技能关联模型 — AI 与 Skill 的关联关系
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from app.database import Base


class AgentSkillRelation(Base):
    __tablename__ = "agent_skill_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    skill_name = Column(String(100), nullable=False)
    
    is_enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint("agent_id", "skill_name", name="uq_agent_skill"),
    )