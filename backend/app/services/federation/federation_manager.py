"""
联邦连接管理器（v1.0.0 ID前缀替代注册表）

v0.3.0 → v1.0.0 变更：
  删除: conversation_uuid 映射, _handle_conversation_announce, _handle_conversation_ack
  新增: _handle_entity_announce（入站实体注册协议）
  转发逻辑改为 federated_id 前缀模式
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import defaultdict

import websockets
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.federation import FederatedEntity, FederationPeer
from app.services.federation_service import (
    get_peer_by_public_id,
    get_decrypted_secret,
    update_peer_connection_state,
    hmac_response,
    generate_challenge,
    handle_remote_message,
    get_instance_info,
    persist_remote_dm_message,
    get_federated_entity_by_fid,
    get_federated_peers_for_entity,
    build_federated_id,
    parse_federated_id,
    enqueue_profile_update,
    list_peers,
    register_federated_entity,
)

logger = logging.getLogger(__name__)

# 配置常量
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TIMEOUT = 60
RECONNECT_BASE = 5
RECONNECT_MAX = 300
RECONNECT_MULTIPLIER = 2
OUTBOX_MAX_SIZE = 1000

def _entity_type_char(entity_type: str) -> str:
    """将完整实体类型映射为单字符（用于 federated_id 拼接）"""
    return {"group": "g", "dm": "d", "user": "u", "agent": "a"}.get(entity_type, entity_type[0])


@dataclass
class PeerConnection:
    """单个对等端的连接状态"""
    websocket: "websockets.WebSocketClientProtocol | None" = None
    instance_id: str = ""
    public_id: str = ""
    peer_id: int = 0
    display_name: str = ""
    remote_url: str = ""
    connected_at: "datetime | None" = None
    last_heartbeat: "datetime | None" = None
    pending_outbox: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=OUTBOX_MAX_SIZE))
    handshake_complete: bool = False
    is_inbound: bool = False  # True = 入站连接（由 federation_ws.py 注册），heartbeat 跳过
    rotation_state: str | None = None
    rotation_id: str | None = None
    new_url: str | None = None
    last_rotation_at: "datetime | None" = None


async def _apply_display_name_update(db, entity_type: str, local_ref_id: str, new_value: str) -> None:
    """将远程 display_name 变更写入实际实体表"""
    from sqlalchemy import text
    try:
        rid = int(local_ref_id)
    except (ValueError, TypeError):
        return
    if entity_type == "group":
        await db.execute(text("UPDATE groups SET name = :n WHERE id = :i"), {"n": new_value, "i": rid})
    elif entity_type == "user":
        await db.execute(text("UPDATE users SET username = :n WHERE id = :i"), {"n": new_value, "i": rid})
    elif entity_type == "agent":
        await db.execute(text("UPDATE agents SET name = :n WHERE id = :i"), {"n": new_value, "i": rid})


async def _apply_avatar_update(db, entity_type: str, local_ref_id: str, new_value: str, peer=None) -> None:
    """将远程 avatar_url 变更写入实际实体表，并下载头像文件到本地"""
    from sqlalchemy import text
    try:
        rid = int(local_ref_id)
    except (ValueError, TypeError):
        return

    local_path = new_value
    # 如果是相对路径，尝试从远端下载头像文件
    if new_value and new_value.startswith("/") and peer and peer.remote_url:
        try:
            base = peer.remote_url.replace("wss://", "https://").replace("ws://", "http://")
            base = base.replace("/federation/ws", "")
            download_url = f"{base}{new_value}"
            import httpx
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.get(download_url)
                if resp.status_code == 200:
                    import os, uuid
                    fname = f"user_{rid}_{uuid.uuid4().hex[:8]}.png"
                    os.makedirs("/app/uploads/avatars", exist_ok=True)
                    fpath = os.path.join("/app/uploads/avatars", fname)
                    with open(fpath, "wb") as f:
                        f.write(resp.content)
                    local_path = f"/api/fs/download-avatar/{fname}"
                    logger.info(f"🖼️ 下载远端头像: {download_url} → {fname}")
        except Exception as e:
            logger.warning(f"🖼️ 下载远端头像失败: {e}")

    if entity_type == "user":
        await db.execute(text("UPDATE users SET avatar_url = :v WHERE id = :i"), {"v": local_path, "i": rid})
    elif entity_type == "agent":
        await db.execute(text("UPDATE agents SET avatar_url = :v WHERE id = :i"), {"v": local_path, "i": rid})


async def _download_federated_avatar(avatar_url: str, entity_type: str, local_id: int, peer) -> None:
    """后台下载联邦头像（fire-and-forget，供 asyncio.create_task 调用）"""
    if not avatar_url or not avatar_url.startswith("/") or not peer or not peer.remote_url:
        return
    import os, uuid
    try:
        base = peer.remote_url.replace("wss://", "https://").replace("ws://", "http://")
        base = base.replace("/federation/ws", "")
        download_url = f"{base}{avatar_url}"
        import httpx
        async with httpx.AsyncClient(verify=False, timeout=15) as client:
            resp = await client.get(download_url)
            if resp.status_code == 200:
                ext = os.path.splitext(avatar_url)[1] or ".png"
                fname = f"{entity_type}_{local_id}_{uuid.uuid4().hex[:8]}{ext}"
                os.makedirs("/app/uploads/avatars", exist_ok=True)
                fpath = os.path.join("/app/uploads/avatars", fname)
                with open(fpath, "wb") as f:
                    f.write(resp.content)
                local_path = f"/api/fs/download-avatar/{fname}"
                from sqlalchemy import text
                async with async_session() as _db:
                    if entity_type == "user":
                        await _db.execute(text("UPDATE users SET avatar_url = :v WHERE id = :i"), {"v": local_path, "i": local_id})
                    elif entity_type == "agent":
                        await _db.execute(text("UPDATE agents SET avatar_url = :v WHERE id = :i"), {"v": local_path, "i": local_id})
                    await _db.commit()
                logger.info(f"🖼️ 下载联邦头像: {download_url} → {fname}")
                # 推送头像更新通知
                try:
                    from app.routers.ws import manager as ws_manager
                    await ws_manager.broadcast_avatar_updated(entity_type, local_id, local_path)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"🖼️ 下载联邦头像失败: {e}")


class FederationManager:
    """联邦连接管理器（单例）"""

    def __init__(self):
        self.peers: dict[str, PeerConnection] = {}  # public_id → PeerConnection
        self._connecting: set[str] = set()
        self._recent_rotation_ids: dict[str, set[str]] = defaultdict(set)
        self._connecting_new_url: set[str] = set()
        self._last_errors: dict[str, str] = {}
        self._running = False

    # ── 连接管理 ──

    async def connect_to_peer(self, peer_record) -> bool:
        """尝试连接到指定对等端。peer_record: FederationPeer ORM 对象"""
        public_id = peer_record.peer_public_id
        url = (peer_record.remote_url or "").strip()

        if public_id in self._connecting:
            logger.info(f"🌐 {public_id} 正在连接中，跳过重复请求")
            return False
        self._connecting.add(public_id)

        # 如果 URL 为空，不尝试出站连接（等对方主动连过来）
        if not url:
            logger.info(f"🌐 {public_id} remote_url 为空，跳过出站连接（等待对方连入）")
            self._connecting.discard(public_id)
            return False

        # 如果已有入站连接，不覆盖
        if public_id in self.peers and self.peers[public_id].handshake_complete:
            logger.info(f"🌐 {public_id} 已有入站连接，跳过出站连接")
            self._connecting.discard(public_id)
            return False

        if public_id in self.peers:
            await self._close_peer_connection(public_id)

        try:
            secret = await get_decrypted_secret(peer_record)
        except Exception as e:
            logger.error(f"🌐 解密对等端 {public_id} 共享密钥失败: {e}")
            self._last_errors[public_id] = f"密钥解密失败：共享密钥可能不匹配或已损坏"
            self._connecting.discard(public_id)
            return False

        conn = PeerConnection(
            public_id=public_id,
            peer_id=peer_record.id,
            display_name=peer_record.display_name or "",
            remote_url=url,
        )
        self.peers[public_id] = conn

        try:
            async with async_session() as db:
                await update_peer_connection_state(db, peer_record.id, "connecting")
        except Exception:
            pass

        try:
            ws = await websockets.connect(
                url,
                ping_interval=None,
                ping_timeout=None,
                close_timeout=10,
                max_size=2**20,
            )
            conn.websocket = ws

            # ── 握手 ──
            my_challenge = generate_challenge()
            handshake_msg = {
                "type": "handshake",
                "public_id": await self._get_my_public_id(),
                "challenge": my_challenge,
            }
            await ws.send(json.dumps(handshake_msg))

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
                ack = json.loads(raw)
            except (asyncio.TimeoutError, json.JSONDecodeError) as e:
                msg = "握手超时（对方未在 15s 内响应）" if isinstance(e, asyncio.TimeoutError) else "握手响应格式无效（非 JSON）"
                logger.warning(f"🌐 握手超时/无效: {public_id} — {e}")
                self._last_errors[public_id] = msg
                await self._close_peer_connection(public_id)
                return False

            if ack.get("type") != "handshake_ack":
                logger.warning(f"🌐 握手阶段收到非预期消息: {ack.get('type')} from {public_id}")
                self._last_errors[public_id] = f"握手阶段收到非预期响应类型: {ack.get('type')}"
                await self._close_peer_connection(public_id)
                return False

            expected_response = hmac_response(secret, my_challenge)
            if ack.get("response") != expected_response:
                logger.warning(f"🌐 HMAC 验证失败: {public_id}")
                self._last_errors[public_id] = "HMAC 验证失败：共享密钥不匹配"
                await self._close_peer_connection(public_id)
                return False

            # 如果对方给我们起了名，且我们自己还没设实例代号，自动采纳
            assigned_name = ack.get("assigned_name", "")
            if assigned_name:
                async with async_session() as db:
                    from app.services.federation_service import get_instance_info, update_instance_info
                    info = await get_instance_info(db)
                    my_current_name = (info.get("display_name") or "").strip()
                    if not my_current_name:
                        await update_instance_info(db, display_name=assigned_name)
                        logger.info(f"🌐 自动采纳对方分配的实例代号: {assigned_name}")

            their_challenge = ack.get("challenge", "")
            finish_msg = {
                "type": "handshake_finish",
                "response": hmac_response(secret, their_challenge),
            }
            await ws.send(json.dumps(finish_msg))

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                ok = json.loads(raw)
            except (asyncio.TimeoutError, json.JSONDecodeError) as e:
                msg = "握手确认超时（对方未在 10s 内确认）" if isinstance(e, asyncio.TimeoutError) else "握手确认响应格式无效"
                logger.warning(f"🌐 握手完成超时: {public_id} — {e}")
                self._last_errors[public_id] = msg
                await self._close_peer_connection(public_id)
                return False

            if ok.get("type") != "handshake_ok":
                self._last_errors[public_id] = f"握手未获对方确认"
                await self._close_peer_connection(public_id)
                return False

            # ── 握手成功 ──
            conn.handshake_complete = True
            conn.connected_at = datetime.now(timezone.utc).replace(tzinfo=None)
            conn.last_heartbeat = conn.connected_at
            conn.instance_id = ack.get("instance_id", "")

            async with async_session() as db:
                await update_peer_connection_state(db, peer_record.id, "connected")

            asyncio.create_task(self._receive_loop(public_id))
            await self._flush_outbox(public_id)

            logger.info(f"🌐 ✅ 已连接到 {public_id} ({conn.display_name})")
            return True

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e) or error_type
            if "TLS" in error_type or "ssl" in error_msg.lower():
                detail = f"TLS/SSL 错误：{error_msg}"
            elif "ConnectionRefusedError" in error_type or "refused" in error_msg.lower():
                detail = f"连接被拒绝：{error_msg}"
            elif "gaierror" in error_type.lower() or "getaddrinfo" in error_msg.lower():
                detail = f"DNS 解析失败：{error_msg}"
            elif error_type == "TimeoutError" or "timeout" in error_msg.lower():
                detail = f"连接超时：{error_msg}"
            elif "403" in error_msg:
                detail = f"握手被拒绝 (403)：{error_msg}"
            elif "404" in error_msg:
                detail = f"联邦端点不存在 (404)：{error_msg}"
            else:
                detail = f"{error_type}：{error_msg}"
            logger.warning(f"🌐 连接失败 {public_id}: {detail}")
            self._last_errors[public_id] = detail
            await self._close_peer_connection(public_id)
            try:
                async with async_session() as db:
                    # 如果已有入站连接，不要覆盖为 failed
                    if public_id in self.peers and self.peers[public_id].handshake_complete:
                        logger.info(f"🌐 {public_id} 出站连接失败但入站已通，保持 connected")
                    else:
                        await update_peer_connection_state(db, peer_record.id, "failed")
            except Exception:
                pass
            return False
        finally:
            self._connecting.discard(public_id)

    def get_last_error(self, public_id: str) -> str | None:
        return self._last_errors.get(public_id)

    async def disconnect_peer(self, public_id: str) -> None:
        await self._close_peer_connection(public_id)
        async with async_session() as db:
            peer = await get_peer_by_public_id(db, public_id)
            if peer:
                await update_peer_connection_state(db, peer.id, "disconnected")
        logger.info(f"🌐 已断开 {public_id}")

    async def connect_all_enabled_peers(self) -> None:
        from app.models.federation import FederationPeer
        async with async_session() as db:
            result = await db.execute(
                select(FederationPeer).where(FederationPeer.is_enabled == True)
            )
            peers = result.scalars().all()
        for peer in peers:
            asyncio.create_task(self.connect_to_peer(peer))
        if peers:
            logger.info(f"🌐 正在连接 {len(peers)} 个对等端...")
        else:
            logger.info("🌐 无已启用对等端")

    async def disconnect_all(self) -> None:
        for public_id in list(self.peers.keys()):
            await self._close_peer_connection(public_id)
        logger.info("🌐 所有对等端连接已关闭")

    # ── 消息转发（使用 federated_id） ──

    async def forward_message(
        self,
        group_id: int,
        message_dict: dict,
        exclude_public_id: str | None = None,
    ) -> None:
        """
        将消息转发给共享此群的所有已连接对等端。
        只传 entity_type + local_id，远端根据 peer 前缀自动拼接。
        """
        async with async_session() as db:
            peers_list = await get_federated_peers_for_entity(db, "group", str(group_id))
            my_info = await get_instance_info(db)
            my_public_id = my_info.get("public_id", "")

        if not peers_list:
            return

        sender_id = message_dict.get("sender_id", 0)
        sender_type = message_dict.get("sender_type", "human")

        payload = {
            "type": "forward_message",
            "conversation_type": "group",
            "group_id": group_id,
            "sender_id": sender_id,
            "sender_type": sender_type,
            "message": message_dict,
            "source_public_id": my_public_id,
        }

        profile_updates = await self._get_pending_profile_updates()
        if profile_updates:
            payload["profile_updates"] = profile_updates

        for peer in peers_list:
            if peer.peer_public_id == exclude_public_id:
                continue
            await self._send_or_buffer(peer.peer_public_id, payload)

    async def forward_dm_message(
        self,
        session_id: str,
        message_dict: dict,
        exclude_public_id: str | None = None,
    ) -> None:
        """将 DM 消息转发给共享此 DM 的所有已连接对等端"""
        async with async_session() as db:
            peers_list = await get_federated_peers_for_entity(db, "dm", session_id)
            my_info = await get_instance_info(db)
            my_public_id = my_info.get("public_id", "")

        if not peers_list:
            return

        payload = {
            "type": "forward_message",
            "conversation_type": "dm",
            "session_id": session_id,
            "message": message_dict,
            "source_public_id": my_public_id,
        }

        profile_updates = await self._get_pending_profile_updates()
        if profile_updates:
            payload["profile_updates"] = profile_updates

        for peer in peers_list:
            if peer.peer_public_id == exclude_public_id:
                continue
            await self._send_or_buffer(peer.peer_public_id, payload)

    # ── 实体发布/取消发布（v1.0.0: 供群主/AI制作者控制联邦共享） ──

    async def announce_entity(
        self,
        peer_public_id: str,
        entity_type: str,
        local_id: str,
        display_name: str = "",
        avatar_url: str = "",
        direction: str = "outgoing",
    ) -> bool:
        """
        向指定已连接对等端发送 entity_announce。
        只传 entity_type + local_id，远端根据 peer 前缀自动拼接 federated_id。
        返回 True 表示已发送，False 表示对等端未连接。
        """
        conn = self.peers.get(peer_public_id)
        if not conn or not conn.handshake_complete or not conn.websocket:
            return False
        try:
            await conn.websocket.send(json.dumps({
                "type": "entity_announce",
                "entity_type": entity_type,
                "local_id": local_id,
                "display_name": display_name,
                "avatar_url": avatar_url,
                "direction": direction,
            }))
            logger.info(f"📢 发送 entity_announce: {entity_type}:{local_id} → {peer_public_id}")
            return True
        except Exception as e:
            logger.warning(f"📢 entity_announce 发送失败: {peer_public_id} — {e}")
            return False

    async def unannounce_entity(
        self,
        peer_public_id: str,
        entity_type: str,
        local_id: str,
    ) -> bool:
        """
        向指定已连接对等端发送 entity_unannounce，通知远端移除联邦实体。
        返回 True 表示已发送，False 表示对等端未连接。
        """
        conn = self.peers.get(peer_public_id)
        if not conn or not conn.handshake_complete or not conn.websocket:
            return False
        try:
            await conn.websocket.send(json.dumps({
                "type": "entity_unannounce",
                "entity_type": entity_type,
                "local_id": local_id,
            }))
            logger.info(f"📢 发送 entity_unannounce: {entity_type}:{local_id} → {peer_public_id}")
            return True
        except Exception as e:
            logger.warning(f"📢 entity_unannounce 发送失败: {peer_public_id} — {e}")
            return False

    async def _send_or_buffer(self, public_id: str, payload: dict) -> None:
        """发送或缓冲消息"""
        conn = self.peers.get(public_id)
        if conn and conn.handshake_complete and conn.websocket:
            try:
                if conn.is_inbound:
                    # Starlette WebSocket（入站连接）
                    await conn.websocket.send_json(payload)
                else:
                    # websockets 库（出站连接）
                    await conn.websocket.send(json.dumps(payload))
                return
            except Exception:
                pass
        # 未连接，放入缓冲
        if conn:
            try:
                conn.pending_outbox.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def _get_pending_profile_updates(self) -> list[dict]:
        """获取待同步的 profile 变更（消息顺带）"""
        from app.services.federation_service import get_pending_updates, clear_pending_updates
        async with async_session() as db:
            updates = await get_pending_updates(db)
            if not updates:
                return []
            result = [
                {
                    "entity_type": u.entity_type,
                    "entity_id": u.entity_id,
                    "field": u.field,
                    "new_value": u.new_value,
                }
                for u in updates
            ]
            # 清除（消息顺带发送后清除）
            await clear_pending_updates(db, [u.id for u in updates])
            return result

    # ── 后台任务 ──

    async def heartbeat_loop(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for public_id, conn in list(self.peers.items()):
                if not conn.handshake_complete or not conn.websocket or conn.is_inbound:
                    continue
                if conn.last_heartbeat:
                    age = (now - conn.last_heartbeat).total_seconds()
                    if age > HEARTBEAT_TIMEOUT:
                        logger.warning(f"🌐 {public_id} 心跳超时 ({age:.0f}s)，断开")
                        await self._close_peer_connection(public_id)
                        continue
                try:
                    await conn.websocket.send(json.dumps({"type": "ping"}))
                except Exception:
                    logger.warning(f"🌐 {public_id} ping 失败，断开")
                    await self._close_peer_connection(public_id)

    async def reconnect_loop(self) -> None:
        from app.models.federation import FederationPeer
        fail_counts: dict[str, int] = defaultdict(int)
        while self._running:
            await asyncio.sleep(RECONNECT_BASE)
            async with async_session() as db:
                result = await db.execute(
                    select(FederationPeer).where(
                        FederationPeer.is_enabled == True,
                        FederationPeer.connection_state.in_(["disconnected", "failed"]),
                    )
                )
                disconnected = result.scalars().all()
            for peer in disconnected:
                pid = peer.peer_public_id
                if pid in self.peers and self.peers[pid].handshake_complete:
                    continue
                fails = fail_counts.get(pid, 0)
                delay = min(RECONNECT_BASE * (RECONNECT_MULTIPLIER ** fails), RECONNECT_MAX)
                await asyncio.sleep(delay)
                logger.info(f"🌐 尝试重连 {pid} (第 {fails + 1} 次, 延迟 {delay}s)")
                success = await self.connect_to_peer(peer)
                if success:
                    fail_counts[pid] = 0
                else:
                    fail_counts[pid] = fails + 1

    # ── 定时 profile 同步 ──

    async def profile_sync_loop(self) -> None:
        """每隔 N 分钟全推一次 profile 更新到所有已连接对等端"""
        from app.services.federation_service import get_pending_updates, clear_pending_updates, get_sync_interval_minutes

        while self._running:
            interval = 30  # 默认
            try:
                async with async_session() as db:
                    interval = await get_sync_interval_minutes(db)
            except Exception:
                pass

            await asyncio.sleep(interval * 60)

            try:
                async with async_session() as db:
                    updates = await get_pending_updates(db)
                    if not updates:
                        continue

                    update_data = [
                        {
                            "entity_type": u.entity_type,
                            "entity_id": u.entity_id,
                            "field": u.field,
                            "new_value": u.new_value,
                        }
                        for u in updates
                    ]

                    payload = {
                        "type": "profile_sync",
                        "updates": update_data,
                    }

                    sent_count = 0
                    for public_id, conn in list(self.peers.items()):
                        if conn.handshake_complete and conn.websocket:
                            try:
                                await conn.websocket.send(json.dumps(payload))
                                sent_count += 1
                            except Exception:
                                pass

                    if sent_count > 0:
                        await clear_pending_updates(db, [u.id for u in updates])
                        logger.info(f"📝 定时 profile 同步: {len(updates)} 条更新 → {sent_count} 个对等端")

            except Exception as e:
                logger.warning(f"📝 profile 同步异常: {e}")

    # ── 接收循环 ──

    async def _receive_loop(self, public_id: str) -> None:
        """接收来自指定对等端的消息"""
        conn = self.peers.get(public_id)
        if not conn or not conn.websocket:
            return

        try:
            async for raw in conn.websocket:
                conn.last_heartbeat = datetime.now(timezone.utc).replace(tzinfo=None)
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(f"🌐 {public_id} 发来无效 JSON")
                    continue

                msg_type = data.get("type", "")
                if msg_type == "pong":
                    pass
                elif msg_type == "ping":
                    try:
                        await conn.websocket.send(json.dumps({"type": "pong"}))
                    except Exception:
                        pass
                elif msg_type == "forward_message":
                    await self._handle_remote_forward(public_id, data)
                elif msg_type == "entity_announce":
                    await self._handle_entity_announce(public_id, data)
                elif msg_type == "entity_unannounce":
                    await self._handle_entity_unannounce(public_id, data)
                elif msg_type == "profile_sync":
                    await self._handle_profile_sync(public_id, data)
                elif msg_type == "error":
                    logger.warning(f"🌐 {public_id} 报错: {data.get('code')} — {data.get('message')}")
                elif msg_type == "url_rotate_propose":
                    await self._handle_url_rotate_propose(public_id, data)
                elif msg_type == "url_rotate_ack":
                    await self._handle_url_rotate_ack(public_id, data)
                elif msg_type == "url_rotate_commit":
                    await self._handle_url_rotate_commit(public_id, data)
                else:
                    logger.debug(f"🌐 未知消息类型: {msg_type} from {public_id}")
        except Exception as e:
            logger.warning(f"🌐 {public_id} 接收循环异常: {e}")
        finally:
            await self._close_peer_connection(public_id)

    async def _handle_remote_forward(self, from_public_id: str, data: dict) -> None:
        """处理远程转发来的消息（v1.0.0: 使用 federated_id 直接解析）"""
        conversation_type = data.get("conversation_type", "group")
        msg = data.get("message", {})
        source_public_id = data.get("source_public_id", from_public_id)

        if not msg:
            return

        # 处理顺带的 profile 更新
        profile_updates = data.get("profile_updates", [])
        if profile_updates:
            await self._apply_profile_updates(from_public_id, profile_updates)

        if conversation_type == "group":
            # 新格式：group_id + entity_type，自行拼接 federated_id
            group_id = data.get("group_id")
            federated_group_id = data.get("federated_group_id", "")  # 兼容旧格式

            if not group_id and not federated_group_id:
                return

            async with async_session() as db:
                entity = None
                peer = None
                if group_id:
                    # 新格式：根据 peer 前缀拼接
                    peer = await get_peer_by_public_id(db, from_public_id)
                    if peer:
                        fid = f"{peer.display_name}:g:{group_id}"
                        entity = await get_federated_entity_by_fid(db, fid)
                elif federated_group_id:
                    entity = await get_federated_entity_by_fid(db, federated_group_id)
                    peer = await get_peer_by_public_id(db, from_public_id)

                if entity is None:
                    lid = group_id or federated_group_id
                    logger.warning(f"🌐 未知联邦群: {lid} from {from_public_id}")
                    return
                gid = int(entity.local_ref_id)

                message = await handle_remote_message(db, gid, msg, source_public_id)
                await db.commit()

                from app.services.group_service import message_to_dict
                original_avatar = msg.get("sender_avatar_url")
                msg_data = message_to_dict(message, sender_name=msg.get("sender_name", "Remote User"), sender_avatar_url=original_avatar)

                # 后台异步下载头像
                if original_avatar and peer:
                    asyncio.create_task(_download_federated_avatar(
                        original_avatar, msg.get("sender_type", "human"),
                        msg.get("sender_id", 0), peer,
                    ))

                from app.routers.ws import manager
                await manager.broadcast_to_group(
                    gid,
                    {"type": "message", "conversation_type": "group", "data": msg_data},
                )

                if msg.get("sender_type") == "human":
                    from app.services.ai_response_worker import message_queue
                    try:
                        message_queue.put_nowait({
                            "conversation_type": "group",
                            "group_id": gid,
                            "message_id": message.id,
                            "content": msg.get("content", ""),
                            "sender_type": "human",
                            "sender_id": 0,
                            "chain_depth": 0,
                            "source_public_id": source_public_id,
                        })
                    except asyncio.QueueFull:
                        pass

        elif conversation_type == "dm":
            session_id = data.get("session_id", "")
            federated_session_id = data.get("federated_session_id", "")  # 兼容旧格式

            if not session_id and not federated_session_id:
                return

            async with async_session() as db:
                entity = None
                peer = None
                if session_id:
                    peer = await get_peer_by_public_id(db, from_public_id)
                    if peer:
                        fid = f"{peer.display_name}:d:{session_id}"
                        entity = await get_federated_entity_by_fid(db, fid)
                elif federated_session_id:
                    entity = await get_federated_entity_by_fid(db, federated_session_id)
                    peer = await get_peer_by_public_id(db, from_public_id)

                if entity is None:
                    sid = session_id or federated_session_id
                    logger.warning(f"🌐 未知联邦 DM: {sid} from {from_public_id}")
                    return
                sid = entity.local_ref_id

                dm_msg = await persist_remote_dm_message(db, sid, msg, source_public_id)
                await db.commit()

                from app.routers.ws import manager
                sender_avatar_dm = msg.get("sender_avatar_url")
                # 后台异步下载头像
                if sender_avatar_dm and peer:
                    asyncio.create_task(_download_federated_avatar(
                        sender_avatar_dm, msg.get("sender_type", "human"),
                        msg.get("sender_id", 0), peer,
                    ))
                dm_data = {
                    "id": dm_msg.id if hasattr(dm_msg, 'id') else None,
                    "session_id": sid,
                    "sender_id": 0,
                    "sender_name": msg.get("sender_name", "Remote User"),
                    "sender_type": msg.get("sender_type", "human"),
                    "sender_avatar_url": sender_avatar_dm,
                    "content": msg.get("content", ""),
                    "reply_to": msg.get("reply_to"),
                    "source_public_id": source_public_id,
                    "created_at": str(dm_msg.created_at) if hasattr(dm_msg, 'created_at') else None,
                    "read_at": None,
                }
                await manager.broadcast_to_dm(
                    sid,
                    {"type": "message", "conversation_type": "dm", "data": dm_data},
                )

    async def _handle_entity_announce(self, from_public_id: str, data: dict) -> None:
        """
        处理入站实体注册通告。

        支持两种格式：
        - 新: { entity_type, local_id, display_name, avatar_url, direction }
        - 旧: { entity_type, federated_id, ... }   （向下兼容）
        """
        entity_type = data.get("entity_type", "")
        display_name = data.get("display_name", "")
        avatar_url = data.get("avatar_url", "")
        direction = data.get("direction", "incoming")

        # 兼容旧格式 federated_id，新格式用 local_id
        federated_id = data.get("federated_id", "")
        local_id = data.get("local_id", "")

        if not entity_type or (not federated_id and not local_id):
            return

        async with async_session() as db:
            peer = await get_peer_by_public_id(db, from_public_id)
            if peer is None:
                logger.warning(f"🌐 entity_announce from unknown peer {from_public_id}")
                return

            # 新格式：根据 peer.display_name + entity_type + local_id 拼接 federated_id
            if not federated_id and local_id:
                type_char = _entity_type_char(entity_type)
                federated_id = f"{peer.display_name}:{type_char}:{local_id}"

            # 检查是否已存在
            existing = await get_federated_entity_by_fid(db, federated_id)
            if existing:
                existing.display_name = display_name or existing.display_name
                existing.avatar_url = avatar_url or existing.avatar_url
                existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await db.commit()
                logger.info(f"🌐 联邦实体已存在，更新缓存: {federated_id}")
                return

            # 解析 federated_id 获取 local_ref_id
            try:
                _, _, remote_local_id = parse_federated_id(federated_id)
            except ValueError:
                logger.warning(f"🌐 无效的 federated_id: {federated_id}")
                return

            entity = FederatedEntity(
                federated_id=federated_id,
                peer_id=peer.id,
                entity_type=entity_type,
                local_ref_id=remote_local_id,
                display_name=display_name,
                avatar_url=avatar_url,
                direction=direction,
            )
            db.add(entity)
            await db.commit()

            logger.info(f"🌐 接受联邦实体通告: {federated_id} (type={entity_type}, from={from_public_id})")

            # 发送确认
            conn = self.peers.get(from_public_id)
            if conn and conn.handshake_complete and conn.websocket:
                try:
                    await conn.websocket.send(json.dumps({
                        "type": "entity_announce_ack",
                        "federated_id": federated_id,
                        "accepted": True,
                    }))
                except Exception:
                    pass

    async def _handle_entity_unannounce(self, from_public_id: str, data: dict) -> None:
        """
        处理入站实体取消通告。
        支持新旧两种格式：
        - 新: { entity_type, local_id }
        - 旧: { federated_id }
        """
        federated_id = data.get("federated_id", "")
        entity_type = data.get("entity_type", "")
        local_id = data.get("local_id", "")

        # 新格式：根据 peer 拼接
        if not federated_id and entity_type and local_id:
            async with async_session() as db:
                peer = await get_peer_by_public_id(db, from_public_id)
                if peer:
                    type_char = _entity_type_char(entity_type)
                    federated_id = f"{peer.display_name}:{type_char}:{local_id}"

        if not federated_id:
            return

        async with async_session() as db:
            entity = await get_federated_entity_by_fid(db, federated_id)
            if entity is None:
                logger.info(f"🌐 entity_unannounce 实体不存在: {federated_id}")
                return

            # 验证来自正确的 peer
            peer = await get_peer_by_public_id(db, from_public_id)
            if peer is None or entity.peer_id != peer.id:
                logger.warning(f"🌐 entity_unannounce peer 不匹配: {federated_id} from {from_public_id}")
                return

            await db.delete(entity)
            await db.commit()
            logger.info(f"🌐 移除联邦实体（远端取消共享）: {federated_id}")

    async def _handle_profile_sync(self, from_public_id: str, data: dict) -> None:
        """处理入站 profile 同步"""
        updates = data.get("updates", [])
        if updates:
            await self._apply_profile_updates(from_public_id, updates)

    async def _apply_profile_updates(self, from_public_id: str, updates: list[dict]) -> None:
        """应用 profile 更新到本地缓存并同步更新实际实体表"""
        async with async_session() as db:
            peer = await get_peer_by_public_id(db, from_public_id)
            if not peer:
                return

            for update in updates:
                entity_type = update.get("entity_type", "")
                entity_id = update.get("entity_id", 0)
                field = update.get("field", "")
                new_value = update.get("new_value", "")

                if not entity_type:
                    continue
                if field not in ("display_name", "avatar_url"):
                    continue

                federated_id = f"{peer.display_name}:{entity_type[0]}:{entity_id}"
                entity = await get_federated_entity_by_fid(db, federated_id)
                if entity:
                    if field == "display_name":
                        entity.display_name = new_value
                        await _apply_display_name_update(db, entity_type, entity.local_ref_id, new_value)
                    elif field == "avatar_url":
                        entity.avatar_url = new_value
                        await _apply_avatar_update(db, entity_type, entity.local_ref_id, new_value, peer)
                    entity.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            await db.commit()

    async def _send_error(self, public_id: str, code: str, entity_id: str) -> None:
        """发送错误消息给对等端"""
        conn = self.peers.get(public_id)
        if conn and conn.handshake_complete and conn.websocket:
            try:
                await conn.websocket.send(json.dumps({
                    "type": "error",
                    "code": code,
                    "entity_id": entity_id,
                }))
            except Exception:
                pass

    # ── URL 轮换（保持不变） ──

    async def initiate_url_rotation(self, public_id: str, new_url: str) -> str | None:
        conn = self.peers.get(public_id)
        if not conn or not conn.handshake_complete:
            return "对等端未连接，无法发起轮换"
        if conn.rotation_state is not None:
            return f"对等端正在轮换中（{conn.rotation_state}），请稍后再试"

        from datetime import timedelta
        MIN_INTERVAL = timedelta(seconds=300)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if conn.last_rotation_at and (now - conn.last_rotation_at) < MIN_INTERVAL:
            remaining = int(MIN_INTERVAL.total_seconds() - (now - conn.last_rotation_at).total_seconds())
            return f"距上次轮换不足 {remaining} 秒，请等待"

        from app.services.federation_service import validate_rotation_url
        err = validate_rotation_url(new_url, conn.remote_url)
        if err:
            return err

        import uuid
        rotation_id = uuid.uuid4().hex[:16]
        expires_at = (now + timedelta(seconds=60)).isoformat()

        async with async_session() as db:
            peer = await get_peer_by_public_id(db, public_id)
            if not peer:
                return "对等端不存在"
            secret = await get_decrypted_secret(peer)

        from app.services.federation_service import url_rotate_hmac
        hmac_val = url_rotate_hmac(secret, rotation_id, new_url, expires_at, "propose")

        conn.rotation_state = "proposing"
        conn.rotation_id = rotation_id
        conn.new_url = new_url
        conn.last_rotation_at = now

        try:
            await conn.websocket.send(json.dumps({
                "type": "url_rotate_propose",
                "rotation_id": rotation_id,
                "new_url": new_url,
                "expires_at": expires_at,
                "hmac": hmac_val,
            }))
        except Exception:
            conn.rotation_state = None
            conn.rotation_id = None
            conn.new_url = None
            return "发送轮换提议失败"

        logger.info(f"🌐 发起 URL 轮换: {public_id} → {new_url}")
        return None

    async def _handle_url_rotate_propose(self, public_id: str, data: dict) -> None:
        conn = self.peers.get(public_id)
        if not conn or not conn.handshake_complete:
            return

        rotation_id = data.get("rotation_id", "")
        new_url = data.get("new_url", "")
        expires_at_str = data.get("expires_at", "")
        hmac_val = data.get("hmac", "")

        if rotation_id in self._recent_rotation_ids.get(public_id, set()):
            logger.warning(f"🌐 重复的 rotation_id: {rotation_id} from {public_id}")
            return
        self._recent_rotation_ids[public_id].add(rotation_id)
        if len(self._recent_rotation_ids[public_id]) > 100:
            self._recent_rotation_ids[public_id] = set(list(self._recent_rotation_ids[public_id])[-50:])

        from datetime import timedelta
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if now > expires_at:
                await self._send_rotation_msg(public_id, "url_rotate_ack", rotation_id, False)
                return
        except (ValueError, TypeError):
            await self._send_rotation_msg(public_id, "url_rotate_ack", rotation_id, False)
            return

        MIN_INTERVAL = timedelta(seconds=300)
        if conn.last_rotation_at and (now - conn.last_rotation_at) < MIN_INTERVAL:
            await self._send_rotation_msg(public_id, "url_rotate_ack", rotation_id, False)
            return

        if conn.rotation_state is not None:
            await self._send_rotation_msg(public_id, "url_rotate_ack", rotation_id, False)
            return

        async with async_session() as db:
            peer = await get_peer_by_public_id(db, public_id)
            if not peer:
                return
            secret = await get_decrypted_secret(peer)
            current_url = peer.remote_url

        from app.services.federation_service import validate_rotation_url
        err = validate_rotation_url(new_url, current_url)
        if err:
            await self._send_rotation_msg(public_id, "url_rotate_ack", rotation_id, False)
            return

        from app.services.federation_service import url_rotate_hmac
        expected_hmac = url_rotate_hmac(secret, rotation_id, new_url, expires_at_str, "propose")
        if hmac_val != expected_hmac:
            logger.warning(f"🌐 轮换提议 HMAC 不匹配 from {public_id}")
            await self._send_rotation_msg(public_id, "url_rotate_ack", rotation_id, False)
            return

        conn.rotation_state = "received_proposal"
        conn.rotation_id = rotation_id
        conn.new_url = new_url
        conn.last_rotation_at = now
        await self._send_rotation_msg(public_id, "url_rotate_ack", rotation_id, True)
        asyncio.create_task(self._test_new_url_connection(public_id, new_url, rotation_id))

    async def _handle_url_rotate_ack(self, public_id: str, data: dict) -> None:
        conn = self.peers.get(public_id)
        if not conn:
            return
        rotation_id = data.get("rotation_id", "")
        accepted = data.get("accepted", False)
        if conn.rotation_state != "proposing" or conn.rotation_id != rotation_id:
            return
        if not accepted:
            conn.rotation_state = None
            conn.rotation_id = None
            conn.new_url = None
            return
        conn.rotation_state = "trying_new"
        asyncio.create_task(self._test_new_url_connection(public_id, conn.new_url, rotation_id))

    async def _handle_url_rotate_commit(self, public_id: str, data: dict) -> None:
        conn = self.peers.get(public_id)
        if not conn:
            return
        rotation_id = data.get("rotation_id", "")
        result = data.get("result", "rollback")
        if conn.rotation_id != rotation_id:
            return
        await self._commit_rotation(public_id, rotation_id, result == "success")

    async def _test_new_url_connection(self, public_id: str, url: str, rotation_id: str) -> None:
        conn = self.peers.get(public_id)
        if not conn:
            return
        test_key = f"{public_id}:{rotation_id}"
        if test_key in self._connecting_new_url:
            return
        self._connecting_new_url.add(test_key)

        success = False
        try:
            logger.info(f"🌐 测试新 URL 连接: {public_id} → {url}")
            test_ws = await asyncio.wait_for(
                websockets.connect(url, ping_interval=None, ping_timeout=None, close_timeout=10, max_size=2**20),
                timeout=15,
            )
            try:
                challenge = generate_challenge()
                my_pub_id = await self._get_my_public_id()
                await test_ws.send(json.dumps({
                    "type": "handshake",
                    "public_id": my_pub_id,
                    "challenge": challenge,
                }))
                raw = await asyncio.wait_for(test_ws.recv(), timeout=10)
                ack = json.loads(raw)
                if ack.get("type") == "handshake_ack":
                    success = True
            finally:
                try:
                    await test_ws.close()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"🌐 新 URL 测试失败: {public_id} — {e}")
        finally:
            self._connecting_new_url.discard(test_key)

        if conn.rotation_id != rotation_id:
            return
        if success:
            conn.rotation_state = "connected_new"
            await self._send_rotation_msg(public_id, "url_rotate_commit", rotation_id, True, "success")
        else:
            conn.rotation_state = "reverted_old"
            await self._send_rotation_msg(public_id, "url_rotate_commit", rotation_id, True, "rollback")

    async def _commit_rotation(self, public_id: str, rotation_id: str, success: bool) -> None:
        conn = self.peers.get(public_id)
        if not conn:
            return
        if success and conn.new_url:
            async with async_session() as db:
                peer = await get_peer_by_public_id(db, public_id)
                if peer:
                    from app.services.federation_service import update_peer_url
                    await update_peer_url(db, peer.id, conn.new_url)
            conn.remote_url = conn.new_url
            logger.info(f"🌐 ✅ URL 轮换成功: {public_id} → {conn.new_url}")
        else:
            logger.info(f"🌐 ↩️ URL 轮换回退: {public_id} 保持 {conn.remote_url}")
        conn.rotation_state = None
        conn.rotation_id = None
        conn.new_url = None

    async def _abort_rotation(self, public_id: str) -> None:
        conn = self.peers.get(public_id)
        if conn and conn.rotation_state is not None:
            logger.warning(f"🌐 中止轮换: {public_id} (状态={conn.rotation_state})")
            conn.rotation_state = None
            conn.rotation_id = None
            conn.new_url = None

    async def _send_rotation_msg(
        self, public_id: str, msg_type: str, rotation_id: str,
        accepted: bool = False, result: str = "",
    ) -> None:
        conn = self.peers.get(public_id)
        if not conn or not conn.websocket or not conn.handshake_complete:
            return
        payload = {"type": msg_type, "rotation_id": rotation_id}
        if msg_type == "url_rotate_ack":
            payload["accepted"] = accepted
        elif msg_type == "url_rotate_commit":
            payload["result"] = result
        async with async_session() as db:
            peer = await get_peer_by_public_id(db, public_id)
            if peer:
                secret = await get_decrypted_secret(peer)
                from app.services.federation_service import url_rotate_hmac
                fields = [str(accepted).lower(), result, msg_type.split("_")[-1]]
                payload["hmac"] = url_rotate_hmac(secret, rotation_id, *fields)
        try:
            await conn.websocket.send(json.dumps(payload))
        except Exception:
            pass

    async def handle_inbound_rotation_message(self, public_id: str, data: dict, inbound_ws=None) -> None:
        msg_type = data.get("type", "")
        is_inbound = public_id not in self.peers or not self.peers[public_id].handshake_complete
        if is_inbound and inbound_ws:
            if public_id not in self.peers:
                self.peers[public_id] = PeerConnection(
                    public_id=public_id,
                    websocket=inbound_ws,
                    handshake_complete=True,
                    remote_url="",
                    is_inbound=True,
                )
        if msg_type == "url_rotate_propose":
            await self._handle_url_rotate_propose(public_id, data)
        elif msg_type == "url_rotate_ack":
            await self._handle_url_rotate_ack(public_id, data)
        elif msg_type == "url_rotate_commit":
            await self._handle_url_rotate_commit(public_id, data)

    async def _close_peer_connection(self, public_id: str) -> None:
        conn = self.peers.get(public_id)
        if conn is None:
            return
        if conn.rotation_state is not None:
            await self._abort_rotation(public_id)
        conn.handshake_complete = False
        if conn.websocket:
            try:
                await conn.websocket.close()
            except Exception:
                pass
            conn.websocket = None
        # 更新 DB 状态为 disconnected，让重连循环能发现
        if conn.peer_id:
            try:
                async with async_session() as db:
                    await update_peer_connection_state(db, conn.peer_id, "disconnected")
            except Exception:
                pass
        logger.info(f"🌐 关闭连接: {public_id}")

    async def _flush_outbox(self, public_id: str) -> None:
        """重连后分批回放缓冲消息，避免一次推太多卡爆"""
        conn = self.peers.get(public_id)
        if not conn or not conn.websocket or not conn.handshake_complete:
            return
        flushed = 0
        batch_size = 5  # 每批最多 5 条
        while not conn.pending_outbox.empty():
            batch = 0
            while batch < batch_size and not conn.pending_outbox.empty():
                try:
                    payload = conn.pending_outbox.get_nowait()
                    if conn.is_inbound:
                        await conn.websocket.send_json(payload)
                    else:
                        await conn.websocket.send(json.dumps(payload))
                    flushed += 1
                    batch += 1
                except asyncio.QueueEmpty:
                    break
                except Exception:
                    break
            if not conn.pending_outbox.empty():
                await asyncio.sleep(0.5)  # 批次间隔 0.5s
        if flushed:
            logger.info(f"🌐 {public_id} 缓冲重放: {flushed} 条消息")

    async def _get_my_public_id(self) -> str:
        async with async_session() as db:
            info = await get_instance_info(db)
            return info.get("public_id", "") or ""


# ── 全局单例 ──

federation_manager = FederationManager()


async def federation_heartbeat():
    """后台心跳任务（供 main.py lifespan 调用）"""
    await federation_manager.heartbeat_loop()


async def federation_reconnect():
    """后台重连任务（供 main.py lifespan 调用）"""
    await federation_manager.reconnect_loop()


async def federation_profile_sync():
    """后台 profile 同步任务（供 main.py lifespan 调用）"""
    await federation_manager.profile_sync_loop()
