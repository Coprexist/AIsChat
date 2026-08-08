"""
状态栈纯函数 — 无 IO、无 DB 依赖。

make_state_frame(): 构建单个状态帧（交接驱动：handoff/completed_handoff）
format_state_stack_summary(): 栈 → AI 可读摘要（只渲染当前帧 + 交接信息）

情感向量纯函数见 emotion.py（独立模块）。
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from app.utils.pure.emotion import (
    normalize_emotion, emotion_to_text,
)


MAX_STACK_DEPTH = 10

# 帧的合法扩展字段（make_state_frame 白名单）
_FRAME_FIELDS = (
    "id", "type", "context_ref", "why", "doing", "todo", "plan", "journal",
    "created_at", "status", "emotion", "emotion_text", "source_emotion",
    "tools", "skills", "call_count", "handoff", "completed_handoff",
)


def make_state_frame(type_: str, context_ref: str = "", **extras) -> dict:
    """构建单个状态帧（纯函数）。extras 只收白名单字段，其余静默忽略。

    常用 extras：why（为什么切换）/ doing（在干嘛）/ todo（回去继续啥）/
    plan / emotion（情感向量）/ emotion_text（文字心情）/ tools、skills（工具隔离）/
    handoff、completed_handoff（交接信息）。
    """
    frame = {
        "id": uuid.uuid4().hex[:12],
        "type": type_,
        "context_ref": context_ref,
        "why": "",
        "doing": "",
        "todo": "",
        "plan": "",
        "journal": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "emotion": {},
        "emotion_text": "",
        "source_emotion": {},
        "tools": None,
        "skills": None,
        "call_count": 0,
        "handoff": {},
        "completed_handoff": {},
    }
    for key, value in extras.items():
        if key in _FRAME_FIELDS and value is not None:
            frame[key] = value
    frame["emotion"] = normalize_emotion(frame["emotion"])
    return frame


def format_state_stack_summary(stack: list[dict], max_chars: int = 500) -> str:
    """栈 → AI 可读摘要（交接驱动）。

    只渲染「当前帧 + 交接信息」，不逐层展开历史帧：
    - 旧交接已在 LLM 对话历史里出现过（工具调用参数），不重复注入
    - 当前帧：doing / TODO / PLAN / 🎭 情感（完整）
    - handoff：本次切换的交接（← 从[来源]来，为什么，回去继续）
    - completed_handoff：pop 回来后刚完成的交接（📝 刚完成）
    - 嵌套提示：栈深 > 1 时给"共 N 帧"计数

    长度控制（max_chars 默认 500）：超限按降级阶梯（_RENDER_*），
    最新帧的 TODO/PLAN 永不丢。
    """
    if not stack:
        return ""
    top = stack[-1]

    def render_top() -> list[str]:
        lines = ["\n\n## 📋 当前状态"]
        status = top.get("status", "active")
        type_name = top.get("type", "?")
        context = top.get("context_ref", "")
        doing = top.get("doing", "")
        why = top.get("why", "")
        todo = top.get("todo", "")
        plan = top.get("plan", "")

        marker = "▸▶" if status == "active" else "▸"
        context_str = f"({context})" if context else ""
        lines.append(f"{marker} [{type_name}] {context_str}: {doing or why}")
        if todo:
            lines.append(f"   TODO: {todo.strip().replace(chr(10), '; ')}")
        if plan:
            lines.append(f"   PLAN: {plan.strip().replace(chr(10), '; ')}")
        # 🎭 情感（含来源情感并置）
        emotion_text = top.get("emotion_text") or ""
        emotion_vec = top.get("emotion") or {}
        src_vec = (top.get("source_emotion") or {}).get("emotion") or {}
        if emotion_text:
            lines.append(f"   🎭 心情: {emotion_text}")
        elif any(v >= 0.05 for v in emotion_vec.values()):
            lines.append(f"   🎭 情感: {emotion_to_text(emotion_vec)}")
        if src_vec and any(v >= 0.05 for v in src_vec.values()):
            src_type = (top.get("source_emotion") or {}).get("type") or ""
            prefix = f"   ← 来源状态({src_type})情感: " if src_type else "   ← 来源状态情感: "
            lines.append(prefix + emotion_to_text(src_vec))
        if len(stack) > 1:
            lines.append(f"   ⏸ 另有 {len(stack) - 1} 帧未完成（可 list_states 查看）")
        return lines

    def render_handoff() -> list[str]:
        lines = []
        comp = top.get("completed_handoff") or {}
        if comp.get("type") or comp.get("doing"):
            lines.append(f"📝 刚完成: [{comp.get('type', '?')}] {comp.get('doing', '')}")
            if comp.get("skipped"):
                lines.append(f"   （跳过了 {comp['skipped']}）")
        handoff = top.get("handoff") or {}
        if handoff.get("from_type") or top.get("why"):
            src = f"[{handoff['from_type']}] {handoff.get('from_doing', '')}".strip()
            parts = [f"← 从{src}来" if src else "← 新状态"]
            if top.get("why"):
                parts.append(f"原因: {top['why']}")
            if todo := top.get("todo"):
                parts.append(f"回去继续: {todo.strip().replace(chr(10), '; ')}")
            lines.append("   " + " · ".join(parts))
        return lines

    def finish(lines: list[str]) -> str:
        lines.append("\n请继续执行当前任务。完成后调用 pop_state 回到上一层（可指定目标帧），或 close_state 放弃。")
        return "\n".join(lines)

    full = finish(render_top() + render_handoff())
    if len(full) <= max_chars:
        return full
    # 超限：砍交接的"原因"细节（保留结构主干）
    compact = finish(render_top() + [l for l in render_handoff() if not l.strip().startswith("原因")])
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "\n……（摘要过长，已截断）"
