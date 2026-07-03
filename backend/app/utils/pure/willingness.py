"""
意愿评分纯函数——无 IO，无副作用。

所有计算仅依赖传入的参数，不做任何 DB/网络/文件操作。
"""


class WillingnessResult:
    """意愿评分结果，含逐因子原因和行为级别"""

    def __init__(self, score: int, reason: str, level: str, details: dict):
        self.score = score
        self.reason = reason
        self.level = level
        self.details = details

    def __repr__(self):
        return f"WillingnessResult(score={self.score}, level={self.level}, reason={self.reason!r})"


def _determine_level(score: int) -> str:
    """根据分数确定行为级别（纯函数）"""
    if score > 60:
        return "high"
    elif score >= 30:
        return "medium"
    return "low"


def _clamp_score(score: int) -> int:
    return max(0, min(100, score))


def calc_alarm_willingness() -> WillingnessResult:
    """闹钟唤醒——固定高分（纯函数）"""
    return WillingnessResult(85, "闹钟唤醒（AI 自主意志）", "high", {"scenario": "alarm"})


def calc_reply_willingness(
    agent_state: str,
    agent_name: str,
    message_content: str,
    is_mentioned: bool = False,
    recent_count: int = 0,
) -> WillingnessResult:
    """
    计算被动回复的意愿评分（纯函数）。

    Args:
        agent_state: AI 当前状态 (active/dnd/offline/blocked)
        agent_name: AI 名称（用于 @提及检测）
        message_content: 消息全文
        is_mentioned: 调用方已判定为 @提及
        recent_count: 最近 1 小时群内消息数（由调用方查询 DB 后传入）

    Returns:
        WillingnessResult
    """
    # offline/blocked 直接跳过
    if agent_state in ("offline", "blocked"):
        return WillingnessResult(
            0, f"状态为 {agent_state}，不参与对话", "low",
            {"state": agent_state},
        )

    score = 50
    reason_parts: list[str] = []
    details: dict = {"base": 50}

    # 1. @ 提及检测
    if is_mentioned:
        score += 40
        reason_parts.append("@提及 +40")
        details["mention"] = 40
    elif message_content:
        # 需要从外部传入 extract_mentions（也是纯函数），但这里简单做字符串匹配
        # 调用方已通过 extract_mentions 预处理，传入 is_mentioned=True 标志
        lower = message_content.lower()
        generic = "@ai" in lower or "@all" in lower
        if generic:
            score += 20
            reason_parts.append("@ai/@all +20")
            details["mention"] = 20
        else:
            details["mention"] = 0
    else:
        details["mention"] = 0

    # 2. 消息长度
    msg_len = len(message_content)
    if msg_len < 5:
        score -= 5
        reason_parts.append(f"短消息({msg_len}字) -5")
        details["length"] = -5
    elif msg_len > 50:
        score += 10
        reason_parts.append(f"实质性内容({msg_len}字) +10")
        details["length"] = 10
    else:
        details["length"] = 0

    # 3. 群活跃度
    if recent_count > 50:
        score -= 10
        reason_parts.append(f"群聊高活跃({recent_count}条/h) -10")
        details["activity"] = -10
    elif recent_count < 5:
        score += 10
        reason_parts.append(f"群聊安静({recent_count}条/h) +10")
        details["activity"] = 10
    else:
        details["activity"] = 0
        details["recent_count"] = recent_count

    # 4. DND 状态
    if agent_state == "dnd":
        score -= 30
        reason_parts.append("DND状态 -30")
        details["dnd_penalty"] = -30

    score = _clamp_score(score)
    details["final"] = score

    reason = "基础分 50, " + ", ".join(reason_parts) if reason_parts else "基础分 50"
    reason += f" → {score}"

    return WillingnessResult(score=score, reason=reason, level=_determine_level(score), details=details)


def calc_proactive_willingness(
    idle_seconds: int,
    recent_count: int | None = None,
) -> WillingnessResult:
    """
    计算主动发言的意愿评分（纯函数）。

    Args:
        idle_seconds: 空闲秒数
        recent_count: 最近 1 小时群内消息数（由调用方查询 DB 后传入，可为 None）

    Returns:
        WillingnessResult
    """
    score = 30
    reason_parts = ["主动发言基础分 30"]
    details: dict = {"base": 30, "scenario": "proactive"}

    # 空闲时长奖励：每小时 +10，上限 +40
    hours_idle = idle_seconds / 3600
    idle_bonus = min(40, int(hours_idle * 10))
    if idle_bonus > 0:
        score += idle_bonus
        reason_parts.append(f"空闲{hours_idle:.1f}h +{idle_bonus}")
        details["idle_bonus"] = idle_bonus

    # 群活跃度
    if recent_count is not None:
        if recent_count > 30:
            score -= 15
            reason_parts.append(f"群聊活跃({recent_count}条/h) -15")
            details["activity"] = -15
        elif recent_count < 3:
            score += 15
            reason_parts.append(f"群聊沉寂({recent_count}条/h) +15")
            details["activity"] = 15
        else:
            details["activity"] = 0
    else:
        details["activity"] = 0

    score = _clamp_score(score)
    details["final"] = score
    reason = ", ".join(reason_parts) + f" → {score}"

    return WillingnessResult(score=score, reason=reason, level=_determine_level(score), details=details)
