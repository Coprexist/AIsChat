"""
状态栈纯函数 — 无 IO、无 DB 依赖。

make_state_frame(): 构建单个状态帧
format_state_stack_summary(): 栈 → AI 可读摘要文本
"""
from datetime import datetime, timezone
import uuid


MAX_STACK_DEPTH = 10

# ─────────────────────────── 情感向量（Plutchik 8 类独立轴） ───────────────────────────
# 每轴独立 0-1，不设对立合并：低落=joy/sadness 双低，复杂情绪=双高。

PLUTCHIK_AXES = [
    "joy", "trust", "fear", "surprise",  # 上半轮
    "sadness", "disgust", "anger", "anticipation",  # 下半轮（独立轴，非对立）
]

EMOTION_AXIS_NAMES = {
    "joy": "开心", "trust": "信任", "fear": "恐惧", "surprise": "惊讶",
    "sadness": "伤心", "disgust": "厌恶", "anger": "愤怒", "anticipation": "期待",
}

# 概括词 → 默认向量（AI 可只传词；可扩展）
EMOTION_WORD_MAP = {
    "平静": {"joy": 0.3, "trust": 0.3, "sadness": 0.1, "anticipation": 0.2},
    "开心": {"joy": 0.8, "trust": 0.5, "surprise": 0.2},
    "难过": {"sadness": 0.8, "joy": 0.1},
    "伤心": {"sadness": 0.8, "joy": 0.1},
    "愤怒": {"anger": 0.8, "disgust": 0.4},
    "生气": {"anger": 0.8, "disgust": 0.4},
    "害怕": {"fear": 0.8, "surprise": 0.3},
    "恐惧": {"fear": 0.8, "surprise": 0.3},
    "厌恶": {"disgust": 0.8, "anger": 0.3},
    "惊讶": {"surprise": 0.8, "joy": 0.2},
    "信任": {"trust": 0.8, "joy": 0.2},
    "期待": {"anticipation": 0.8, "joy": 0.3},
    "喜极而泣": {"joy": 0.9, "sadness": 0.6, "surprise": 0.5},
    "焦虑": {"fear": 0.6, "anticipation": 0.6, "sadness": 0.3},
    "麻木": {"joy": 0.1, "sadness": 0.1, "trust": 0.1, "anticipation": 0.1},
    "百感交集": {"joy": 0.6, "sadness": 0.6, "anticipation": 0.5},
}


def empty_emotion() -> dict:
    """全零情感向量"""
    return {axis: 0.0 for axis in PLUTCHIK_AXES}


def normalize_emotion(emotion: dict) -> dict:
    """清洗情感向量：只留合法轴，clamp 0-1"""
    out = empty_emotion()
    for k, v in (emotion or {}).items():
        if k in PLUTCHIK_AXES:
            try:
                out[k] = max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                pass
    return out


def emotion_from_word(word: str) -> dict:
    """概括词 → 情感向量（未收录的词 → 全零）"""
    return normalize_emotion(EMOTION_WORD_MAP.get(word.strip(), {}))


def apply_emotion_update(cur: dict | None, update) -> dict:
    """应用情感更新：增量（"+0.2"/"-0.1" 字符串值）/ 完整向量（纯数字）/ 概括词（字符串）。"""
    base = normalize_emotion(cur or {})
    if update is None:
        return base
    if isinstance(update, str):
        return emotion_from_word(update)
    if isinstance(update, dict):
        return _apply_dict(base, update)
    return base


def _apply_dict(base: dict, update: dict) -> dict:
    out = dict(base)
    for k, v in update.items():
        if k not in PLUTCHIK_AXES:
            continue
        if isinstance(v, str):
            s = v.strip()
            try:
                if s.startswith("+"):
                    out[k] = max(0.0, min(1.0, out[k] + float(s[1:])))
                elif s.startswith("-"):
                    out[k] = max(0.0, min(1.0, out[k] - float(s[1:])))
                else:
                    out[k] = max(0.0, min(1.0, float(s)))
            except ValueError:
                pass
        else:
            try:
                out[k] = max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                pass
    return out


def decay_emotion(emotion: dict, calls: int = 1, rate: float = 0.02) -> dict:
    """情感随调用次数回归基线（mood homeostasis）：每次调用向 0 靠拢 rate。"""
    out = normalize_emotion(emotion)
    factor = max(0.0, 1.0 - rate * max(0, calls))
    for k in out:
        out[k] = round(out[k] * factor, 3)
    return out


