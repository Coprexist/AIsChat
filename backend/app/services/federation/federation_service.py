"""
联邦通信服务（v1.0.0 ID前缀替代注册表）

v0.3.0 → v1.0.0 变更：
  删除: share_group, unshare_group, share_dm_with_peer, unshare_dm,
        list_group_shares, get_dm_shares_for_session, lookup_local_conversation_by_uuid,
        _handle_conversation_announce, _handle_conversation_ack
  新增: register_federated_entity, get_federated_entity, list_federated_entities,
        enqueue_profile_update, flush_profile_updates_to_peer, is_group_federated
  GitHub 注册改为可选（不再强制要求注册）
"""
import uuid
import hmac
import hashlib
import os
import time
import base64
import json
import secrets
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_

from app.utils.crypto import encrypt_api_key, decrypt_api_key
from app.config import settings
from app.models.federation import InstanceConfig, FederationPeer, FederatedEntity, PendingProfileUpdate
import httpx

logger = logging.getLogger(__name__)


# ── 错误码（结构化，前端可据此处理 UI 状态） ──

class FedError:
    """联邦通信错误码常量"""
    REGISTRY_CONFLICT = "REGISTRY_CONFLICT"         # 公网 ID 已被占用
    URL_UNREACHABLE = "URL_UNREACHABLE"             # 公网 URL 不可达
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"         # URL 端点返回的 ID 与注册 ID 不一致
    TOKEN_MISSING = "TOKEN_MISSING"                 # 未配置 GitHub Token
    TOKEN_INVALID = "TOKEN_INVALID"                 # GitHub Token 无效/已过期
    SHA_CONFLICT = "SHA_CONFLICT"                   # 注册表并发修改冲突
    NETWORK_ERROR = "NETWORK_ERROR"                 # 网络不可达
    INSTANCE_NOT_INIT = "INSTANCE_NOT_INIT"         # 实例尚未初始化
    MISSING_PUBLIC_URL = "MISSING_PUBLIC_URL"       # 未设置公网 URL
    RATE_LIMITED = "RATE_LIMITED"                   # GitHub API 速率限制
    DISPLAY_NAME_CONFLICT = "DISPLAY_NAME_CONFLICT" # 实例代号重复


def _error(code: str, message: str, **extra) -> dict:
    """构建结构化错误响应"""
    return {"success": False, "error_code": code, "message": message, **extra}


# ── 实例配置查询辅助 ──

async def _get_instance_config(db: AsyncSession):
    """获取单例 InstanceConfig ORM 对象（复用，消除重复查询）"""
    result = await db.execute(select(InstanceConfig).where(InstanceConfig.id == 1))
    return result.scalar_one_or_none()


# ── ULID 生成（纯 Python，零依赖） ──

_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

def _encode_base32(value: int, length: int) -> str:
    """将整数编码为指定长度的 Base32 字符串"""
    chars = []
    for _ in range(length):
        chars.append(_BASE32[value & 0x1F])
        value >>= 5
    return ''.join(reversed(chars))

def generate_ulid() -> str:
    """生成 ULID"""
    timestamp = int(time.time() * 1000)
    random_bytes = os.urandom(10)
    random_int = int.from_bytes(random_bytes, 'big')
    ts_part = _encode_base32(timestamp, 10)
    rand_part = _encode_base32(random_int, 16)
    return ts_part + rand_part

def generate_public_id() -> str:
    """生成 AIsChat 公网 ID（AIsChat- + ULID）"""
    return f"AIsChat-{generate_ulid()}"

def build_federated_id(peer_display_name: str, entity_type: str, local_id: int | str) -> str:
    """构建联邦 ID: {实例代号}:{类型}:{本地ID}，如 大同AI:g:42"""
    return f"{peer_display_name}:{entity_type}:{local_id}"

def parse_federated_id(federated_id: str) -> tuple[str, str, str]:
    """解析联邦 ID → (实例代号, 实体类型, 本地ID)"""
    parts = federated_id.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"无效的联邦 ID 格式: {federated_id}")
    return parts[0], parts[1], parts[2]


# ── 实例身份 ──

