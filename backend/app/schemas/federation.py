"""
联邦通信 Schema（v0.2.0 ID前缀替代注册表）

v0.1.2 → v0.2.0 变更：
  删除: GroupShareCreate, GroupShareResponse, DMShareCreate, DMShareResponse
  新增: EntityAnnounce（入站实体注册）, ProfileUpdateItem（改名同步）
"""
from pydantic import BaseModel, Field


# ── 实例身份 ──

class InstanceConfigResponse(BaseModel):
    """本实例身份信息"""
    instance_id: str
    public_id: str | None = None
    display_name: str = ""
    public_url: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class InstanceConfigUpdate(BaseModel):
    """更新实例身份"""
    display_name: str | None = None
    public_url: str | None = None
    public_id: str | None = None


# ── 对等端 ──

class PeerCreate(BaseModel):
    """添加对等端。remote_url 可选：留空则自动从 GitHub 注册表获取对方的公网 URL。"""
    peer_public_id: str = Field(..., min_length=1, max_length=50, description="对方公网 ID")
    display_name: str = Field(..., min_length=1, max_length=100, description="实例代号（唯一，用作ID前缀）")
    remote_url: str = Field(default="", max_length=500, description="ws://host:port/federation/ws（选填，留空则从 GitHub 注册表自动获取）")
    shared_secret: str = Field(..., min_length=8, description="共享密钥（明文，服务端加密存储）")


class PeerUpdate(BaseModel):
    """更新对等端"""
    display_name: str | None = None
    remote_url: str | None = None
    shared_secret: str | None = Field(default=None, min_length=8)
    is_enabled: bool | None = None


class PeerResponse(BaseModel):
    """对等端响应（不含密钥明文）"""
    id: int
    peer_public_id: str
    display_name: str
    remote_url: str
    is_enabled: bool
    connection_state: str
    last_connected_at: str | None = None
    url_rotated_at: str | None = None
    url_rotation_count: int = 0
    remote_url_backup: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ── 联邦实体（替代 GroupShare / DMShare） ──

class FederatedEntityResponse(BaseModel):
    """联邦实体信息"""
    id: int
    federated_id: str
    peer_id: int
    peer_display_name: str = ""
    entity_type: str  # group / dm / user / agent
    local_ref_id: str
    display_name: str = ""
    is_enabled: bool
    direction: str
    created_at: str | None = None
    updated_at: str | None = None


class FederatedEntityUpdate(BaseModel):
    """更新联邦实体（管理员操作）"""
    is_enabled: bool | None = None
    direction: str | None = None  # incoming → bidirectional


# ── 注册表 ──

class RegistryEntry(BaseModel):
    """GitHub 注册表中的单个实例条目"""
    public_id: str
    display_name: str
    public_url: str = ""
    registered_at: str | None = None
    contact: str = ""


class FederationRegistry(BaseModel):
    """GitHub 公开注册表"""
    version: int
    updated_at: str
    instances: dict[str, RegistryEntry]
