"""
群视界实时 WebSocket 路由

WS /world/{world_id}/realtime?token=<JWT>

为常驻世界提供最小实时消息收发通道。
与聊天 WebSocket（ws.py）完全独立，互不影响。
"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.database import async_session
from app.models.world import World
from app.services.world.realtime_connection_manager import realtime_manager
from app.services.world.world_resident import manager as resident_manager
from app.utils.auth import decode_access_token

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/world/{world_id}/realtime")
async def world_realtime_ws(
    websocket: WebSocket,
    world_id: int,
    token: str = Query(...),
):
    """群视界实时 WebSocket 端点"""

    # ── JWT 校验 ──
    result = decode_access_token(token)
    if result.is_err():
        await websocket.close(code=4001, reason="无效 token")
        return
    user_id = result.ok.get("user_id")
    if user_id is None:
        await websocket.close(code=4001, reason="token 中无 user_id")
        return

    # ── 世界存在性 + 常驻校验 ──
    async with async_session() as db:
        world = await db.get(World, world_id)
        if world is None:
            await websocket.close(code=4004, reason="世界不存在")
            return
        is_resident = resident_manager.is_resident(world)

    # ── 接受连接 ──
    await realtime_manager.connect(world_id, user_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await realtime_manager.send_to_user(world_id, user_id, {
                    "type": "error", "code": "INVALID_JSON", "message": "消息格式无效",
                })
                continue

            msg_type = msg.get("type", "")

            if msg_type == "input":
                # ── 实时输入事件 ──
                if not is_resident:
                    await realtime_manager.send_to_user(world_id, user_id, {
                        "type": "error", "code": "NOT_RESIDENT",
                        "message": "当前世界不支持实时交互",
                    })
                    continue

                seq = msg.get("seq")
                input_data = msg.get("input", {})

                dispatched = await resident_manager.dispatch(world_id, {
                    "type": "user_input",
                    "user_id": user_id,
                    "input": input_data,
                })

                if not dispatched:
                    await realtime_manager.send_to_user(world_id, user_id, {
                        "type": "error", "code": "DISPATCH_FAILED",
                        "message": "事件投递失败，常驻进程可能已停止",
                    })

                # 确认收到（客户端可据此做 seq 追踪）
                await realtime_manager.send_to_user(world_id, user_id, {
                    "type": "ack", "seq": seq,
                })

            elif msg_type == "ping":
                await realtime_manager.send_to_user(world_id, user_id, {
                    "type": "pong",
                })

            else:
                await realtime_manager.send_to_user(world_id, user_id, {
                    "type": "error", "code": "UNKNOWN_TYPE",
                    "message": f"未知消息类型: {msg_type}",
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 实时 WS 异常: {e}")
    finally:
        realtime_manager.disconnect(world_id, user_id)
