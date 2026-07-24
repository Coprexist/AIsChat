"""
联邦端点（v1.0.0 ID前缀替代注册表）

- GET /federation/identity — 公开端点，实例身份
- WS /federation/ws   — 实例间 WebSocket 连接
"""
import asyncio
import json
import logging
import os
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session, get_db
from app.services.federation.federation_service import (
    get_peer_by_public_id,
    get_decrypted_secret,
    hmac_response,
    generate_challenge,
    handle_remote_message,
    get_instance_info,
    get_federated_entity_by_fid,
    persist_remote_dm_message,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/federation/identity")
async def federation_identity(db: AsyncSession = Depends(get_db)):
    """
    公开端点，返回本实例的 public_id 和 instance_id。
    用于注册表验证（可选）：第三方请求此端点，比对返回的 public_id 是否与注册声明一致。
    无需认证。
    """
    info = await get_instance_info(db)
    return {
        "public_id": info.get("public_id"),
        "instance_id": info.get("instance_id"),
        "display_name": info.get("display_name"),
    }


@router.websocket("/federation/ws")
async def federation_websocket(ws: WebSocket):
    """接受远程实例的连接，完成挑战-应答握手后进入消息循环"""
    await ws.accept()

    peer_public_id = "unknown"

    try:
        # ── 阶段 1: 等待 handshake ──
        raw = await ws.receive_text()
        try:
            handshake = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "code": "BAD_JSON", "message": "无效 JSON"})
            await ws.close()
            return

        if handshake.get("type") != "handshake":
            await ws.send_json({"type": "error", "code": "BAD_HANDSHAKE", "message": "预期 handshake"})
            await ws.close()
            return

        peer_public_id = handshake.get("public_id", "unknown")
        their_challenge = handshake.get("challenge", "")

        async with async_session() as db:
            peer = await get_peer_by_public_id(db, peer_public_id)
            if peer is None:
                await ws.send_json({
                    "type": "error",
                    "code": "UNKNOWN_PEER",
                    "message": f"未知对等端: {peer_public_id}",
                })
                await ws.close()
                logger.warning(f"🌐 拒绝未知对等端连接: {peer_public_id}")
                return

            if not peer.is_enabled:
                await ws.send_json({
                    "type": "error",
                    "code": "PEER_DISABLED",
                    "message": "此对等端已被禁用",
                })
                await ws.close()
                return

            secret = await get_decrypted_secret(peer)

        # ── 阶段 2: 发送 handshake_ack ──
        my_challenge = generate_challenge()
        my_public_id, my_instance_id, my_display_name = await _get_my_identity_full()
        # 告诉对方我们给它起的名（对方可以用这个做实例代号）
        their_assigned_name = peer.display_name or ""
        await ws.send_json({
            "type": "handshake_ack",
            "public_id": my_public_id,
            "instance_id": my_instance_id,
            "display_name": my_display_name,
            "assigned_name": their_assigned_name,
            "response": hmac_response(secret, their_challenge),
            "challenge": my_challenge,
        })

        # ── 阶段 3: 等待 handshake_finish ──
        raw = await ws.receive_text()
        try:
            finish = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "code": "BAD_JSON", "message": "无效 JSON"})
            await ws.close()
            return

        if finish.get("type") != "handshake_finish":
            await ws.send_json({
                "type": "error",
                "code": "BAD_HANDSHAKE",
                "message": "预期 handshake_finish",
            })
            await ws.close()
            return

        expected_response = hmac_response(secret, my_challenge)
        if finish.get("response") != expected_response:
            await ws.send_json({
                "type": "error",
                "code": "AUTH_FAILED",
                "message": "共享密钥不匹配",
            })
            await ws.close()
            logger.warning(f"🌐 {peer_public_id} HMAC 验证失败")
            return

        # ── 握手成功 ──
        await ws.send_json({"type": "handshake_ok", "instance_id": my_instance_id})
        logger.info(f"🌐 ✅ 接受连接: {peer_public_id}")

        async with async_session() as db:
            from app.services.federation.federation_service import update_peer_connection_state
            await update_peer_connection_state(db, peer.id, "connected")

        # 注册入站连接到 federation_manager.peers，使 _send_or_buffer 能回传消息
        from app.services.federation.federation_manager import federation_manager, PeerConnection
        if peer_public_id not in federation_manager.peers:
            federation_manager.peers[peer_public_id] = PeerConnection(
                public_id=peer_public_id,
                websocket=ws,
                handshake_complete=True,
                remote_url="",
                peer_id=peer.id,
                display_name=peer.display_name or "",
                is_inbound=True,
            )
            logger.info(f"🌐 注册入站连接: {peer_public_id}")
            # 分批回放断线期间缓冲的消息
            await federation_manager._flush_outbox(peer_public_id)

        # ── 消息循环 ──
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
            elif msg_type == "pong":
                # 更新入站连接的 last_heartbeat，防止心跳超时断连
                conn = federation_manager.peers.get(peer_public_id)
                if conn:
                    from datetime import datetime as dt, timezone
                    conn.last_heartbeat = dt.now(timezone.utc).replace(tzinfo=None)
            elif msg_type == "forward_message":
                await _handle_forwarded_message(peer_public_id, data)
                # 处理随消息 piggyback 的 profile_updates
                profile_updates = data.get("profile_updates")
                if profile_updates:
                    from app.services.federation.federation_manager import federation_manager
                    await federation_manager._apply_profile_updates(peer_public_id, profile_updates)
            elif msg_type == "entity_announce":
                from app.services.federation.federation_manager import federation_manager
                await federation_manager._handle_entity_announce(peer_public_id, data)
            elif msg_type == "entity_unannounce":
                from app.services.federation.federation_manager import federation_manager
                await federation_manager._handle_entity_unannounce(peer_public_id, data)
            elif msg_type == "profile_sync":
                from app.services.federation.federation_manager import federation_manager
                await federation_manager._handle_profile_sync(peer_public_id, data)
            elif msg_type in ("url_rotate_propose", "url_rotate_ack", "url_rotate_commit"):
                from app.services.federation.federation_manager import federation_manager
                await federation_manager.handle_inbound_rotation_message(peer_public_id, data, ws)
            elif msg_type == "subscribe":
                logger.info(f"🌐 {peer_public_id} 订阅群: {data.get('group_id')}")
            else:
                logger.debug(f"🌐 忽略消息类型: {msg_type} from {peer_public_id}")

    except WebSocketDisconnect:
        logger.info(f"🌐 {peer_public_id} 断开连接")
    except Exception as e:
        logger.error(f"🌐 {peer_public_id} 连接异常: {e}", exc_info=True)
    finally:
        # 清理入站连接（从 federation_manager.peers 中移除）
        from app.services.federation.federation_manager import federation_manager
        federation_manager.peers.pop(peer_public_id, None)
        try:
            async with async_session() as db:
                peer = await get_peer_by_public_id(db, peer_public_id)
                if peer:
                    from app.services.federation.federation_service import update_peer_connection_state
                    await update_peer_connection_state(db, peer.id, "disconnected")
        except Exception:
            pass


