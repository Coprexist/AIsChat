"""世界工具展示文案的完备性守卫。

`_tool_result_summary` 是一长串 `name == "..."` 分派；漏写一个工具，前端卡片就只剩
「工具执行成功」这种零信息量文案，用户看不出刚发生了什么。这里用 AST 把分派里实际出现过的
工具名抠出来，与 `WORLD_TOOLS` 清单对齐，让"漏写文案"在 CI 暴露，而不是等用户发现。
"""
from __future__ import annotations

import ast
import inspect

from app.services.world.world_tools import WORLD_TOOLS, _tool_result_summary


def _declared_tool_names() -> set[str]:
    return {t["function"]["name"] for t in WORLD_TOOLS}


def _covered_tool_names() -> set[str]:
    tree = ast.parse(inspect.getsource(_tool_result_summary))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not (isinstance(node.left, ast.Name) and node.left.id == "name"):
            continue
        names.update(
            c.value for c in node.comparators
            if isinstance(c, ast.Constant) and isinstance(c.value, str)
        )
    return names


def test_world_tools_all_have_summary():
    missing = sorted(_declared_tool_names() - _covered_tool_names())
    assert not missing, f"这些世界工具没有展示文案，会落到兜底分支：{missing}"


def test_skill_fallback_carries_tool_name_and_gist():
    # 世界自定义 skill 的名字与返回值都不固定，只能走兜底分支：至少要带工具名和一句结果
    ok = _tool_result_summary("watch_gift", {"success": True, "result": "本轮共 3 次"})
    assert "watch_gift" in ok and "本轮共 3 次" in ok
    assert "工具执行成功" not in ok

    failed = _tool_result_summary("watch_gift", {"success": False, "error": "沙箱超时"})
    assert "失败" in failed and "沙箱超时" in failed


def test_manage_records_summary_follows_action():
    written = _tool_result_summary(
        "manage_records",
        {"success": True, "action": "set", "category": "user", "sub_key": "偏好", "field": "风格"},
    )
    assert written == "结构化记忆已写入：user/偏好/风格"

    cats = _tool_result_summary(
        "manage_records",
        {"success": True, "action": "categories", "categories": ["user", "project", "world"]},
    )
    assert "3" in cats and "user" in cats
