"""
注意力模型 — AI 的消息过滤和兴趣域配置
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.db_providers import json_column
from app.database import Base


class AgentAttention(Base):
    __tablename__ = "agent_attention"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)
    
    interested_topics = Column(json_column(), default=list)
    interested_users = Column(json_column(), default=list)
    interested_patterns = Column(json_column(), default=list)
    
    ignored_topics = Column(json_column(), default=list)
    ignored_patterns = Column(json_column(), default=list)
    
    match_action = Column(String(20), default="highlight")  # highlight | wake | silent_remember | ignore
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())