"""会话记录导出（Markdown / JSON）的契约守卫。

导出 = 另存为：内容必须与对话面板所见一致（正文 / 思考 / 工具 / 报错、按时间正序），
且**不得**带出凭据——世界自己的 API token 若被 AI 打进工具输出，导出必须打码。
"""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

from app.services.world.world_chat_export import render, render_json, render_markdown, safe_filename


def _world(token: str = "") -> SimpleNamespace:
    return SimpleNamespace(id=7, name="诗の子", config={"api_token": token})


def _msg(i, role, content, **kw) -> SimpleNamespace:
    row = dict(id=i, role=role, content=content, reasoning=None, tool_name=None,
               tool_detail=None, is_error=False, attachments=None,
               created_at=datetime(2026, 9, 16, 10, 0))
    row.update(kw)
    return SimpleNamespace(**row)


SESSION = {"id": "w7:m:abc", "title": "造卡牌对战界面", "created_at": "t", "last_active_at": "t"}


def test_markdown_covers_every_role_in_order():
    msgs = [
        _msg(1, "user", "帮我做个卡牌界面"),
        _msg(2, "note", "先看看现有文件"),
        _msg(3, "tool", "已写入 index.html", tool_name="file_write", tool_detail="参数\n{}"),
        _msg(4, "tool", "磁盘满了", tool_name="file_write", is_error=True),
        _msg(5, "ai", "做好了"),
    ]
    md = render_markdown(_world(), SESSION, msgs)
    assert md.startswith("# 造卡牌对战界面")
    for token in ("**用户**", "**思考**", "**工具 · file_write**", "❌ 失败", "**AI**",
                  "帮我做个卡牌界面", "做好了", "先看看现有文件", "调用详情："):
        assert token in md, token
    assert md.index("帮我做个卡牌界面") < md.index("先看看现有文件") < md.index("做好了")


def test_markdown_does_not_repeat_reasoning_that_already_has_a_note():
    dup = "同一段思考"
    md = render_markdown(_world(), SESSION, [_msg(1, "note", dup), _msg(2, "ai", "结论", reasoning=dup)])
    assert md.count(dup) == 1          # 思考条已经展示过，就不再重复（与面板同一条规则）


def test_export_redacts_the_world_api_token():
    token = "wt_" + "a" * 20
    msgs = [
        _msg(1, "tool", f"WORLD_API_TOKEN={token}", tool_name="run_world_code", tool_detail=f"env: {token}"),
        _msg(2, "ai", f"我看到 {token} 了"),
    ]
    md = render_markdown(_world(token), SESSION, msgs)
    js = render_json(_world(token), SESSION, msgs)
    assert token not in md and token not in js
    assert "***" in md and "***" in js


def test_json_keeps_structured_fields():
    msgs = [_msg(1, "tool", "ok", tool_name="file_read", attachments=[{"name": "a.png"}], is_error=True)]
    data = json.loads(render_json(_world(), SESSION, msgs))
    assert data["world"] == {"id": 7, "name": "诗の子"}
    assert data["session"]["title"] == "造卡牌对战界面"
    assert data["count"] == 1
    m = data["messages"][0]
    assert m["role"] == "tool" and m["tool_name"] == "file_read" and m["is_error"] is True
    assert m["attachments"][0]["name"] == "a.png"
    assert m["created_at"].startswith("2026-09-16")


def test_render_picks_format_and_filename():
    body, media, name = render(_world(), SESSION, [_msg(1, "ai", "hi")], "md")
    assert body.startswith("# ") and media.startswith("text/markdown")
    assert name.endswith(".md") and "造卡牌对战界面" in name
    body, media, name = render(_world(), SESSION, [], "json")
    assert media.startswith("application/json") and name.endswith(".json")
    assert json.loads(body)["count"] == 0


def test_filename_has_no_path_characters():
    world = SimpleNamespace(id=1, name='a/b:c*d?e"f<g>h|i', config={})
    name = safe_filename(world, {"id": "x", "title": "t\nx"}, "md")
    for ch in '/\\:*?"<>|':
        assert ch not in name, f"{ch} 不该出现在文件名里：{name}"
