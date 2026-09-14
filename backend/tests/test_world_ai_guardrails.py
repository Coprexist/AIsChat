"""世界 AI 安全护栏的契约守卫（2026-09-15 产品定）。

三件事必须有静态可验证的边界，不能只靠提示词自觉：
1. 禁用后缀：可执行文件/安装包/宿主脚本——创建即拒，遗留的兜底强删，AI 与用户同一套；
2. 下载：固定落点 downloads/，违规内容（色情/暴力/违法）命中即失败、不落盘；
3. 运行模式：自动放行、审阅弹窗、计划先挡；AI 没有改模式的工具（用户侧 API 才有）。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import tempfile

from app.services.world import world_file_service as fs
from app.services.world.world_ai_mode import (
    DEFAULT_MODE,
    MODES,
    action_of,
    gate_tool_call,
    get_mode,
    pending_approvals,
    resolve_approval,
)
from app.services.world.world_turn import TurnBroadcast, _workers
from app.services.world.world_moderation import inspect

WORLD_ID = 987654


@contextlib.contextmanager
def _raises(*exc):
    """pytest.raises 的最小替身（无 pytest 运行器只提供 fixture/mark，不扩展它）"""
    try:
        yield
    except exc:
        return
    raise AssertionError(f"期望抛出 {exc}，但没有")


@contextlib.contextmanager
def _sandbox_world_dir():
    """把世界文件根指向临时目录（测试不碰真实 data/worlds）"""
    tmp = tempfile.mkdtemp(prefix="world-guard-")
    old = fs.WORLDS_ROOT
    fs.WORLDS_ROOT = __import__("pathlib").Path(tmp)
    try:
        yield fs._world_dir(WORLD_ID)
    finally:
        fs.WORLDS_ROOT = old
        shutil.rmtree(tmp, ignore_errors=True)


class _World:
    """世界替身：门禁只读 config（模式）与 id"""

    def __init__(self, mode: str | None = None):
        self.id = WORLD_ID
        self.config = {} if mode is None else {"ai_mode": mode}


def test_banned_extensions_are_rejected_at_creation():
    """AI 与用户共用同一条写入收口：禁用后缀创建即拒，普通世界代码照常"""
    with _sandbox_world_dir() as d:
        assert fs.write_file(WORLD_ID, "js/app.js", "console.log(1)")["path"] == "js/app.js"
        assert fs.write_file(WORLD_ID, "main.py", "print(1)")["path"] == "main.py"
        for name in ("tool.exe", "setup.msi", "run.sh", "hook.ps1", "lib.dll", "app.apk"):
            with _raises(fs.BannedFileError):
                fs.write_file(WORLD_ID, name, "x")
        with _raises(ValueError):              # 非禁用但也不在允许清单 → 同样拒绝
            fs.write_file(WORLD_ID, "notes.weird", "x")
        assert (d / "tool.exe").exists() is False


def test_sweep_removes_planted_binaries():
    """兜底强删：手动拷进目录的可执行文件，扫描一次就没了（返回被删清单）"""
    with _sandbox_world_dir() as d:
        fs.write_file(WORLD_ID, "index.html", "<html></html>")
        (d / "evil.exe").write_bytes(b"MZ")
        (d / "sub").mkdir()
        (d / "sub" / "agent.bat").write_text("del /f /q")
        assert sorted(fs.sweep_banned_files(WORLD_ID)) == ["evil.exe", "sub/agent.bat"]
        assert fs.sweep_banned_files(WORLD_ID) == []          # 幂等
        assert [f["path"] for f in fs.list_files(WORLD_ID)] == ["index.html"]


def test_move_and_copy_stay_inside_the_world():
    """移动/复制都走同一套越界与后缀校验"""
    with _sandbox_world_dir():
        fs.write_file(WORLD_ID, "css/a.css", "body{}")
        assert fs.move_file(WORLD_ID, "css/a.css", "assets/b.css")["path"] == "assets/b.css"
        assert fs.copy_file(WORLD_ID, "assets/b.css", "assets/c.css")["path"] == "assets/c.css"
        for call in (
            lambda: fs.move_file(WORLD_ID, "assets/b.css", "../escape.css"),
            lambda: fs.move_file(WORLD_ID, "assets/b.css", "assets/x.exe"),
            lambda: fs.copy_file(WORLD_ID, "assets/b.css", "assets/x.msi"),
            lambda: fs.move_file(WORLD_ID, "assets/missing.css", "assets/y.css"),
        ):
            with _raises(ValueError, FileNotFoundError):
                call()


def test_download_lands_in_fixed_dir():
    """下载位置固定：一律落在 downloads/ 下，越界直接拒绝"""
    from app.tools.world.shared import DOWNLOAD_DIR, download_target

    assert download_target("") == DOWNLOAD_DIR
    assert download_target("vue/vue.js") == f"{DOWNLOAD_DIR}/vue/vue.js"
    assert download_target("/vue/vue.js") == f"{DOWNLOAD_DIR}/vue/vue.js"
    assert download_target(f"{DOWNLOAD_DIR}/vue/vue.js") == f"{DOWNLOAD_DIR}/vue/vue.js"  # 不叠前缀
    with _raises(ValueError):
        download_target("../outside.js")


def test_code_urls_are_normalized_to_raw():
    """GitHub 页面链接自动转 raw 直链（AI 常直接贴浏览器地址）"""
    from app.tools.world.shared import normalize_code_url as norm

    assert norm("https://github.com/a/b/blob/main/src/x.ts") == \
        "https://raw.githubusercontent.com/a/b/main/src/x.ts"
    assert norm("https://gist.github.com/u/abc123") == "https://gist.github.com/u/abc123/raw"
    plain = "https://example.com/x.css"
    assert norm(plain) == plain


def test_moderation_blocks_flagged_url_and_body():
    """违规内容拦截：链接/文件名在下载前查，文本正文在下载后查"""
    assert inspect("https://pornhub.com/x.js") is not None
    assert inspect("https://example.com/a.js", "nsfw-pack.js") is not None
    assert inspect("https://example.com/a.js", "a.js", "…gore…".encode()) is not None
    assert inspect("https://example.com/a.js", "assets/a.js", b"body{color:red}") is None
    # 短词整词匹配：不能被 gorgeous / java 这类误伤
    assert inspect("https://example.com/gorgeous.css") is None
    assert inspect("https://example.com/java/App.java") is None


def test_action_classes_are_conservative():
    """只读工具明列；未登记的工具一律按「改动机制」——宁可多问一次"""
    assert action_of("file_read") is None
    assert action_of("web_fetch") is None
    assert action_of("web_download") == "download"
    assert action_of("file_delete") == "delete"
    assert action_of("file_write") == "modify"
    assert action_of("some_future_tool") == "modify"
    assert action_of("world_stats") == "modify"          # 世界自定义 skill 同样受管


def test_mode_defaults_to_review_and_ignores_garbage():
    assert DEFAULT_MODE in MODES
    assert get_mode(_World()) == DEFAULT_MODE
    assert get_mode(_World("auto")) == "auto"
    assert get_mode(_World("nonsense")) == DEFAULT_MODE


async def test_gate_auto_allows_plan_blocks_review_needs_a_human():
    """三种模式的门禁行为（没有可交互前端时审阅按「不同意」处理，不空等）"""
    args = {"url": "https://example.com/a.js"}

    allowed, approved, _ = await gate_tool_call(_World("auto"), WORLD_ID, "web_download", args, {})
    assert allowed and approved

    allowed, _, reason = await gate_tool_call(_World("plan"), WORLD_ID, "file_write", {"path": "a.js"}, {})
    assert not allowed and "计划" in reason
    allowed, approved, _ = await gate_tool_call(
        _World("plan"), WORLD_ID, "file_write", {"path": "a.js"}, {"plan_approved": True},
    )
    assert allowed and approved

    state: dict = {}
    allowed, _, reason = await gate_tool_call(_World("review"), WORLD_ID, "file_delete", {"path": "a.js"}, state)
    assert not allowed and "没有同意" in reason
    assert state.get("approved_classes", set()) == set()

    # 只读工具在任何模式下都不设卡
    for mode in MODES:
        allowed, approved, _ = await gate_tool_call(_World(mode), WORLD_ID, "file_read", {"path": "a.js"}, {})
        assert allowed and not approved


def test_resolve_approval_rejects_unknown_id():
    """点了已失效/不存在的审批项 → 明确返回 False（端点据此回 404）"""
    assert resolve_approval("no-such-approval", True) is False


class _LiveWorker:
    """活着的 world worker 替身：只提供门禁要用的两件事（turns / subscribe）"""

    def __init__(self, tb: TurnBroadcast):
        self.turns = {tb.turn_id: tb}
        self.task = asyncio.get_running_loop().create_future()   # 未完成 = worker 还活着

    def subscribe(self, turn_id: str):
        return self.turns.get(turn_id)


async def test_review_popup_round_trip():
    """审阅模式弹窗的完整闭环：门禁广播 → 用户点同意 → 工具被放行（不碰 LLM、不碰网络）"""
    wid_turn = 987655
    tb = TurnBroadcast("t_test")
    queue = tb.subscribe()                       # 模拟前端连着这条 SSE（没订阅者就不弹窗）
    _workers[wid_turn] = _LiveWorker(tb)
    turn_state = {"turn_id": "t_test"}
    try:
        task = asyncio.create_task(gate_tool_call(
            _World("review"), wid_turn, "web_download",
            {"url": "https://example.com/a.js"}, turn_state,
        ))
        # 弹窗事件必须带着 approval_id + 事件类型关键词到达前端
        raw = await asyncio.wait_for(queue.get(), timeout=2)
        payload = json.loads(raw.removeprefix("data: [APPROVAL]").strip())
        assert payload["status"] == "pending" and payload["kind"] == "download"
        assert payload["approval_id"]
        assert [a["approval_id"] for a in pending_approvals(wid_turn)] == [payload["approval_id"]]

        # 等待期间工具没被放行（还没点按钮）
        assert not task.done()

        assert resolve_approval(payload["approval_id"], True, "同意下载") is True
        allowed, approved, reason = await asyncio.wait_for(task, timeout=2)
        assert allowed and approved and not reason
        assert pending_approvals(wid_turn) == []
        assert "download" in turn_state["approved_classes"]     # 同类操作本轮不再问

        # resolved 回执：前端据此关掉弹窗
        resolved = json.loads((await asyncio.wait_for(queue.get(), timeout=2))
                              .removeprefix("data: [APPROVAL]").strip())
        assert resolved["status"] == "resolved" and resolved["approved"] is True

        # 已批准的同类操作不再弹窗（第二次直接放行）
        await gate_tool_call(_World("review"), wid_turn, "web_download",
                             {"url": "https://example.com/b.js"}, turn_state)
        assert queue.qsize() == 0
    finally:
        _workers.pop(wid_turn, None)
