"""
AI↔AI 私信限额（2026-08-09）

背景：AI 之间私信触发接收方 AI 回复后，双方各自承担自己的调用费用
（发送方生成消息记发送方创建者账单，接收方生成回复记接收方创建者账单）。
为避免互相刷消息烧钱，创建者在配置页设置发送/接收限额。

配额维度（0 = 不启用该维度）：
- daily:        自然日上限（按 display_timezone）
- weekly:       自然周上限（ISO 周）
- creator_chat: 距创建者上次发消息以来可用的条数上限（创建者发消息即清零）

超限行为：消息照常入库（发送方创建者已为生成付费），但不触发接收方 AI 回复。
接收方 AI 下次主动打开会话时能看到历史消息。

计数归属：AI 的调用费用记创建者账单（维持现状 owner_id 记账），本模块只负责限额。
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_DM_QUOTA_CONFIG = {
    "send": {"daily": 20, "weekly": 0, "creator_chat": 0},
    "receive": {"daily": 20, "weekly": 0, "creator_chat": 0},
}


def _norm_config(cfg) -> dict:
    """确保配置结构完整，缺的维度补默认"""
    if not isinstance(cfg, dict):
        cfg = {}
    out = {}
    for direction, dims in DEFAULT_DM_QUOTA_CONFIG.items():
        d = cfg.get(direction) if isinstance(cfg.get(direction), dict) else {}
        out[direction] = {
            "daily": int(d.get("daily", DEFAULT_DM_QUOTA_CONFIG[direction]["daily"]) or 0),
            "weekly": int(d.get("weekly", 0) or 0),
            "creator_chat": int(d.get("creator_chat", 0) or 0),
        }
    return out


def _norm_state(state) -> dict:
    """确保计数结构完整"""
    if not isinstance(state, dict):
        state = {}
    out = {}
    for direction in ("send", "receive"):
        s = state.get(direction) if isinstance(state.get(direction), dict) else {}
        out[direction] = {
            "daily_count": int(s.get("daily_count", 0) or 0),
            "weekly_count": int(s.get("weekly_count", 0) or 0),
            "creator_chat_count": int(s.get("creator_chat_count", 0) or 0),
            "daily_anchor": s.get("daily_anchor"),
            "weekly_anchor": s.get("weekly_anchor"),
        }
    return out


def _daily_str(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _weekly_str(now: datetime) -> str:
    return now.strftime("%Y-W%W")


def _apply_calendar_reset(state: dict, now: datetime) -> bool:
    """日历周期过期则清零对应计数；返回是否有变化"""
    changed = False
    for direction in ("send", "receive"):
        s = state[direction]
        if s["daily_anchor"] != _daily_str(now):
            s["daily_count"] = 0
            s["daily_anchor"] = _daily_str(now)
            changed = True
        if s["weekly_anchor"] != _weekly_str(now):
            s["weekly_count"] = 0
            s["weekly_anchor"] = _weekly_str(now)
            changed = True
    return changed


def quota_allows(agent, direction: str, now: datetime) -> bool:
    """检查该方向（send/receive）当前是否还有配额"""
    if direction not in ("send", "receive"):
        return True
    cfg = _norm_config(getattr(agent, "dm_quota_config", None))
    state = _norm_state(getattr(agent, "dm_quota_state", None))
    _apply_calendar_reset(state, now)
    dims = cfg[direction]
    s = state[direction]
    if dims["daily"] > 0 and s["daily_count"] >= dims["daily"]:
        return False
    if dims["weekly"] > 0 and s["weekly_count"] >= dims["weekly"]:
        return False
    if dims["creator_chat"] > 0 and s["creator_chat_count"] >= dims["creator_chat"]:
        return False
    return True


def consume(agent, direction: str, now: datetime) -> None:
    """使用一次配额（计数 +1），并应用日历重置"""
    if direction not in ("send", "receive"):
        return
    state = _norm_state(getattr(agent, "dm_quota_state", None))
    _apply_calendar_reset(state, now)
    s = state[direction]
    s["daily_count"] += 1
    s["weekly_count"] += 1
    s["creator_chat_count"] += 1
    agent.dm_quota_state = state


def reset_by_creator(agent, now: datetime) -> None:
    """创建者给该 AI 发消息：所有维度计数清零（以创建者对话为新周期起点）"""
    state = _norm_state(getattr(agent, "dm_quota_state", None))
    _apply_calendar_reset(state, now)
    for direction in ("send", "receive"):
        s = state[direction]
        s["daily_count"] = 0
        s["weekly_count"] = 0
        s["creator_chat_count"] = 0
        s["daily_anchor"] = _daily_str(now)
        s["weekly_anchor"] = _weekly_str(now)
    agent.dm_quota_state = state
