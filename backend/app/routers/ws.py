"""
WebSocket 实时通信处理器
支持 DND 过滤、消息暂存、错误推送
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select, func, update as sa_update
from app.database import async_session
from app.models.user import User as UserModel
from app.models.agent import Agent as AgentModel
from app.models.group import GroupMember as GroupMemberModel
from app.utils.auth import decode_access_token
from app.utils.error_handler import build_ws_error, log_error
from app.chat.connection import ConnectionManager
from app.chat import chat_api
from app.chat.message import create_message, message_to_dict
from app.chat.delivery import store_pending_message

logger = logging.getLogger(__name__)

router = APIRouter()


manager = ConnectionManager()
chat_api.set_manager(manager)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    """WebSocket 端点：/ws?token=JWT"""

    # 必须先 accept，再验证 token——否则浏览器报 "closed before established"
    await ws.accept()

    payload_result = decode_access_token(token)
    if payload_result.is_err():
        await ws.close(code=4001, reason=payload_result.error)
        return
    payload = payload_result.ok

    user_id = int(payload.get("user_id", 0))
    username = payload.get("username", "unknown")

    if user_id == 0:
        await ws.close(code=4001, reason="令牌数据不完整")
        return
    current_group_id: int | None = None
    current_session_id: str | None = None  # DM 会话 ID 追踪

    # 记录 WebSocket 连接活动（在线追踪兜底）
    from app.services.infrastructure.online_tracker import record_ws_activity
    record_ws_activity(user_id)

    # 缓存用户信息（打字状态/在线需要头像）
    _user_avatar = None
    try:
        from app.database import async_session as _init_db
        async with _init_db() as _init_session:
            from app.models.user import User as UserModel
            _u = (await _init_session.execute(select(UserModel.avatar_url).where(UserModel.id == user_id))).scalar()
            if _u:
                _user_avatar = _u
    except Exception:
        pass

    # WebSocket 连接成功 → 标记为当前在线
    try:
        async with async_session() as _online_db:
            await _online_db.execute(
                sa_update(UserModel).where(UserModel.id == user_id).values(last_active_at=None)
            )
            await _online_db.commit()
    except Exception:
        pass

    # 启动心跳检测
    heartbeat_task = manager.start_heartbeat(ws, user_id)

    try:
        while True:
            raw = await ws.receive_text()
            manager.record_activity(user_id)
            record_ws_activity(user_id)

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json(build_ws_error("INVALID_JSON", "无效的 JSON 格式"))
                continue

            msg_type = data.get("type", "")

            # ---- 订阅（群聊或私信） ----
            if msg_type == "subscribe":
                group_id = data.get("group_id")
                session_id = data.get("session_id")

                # 向后兼容：group_id → 群聊，session_id → 私信
                if group_id is not None:
                    conversation_type = "group"
                elif session_id is not None:
                    conversation_type = "dm"
                else:
                    await ws.send_json(build_ws_error("MISSING_GROUP", "缺少 group_id 或 session_id"))
                    continue

                # 断开旧连接
                if current_group_id is not None:
                    manager.disconnect(current_group_id, user_id)
                if current_session_id is not None:
                    manager.disconnect_dm(current_session_id, user_id)

                if conversation_type == "group":
                    await manager.connect(ws, group_id, user_id)
                    current_group_id = group_id
                    await ws.send_json({
                        "type": "subscribed",
                        "conversation_type": "group",
                        "data": {"group_id": group_id},
                    })
                    await manager.broadcast_to_group(
                        group_id,
                        {"type": "user_online", "conversation_type": "group", "data": {"user_id": user_id, "username": username}},
                        exclude_user_id=user_id,
                    )
                else:
                    # DM 订阅
                    # 验证用户是此会话的参与者
                    from app.models.dm import DMSession
                    from sqlalchemy import select as sa_select
                    async with async_session() as verify_db:
                        sess_result = await verify_db.execute(
                            sa_select(DMSession).where(DMSession.session_id == session_id)
                        )
                        dm_session = sess_result.scalar_one_or_none()
                        if dm_session is None:
                            await ws.send_json(build_ws_error("INVALID_SESSION", "私信会话不存在"))
                            continue
                        if user_id not in (dm_session.user1_id, dm_session.user2_id):
                            await ws.send_json(build_ws_error("FORBIDDEN", "无权访问此私信会话"))
                            continue

                    current_session_id = session_id
                    await manager.connect_dm(ws, session_id, user_id)
                    await ws.send_json({
                        "type": "subscribed",
                        "conversation_type": "dm",
                        "data": {"session_id": session_id},
                    })
                    # 真人上线 → 通知 DM 对方更新状态点
                    await manager.broadcast_to_dm(
                        session_id,
                        {"type": "state_change", "data": {
                            "user_id": user_id,
                            "state": "active",
                            "last_active_at": None,
                        }},
                        exclude_user_id=user_id,
                    )

            # ---- 发送消息（群聊或私信） ----
            elif msg_type == "send":
                session_id = data.get("session_id")
                group_id = data.get("group_id", current_group_id)
                content = data.get("content", "")
                reply_to = data.get("reply_to")
                sender_type = data.get("sender_type", "human")

                # 判断会话类型
                if session_id:
                    # ── 私信消息 ──
                    dm_attachments = data.get("attachments")
                    if not content and not dm_attachments:
                        await ws.send_json(build_ws_error("MISSING_FIELD", "缺少 content"))
                        continue

                    async with async_session() as db:
                        try:
                            from app.chat.dm import send_dm_message as send_dm_msg, is_user_in_dm_dnd
                            msg = await send_dm_msg(
                                db, session_id, sender_id=user_id,
                                content=content, reply_to=reply_to,
                                attachments=dm_attachments,
                            )
                            await db.commit()
                        except ValueError as e:
                            await ws.send_json(build_ws_error("SEND_FAILED", str(e)))
                            continue
                        except Exception as e:
                            logger.error(f"DM 消息持久化失败: {e}")
                            await ws.send_json(build_ws_error("SEND_FAILED", "消息发送失败"))
                            continue

                    msg["conversation_type"] = "dm"
                    # 审计日志：用户发送消息（fire-and-forget）
                    asyncio.create_task(_log_message_audit(user_id, "dm", session_id, msg["id"]))
                    # 回显给发送者
                    await ws.send_json({"type": "message", "conversation_type": "dm", "data": msg})
                    # 推送给对方（排除发送者）
                    await manager.broadcast_to_dm(
                        session_id,
                        {"type": "message", "conversation_type": "dm", "data": msg},
                        exclude_user_id=user_id,
                    )

                    # 触发 AI 回复（如果对方是 AI）
                    if sender_type == "human":
                        from app.ai.response_worker import message_queue
                        try:
                            message_queue.put_nowait({
                                "conversation_type": "dm",
                                "session_id": session_id,
                                "message_id": msg["id"],
                                "content": content,
                                "sender_type": sender_type,
                                "sender_id": user_id,
                                "chain_depth": 0,
                            })
                        except asyncio.QueueFull:
                            logger.warning("AI 回复队列已满，丢弃 DM 事件")

                    # Federation: forward DM to connected peers
                    try:
                        from app.services.federation.federation_manager import federation_manager as fed_mgr
                        asyncio.create_task(
                            fed_mgr.forward_dm_message(session_id, msg)
                        )
                    except Exception:
                        pass  # 联邦转发失败不影响本地消息

                else:
                    # ── 群聊消息（原有逻辑） ──
                    attachments = data.get("attachments")
                    if not group_id or (not content and not attachments):
                        await ws.send_json(build_ws_error("MISSING_FIELD", "缺少 group_id 或 content"))
                        continue

                    async with async_session() as db:
                        try:
                            message = await create_message(
                                db, group_id=group_id, sender_type=sender_type,
                                sender_id=user_id, content=content, reply_to=reply_to,
                                attachments=attachments,
                            )
                            await db.flush()
                        except Exception as e:
                            logger.error(f"消息持久化失败: {e}")
                            await ws.send_json(build_ws_error("SEND_FAILED", "消息发送失败"))
                            continue

                        # 统一走 users 表
                        sender_avatar = None
                        sender_state = None
                        try:
                            from app.models.user import User as UserModel
                            u = (await db.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one_or_none()
                            if u:
                                sender_avatar = u.avatar_url
                                if u.type == "ai":
                                    a = (await db.execute(select(AgentModel).where(AgentModel.user_id == user_id))).scalar_one_or_none()
                                    if a:
                                        sender_avatar = a.avatar_url or sender_avatar
                                        sender_state = a.state
                        except Exception as e:
                            logger.error(f"获取头像失败: {e}", exc_info=True)

                        msg_data = message_to_dict(message, sender_name=username, sender_avatar_url=sender_avatar, sender_state=sender_state)

                        # 审计日志：用户发送消息（fire-and-forget）
                        asyncio.create_task(_log_message_audit(user_id, "group", group_id, message.id))

                        # 先回显给发送者
                        await ws.send_json({"type": "message", "conversation_type": "group", "data": msg_data})

                        # 收集在线成员 ID 列表
                        online_ids = [
                            uid for uid in manager.group_connections.get(group_id, {})
                            if uid != user_id
                        ]

                        if online_ids:
                            try:
                                # 批量查询所有在线成员的 DND 状态（替代逐个 N+1 查询）
                                paused_result = await db.execute(
                                    select(AgentModel.id).where(
                                        AgentModel.id.in_(online_ids),
                                        AgentModel.is_paused == True,
                                    )
                                )
                                paused_ids = {row[0] for row in paused_result.all()}

                                now = datetime.utcnow()
                                dnd_result = await db.execute(
                                    select(GroupMemberModel.member_id, GroupMemberModel.dnd_until).where(
                                        GroupMemberModel.group_id == group_id,
                                        GroupMemberModel.member_type == "ai",
                                        GroupMemberModel.member_id.in_(online_ids),
                                    )
                                )
                                dnd_map: dict[int, datetime | None] = {row[0]: row[1] for row in dnd_result.all()}

                                # 广播：DND 成员暂存消息，但 @提及 强制推送
                                from app.utils.text import extract_mentions
                                mentioned_names = extract_mentions(content)
                                is_all_call = "@all" in content.lower() or "@ai" in content.lower()
                                mentioned_agents = set()
                                for uid in online_ids:
                                    agent_name_result = await db.execute(
                                        select(AgentModel.name).where(AgentModel.id == uid)
                                    )
                                    agent_name = agent_name_result.scalar_one_or_none()
                                    if agent_name and (agent_name in mentioned_names or is_all_call):
                                        mentioned_agents.add(uid)

                                for uid, user_ws in manager.group_connections[group_id].items():
                                    if uid == user_id:
                                        continue

                                    in_dnd = (
                                        uid in paused_ids
                                        or (uid in dnd_map and (dnd_map[uid] is None or dnd_map[uid] > now))
                                    )

                                    # @提及强制推送（即使 DND 也推送）
                                    if in_dnd and uid in mentioned_agents:
                                        try:
                                            await user_ws.send_json({"type": "message", "conversation_type": "group", "data": msg_data})
                                        except Exception as e:
                                            logger.warning(f"发送消息给用户 {uid} 失败: {e}")
                                        continue

                                    if in_dnd:
                                        try:
                                            await store_pending_message(
                                                db, agent_id=uid, group_id=group_id,
                                                message_id=message.id,
                                            )
                                        except Exception as e:
                                            logger.warning(f"暂存消息给 AI {uid} 失败: {e}")
                                        continue

                                    try:
                                        await user_ws.send_json({"type": "message", "conversation_type": "group", "data": msg_data})
                                    except Exception as e:
                                        logger.warning(f"发送消息给用户 {uid} 失败: {e}")
                            except Exception as e:
                                logger.error(f"广播消息给群成员失败: {e}", exc_info=True)
                                # 广播失败不阻断消息已创建的事实

                        # 持久化提交
                        try:
                            await db.commit()
                        except Exception as e:
                            logger.error(f"消息提交失败: {e}", exc_info=True)
                            await ws.send_json(build_ws_error("SEND_FAILED", "消息提交失败"))
                            continue

                        # 联邦通信：异步转发到共享此群的对等端
                        try:
                            from app.services.federation.federation_service import is_group_federated as check_grp_fed
                            is_fed = await check_grp_fed(db, group_id)
                            if is_fed:
                                from app.services.federation.federation_manager import federation_manager as fed_mgr
                                asyncio.create_task(
                                    fed_mgr.forward_message(group_id, msg_data)
                                )
                        except Exception:
                            pass  # 联邦转发失败不影响本地消息

                        # 触发 AI 自动回复 worker（仅人类消息，始终触发不受在线用户数影响）
                        if sender_type == "human":
                            from app.ai.response_worker import message_queue
                            try:
                                message_queue.put_nowait({
                                    "conversation_type": "group",
                                    "group_id": group_id,
                                    "message_id": message.id,
                                    "content": content,
                                    "sender_type": sender_type,
                                    "sender_id": user_id,
                                    "chain_depth": 0,
                                })
                                logger.info(f"📨 消息已推入 AI 队列: group={group_id}, msg={message.id}, queue_size={message_queue.qsize()}")
                            except asyncio.QueueFull:
                                logger.warning("AI 回复队列已满，丢弃事件")

                        # 触发向量化 pipeline（仅向量加速群聊）
                        try:
                            from app.models.group import Group as GroupModel
                            group_check = await db.execute(
                                select(GroupModel.is_vector_accelerated).where(
                                    GroupModel.id == group_id,
                                )
                            )
                            is_accelerated = group_check.scalar_one_or_none()
                            if is_accelerated:
                                from app.services.memory.vector_pipeline import embedding_queue
                                try:
                                    embedding_queue.put_nowait({
                                        "group_id": group_id,
                                        "message_id": message.id,
                                    })
                                except asyncio.QueueFull:
                                    pass  # 向量化队列满则丢弃，不影响主流程
                        except Exception as e:
                            logger.warning(f"向量化 pipeline 触发失败: {e}")

            # ---- 输入状态 ----
            elif msg_type == "typing":
                session_id = data.get("session_id")
                group_id = data.get("group_id", current_group_id)
                is_typing = data.get("is_typing", False)

                # 使用连接时缓存的头像
                sender_avatar_url = _user_avatar

                if session_id:
                    # DM 输入状态
                    await manager.broadcast_to_dm(
                        session_id,
                        {
                            "type": "typing",
                            "conversation_type": "dm",
                            "data": {
                                "session_id": session_id,
                                "sender_id": user_id,
                                "username": username,
                                "avatar_url": sender_avatar_url,
                                "is_typing": is_typing,
                            },
                        },
                        exclude_user_id=user_id,
                    )
                elif group_id:
                    await manager.broadcast_to_group(
                        group_id,
                        {
                            "type": "typing",
                            "conversation_type": "group",
                            "data": {
                                "group_id": group_id,
                                "sender_id": user_id,
                                "username": username,
                                "avatar_url": sender_avatar_url,
                                "is_typing": is_typing,
                            },
                        },
                        exclude_user_id=user_id,
                    )

            # ---- pong（心跳响应）— 静默忽略，_last_activity 已更新 ----
            elif msg_type == "pong":
                pass

            # ---- 未知类型 ----
            else:
                logger.debug(f"未知消息类型: {msg_type}")
                # 不报错，静默忽略（允许客户端扩展协议）

    except WebSocketDisconnect:
        logger.info(f"用户 {user_id} WebSocket 断开")
    finally:
        heartbeat_task.cancel()
        # 记录离线时间
        try:
            async with async_session() as _offline_db:
                # 心跳首次检测到离线的时间（一个周期无回应）；正常断开则为 func.now()
                ts = manager.get_offline_timestamp(user_id) or func.now()
                await _offline_db.execute(
                    sa_update(UserModel).where(UserModel.id == user_id).values(last_active_at=ts)
                )
                await _offline_db.commit()
        except Exception:
            pass
        if current_group_id is not None:
            manager.disconnect(current_group_id, user_id)
            await manager.broadcast_to_group(
                current_group_id,
                {"type": "user_offline", "conversation_type": "group", "data": {"user_id": user_id, "username": username}},
            )
        if current_session_id is not None:
            # 真人下线 → 通知 DM 对方更新状态点
            await manager.broadcast_to_dm(
                current_session_id,
                {"type": "state_change", "data": {
                    "user_id": user_id,
                    "state": "inactive",
                    "last_active_at": None,
                }},
                exclude_user_id=user_id,
            )
            manager.disconnect_dm(current_session_id, user_id)

async def _log_message_audit(user_id: int, conv_type: str, conv_id: int | str, message_id: int):
    """审计日志：用户发送消息（只记 message_id，内容查消息表）"""
    try:
        from app.database import async_session
        from app.services.audit_service import log_user_action
        from app.utils.auth import get_current_request_ip
        async with async_session() as session:
            await log_user_action(
                session, "send_message", user_id, conv_type,
                target_id=conv_id if isinstance(conv_id, int) else 0,
                details={"message_id": message_id},
                ip=get_current_request_ip(),
            )
    except Exception:
        pass
