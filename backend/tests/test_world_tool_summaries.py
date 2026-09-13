"""世界工具插件的契约守卫。

每个世界工具必须自报家门：label / segment / summary —— 注册表在 import 时就把关
（缺 summary 的类根本注册不进来），这里再补业务向断言：清单完整、文案是人话、展示入口可达。
"""
from __future__ import annotations

from app.tools.world import (
    SEGMENTS,
    WORLD_TOOLS,
    WorldToolRegistry,
    tool_result_detail,
    tool_result_summary,
)


def test_registry_covers_declared_schemas():
    """发给 LLM 的每个工具都必须有插件实现，反之亦然（一个工具一个文件）"""
    declared = {d["function"]["name"] for d in WORLD_TOOLS}
    implemented = {p.name for p in WorldToolRegistry.all() if p.exposed}
    assert declared == implemented
    assert len(declared) >= 29


def test_every_plugin_self_describes():
    """没有展示定义的插件注册不进来；成功/失败两条路径都必须有话可说"""
    for plugin in WorldToolRegistry.all():
        assert plugin.label, f"{plugin.name} 缺中文名"
        assert plugin.segment in SEGMENTS, f"{plugin.name} 分组非法"
        for result in ({"success": True}, {"success": False, "error": "boom"}):
            text = plugin.summary(result)
            assert text and "工具执行成功" not in text, f"{plugin.name} 展示文案不合格：{text!r}"


def test_skill_fallback_is_informative():
    """世界自定义 skill 走统一定义的规则：带工具名 + 结果摘要 + 错误原文"""
    ok = tool_result_summary("watch_gift", {"success": True, "result": "本轮共 3 次"})
    assert "watch_gift" in ok and "本轮共 3 次" in ok

    failed = tool_result_summary("watch_gift", {"success": False, "error": "沙箱超时"})
    assert "失败" in failed and "沙箱超时" in failed


def test_detail_shows_args_and_result():
    """点击卡片展开的内容：参数 + 结果（工具想更好读就覆盖 detail）"""
    text = tool_result_detail("file_read", {"path": "main.py"}, {"success": True, "path": "main.py"})
    assert "main.py" in text and "参数" in text and "结果" in text
