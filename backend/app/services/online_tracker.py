"""
在线状态追踪 — 基于用户 API 活动时间戳，不依赖 WebSocket 连接

比 WebSocket 连接更可靠：只要有 API 请求（token 验证通过），
1 分钟内都算在线。
"""
import time

# {user_id: last_activity_timestamp}
_user_activity: dict[int, float] = {}

ACTIVITY_WINDOW_SECONDS = 60  # 1 分钟内有活动即在线


def record_activity(user_id: int) -> None:
    """记录用户活动时间戳（每次 API 请求调用）"""
    _user_activity[user_id] = time.monotonic()


def is_online(user_id: int) -> bool:
    """检查用户是否在线（1 分钟内有活动）"""
    last = _user_activity.get(user_id)
    if last is None:
        return False
    return (time.monotonic() - last) < ACTIVITY_WINDOW_SECONDS


def get_online_user_ids() -> set[int]:
    """获取当前在线的所有用户 ID"""
    now = time.monotonic()
    return {uid for uid, ts in _user_activity.items() if (now - ts) < ACTIVITY_WINDOW_SECONDS}


def record_ws_activity(user_id: int) -> None:
    """WebSocket 消息也记为活动（发送消息时调用）"""
    _user_activity[user_id] = time.monotonic()