def emotion_to_text(emotion: dict) -> str:
    """情感向量 → 摘要文本（只显示非零轴）"""
    e = normalize_emotion(emotion)
    parts = [f"{EMOTION_AXIS_NAMES[k]} {v:.1f}" for k, v in e.items() if v >= 0.05]
    return " · ".join(parts) if parts else "平静"


def make_state_frame(
    type_: str,
    context_ref: str = "",
    why: str = "",
    doing: str = "",
    todo: str = "",
    plan: str = "",
    journal: str = "",
    status: str = "active",
    emotion: dict | None = None,
    emotion_text: str = "",
    source_emotion: dict | None = None,
    tools: list[str] | None = None,
    skills: list[str] | None = None,
) -> dict:
    """构建单个状态帧（纯函数）。新增：情感向量/文字、来源情感、工具/技能白名单、调用计数。"""
    return {
        "id": uuid.uuid4().hex[:12],
        "type": type_,
        "context_ref": context_ref,
        "why": why,
        "doing": doing,
        "todo": todo,
        "plan": plan,
        "journal": journal,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "emotion": normalize_emotion(emotion) if emotion else {},
        "emotion_text": emotion_text,
        "source_emotion": source_emotion or {},
        "tools": tools,          # None = 全部工具
        "skills": skills,        # None = 全部技能
        "call_count": 0,         # 该状态内 AI 调用次数（分状态时间尺度）
    }


def format_state_stack_summary(stack: list[dict], max_chars: int = 1500) -> str:
    """
    纯函数：将状态栈转为 AI 可读摘要（高密度结构化，尾部放 prompt 缓存友好）。

    格式：
    📋 状态栈（底→顶）
    ▸  [type] (context): 基础状态
    ▸↑ [type] (context): 暂停的任务  TODO: xxx  PLAN: xxx
    ▸▶ [type] (context): 当前活跃任务  TODO: xxx  PLAN: xxx

    长度控制（max_chars 默认 1500）：超限时从最旧帧开始降级——
    去掉 TODO/PLAN/情感行只留主干，仍超限则截断末尾加省略号。
    """
    if not stack:
        return ""

    def render(frames: list[dict], verbose: bool) -> list[str]:
        lines = ["\n\n## 📋 状态栈（底→顶）"]
        for i, frame in enumerate(frames):
            status = frame.get("status", "active")
            type_name = frame.get("type", "?")
            context = frame.get("context_ref", "")
            doing = frame.get("doing", "")
            why = frame.get("why", "")
            todo = frame.get("todo", "")
            plan = frame.get("plan", "")

            if i == len(frames) - 1 and status == "active":
                marker = "▸▶"
            elif status == "paused":
                marker = "▸↑"
            else:
                marker = "▸"

            context_str = f"({context})" if context else ""
            action = doing or why
            lines.append(f"{marker} [{type_name}] {context_str}: {action}")
            if not verbose:
                continue
            if todo:
                items = todo.strip().replace("\n", "; ")
                lines.append(f"   TODO: {items}")
            if plan:
                items = plan.strip().replace("\n", "; ")
                lines.append(f"   PLAN: {items}")
            # 🎭 情感行：本状态情感 + 来源情感（并置不抹除）
            emotion_text = frame.get("emotion_text") or ""
            emotion_vec = frame.get("emotion") or {}
            src_vec = (frame.get("source_emotion") or {}).get("emotion") or {}
            if emotion_text:
                lines.append(f"   🎭 心情: {emotion_text}")
            elif any(v >= 0.05 for v in emotion_vec.values()):
                lines.append(f"   🎭 情感: {emotion_to_text(emotion_vec)}")
            if src_vec and any(v >= 0.05 for v in src_vec.values()):
                src_type = (frame.get("source_emotion") or {}).get("type") or ""
                prefix = f"   ← 来源状态({src_type})情感: " if src_type else "   ← 来源状态情感: "
                lines.append(prefix + emotion_to_text(src_vec))
        return lines

    def finish(lines: list[str]) -> str:
        active_frames = [f for f in stack if f.get("status") == "active"]
        if active_frames:
            lines.append("\n请继续执行栈顶活跃任务。完成后调用 pop_state 回到上一层，或 close_state 放弃。")
        return "\n".join(lines)

    full = finish(render(stack, verbose=True))
    if len(full) <= max_chars:
        return full

    # 超限：从最旧帧开始降级（只留主干），保留顶部（最新）帧完整
    degraded = finish(render(stack, verbose=False))
    if len(degraded) <= max_chars:
        return degraded

    # 仍超限：截断末尾 + 省略号
    return degraded[:max_chars].rstrip() + "\n……（状态栈摘要过长，已截断）"
