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


async def test_slash_command_reuses_the_single_summary_entry():
    """命令文案必须走 tool_result_summary（唯一展示入口），并如实报告做没做成。

    自己再抄一遍格式就会漂移：/compact 原先手拼字符串，漏了「无需压缩」这条分支，
    于是用户看到「上下文已压缩：None → None tokens（压缩率 None%）」，还配着一个 ✓。
    """
    import app.tools.world as world_tools
    from app.services.world import world_chat_commands as cmds

    scripted = [
        {"success": True, "skipped": True, "real_messages": 3, "keep_last": 20},
        {"success": True, "before_tokens": 12000, "after_tokens": 3000, "compression_ratio_pct": 75},
        {"success": False, "error": "模型超时"},
    ]

    async def fake_run(_repo, _world, name, arguments, *a, **k):
        assert name == "compact_context"
        return scripted.pop(0)

    original = world_tools.run_world_tool
    world_tools.run_world_tool = fake_run
    try:
        ctx = cmds.CmdContext(world_repo=None, world=None, cmd_text="/compact", user_id=1, args="")
        noop, compacted, failed = [await cmds._cmd_compact(ctx) for _ in range(3)]
    finally:
        world_tools.run_world_tool = original

    # 空操作如实说「无需压缩」：不能假装压过了，更不该冒出 None（也不许硬画 ✓）
    assert noop.ok is True and "无需压缩" in noop.text and "None" not in noop.text
    assert "3" in noop.text and "20" in noop.text
    assert compacted.ok is True and "12000" in compacted.text and "75" in compacted.text
    assert failed.ok is False and "模型超时" in failed.text


async def test_slash_command_boundary_normalizes_result():
    """边界归一：handler 返回 str（其余六条命令）也收成 CmdResult；非命令返回 None"""

    class _WorldStub:
        """极简世界替身：/sessions 只读 config"""

        id = 1
        config: dict = {}

    from app.services.world import world_chat_commands as cmds

    assert await cmds.run_slash_command(None, _WorldStub(), "普通消息") is None
    assert await cmds.run_slash_command(None, _WorldStub(), "/不存在") is None
    result = await cmds.run_slash_command(None, _WorldStub(), "/sessions")
    assert result is not None and result.ok is True and "会话" in result.text
