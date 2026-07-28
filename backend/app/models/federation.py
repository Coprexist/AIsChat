"""
联邦通信 ORM 模型（v0.2.0 ID前缀替代注册表）

v0.1.2 → v0.2.0 变更：
  删除: FederationGroupShare, FederationDMShare（注册表交换模式）
  新增: FederatedEntity（ID 前缀映射）, PendingProfileUpdate（改名同步队列）
  display_name 新增唯一约束（作为实例代号）
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, func, Text,
    CheckConstraint, UniqueConstraint, Index,
)
from app.database import Base


class InstanceConfig(Base):
    """实例身份配置（单例表，仅一行）"""
    __tablename__ = "instance_config"

    id = Column(Integer, primary_key=True, default=1)
    instance_id = Column(String(36), unique=True, nullable=False)  # 子网 UUID v4
    public_id = Column(String(50), unique=True, nullable=True)      # 公网 ID: AIsChat-xxxxxxxx
    display_name = Column(String(100), default="")                   # 人类可读名称
    public_url = Column(String(500), default="")                     # 本实例公网可达 URL
    github_token_encrypted = Column(String, nullable=True)           # Fernet 加密的 GitHub Token（可选，仅用于公开发现）
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())


class FederationPeer(Base):
    """联邦对等端（其他 AIsChat 实例）"""
    __tablename__ = "federation_peers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    peer_public_id = Column(String(50), nullable=False)  # 对方公网 ID
    display_name = Column(String(100), default="", unique=True, nullable=False)  # 实例代号（唯一，用作ID前缀 + 前端路由）
    remote_url = Column(String(500), nullable=False)      # ws://host:port/federation/ws
    remote_url_backup = Column(String(500), nullable=True)  # 轮换回退
    shared_secret_encrypted = Column(String, nullable=False)  # Fernet 加密的共享密钥
    is_enabled = Column(Boolean, default=True)
    connection_state = Column(String(20), default="disconnected")  # connecting|connected|disconnected|failed
    last_connected_at = Column(DateTime, nullable=True)
    url_rotated_at = Column(DateTime, nullable=True)
    url_rotation_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "connection_state IN ('connecting', 'connected', 'disconnected', 'failed')",
            name="ck_peer_connection_state",
        ),
    )


class FederatedEntity(Base):
    """
    联邦实体注册表（v0.2.0 替代 FederationGroupShare + FederationDMShare）

    记录从远端实例接入的实体。ID 前缀直接编码归属，无需 conversation_uuid 翻译。
    一张表统一群聊/DM/用户/AI 四种实体类型。
    """
    __tablename__ = "federated_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    federated_id = Column(String(200), unique=True, nullable=False, index=True)  # "大同AI:g:42"
    peer_id = Column(Integer, ForeignKey("federation_peers.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(10), nullable=False)  # group / dm / user / agent
    local_ref_id = Column(String(100), nullable=False)  # 映射到的本地 ID（群ID/DM session_id）
    display_name = Column(String(200), default="")       # 缓存的远端显示名（profile sync 更新）
    avatar_url = Column(Text, default="")                 # 缓存的远端头像 URL（profile sync 更新）
    is_enabled = Column(Boolean, default=True)
    direction = Column(String(20), default="incoming")   # incoming / bidirectional
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('group', 'dm', 'user', 'agent')",
            name="ck_fed_entity_type",
        ),
        CheckConstraint(
            "direction IN ('incoming', 'bidirectional', 'outgoing')",
            name="ck_fed_entity_direction",
        ),
        UniqueConstraint("peer_id", "entity_type", "local_ref_id", name="uq_fed_entity_peer_local"),
        Index("idx_fed_entity_type_ref", "entity_type", "local_ref_id"),
    )


class PendingProfileUpdate(Base):
    """
    改名同步队列（v0.2.0）

    记录本地实体变更，传播到联邦对等端后自动清除。
    传播方式：A) 发消息时顺带  B) 定时全推（N分钟，管理员可配）
    """
    __tablename__ = "pending_profile_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(10), nullable=False)  # user / agent
    entity_id = Column(Integer, nullable=False)        # local user_id / agent_id
    field = Column(String(50), nullable=False)         # display_name / avatar_url
    new_value = Column(String(500), nullable=False)
    changed_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ppu_entity", "entity_type", "entity_id"),
    )
