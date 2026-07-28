"""
兑换码模型
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, func
from app.database import Base


class RedemptionCode(Base):
    __tablename__ = "redemption_codes"

    code = Column(String(32), primary_key=True)
    quota_amount = Column(Integer, nullable=False)
    code_type = Column(String(20), default="ai_quota")  # 'ai_quota' | 'api_credit' | 'agent_bundle' | 'file_quota'
    expires_at = Column(DateTime)
    used_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    # v0.1.5: 兑换码增强
    note = Column(Text, nullable=True, comment="管理员备注（不暴露给用户）")
    max_usage = Column(Integer, nullable=True, comment="此码最多可用多少 credit（NULL=一次性全额）")
    is_api_pool = Column(Boolean, default=False, comment="是否使用 API 池额度")
    created_at = Column(DateTime, server_default=func.now())
