"""
纯配置查找/解析函数——无 IO，无副作用。
"""


def find_old_config(old_raw, host: str, username: str) -> dict | None:
    """从旧配置中查找匹配 host+username 的配置项（用于密码保留）。

    Args:
        old_raw: 旧配置数据，可以是 dict（单配置）或 list[dict]（多配置）
        host: 主机名
        username: 用户名

    Returns:
        匹配的配置项 dict，或 None
    """
    if not old_raw:
        return None
    if isinstance(old_raw, dict):
        configs = [old_raw]
    elif isinstance(old_raw, list):
        configs = old_raw
    else:
        return None
    for c in configs:
        if isinstance(c, dict) and c.get("host") == host and c.get("username") == username:
            return c
    return None
