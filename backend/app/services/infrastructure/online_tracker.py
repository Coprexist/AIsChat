"""
在线状态追踪 — 统一入口

所有模块通过 get_user_online_status(user_id) 获取用户的实时在线状态，
内部合并 WebSocket 连接 + API 活动追踪两个来源。
"""
import time

# {user_id: last_activity_timestamp}
_user_activity: dict[int, float] = {}

ACTIVITY_WINDOW_SECONDS = 60  # 1 分钟内有活动即在线


def record_activity(user_id: int) -> None:
    """记录用户活动时间戳（每次 API 请求调用）"""
    _user_activity[user_id] = time.monotonic()


def record_ws_activity(user_id: int) -> None:
    """WebSocket 消息也记为活动"""
    _user_activity[user_id] = time.monotonic()


def get_online_user_ids() -> set[int]:
    """获取当前在线的所有用户 ID（活动追踪）"""
    now = time.monotonic()
    return {uid for uid, ts in _user_activity.items() if (now - ts) < ACTIVITY_WINDOW_SECONDS}


def get_user_online_status(user_id: int) -> bool:
    """
    统一判断用户是否在线。
    合并 WebSocket 连接 + API 活动追踪两个来源。
    所有模块都通过此函数判断，不要各自重复实现。
    """
    # 惰性导入避免循环依赖（ws.py → auth.py → online_tracker.py）
    from app.routers.ws import manager as ws_manager
    if ws_manager.is_user_online(user_id):
        return True
    last = _user_activity.get(user_id)
    if last is not None and (time.monotonic() - last) < ACTIVITY_WINDOW_SECONDS:
        return True
    return False