async def _handle_forwarded_message(from_public_id: str, data: dict) -> None:
    """处理对等端转发来的消息"""
    conversation_type = data.get("conversation_type", "group")
    msg = data.get("message", {})
    source_public_id = data.get("source_public_id", from_public_id)

    if not msg:
        return

    # 根据 peer 前缀拼接 federated_id 的辅助函数，同时返回 peer 避免外部重复查询
    async def _resolve_entity(entity_type: str, local_id: str | int) -> tuple[object | None, object | None]:
        async with async_session() as db:
            from app.services.federation.federation_service import get_peer_by_public_id
            peer = await get_peer_by_public_id(db, from_public_id)
            if peer:
                type_char = {"group": "g", "dm": "d", "user": "u", "agent": "a"}.get(entity_type, entity_type[0])
                fid = f"{peer.display_name}:{type_char}:{local_id}"
                entity = await get_federated_entity_by_fid(db, fid)
                if entity:
                    return entity, peer
                # 回退：federated_id 可能因格式变更不匹配，按 entity_type + local_ref_id + peer_id 查找
                from app.models.federation import FederatedEntity
                from sqlalchemy import select as sa_select
                result = await db.execute(
                    sa_select(FederatedEntity).where(
                        FederatedEntity.entity_type == entity_type,
                        FederatedEntity.local_ref_id == str(local_id),
                        FederatedEntity.peer_id == peer.id,
                    )
                )
                entity = result.scalar_one_or_none()
                return entity, peer if entity else None
        return None, None

    # 从发送端下载头像到本地，返回本地路径（避免浏览器跨域/证书问题）
    async def _download_remote_avatar(avatar_url: str, entity_type: str, local_id: int, peer) -> str:
        if not avatar_url or not avatar_url.startswith("/") or not peer or not peer.remote_url:
            return avatar_url
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
                    # 更新本地实体表
                    from sqlalchemy import text
                    async with async_session() as _db:
                        if entity_type == "user":
                            await _db.execute(text("UPDATE users SET avatar_url = :v WHERE id = :i"), {"v": local_path, "i": local_id})
                        elif entity_type == "agent":
                            await _db.execute(text("UPDATE agents SET avatar_url = :v WHERE id = :i"), {"v": local_path, "i": local_id})
                        await _db.commit()
                    logger.info(f"Downloaded federated avatar: {download_url} -> {fname}")
                    # 推送头像更新通知，前端收到后更新已渲染消息中的头像 URL
                    try:
                        from app.routers.ws import manager as ws_manager
                        await ws_manager.broadcast_avatar_updated(entity_type, local_id, local_path)
                    except Exception:
                        pass
                    return local_path
        except Exception as e:
            logger.warning(f"Failed to download federated avatar: {e}")
        return avatar_url

    if conversation_type == "group":
        group_id = data.get("group_id")
        federated_group_id = data.get("federated_group_id", "")  # 兼容旧格式

        if not group_id and not federated_group_id:
            return

        async with async_session() as db:
            entity = None
            peer_for_avatar = None
            if group_id:
                entity, peer_for_avatar = await _resolve_entity("group", group_id)
            elif federated_group_id:
                entity = await get_federated_entity_by_fid(db, federated_group_id)
                peer_for_avatar = await get_peer_by_public_id(db, from_public_id)

            if entity is None:
                logger.warning(f"🌐 未知联邦群: {group_id or federated_group_id} from {from_public_id}")
                return
            group_id = int(entity.local_ref_id)

        try:
            async with async_session() as db:
                message = await handle_remote_message(db, group_id, msg, source_public_id)
                await db.commit()

                from app.chat.message import message_to_dict
                # 先用原始头像 URL 立即广播，头像下载放到后台不阻塞消息
                original_avatar = msg.get("sender_avatar_url")
                msg_data = message_to_dict(message, sender_name=msg.get("sender_name", "远程用户"), sender_avatar_url=original_avatar)
                # 后台异步下载头像（不影响消息即时送达）
                asyncio.create_task(_download_remote_avatar(
                    msg.get("sender_avatar_url"), msg.get("sender_type", "human"),
                    msg.get("sender_id", 0), peer_for_avatar,
                ))

                from app.routers.ws import manager
                await manager.broadcast_to_group(
                    group_id,
                    {"type": "message", "conversation_type": "group", "data": msg_data},
                )

                if msg.get("sender_type") == "human":
                    from app.ai.response_worker import message_queue
                    try:
                        message_queue.put_nowait({
                            "conversation_type": "group",
                            "group_id": group_id,
                            "message_id": message.id,
                            "content": msg.get("content", ""),
                            "sender_type": "human",
                            "sender_id": 0,
                            "chain_depth": 0,
                            "source_public_id": source_public_id,
                        })
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"🌐 处理转发消息失败: {e}", exc_info=True)

    elif conversation_type == "dm":
        session_id = data.get("session_id", "")
        federated_session_id = data.get("federated_session_id", "")  # 兼容旧格式

        if not session_id and not federated_session_id:
            return

        async with async_session() as db:
            entity = None
            peer_for_dm_avatar = None
            if session_id:
                entity, peer_for_dm_avatar = await _resolve_entity("dm", session_id)
            elif federated_session_id:
                entity = await get_federated_entity_by_fid(db, federated_session_id)
                peer_for_dm_avatar = await get_peer_by_public_id(db, from_public_id)

            if entity is None:
                logger.warning(f"Unknown federated DM: {session_id or federated_session_id}")
                return
            session_id = entity.local_ref_id

        if not session_id:
            return

        try:
            async with async_session() as db:
                dm_msg = await persist_remote_dm_message(db, str(session_id), msg, source_public_id)
                await db.commit()
                from app.routers.ws import manager
                # 先广播再后台下载头像
                sender_avatar_dm = msg.get("sender_avatar_url")
                asyncio.create_task(_download_remote_avatar(
                    msg.get("sender_avatar_url"), msg.get("sender_type", "human"),
                    msg.get("sender_id", 0), peer_for_dm_avatar,
                ))
                from app.utils.message_serializer import serialize_message
                dm_data = serialize_message(
                    dm_msg,
                    sender_name=msg.get("sender_name", "远程用户"),
                    sender_type=msg.get("sender_type", "human"),
                    sender_avatar_url=sender_avatar_dm,
                    conversation_key='session_id',
                    include_read_at=True,
                )
                # 联邦消息的 sender_id 固定为 0（远端用户），覆盖 serialize_message 的 ORM 默认值
                dm_data["sender_id"] = 0
                await manager.broadcast_to_dm(
                    str(session_id),
                    {"type": "message", "conversation_type": "dm", "data": dm_data},
                )
        except Exception as e:
            logger.error(f"Handle forwarded DM error: {e}")

async def _get_my_identity_full() -> tuple[str, str, str]:
    """获取本实例的 public_id、instance_id 和 display_name"""
    from app.services.federation.federation_service import get_instance_info
    async with async_session() as db:
        info = await get_instance_info(db)
        return (
            info.get("public_id", "") or "",
            info.get("instance_id", "") or "",
            info.get("display_name", "") or "",
        )
