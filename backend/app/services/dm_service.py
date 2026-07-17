"""
私信（DM）服务 —— 兼容层（委托到 chat/ 子模块）

⚠️ 旧代码直接 import 本文件，因此保留所有导出。
新代码应直接使用 app.chat 或 ChatApi。
"""

from app.chat.dm import (
    _dm_message_to_dict,
    _require_friendship,
    generate_dm_session_id,
    get_or_create_dm_session,
    list_dm_sessions,
    get_dm_session,
    get_dm_messages,
    send_dm_message,
    set_dm_dnd,
    cancel_dm_dnd,
    _get_partner_info,
    _get_user_name,
    _get_messages,
    is_user_in_dm_dnd,
)


__all__ = [
    "generate_dm_session_id",
    "get_or_create_dm_session",
    "list_dm_sessions",
    "get_dm_session",
    "get_dm_messages",
    "send_dm_message",
    "set_dm_dnd",
    "cancel_dm_dnd",
    "is_user_in_dm_dnd",
]
