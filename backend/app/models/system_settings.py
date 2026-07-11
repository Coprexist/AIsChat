"""
平台全局系统设置 — 单行表（id=1）
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)
    default_language = Column(String(10), default="en")
    default_platform_credit = Column(Integer, default=0, comment="全局默认平台赠送额度（0=禁用）")

    federation_sync_interval_minutes = Column(Integer, default=720, comment="联邦 profile 同步间隔（分钟），默认 720（12小时）")

    orphan_retention_days = Column(Integer, default=7, comment="孤儿文件宽限期（天），到期自动物理删除")

    default_file_quota_mb = Column(Integer, default=100, comment="新用户默认文件存储配额（MB）")
    default_concurrent_ai_limit = Column(Integer, default=3, comment="新建群聊默认 AI 并发数")

    system_prompt_overrides = Column(JSONB, nullable=True, comment="系统提示词覆盖（管理员自定义 core_identity/protocols 等段）")
    system_prompt_order = Column(JSONB, nullable=True, comment="系统提示词段拼接顺序（NULL=使用代码默认 SEGMENT_ORDER）")

    # v1.0.0 邮箱认证
    smtp_config = Column(JSONB, nullable=True, comment="SMTP 邮件配置（密码 Fernet 加密）")

    # v1.0.0 自定义邮件模板
    email_templates = Column(JSONB, nullable=True, comment="自定义邮件模板（含预设选择：gradient/simple/custom）")

    # v1.0.0 LLM 厂商配置
    provider_config = Column(JSONB, nullable=True, comment="LLM 厂商预设：{provider, base_url, chat_model, work_model, embedding_model, model_options}")
    require_email_verification = Column(Boolean, default=False, comment="注册是否必须验证邮箱（默认关闭）")
    login_providers = Column(JSONB, default=lambda: ["direct"], comment="可用登录方式: direct/email_code/wechat/qq")

    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
