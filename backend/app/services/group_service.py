"""
群聊服务 —— 兼容层（委托到 chat/ 子模块）

⚠️ 旧代码直接 import 本文件，因此保留所有导出。
新代码应直接使用 app.chat 或 ChatApi。

AI 专属逻辑已迁移到 app.ai.group_logic，此处仅做兼容导出。
"""

from app.chat.message import (
    create_group,
    get_group,
    list_user_groups,
    add_member,
    get_group_members,
    create_message,
    get_recent_messages,
    message_to_dict,
    is_member_of_group,
    remove_member,
    leave_group,
    update_last_read,
    update_group_settings,
    change_member_role,
    disband_group,
    set_announcement,
    delete_announcement,
    get_unread_info,
)
from app.chat.delivery import (
    set_group_dnd,
    cancel_group_dnd,
    is_member_in_dnd,
    is_member_muted,
    store_pending_message,
    get_pending_messages,
    mark_pending_read,
    check_unread,
    generate_llm_summary,
)

from app.chat.message import _get_member


from app.ai.group_logic import (
    is_ai_only_group,
    pause_notifications,
    resume_and_fetch,
)


__all__ = [
    "create_group", "get_group", "list_user_groups", "add_member",
    "get_group_members", "create_message", "get_recent_messages",
    "message_to_dict", "is_member_of_group", "remove_member", "leave_group",
    "update_last_read", "update_group_settings", "change_member_role",
    "disband_group", "set_announcement", "delete_announcement", "get_unread_info",
    "set_group_dnd", "cancel_group_dnd", "is_member_in_dnd", "is_member_muted",
    "store_pending_message", "get_pending_messages", "mark_pending_read",
    "check_unread", "generate_llm_summary",
    "is_ai_only_group", "pause_notifications", "resume_and_fetch",
]