"""工具调用链校验（app/utils/pure/tool_chain.py）的契约守卫。

背景：OpenAI 兼容接口要求 assistant 的每个 tool_call_id 都有 tool 响应，
少一条整次请求 400 invalid_request_error。2026-09-14 线上 9 次 400 全部由
「工具轮次用尽 → 最后一批工具没执行 → 收尾轮带着悬空链」触发；agent 执行器的
「并行工具里前一个 end_turn 后续被跳过」是同一类问题。
"""
from __future__ import annotations

from app.utils.pure.tool_chain import heal_tool_chain


def _tc(cid: str, name: str = "file_write") -> dict:
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": "{}"}}


def _tool(cid: str) -> dict:
    return {"role": "tool", "tool_call_id": cid, "content": '{"success": true}'}


def _assert_chain_legal(messages: list) -> None:
    """与 API 同一口径：每个 assistant(tool_calls) 后面必须紧跟它全部 id 的 tool 响应"""
    i = 0
    while i < len(messages):
        tcs = messages[i].get("tool_calls") if messages[i].get("role") == "assistant" else None
        if tcs:
            want = [t["id"] for t in tcs]
            got = []
            j = i + 1
            while j < len(messages) and messages[j].get("role") == "tool":
                got.append(messages[j]["tool_call_id"])
                j += 1
            assert want == got, f"链非法：要 {want}，实际 {got}"
            i = j
        else:
            i += 1


def test_complete_chain_is_left_untouched():
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "assistant", "content": "", "tool_calls": [_tc("call_1"), _tc("call_2")]},
        _tool("call_1"), _tool("call_2"),
        {"role": "user", "content": "继续"},
    ]
    before = [dict(m) for m in msgs]
    assert heal_tool_chain(msgs) == 0
    assert msgs == before
    _assert_chain_legal(msgs)


def test_exhausted_round_batch_is_healed():
    """线上现场：轮次用尽，最后那个 assistant 的两个工具没执行，收尾轮前补齐"""
    msgs = [
        {"role": "assistant", "content": "", "tool_calls": [_tc("call_1")]},
        _tool("call_1"),
        {"role": "system", "content": "最后 1 轮提醒"},
        {"role": "assistant", "content": "", "tool_calls": [_tc("call_2"), _tc("call_3")]},
    ]
    assert heal_tool_chain(msgs) == 2
    _assert_chain_legal(msgs)
    assert [m["tool_call_id"] for m in msgs if m.get("role") == "tool"] ==         ["call_1", "call_2", "call_3"]
    # 补的是「未执行」，不伪造成功——模型据此知道那步没做
    assert '"success": false' in msgs[4]["content"]
    assert heal_tool_chain(msgs) == 0          # 幂等


def test_partially_answered_batch_fills_only_the_gap():
    msgs = [
        {"role": "assistant", "content": "", "tool_calls": [_tc("call_1"), _tc("call_2")]},
        _tool("call_1"),
    ]
    assert heal_tool_chain(msgs) == 1
    _assert_chain_legal(msgs)
    assert msgs[2]["tool_call_id"] == "call_2"


def test_tool_calls_without_id_still_get_a_response():
    """id 缺失（极端容错）也不能让链断掉，否则整次请求 400"""
    msgs = [{"role": "assistant", "content": "", "tool_calls": [{"type": "function", "function": {"name": "x"}}]}]
    assert heal_tool_chain(msgs) == 1
    assert msgs[1]["tool_call_id"] == ""


def test_plain_conversation_is_untouched():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"}]
    before = [dict(m) for m in msgs]
    assert heal_tool_chain(msgs) == 0
    assert msgs == before
