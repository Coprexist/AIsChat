"""
群视界实时 WebSocket 连接管理器

维护 world_id -> user_id -> WebSocket 连接映射，
提供广播和单播能力。与聊天 ConnectionManager 完全独立。
"""
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WorldRealtimeManager:
    """群视界实时连接管理器（单例）"""

    def __init__(self) -> None:
        # world_id -> {user_id -> WebSocket}
        self._connections: dict[int, dict[int, WebSocket]] = {}

    async def connect(self, world_id: int, user_id: int, ws: WebSocket) -> None:
        """接受 WebSocket 连接并注册"""
        await ws.accept()
        self._connections.setdefault(world_id, {})[user_id] = ws
        logger.debug(f"🌐 世界 #{world_id} 实时连接: user={user_id}")

    def disconnect(self, world_id: int, user_id: int) -> None:
        """断开连接并移除注册"""
        world_conns = self._connections.get(world_id)
        if world_conns:
            world_conns.pop(user_id, None)
            if not world_conns:
                self._connections.pop(world_id, None)
        logger.debug(f"🌐 世界 #{world_id} 实时断开: user={user_id}")

    async def broadcast_state(self, world_id: int, state: dict[str, Any]) -> None:
        """向世界内所有连接广播状态"""
        world_conns = self._connections.get(world_id, {})
        if not world_conns:
            return
        payload = json.dumps({"type": "state", "state": state}, ensure_ascii=False)
        dead: list[int] = []
        for uid, ws in world_conns.items():
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(uid)
        for uid in dead:
            world_conns.pop(uid, None)

    async def send_to_user(self, world_id: int, user_id: int, message: dict[str, Any]) -> None:
        """向单个用户发送消息"""
        ws = self._connections.get(world_id, {}).get(user_id)
        if ws is None:
            return
        try:
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            self._connections.get(world_id, {}).pop(user_id, None)


# 全局单例
realtime_manager = WorldRealtimeManager()
