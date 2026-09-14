"""
工具调用链校验（纯函数，无 IO）— 世界对话与 agent 执行器共用一份实现

背景（2026-09-14 线上事故）：OpenAI 兼容接口硬性要求 —— assistant 消息里的
**每个 tool_call_id 都必须有一条 tool 响应**，少一条整次请求就 400
invalid_request_error（"insufficient tool messages following tool_calls message"）。

两种真实触发路径（都已修，这里是通用兜底）：
1. 世界对话：工具轮次用尽（max_tool_rounds）时循环直接退出，最后一批工具没执行，
   强制收尾轮带着悬空链请求 API → 400（用户看到「执行到一半就 400」）；
2. agent 执行器：同一批并行工具调用里前一个 already end_turn，后面的被跳过，
   但 assistant 消息仍带着全部 tool_calls → 400。

补的响应如实写「未执行」——不伪造成功，模型据此知道那步没做。
"""

import json


def _response(tc_id: str, error: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tc_id,
        "content": json.dumps({"success": False, "error": error}, ensure_ascii=False),
    }


def heal_tool_chain(messages: list, error: str = "该工具调用未执行（轮次预算用尽或对话中断）") -> int:
    """补齐悬空的工具调用链：assistant(tool_calls) 缺 tool 响应时就地补一条「未执行」响应。

    返回补齐条数（0 = 链本来就完整）。
    """
    filled = 0
    i = 0
    while i < len(messages):
        if messages[i].get("role") != "assistant":
            i += 1
            continue
        tcs = messages[i].get("tool_calls") or []
        if not tcs:
            i += 1
            continue
        answered = set()
        j = i + 1
        while j < len(messages) and messages[j].get("role") == "tool":
            answered.add(messages[j].get("tool_call_id"))
            j += 1
        for tc in tcs:
            if tc.get("id") in answered:
                continue
            messages.insert(j, _response(tc.get("id") or "", error))
            j += 1
            filled += 1
        i = j
    return filled
