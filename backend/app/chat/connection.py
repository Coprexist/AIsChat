"""
WebSocket 连接管理器

职责：管理群聊、私信、用户的 WebSocket 连接池。
这是纯消息通道，不含 AI 决策逻辑。
"""

import logging
from fastapi import WebSocket
from app.utils.error_handler import build_ws_error

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器（支持 DND 过滤、错误推送、私信）"""

    def __init__(self):
        # 群聊连接：{group_id: {user_id: websocket}}
        self.group_connections: dict[int, dict[int, WebSocket]] = {}
        # 私信连接：{session_id: {user_id: websocket}}
        self.dm_connections: dict[str, dict[int, WebSocket]] = {}
        # 用户全局连接：{user_id: websocket} 用于推送/通知
        self.user_connections: dict[int, WebSocket] = {}

    async def connect(self, ws: WebSocket, group_id: int, user_id: int):
        if group_id not in self.group_connections:
            self.group_connections[group_id] = {}
        self.group_connections[group_id][user_id] = ws
        self.user_connections[user_id] = ws
        logger.info(f"用户 {user_id} 加入群聊 {group_id} 的 WebSocket")

    def disconnect(self, group_id: int, user_id: int):
        if group_id in self.group_connections:
            self.group_connections[group_id].pop(user_id, None)
            if not self.group_connections[group_id]:
                del self.group_connections[group_id]
        self.user_connections.pop(user_id, None)
        logger.info(f"用户 {user_id} 离开群聊 {group_id} 的 WebSocket")

    async def broadcast_to_group(
        self,
        group_id: int,
        message: dict,
        exclude_user_id: int | None = None,
    ):
        """向群聊广播消息（排除发送者）"""
        if group_id in self.group_connections:
            for uid, ws in list(self.group_connections[group_id].items()):
                if exclude_user_id is not None and uid == exclude_user_id:
                    continue
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.warning(f"发送消息给用户 {uid} 失败: {e}")

    async def send_to_user(self, user_id: int, message: dict):
        """向特定用户发送消息（如错误通知、摘要）"""
        if user_id in self.user_connections:
            try:
                await self.user_connections[user_id].send_json(message)
            except Exception as e:
                logger.warning(f"发送消息给用户 {user_id} 失败: {e}")

    async def send_error(self, user_id: int, code: str, message: str,
                         tool_call_id: str | None = None):
        """向特定用户发送 WebSocket 错误事件"""
        error_event = build_ws_error(code, message, tool_call_id)
        await self.send_to_user(user_id, error_event)

    def get_online_users(self, group_id: int) -> list[int]:
        if group_id in self.group_connections:
            return list(self.group_connections[group_id].keys())
        return []

    def is_user_online(self, user_id: int) -> bool:
        return user_id in self.user_connections

    def get_online_user_ids(self) -> set[int]:
        return set(self.user_connections.keys())

    # ── DM 连接管理 ──

    async def connect_dm(self, ws: WebSocket, session_id: str, user_id: int):
        if session_id not in self.dm_connections:
            self.dm_connections[session_id] = {}
        self.dm_connections[session_id][user_id] = ws
        self.user_connections[user_id] = ws
        logger.info(f"用户 {user_id} 加入私信 {session_id} 的 WebSocket")

    def disconnect_dm(self, session_id: str, user_id: int):
        if session_id in self.dm_connections:
            self.dm_connections[session_id].pop(user_id, None)
            if not self.dm_connections[session_id]:
                del self.dm_connections[session_id]

    async def broadcast_to_dm(
        self,
        session_id: str,
        message: dict,
        exclude_user_id: int | None = None,
    ):
        """向私信会话广播消息（通常是推送给对方）"""
        if session_id in self.dm_connections:
            for uid, ws in list(self.dm_connections[session_id].items()):
                if exclude_user_id is not None and uid == exclude_user_id:
                    continue
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.warning(f"发送 DM 消息给用户 {uid} 失败: {e}")

    async def broadcast_avatar_updated(
        self, entity_type: str, entity_id: int, avatar_url: str,
    ):
        """头像下载完成后通知所有已连接客户端更新消息气泡中的头像 URL"""
        event = {
            "type": "avatar_updated",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "avatar_url": avatar_url,
        }
        for conns in self.group_connections.values():
            for ws in conns.values():
                try:
                    await ws.send_json(event)
                except Exception:
                    pass
        for conns in self.dm_connections.values():
            for ws in conns.values():
                try:
                    await ws.send_json(event)
                except Exception:
                    pass

    async def broadcast_to_all(self, message: dict):
        """向所有已连接的用户广播消息（用于维护模式等全局通知）"""
        dead = []
        for user_id, ws in list(self.user_connections.items()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(user_id)
        for uid in dead:
            self.user_connections.pop(uid, None)
