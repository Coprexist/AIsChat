"""
AI 代理模型
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Text, DateTime,
    ForeignKey, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(50), nullable=False)

    # 原始配置（管理员设定，不可被 AI 覆盖）
    original_system_prompt = Column(Text)
    original_temperature = Column(Float, default=0.8)
    original_top_p = Column(Float, default=0.9)
    original_presence_penalty = Column(Float, default=0.5)
    original_frequency_penalty = Column(Float, default=0.5)

    # 当前配置（AI 可自修改）
    current_system_prompt = Column(Text)
    pending_system_prompt = Column(Text, nullable=True)  # AI自修改暂存，压缩时切到current
    current_temperature = Column(Float)
    current_top_p = Column(Float)
    current_presence_penalty = Column(Float)
    current_frequency_penalty = Column(Float)

    # 模型选择（NULL = 继承全局默认）
    chat_model = Column(String(50))
    work_model = Column(String(50))

    # 状态机
    state = Column(String(20), default="active")  # active|dnd|offline|blocked
    offline_until = Column(DateTime)

    # 全局暂停通知（任务期间暂存所有群聊消息）
    is_paused = Column(Boolean, default=False)

    # 意愿评分 + 自动免打扰配置
    auto_dnd_threshold = Column(Integer, default=20)  # 低于此分自动开 DND
    auto_dnd_duration = Column(Integer, default=5)    # 自动 DND 时长（分钟）

    # 是否允许 AI 自修改
    is_ai_editable = Column(Boolean, default=True)

    # 深度推理模式（DeepSeek thinking），AI 可自行切换
    thinking_enabled = Column(Boolean, default=False)

    # 三档 AI 配置：chat / immersive / digital_life（选一个作为起点，之后可自由调参）
    config_profile = Column(String(20), default="chat")

    # AI 在 users 表中的身份（统一 ID 空间，用于私信等场景）
    user_id = Column(Integer, ForeignKey("users.id"))

    # 对话日志：此 AI 的保留上限（NULL=使用全局 max_conversation_logs）
    conversation_logs_limit = Column(Integer, nullable=True)
    # 对话日志：用户是否可查看此 AI 的日志（NULL=使用全局 default_user_log_access）
    user_can_view_logs = Column(Boolean, nullable=True)

    # API 调用额度成本（创建时从用户 api_credit 扣除，删除时返还）
    api_credit_cost = Column(Integer, default=0)

    # 单 AI 级 API 配置覆盖（NULL = 继承用户全局设置）
    api_base_url = Column(Text)
    api_key_encrypted = Column(Text)

    # 延迟回复功能开关（NULL=继承全局默认，False=关闭，True=开启）
    delay_reply_enabled = Column(Boolean, nullable=True, comment="延迟回复功能开关，NULL=继承全局默认")

    # 单次回复最大工具调用轮次（3 档预设：chat=2 / immersive=4 / digital_life=10）
    max_tool_rounds = Column(Integer, default=3)

    # 闹钟/心跳最大工具调用轮次（独立于普通回复，默认更高以支持深度自主任务）
    alarm_max_tool_rounds = Column(Integer, default=10)

    # 对话结束时是否强制要求 AI 设定闹钟（数字生命档默认开启，防止"睡死"）
    force_alarm_on_end = Column(Boolean, default=False)

    # AI 最多可设多少个活跃闹钟（心跳节奏的边界）
    max_alarms = Column(Integer, default=10)

    # 系统提醒额外轮次模式: every_time(每次都不计) | once(仅一次) | off(计入配额)
    reminder_grace = Column(String(10), default="every_time")

    # 隐藏 AI 身份（开启后系统提示词不包含"你是 AI"相关表述）
    hide_ai_identity = Column(Boolean, default=False)

    # 好友与社交控制（v0.6.0）
    allow_friend_requests = Column(Boolean, default=True, comment="是否允许接收好友申请")
    auto_respond_friend_request = Column(Boolean, default=False, comment="收到好友申请时是否自动触发 API 响应")
    discoverable = Column(Boolean, default=True, comment="是否允许他人发现与查找此 AI")

    # AI 类型 (v0.4.0): general(通用) | semi_general(半通用) | resonance(共振, 默认)
    ai_type = Column(String(20), default="resonance")

    # ── 对话权限与限额 (v0.9.0) ──
    allow_others_chat = Column(Boolean, default=True, comment="是否允许非主人触发此 AI 对话")
    others_chat_mode = Column(String(20), default="unlimited", comment="允许时的模式: unlimited | quota")
    others_chat_quota = Column(Integer, default=30, comment="配额上限（触发次数），仅 quota 模式生效")
    others_chat_used = Column(Integer, default=0, comment="当前已使用次数（可重置）")
    disallow_mode = Column(String(20), default="strict", comment="禁止时的模式: strict | own_key")

    # ── 自动重置配额 (v1.1.0) ──
    auto_reset_quota = Column(Boolean, default=False, comment="每次用户 DM 时自动重置配额计数")
    # ── 配额白名单 (v1.1.0): JSONB 数组 [{type:"group"|"user", id:int}, ...] ──
    quota_whitelist = Column(JSONB, default=list, comment="不消耗配额的白名单实体列表")
    # ── 群主支付 (v1.1.0): 群聊 AI 消息默认由群主付费 ──
    group_owner_pays = Column(Boolean, default=True, comment="群聊中 AI 消息是否由群主付费")

    # ── 文件系统记忆配置 (v0.7.0) ──
    # 记忆加载模式: index_only(仅索引) | index_plus_recent(索引+最近N篇内容) | index_plus_semantic(索引+语义检索)
    memory_load_mode = Column(String(30), default="index_only")
    # index_plus_recent 模式下加载最近 N 个文件的完整内容
    memory_recent_count = Column(Integer, default=0)
    # 共享记忆范围: private_only | private_plus_shared_by_user | private_plus_shared_all
    memory_shared_scope = Column(String(30), default="private_only")

    # 最近意愿评分和原因 (v0.4.0)
    last_willingness_score = Column(Integer, nullable=True)
    last_willingness_reason = Column(Text, nullable=True)

    # 头像 URL
    avatar_url = Column(Text)

    # 个人简介（创建者/合作者可编辑，展示在资料卡中）
    bio = Column(Text, nullable=True, comment="AI 简介")

    # 自定义状态文本（AI 可通过工具自行设置，展示在资料卡和消息旁）
    status_text = Column(String(100), nullable=True, comment="自定义状态文本")
    status_color = Column(String(20), nullable=True, comment="状态文字颜色(hex)")

    # API Token（供外部调用该 AI）
    api_token = Column(String(64))

    # 状态栈 — AI 跨任务上下文追踪（v1.0.1）
    # JSONB 数组，每个元素 {id, type, context_ref, why, doing, todo, plan, journal, created_at, status}
    state_stack = Column(JSONB, default=list)

    created_at = Column(DateTime, server_default=func.now())


class AgentUserConfig(Base):
    """per-user AI 配置覆盖（通用/半通用 AI 专用）
    每个(user_id, agent_id)对存储该用户对此 AI 的个性化配置。
    NULL 值表示继承 AI 默认值。
    """
    __tablename__ = "agent_user_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # 以下均为覆盖值，NULL = 使用 agent 本体配置
    temperature = Column(Float, nullable=True)
    top_p = Column(Float, nullable=True)
    presence_penalty = Column(Float, nullable=True)
    frequency_penalty = Column(Float, nullable=True)
    thinking_enabled = Column(Boolean, nullable=True)
    hide_ai_identity = Column(Boolean, nullable=True)
    system_prompt_override = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("agent_id", "user_id", name="uq_agent_user_config"),
    )


class AgentConfigHistory(Base):
    """AI 配置历史记录（用于回滚）"""
    __tablename__ = "agent_config_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)

    system_prompt = Column(Text)
    temperature = Column(Float)
    top_p = Column(Float)
    presence_penalty = Column(Float)
    frequency_penalty = Column(Float)

    created_at = Column(DateTime, server_default=func.now())


class AgentCollaborator(Base):
    """AI 合作者（创建者可添加其他用户共同管理此 AI）"""
    __tablename__ = "agent_collaborators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    can_edit = Column(Boolean, default=True)
    can_delete = Column(Boolean, default=False)
    can_manage_collaborators = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("agent_id", "user_id", name="uq_agent_collaborator"),
    )