async def initialize_instance(db: AsyncSession) -> dict:
    """首次启动生成子网 UUID v4 + 公网 ULID"""
    config = await _get_instance_config(db)
    if config is None:
        config = InstanceConfig(
            id=1,
            instance_id=str(uuid.uuid4()),
            public_id=generate_public_id(),
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
        logger.info(f"🌐 首次启动，实例子网 ID: {config.instance_id}, 公网 ID: {config.public_id}")
    elif not config.public_id:
        config.public_id = generate_public_id()
        config.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        await db.refresh(config)
        logger.info(f"🌐 补生成公网 ID: {config.public_id}")
    return _instance_config_to_dict(config)


async def get_instance_info(db: AsyncSession) -> dict:
    """获取本实例身份信息"""
    config = await _get_instance_config(db)
    if config is None:
        return await initialize_instance(db)
    return _instance_config_to_dict(config)


async def update_instance_info(
    db: AsyncSession,
    display_name: str | None = None,
    public_url: str | None = None,
    public_id: str | None = None,
) -> dict:
    """更新实例身份信息"""
    config = await _get_instance_config(db)
    if config is None:
        config = InstanceConfig(id=1, instance_id=str(uuid.uuid4()))
        db.add(config)
        await db.flush()

    if display_name is not None and display_name.strip():
        name = display_name.strip()
        # 唯一性校验：不能与已有 peer 的 display_name 冲突
        existing = await db.execute(
            select(FederationPeer).where(FederationPeer.display_name == name)
        )
        if existing.scalar_one_or_none():
            return {"error": True, "message": f"实例代号「{name}」已被对等端占用，请换一个"}
        config.display_name = name
    elif display_name is not None:
        config.display_name = display_name
    if public_url is not None:
        config.public_url = public_url
    if public_id is not None:
        config.public_id = public_id

    config.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(config)
    logger.info(f"🌐 更新实例信息: display_name={config.display_name}, public_id={config.public_id}")
    return {"success": True, "instance": _instance_config_to_dict(config)}


async def regenerate_public_id(db: AsyncSession) -> dict:
    """重新生成公网 ID"""
    config = await _get_instance_config(db)
    if config is None:
        return _error(FedError.INSTANCE_NOT_INIT, "实例尚未初始化")
    old_id = config.public_id
    config.public_id = generate_public_id()
    config.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(config)
    logger.info(f"🔄 更换公网 ID: {old_id} → {config.public_id}")
    return {"success": True, "old_public_id": old_id, "public_id": config.public_id}


# ── GitHub Token 管理（数据库存储，前端图形化配置） ──

async def set_github_token(db: AsyncSession, token: str) -> dict:
    """前端配置 GitHub Token（加密存储到 instance_config）"""
    config = await _get_instance_config(db)
    if config is None:
        return _error(FedError.INSTANCE_NOT_INIT, "实例尚未初始化")
    config.github_token_encrypted = encrypt_api_key(token)
    config.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    logger.info("🔑 GitHub Token 已更新（加密存储）")
    return {"success": True, "message": "GitHub Token 已加密保存"}


def _get_active_github_token(config) -> str | None:
    """获取活跃的 GitHub Token（数据库优先，.env 兜底）"""
    if config and config.github_token_encrypted:
        try:
            return decrypt_api_key(config.github_token_encrypted)
        except Exception:
            pass
    if settings.github_token:
        return settings.github_token
    return None


# ── GitHub 注册表（可选：仅为公开发现，非强制性） ──

REGISTRY_URL = f"https://api.github.com/repos/{settings.registry_repo}/contents/{settings.registry_file}"


async def fetch_github_registry(db: AsyncSession | None = None) -> dict:
    """从 GitHub Contents API 拉取注册表（可选功能）"""
    token = settings.github_token
    if db:
        config = await _get_instance_config(db)
        active = _get_active_github_token(config) if config else None
        if active:
            token = active

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(REGISTRY_URL, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                registry = json.loads(content)
                return {
                    "success": True,
                    "registry": registry,
                    "sha": data["sha"],
                    "updated_at": registry.get("updated_at", ""),
                }
            elif resp.status_code == 401:
                return _error(FedError.TOKEN_INVALID, "GitHub Token 无效或已过期")
            elif resp.status_code == 404:
                return {
                    "success": True,
                    "registry": {"version": 1, "updated_at": "", "instances": {}},
                    "sha": None,
                }
            elif resp.status_code == 403:
                try:
                    gh_msg = resp.json().get("message", "")
                except Exception:
                    gh_msg = ""
                if "rate limit" in gh_msg.lower():
                    return _error(FedError.RATE_LIMITED, "GitHub API 速率限制，请稍后重试")
                else:
                    return _error(FedError.TOKEN_INVALID, f"GitHub 拒绝访问 (403): {gh_msg}")
            else:
                return _error(FedError.NETWORK_ERROR, f"GitHub API 返回 {resp.status_code}")
    except httpx.HTTPError as e:
        logger.warning(f"拉取 GitHub 注册表失败: {e}")
        return _error(FedError.NETWORK_ERROR, f"网络错误: {e}")


async def register_public_id(db: AsyncSession) -> dict:
    """
    将当前实例的公网 ID 注册到 GitHub 注册表（可选功能）。

    注册表只是一个公开"电话本"，让其他实例可以发现你。
    不注册也能联邦通信——只要双方知道彼此 URL 和共享密钥。
    """
    config = await _get_instance_config(db)
    if config is None:
        return _error(FedError.INSTANCE_NOT_INIT, "实例尚未初始化")

    token = _get_active_github_token(config)
    if not token:
        return _error(
            FedError.TOKEN_MISSING,
            "未配置 GitHub Token。注册到 GitHub 公开目录需要 Token。\n"
            "提示：不想公开注册也可以直接联邦通信——只要对方知道你的 URL 和共享密钥即可。\n"
            "获取 Token: https://github.com/settings/tokens/new → 勾选 repo（classic token）",
        )

    if not config.public_id:
        return _error(FedError.INSTANCE_NOT_INIT, "实例尚未生成公网 ID")

    public_url = (config.public_url or "").strip()
    if not public_url:
        return _error(FedError.MISSING_PUBLIC_URL, "请先设置公网 URL 再进行注册")

    url_error = await _validate_public_url(public_url, config.public_id)
    if url_error:
        if "身份不匹配" in url_error:
            return _error(FedError.IDENTITY_MISMATCH, url_error)
        return _error(FedError.URL_UNREACHABLE, f"公网 URL 验证失败: {url_error}")

    registry_result = await fetch_github_registry(db)
    if not registry_result["success"]:
        error_code = registry_result.get("error_code", FedError.NETWORK_ERROR)
        return _error(error_code, registry_result["message"])

    registry = registry_result["registry"]
    current_sha = registry_result["sha"]

    existing = registry.get("instances", {}).get(config.public_id)
    if existing:
        return _error(
            FedError.REGISTRY_CONFLICT,
            f"公网 ID「{config.public_id}」已被占用。\n"
            f"占用实例: {existing.get('display_name', '未知')}，"
            f"注册时间: {existing.get('registered_at', '未知')}。\n"
            f"请点击「重新生成 ID」更换公网 ID。",
            existing_entry=existing,
        )

    registry["instances"][config.public_id] = {
        "display_name": config.display_name or "",
        "public_url": config.public_url or "",
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    registry["updated_at"] = datetime.now(timezone.utc).isoformat()

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }
    body = {
        "message": f"Register {config.public_id}",
        "content": base64.b64encode(
            json.dumps(registry, indent=2, ensure_ascii=False).encode("utf-8")
        ).decode("ascii"),
    }
    if current_sha:
        body["sha"] = current_sha

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(REGISTRY_URL, json=body, headers=headers)
            if resp.status_code in (200, 201):
                logger.info(f"✅ 公网 ID {config.public_id} 已注册到 GitHub 注册表")
                return {
                    "success": True,
                    "message": f"公网 ID「{config.public_id}」已成功注册到 GitHub 注册表",
                    "registry_url": f"https://github.com/{settings.registry_repo}/blob/main/{settings.registry_file}",
                }
            elif resp.status_code == 401:
                return _error(FedError.TOKEN_INVALID, "GitHub Token 无效或已过期")
            elif resp.status_code == 403:
                return _error(FedError.TOKEN_INVALID, "GitHub 拒绝访问 (403)，请检查 Token 权限")
            elif resp.status_code == 409:
                return _error(FedError.SHA_CONFLICT, "注册表已被他人修改，请重试")
            else:
                return _error(FedError.NETWORK_ERROR, f"GitHub API 返回 {resp.status_code}")
    except httpx.HTTPError as e:
        return _error(FedError.NETWORK_ERROR, f"GitHub API 请求失败: {e}")


async def _validate_public_url(public_url: str, expected_public_id: str) -> str | None:
    """验证 public_url 是否指向运行中的 AIsChat 实例"""
    parsed = urlparse(public_url)
    host = parsed.hostname
    scheme = parsed.scheme
    if not host:
        return f"无法解析公网 URL 中的域名: {public_url}"
    http_scheme = "https" if scheme == "wss" else "http"
    port = f":{parsed.port}" if parsed.port else ""
    identity_url = f"{http_scheme}://{host}{port}/api/federation/identity"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(identity_url)
            if resp.status_code != 200:
                return f"实例端点返回 {resp.status_code}（期望 200）"
            data = resp.json()
            remote_public_id = data.get("public_id", "")
            if remote_public_id != expected_public_id:
                return f"身份不匹配：远端实例公网 ID 为「{remote_public_id}」，当前注册 ID 为「{expected_public_id}」"
            return None
    except httpx.ConnectTimeout:
        return f"连接超时: 无法在 8 秒内连接到 {host}{port}"
    except httpx.ConnectError:
        return f"连接失败: 无法连接到 {host}{port}"


# ── 对等端管理 ──

async def list_peers(db: AsyncSession) -> list[dict]:
    """列出所有对等端"""
    result = await db.execute(select(FederationPeer).order_by(FederationPeer.created_at.asc()))
    peers = result.scalars().all()
    return [_peer_to_dict(p) for p in peers]


async def add_peer(
    db: AsyncSession,
    peer_public_id: str,
    remote_url: str,
    shared_secret: str,
    display_name: str = "",
) -> dict:
    """
    添加对等端（加密存储共享密钥）。display_name 唯一性校验。

    remote_url 可选：留空时自动从 GitHub 注册表获取对方的公网 URL。
    如果对方未注册 GitHub 注册表，则需要手动提供 URL 或直接告诉对方你的 URL。
    """
    # 检查 display_name 唯一性
    if display_name:
        existing_name = await db.execute(
            select(FederationPeer).where(FederationPeer.display_name == display_name)
        )
        if existing_name.scalar_one_or_none():
            return {"error": True, "message": f"实例代号「{display_name}」已被使用，请换一个名称"}

    # 检查 peer_public_id 是否已存在
    existing = await db.execute(
        select(FederationPeer).where(FederationPeer.peer_public_id == peer_public_id)
    )
    if existing.scalar_one_or_none():
        return {"error": True, "message": f"对等端 {peer_public_id} 已存在"}

    # 如果 remote_url 为空，尝试从 GitHub 注册表获取
    if not remote_url.strip():
        logger.info(f"🌐 remote_url 未提供，尝试从 GitHub 注册表获取 {peer_public_id}...")
        registry_result = await fetch_github_registry(db)
        if registry_result.get("success"):
            registry = registry_result.get("registry", {})
            instances = registry.get("instances", {})
            entry = instances.get(peer_public_id)
            if entry and entry.get("public_url", "").strip():
                remote_url = entry["public_url"].strip()
                logger.info(f"🌐 从 GitHub 注册表获取到 URL: {remote_url}")
            else:
                logger.info(f"🌐 未在 GitHub 注册表中找到 {peer_public_id}，remote_url 留空（仅可被对方主动连接）")
        else:
            logger.info(f"🌐 无法连接 GitHub 注册表，remote_url 留空（仅可被对方主动连接）")

    encrypted_secret = encrypt_api_key(shared_secret)
    peer = FederationPeer(
        peer_public_id=peer_public_id,
        display_name=display_name,
        remote_url=remote_url,
        shared_secret_encrypted=encrypted_secret,
    )
    db.add(peer)
    await db.commit()
    await db.refresh(peer)

    logger.info(f"🌐 添加对等端: {display_name or peer_public_id} ({remote_url})")
    return {"success": True, "peer": _peer_to_dict(peer)}


async def update_peer(
    db: AsyncSession,
    peer_id: int,
    display_name: str | None = None,
    remote_url: str | None = None,
    shared_secret: str | None = None,
    is_enabled: bool | None = None,
) -> dict:
    """更新对等端配置。display_name 变更会级联更新 federated_entities 中的 federated_id。"""
    result = await db.execute(select(FederationPeer).where(FederationPeer.id == peer_id))
    peer = result.scalar_one_or_none()
    if peer is None:
        return {"error": True, "message": "对等端不存在"}

    old_display_name = peer.display_name

    if display_name is not None:
        # 唯一性校验
        if display_name != old_display_name:
            existing_name = await db.execute(
                select(FederationPeer).where(
                    FederationPeer.display_name == display_name,
                    FederationPeer.id != peer_id,
                )
            )
            if existing_name.scalar_one_or_none():
                return {"error": True, "message": f"实例代号「{display_name}」已被使用"}
        peer.display_name = display_name

    if remote_url is not None:
        peer.remote_url = remote_url
    if shared_secret is not None:
        peer.shared_secret_encrypted = encrypt_api_key(shared_secret)
    if is_enabled is not None:
        peer.is_enabled = is_enabled

    peer.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(peer)

    # 如果 display_name 变更，级联更新 federated_entities 中的 federated_id
    if display_name and display_name != old_display_name and old_display_name:
        entities = await db.execute(
            select(FederatedEntity).where(
                FederatedEntity.peer_id == peer_id,
                FederatedEntity.federated_id.like(f"{old_display_name}:%"),
            )
        )
        for entity in entities.scalars().all():
            old_prefix = f"{old_display_name}:"
            new_prefix = f"{display_name}:"
            if entity.federated_id.startswith(old_prefix):
                entity.federated_id = new_prefix + entity.federated_id[len(old_prefix):]
        await db.commit()
        logger.info(f"🌐 实例代号变更 {old_display_name} → {display_name}，已级联更新 {len(entities.scalars().all())} 条联邦实体")

    logger.info(f"🌐 更新对等端 #{peer_id}: {peer.peer_public_id}")
    return {"success": True, "peer": _peer_to_dict(peer)}


async def remove_peer(db: AsyncSession, peer_id: int) -> dict:
    """移除对等端（级联删除联邦实体）"""
    result = await db.execute(select(FederationPeer).where(FederationPeer.id == peer_id))
    peer = result.scalar_one_or_none()
    if peer is None:
        return {"error": True, "message": "对等端不存在"}

    peer_name = peer.peer_public_id
    await db.delete(peer)
    await db.commit()

    logger.info(f"🌐 移除对等端 #{peer_id}: {peer_name}")
    return {"success": True, "message": f"对等端「{peer_name}」已移除"}


async def get_peer_by_public_id(db: AsyncSession, public_id: str):
    """根据公网 ID 查找对等端"""
    result = await db.execute(
        select(FederationPeer).where(FederationPeer.peer_public_id == public_id)
    )
    return result.scalar_one_or_none()


async def get_peer_by_display_name(db: AsyncSession, display_name: str):
    """根据实例代号（display_name）查找对等端"""
    result = await db.execute(
        select(FederationPeer).where(FederationPeer.display_name == display_name)
    )
    return result.scalar_one_or_none()


async def get_decrypted_secret(peer) -> str:
    """解密对等端的共享密钥"""
    return decrypt_api_key(peer.shared_secret_encrypted)


async def update_peer_connection_state(db: AsyncSession, peer_id: int, state: str) -> None:
    """更新对等端连接状态"""
    result = await db.execute(select(FederationPeer).where(FederationPeer.id == peer_id))
    peer = result.scalar_one_or_none()
    if peer is None:
        return
    peer.connection_state = state
    if state == "connected":
        peer.last_connected_at = datetime.now(timezone.utc).replace(tzinfo=None)
    peer.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()


# ── 联邦实体管理（替代 share_group / share_dm） ──

async def register_federated_entity(
    db: AsyncSession,
    peer_id: int,
    entity_type: str,
    federated_id: str,
    local_ref_id: str,
    display_name: str = "",
    direction: str = "incoming",
) -> dict:
    """
    注册一个新的联邦实体（接收端：管理员接受远端共享后调用）。

    federated_id 格式: {实例代号}:{类型}:{远端本地ID}，如 大同AI:g:42
    """
    # 检查 peer 存在
    peer_result = await db.execute(select(FederationPeer).where(FederationPeer.id == peer_id))
    peer = peer_result.scalar_one_or_none()
    if peer is None:
        return {"error": True, "message": "对等端不存在"}

    # 检查 federated_id 唯一性
    existing = await db.execute(
        select(FederatedEntity).where(FederatedEntity.federated_id == federated_id)
    )
    if existing.scalar_one_or_none():
        return {"error": True, "message": f"联邦实体「{federated_id}」已存在"}

    entity = FederatedEntity(
        federated_id=federated_id,
        peer_id=peer_id,
        entity_type=entity_type,
        local_ref_id=local_ref_id,
        display_name=display_name,
        direction=direction,
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    logger.info(f"🌐 注册联邦实体: {federated_id} → local {entity_type}={local_ref_id}")
    return {"success": True, "entity": _entity_to_dict(entity, peer.display_name)}


async def remove_federated_entity(db: AsyncSession, entity_id: int) -> dict:
    """移除联邦实体"""
    result = await db.execute(select(FederatedEntity).where(FederatedEntity.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        return {"error": True, "message": "联邦实体不存在"}
    fid = entity.federated_id
    await db.delete(entity)
    await db.commit()
    logger.info(f"🌐 移除联邦实体: {fid}")
    return {"success": True, "message": f"联邦实体「{fid}」已移除"}


async def get_federated_entity_by_fid(db: AsyncSession, federated_id: str):
    """根据联邦 ID 查找实体（返回 ORM 对象或 None）"""
    result = await db.execute(
        select(FederatedEntity).where(
            FederatedEntity.federated_id == federated_id,
            FederatedEntity.is_enabled == True,
        )
    )
    return result.scalar_one_or_none()


async def get_federated_entity_by_local(
    db: AsyncSession, entity_type: str, local_ref_id: str
):
    """根据本地 ID 查找联邦实体（返回 ORM 对象或 None）"""
    result = await db.execute(
        select(FederatedEntity).where(
            FederatedEntity.entity_type == entity_type,
            FederatedEntity.local_ref_id == local_ref_id,
            FederatedEntity.is_enabled == True,
        )
    )
    return result.scalar_one_or_none()


async def list_federated_entities(db: AsyncSession, peer_id: int | None = None) -> list[dict]:
    """列出联邦实体，可选按 peer 过滤"""
    stmt = select(FederatedEntity, FederationPeer.display_name).join(
        FederationPeer, FederatedEntity.peer_id == FederationPeer.id
    )
    if peer_id is not None:
        stmt = stmt.where(FederatedEntity.peer_id == peer_id)
    stmt = stmt.order_by(FederatedEntity.created_at.asc())

    result = await db.execute(stmt)
    entities = []
    for entity, peer_name in result.all():
        d = _entity_to_dict(entity, peer_name)
        entities.append(d)
    return entities


async def update_federated_entity(
    db: AsyncSession,
    entity_id: int,
    is_enabled: bool | None = None,
    direction: str | None = None,
) -> dict:
    """更新联邦实体（管理员操作）"""
    result = await db.execute(select(FederatedEntity).where(FederatedEntity.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        return {"error": True, "message": "联邦实体不存在"}

    if is_enabled is not None:
        entity.is_enabled = is_enabled
    if direction is not None:
        entity.direction = direction

    entity.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(entity)

    # 获取 peer display_name
    peer_result = await db.execute(select(FederationPeer).where(FederationPeer.id == entity.peer_id))
    peer = peer_result.scalar_one_or_none()
    return {"success": True, "entity": _entity_to_dict(entity, peer.display_name if peer else "")}


async def is_group_federated(db: AsyncSession, group_id: int) -> bool:
    """检查群聊是否启用了联邦共享"""
    result = await db.execute(
        select(FederatedEntity).where(
            FederatedEntity.entity_type == "group",
            FederatedEntity.local_ref_id == str(group_id),
            FederatedEntity.is_enabled == True,
        )
    )
    return result.first() is not None


async def is_dm_federated(db: AsyncSession, session_id: str) -> bool:
    """检查 DM 会话是否启用了联邦共享"""
    result = await db.execute(
        select(FederatedEntity).where(
            FederatedEntity.entity_type == "dm",
            FederatedEntity.local_ref_id == session_id,
            FederatedEntity.is_enabled == True,
        )
    )
    return result.first() is not None


async def get_federated_peers_for_entity(
    db: AsyncSession, entity_type: str, local_ref_id: str
) -> list:
    """获取共享某实体的所有已连接对等端（返回 FederationPeer ORM 对象列表）"""
    result = await db.execute(
        select(FederationPeer)
        .join(FederatedEntity, FederatedEntity.peer_id == FederationPeer.id)
        .where(
            FederatedEntity.entity_type == entity_type,
            FederatedEntity.local_ref_id == local_ref_id,
            FederatedEntity.is_enabled == True,
            FederationPeer.is_enabled == True,
            FederationPeer.connection_state == "connected",
        )
        .distinct()
    )
    return result.scalars().all()


# ── Profile 同步队列 ──

async def enqueue_profile_update(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    field: str,
    new_value: str,
) -> None:
    """记录本地实体变更到同步队列"""
    update = PendingProfileUpdate(
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        new_value=new_value,
    )
    db.add(update)
    await db.commit()
    logger.debug(f"📝 入队 profile 更新: {entity_type}#{entity_id} {field}={new_value}")


async def get_pending_updates(
    db: AsyncSession, entity_type: str | None = None
) -> list[PendingProfileUpdate]:
    """获取待同步的 profile 变更。可选按类型过滤。"""
    stmt = select(PendingProfileUpdate).order_by(PendingProfileUpdate.changed_at.asc())
    if entity_type:
        stmt = stmt.where(PendingProfileUpdate.entity_type == entity_type)
    result = await db.execute(stmt)
    return result.scalars().all()


async def clear_pending_updates(db: AsyncSession, update_ids: list[int]) -> None:
    """清除已同步的 profile 变更"""
    if not update_ids:
        return
    await db.execute(
        delete(PendingProfileUpdate).where(PendingProfileUpdate.id.in_(update_ids))
    )
    await db.commit()


async def get_sync_interval_minutes(db: AsyncSession) -> int:
    """获取联邦 profile 同步间隔（分钟），默认 30"""
    from app.models.system_settings import SystemSettings
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    settings_row = result.scalar_one_or_none()
    if settings_row:
        return getattr(settings_row, "federation_sync_interval_minutes", 720) or 720
    return 720


# ── 群联邦共享控制（v1.0.0: 群主/AI制作者控制每个群的联邦共享）──

async def can_manage_group_federation(db: AsyncSession, group_id: int, user_id: int) -> bool:
    """检查用户是否有权管理群联邦共享设置"""
    from app.models.group import Group, GroupMember
    from app.models.agent import Agent
    from app.models.user import User

    # 情况0: 系统管理员始终有权
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user and user.role == "admin":
        return True

    # 查群信息
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        return False

    # 情况1: 群主是人类，且当前用户就是群主
    if group.owner_type == "human" and group.owner_id == user_id:
        return True

    # 情况2: 群主是 AI，检查当前用户是否是这个 AI 的创建者
    if group.owner_type == "ai":
        agent_result = await db.execute(
            select(Agent).where(Agent.user_id == group.owner_id)
        )
        agent = agent_result.scalar_one_or_none()
        if agent and agent.owner_id == user_id:
            return True

    # 情况3: 当前用户是群的 human admin
    member_result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.member_type == "human",
            GroupMember.member_id == user_id,
            GroupMember.role.in_(["owner", "admin"]),
        )
    )
    if member_result.scalar_one_or_none():
        return True

    return False


async def get_group_federation_peers(
    db: AsyncSession, group_id: int, user_id: int
) -> dict:
    """
    获取群联邦共享状态：列出所有对等端，标记哪些已共享此群。
    需要 can_manage_group_federation 权限。
    """
    if not await can_manage_group_federation(db, group_id, user_id):
        return {"error": True, "message": "无权限管理此群的联邦共享设置"}

    my_info = await get_instance_info(db)
    my_display_name = my_info.get("display_name", "") or ""

    # 列出所有启用的对等端
    peers = await list_peers(db)

    # 查当前群已有的 outgoing 联邦实体
    result = await db.execute(
        select(FederatedEntity).where(
            FederatedEntity.entity_type == "group",
            FederatedEntity.local_ref_id == str(group_id),
            FederatedEntity.direction == "outgoing",
        )
    )
    outgoing_entities = result.scalars().all()
    shared_peer_ids = {e.peer_id for e in outgoing_entities}

    peer_list = []
    for peer in peers:
        peer_list.append({
            "peer_id": peer["id"],
            "display_name": peer["display_name"] or peer["peer_public_id"],
            "peer_public_id": peer["peer_public_id"],
            "is_connected": peer["connection_state"] == "connected",
            "is_shared": peer["id"] in shared_peer_ids,
            "federated_id": build_federated_id(my_display_name, "g", group_id)
                if my_display_name else "",
        })

    return {
        "success": True,
        "group_id": group_id,
        "my_display_name": my_display_name,
        "peers": peer_list,
    }


async def share_group_to_peers(
    db: AsyncSession,
    group_id: int,
    peer_ids: list[int],
    user_id: int,
) -> dict:
    """
    将群共享到指定对等端。
    - 创建 FederatedEntity 记录（direction=outgoing）
    - 通过 WebSocket 发送 entity_announce 给已连接的对等端
    """
    if not await can_manage_group_federation(db, group_id, user_id):
        return {"error": True, "message": "无权限管理此群的联邦共享设置"}

    my_info = await get_instance_info(db)
    my_display_name = my_info.get("display_name", "") or ""
    if not my_display_name:
        return {"error": True, "message": "请先在实例设置中配置「实例代号」（display_name）"}

    # 获取群信息用于 display_name
    from app.models.group import Group
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()
    if group is None:
        return {"error": True, "message": "群聊不存在"}

    shared = []
    already_shared = []
    not_connected = []

    for peer_id in peer_ids:
        # 检查 peer 存在
        peer_result = await db.execute(
            select(FederationPeer).where(FederationPeer.id == peer_id)
        )
        peer = peer_result.scalar_one_or_none()
        if peer is None:
            continue

        # 检查是否已有 outgoing 记录
        existing = await db.execute(
            select(FederatedEntity).where(
                FederatedEntity.peer_id == peer_id,
                FederatedEntity.entity_type == "group",
                FederatedEntity.local_ref_id == str(group_id),
                FederatedEntity.direction == "outgoing",
            )
        )
        if existing.scalar_one_or_none():
            already_shared.append(peer.display_name or peer.peer_public_id)
            continue

        # 创建 FederatedEntity（内部 federated_id 加后缀保证唯一性）
        internal_federated_id = f"{my_display_name}:g:{group_id}:out:{peer_id}"
        entity = FederatedEntity(
            federated_id=internal_federated_id,
            peer_id=peer_id,
            entity_type="group",
            local_ref_id=str(group_id),
            display_name=group.name,
            direction="outgoing",
        )
        db.add(entity)

        # 如果对等端已连接，发送 entity_announce（只传 entity_type + local_id）
        if peer.connection_state == "connected":
            from app.services.federation_manager import federation_manager
            sent = await federation_manager.announce_entity(
                peer.peer_public_id,
                entity_type="group",
                local_id=str(group_id),
                display_name=group.name,
                direction="outgoing",
            )
            if not sent:
                not_connected.append(peer.display_name or peer.peer_public_id)
        else:
            not_connected.append(peer.display_name or peer.peer_public_id)

        shared.append(peer.display_name or peer.peer_public_id)

    await db.commit()

    logger.info(f"🌐 群 {group_id} 已共享到 {len(shared)} 个对等端: {shared}")
    return {
        "success": True,
        "shared": shared,
        "already_shared": already_shared,
        "not_connected": not_connected,
    }


async def unshare_group_from_peers(
    db: AsyncSession,
    group_id: int,
    peer_ids: list[int],
    user_id: int,
) -> dict:
    """
    取消群对指定对等端的联邦共享。
    - 删除 FederatedEntity 记录
    - 通过 WebSocket 发送 entity_unannounce 给已连接的对等端
    """
    if not await can_manage_group_federation(db, group_id, user_id):
        return {"error": True, "message": "无权限管理此群的联邦共享设置"}

    unshared = []
    not_found = []

    for peer_id in peer_ids:
        # 查找 outgoing 实体
        existing = await db.execute(
            select(FederatedEntity).where(
                FederatedEntity.peer_id == peer_id,
                FederatedEntity.entity_type == "group",
                FederatedEntity.local_ref_id == str(group_id),
                FederatedEntity.direction == "outgoing",
            )
        )
        entity = existing.scalar_one_or_none()
        if entity is None:
            not_found.append(str(peer_id))
            continue

        peer_result = await db.execute(
            select(FederationPeer).where(FederationPeer.id == peer_id)
        )
        peer = peer_result.scalar_one_or_none()
        peer_name = peer.display_name or (peer.peer_public_id if peer else str(peer_id))

        # 删除本地记录
        await db.delete(entity)

        # 如果对等端已连接，发送 entity_unannounce（只传 entity_type + local_id）
        if peer and peer.connection_state == "connected":
            from app.services.federation_manager import federation_manager
            await federation_manager.unannounce_entity(
                peer.peer_public_id,
                entity_type="group",
                local_id=str(group_id),
            )

        unshared.append(peer_name)

    await db.commit()

    logger.info(f"🌐 群 {group_id} 已取消共享到 {len(unshared)} 个对等端: {unshared}")
    return {
        "success": True,
        "unshared": unshared,
        "not_found": not_found,
    }


# ── 远程消息处理 ──

async def handle_remote_message(
    db: AsyncSession,
    group_id: int,
    msg_dict: dict,
    source_public_id: str,
) -> "Message":
    """持久化来自远程实例的消息"""
    from app.models.message import Message

    message = Message(
        group_id=group_id,
        sender_type=msg_dict.get("sender_type", "human"),
        sender_id=0,
        sender_name=msg_dict.get("sender_name") or f"{source_public_id} User",
        content=msg_dict.get("content", ""),
        reply_to=msg_dict.get("reply_to"),
        source_public_id=source_public_id,
        sender_avatar_url=msg_dict.get("sender_avatar_url", ""),
    )
    remote_time = msg_dict.get("created_at")
    if remote_time:
        try:
            from datetime import datetime as dt
            message.created_at = dt.fromisoformat(remote_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    db.add(message)
    await db.flush()
    logger.info(f"🌐 持久化远程消息: group={group_id} from={source_public_id} id={message.id}")
    return message


async def persist_remote_dm_message(
    db: AsyncSession, session_id: str, msg_dict: dict, source_public_id: str,
):
    """持久化来自远程实例的 DM 消息"""
    from app.models.dm import DMMessage
    from datetime import datetime as dt

    dm_msg = DMMessage(
        session_id=session_id,
        sender_id=0,
        content=msg_dict.get("content", ""),
        reply_to=msg_dict.get("reply_to"),
        source_public_id=source_public_id,
    )
    remote_time = msg_dict.get("created_at")
    if remote_time:
        try:
            dm_msg.created_at = dt.fromisoformat(remote_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    db.add(dm_msg)
    await db.flush()
    return dm_msg


# ── HMAC 挑战-应答 ──

def hmac_response(secret: str, challenge: str) -> str:
    """计算挑战的 HMAC-SHA256 应答"""
    return hmac.new(
        secret.encode("utf-8"),
        challenge.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_challenge() -> str:
    """生成 256-bit 随机挑战字符串"""
    return secrets.token_hex(32)


def url_rotate_hmac(secret: str, rotation_id: str, *fields: str) -> str:
    """URL 轮换消息 HMAC-SHA256"""
    message = rotation_id + "|" + "|".join(fields)
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def validate_rotation_url(url: str, current_url: str) -> str | None:
    """验证轮换 URL 合法性"""
    if not url:
        return "URL 不能为空"
    if not (url.startswith("ws://") or url.startswith("wss://")):
        return "URL 必须以 ws:// 或 wss:// 开头"
    if not url.endswith("/federation/ws"):
        return "URL 必须以 /federation/ws 结尾"
    if url == current_url:
        return "新 URL 不能与当前 URL 相同"
    if len(url) > 500:
        return "URL 长度不能超过 500 字符"
    return None


async def update_peer_url(db: AsyncSession, peer_id: int, new_url: str) -> bool:
    """提交 URL 轮换"""
    from app.models.federation import FederationPeer as FP
    result = await db.execute(select(FP).where(FP.id == peer_id))
    peer = result.scalar_one_or_none()
    if peer is None:
        return False
    peer.remote_url_backup = peer.remote_url
    peer.remote_url = new_url
    peer.url_rotated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    peer.url_rotation_count = (peer.url_rotation_count or 0) + 1
    peer.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    logger.info(f"🌐 URL 轮换成功 #{peer_id}: {peer.remote_url_backup} → {new_url}")
    return True


async def rollback_peer_url(db: AsyncSession, peer_id: int) -> bool:
    """回退 URL 轮换"""
    result = await db.execute(select(FederationPeer).where(FederationPeer.id == peer_id))
    peer = result.scalar_one_or_none()
    if peer is None or not peer.remote_url_backup:
        return False
    peer.remote_url = peer.remote_url_backup
    peer.remote_url_backup = None
    peer.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    return True


# ── dict 转换 ──

def _instance_config_to_dict(config) -> dict:
    return {
        "instance_id": config.instance_id,
        "public_id": config.public_id,
        "display_name": config.display_name or "",
        "public_url": config.public_url or "",
        "github_token_configured": bool(config.github_token_encrypted),
        "created_at": str(config.created_at) if config.created_at else None,
        "updated_at": str(config.updated_at) if config.updated_at else None,
    }


def _peer_to_dict(peer) -> dict:
    return {
        "id": peer.id,
        "peer_public_id": peer.peer_public_id,
        "display_name": peer.display_name or "",
        "remote_url": peer.remote_url,
        "is_enabled": peer.is_enabled,
        "connection_state": peer.connection_state,
        "last_connected_at": str(peer.last_connected_at) if peer.last_connected_at else None,
        "url_rotated_at": str(peer.url_rotated_at) if peer.url_rotated_at else None,
        "url_rotation_count": peer.url_rotation_count or 0,
        "remote_url_backup": peer.remote_url_backup or None,
        "created_at": str(peer.created_at) if peer.created_at else None,
        "updated_at": str(peer.updated_at) if peer.updated_at else None,
    }


def _entity_to_dict(entity, peer_display_name: str = "") -> dict:
    return {
        "id": entity.id,
        "federated_id": entity.federated_id,
        "peer_id": entity.peer_id,
        "peer_display_name": peer_display_name,
        "entity_type": entity.entity_type,
        "local_ref_id": entity.local_ref_id,
        "display_name": entity.display_name or "",
        "is_enabled": entity.is_enabled,
        "direction": entity.direction,
        "created_at": str(entity.created_at) if entity.created_at else None,
        "updated_at": str(entity.updated_at) if entity.updated_at else None,
    }
