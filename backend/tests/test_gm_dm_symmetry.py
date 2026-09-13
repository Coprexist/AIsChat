"""群聊（GM）与私信（DM）的接口命名对称。

约定见 docs/guides/用户手册.md：GM = Group Message，DM = Direct Message。
REST 侧同形：/gm/{group_id}/messages ↔ /dm/{session_id}/messages。

历史事故：群消息一度有三个入口（/chat/message、/chat/messages、
/groups/{id}/messages）。其中 /chat/* 无认证，且 POST 恒 500 —— ChatApi
签名缺 dm_session_id 参数。本用例锁住"群消息只有一个入口"。
"""
from app.main import app

GROUP_MESSAGE_PATH = "/gm/{group_id}/messages"
DM_MESSAGE_PATH = "/dm/{session_id}/messages"

# 已删除的重复入口：重新出现即视为回归
REMOVED_PATHS = (
    "/chat/message",
    "/chat/messages",
    "/groups/{group_id}/messages",
    "/chat/group/dnd",
    "/chat/group/{group_id}",
    "/chat/group/{group_id}/members",
    "/chat/group/join",
    "/chat/group/leave",
)


def _route_table() -> dict[str, set[str]]:
    table: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        table.setdefault(path, set()).update(getattr(route, "methods", None) or ())
    return table


async def test_gm_and_dm_message_endpoints_are_symmetric():
    table = _route_table()
    for path in (GROUP_MESSAGE_PATH, DM_MESSAGE_PATH):
        assert path in table, f"{path} 未注册"
        methods = table[path]
        assert {"GET", "POST"} <= methods, f"{path} 应同时提供 GET/POST，实际 {sorted(methods)}"


async def test_duplicate_group_message_entrypoints_stay_removed():
    table = _route_table()
    for path in REMOVED_PATHS:
        assert path not in table, f"{path} 是已删除的重复入口，不得回归"


async def test_user_and_friend_routes_are_kept():
    """chat 前缀下剩下的是用户与好友查询，不属群聊语义，按约定保留。"""
    table = _route_table()
    assert "/chat/user/{user_id}" in table
    assert "/chat/friend/request" in table
