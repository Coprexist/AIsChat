"""
情感向量纯函数 — 无 IO、无 DB 依赖。

Plutchik 8 类独立轴（0-1，不设对立合并）：
- 低落 = joy/sadness 双低，复杂情绪（喜极而泣）= 双高——单轴比例表达不了
- 概括词映射、增量/覆盖/词三种输入模式、mood homeostasis 衰减
"""
from __future__ import annotations

# ── 轴定义（每轴独立 0-1，可同时多轴非零）──
PLUTCHIK_AXES = [
    "joy", "trust", "fear", "surprise",          # 上半轮
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


def normalize_emotion(emotion: dict | None) -> dict:
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
    """应用情感更新，三种写法（丰俭由人）：
    - 字符串：概括词（"平静"）
    - dict 值带 +/- 前缀：增量（{"anger": "+0.2"}）
    - dict 纯数字：完整向量覆盖（{"joy": 0.8}）
    """
    base = normalize_emotion(cur or {})
    if isinstance(update, str):
        return emotion_from_word(update)
    if isinstance(update, dict):
        return _apply_dict(base, update)
    return base


def _apply_dict(base: dict, update: dict) -> dict:
    """按轴应用更新：字符串 +0.2/-0.1 = 增量，纯数字 = 覆盖"""
    out = dict(base)
    for k, v in update.items():
        if k not in PLUTCHIK_AXES:
            continue
        try:
            if isinstance(v, str):
                s = v.strip()
                if s.startswith("+"):
                    out[k] = max(0.0, min(1.0, out[k] + float(s[1:])))
                elif s.startswith("-"):
                    out[k] = max(0.0, min(1.0, out[k] - float(s[1:])))
                else:
                    out[k] = max(0.0, min(1.0, float(s)))
            else:
                out[k] = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            pass
    return out


def decay_emotion(emotion: dict | None, calls: int = 1, rate: float = 0.02) -> dict:
    """情感随调用次数回归基线（mood homeostasis）：每次调用向 0 靠拢 rate。"""
    out = normalize_emotion(emotion)
    factor = max(0.0, 1.0 - rate * max(0, calls))
    return {k: round(v * factor, 3) for k, v in out.items()}


def emotion_to_text(emotion: dict | None) -> str:
    """情感向量 → 摘要文本（只显示非零轴）"""
    e = normalize_emotion(emotion)
    parts = [f"{EMOTION_AXIS_NAMES[k]} {v:.1f}" for k, v in e.items() if v >= 0.05]
    return " · ".join(parts) if parts else "平静"
