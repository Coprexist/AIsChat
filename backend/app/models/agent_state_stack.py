"""
状态栈模型 — AI 的状态帧堆栈
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from app.database import Base


class AgentStateStack(Base):
    __tablename__ = "agent_state_stack"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    
    frame_type = Column(String(50), nullable=False)
    context_ref = Column(String(100))
    why = Column(Text)
    doing = Column(Text)
    todo = Column(Text)
    plan = Column(Text)
    journal = Column(Text)
    
    status = Column(String(20), default="active")  # active | paused | completed | cancelled
    
    created_at = Column(DateTime, server_default=func.now())