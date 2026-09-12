"""
世界对话斜杠命令 — 用户输入，不走 LLM（从 world_chat_service 拆分）

- /clear   清空当前会话上下文（历史+摘要+工作流记忆），长期记忆保留；其他会话不受影响
- /compact 压缩当前会话上下文为摘要
- /new     开新会话（旧会话保存，可用 /use 切回；id = w{wid}:m:{uuid12}）
- /sessions 列出所有会话（id + 时间 + 收藏标记）
- /use <id> 切换到指定会话（上下文按会话隔离，id 一致）
- /pin /unpin 收藏/取消收藏当前会话（每用户最多 16 个，收藏的会话不被 90 天清理）
命令消息与结果落库（role=tool），调用方负责 yield [TOOL]/[DONE]。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.repositories.world_repo import WorldRepository

logger = logging.getLogger(__name__)


MAX_PINNED_PER_USER = 16


# ═══════════════════════════════════════════════════════════════
# 命令能力声明 —— **前后端唯一来源**
#
# 前端不再自己用 startswith('/') 猜"是不是命令、能不能中途发"：
#   · 输入框 / 自动补全列表  → GET /worlds/{id}/chat 的 commands 字段
#   · 排队/插入分流          → world_turn.enqueue() 调 may_insert_mid_turn()
#
# mid_turn：
#   False（默认）= 必须等当前轮次结束再执行（/clear /compact 等会改上下文的命令）
#   True        = 允许 AI 工具轮进行中直接送进本轮上下文
# 新增命令时只改这里一处，并在 run_slash_command 里加对应分支。
# ═══════════════════════════════════════════════════════════════
COMMAND_SPECS: list[dict] = [
    {"cmd": "/new", "desc": "开新对话（旧对话保存，可切回）", "mid_turn": False},
    {"cmd": "/sessions", "desc": "列出所有会话（id + 时间 + 收藏）", "mid_turn": False},
    {"cmd": "/use <id>", "desc": "切回指定会话继续对话", "mid_turn": False},
    {"cmd": "/pin", "desc": "收藏当前会话（最多 16 个，不被清理）", "mid_turn": False},
    {"cmd": "/unpin", "desc": "取消收藏当前会话", "mid_turn": False},
    {"cmd": "/clear", "desc": "清空当前会话上下文（保留长期记忆）", "mid_turn": False},
    {"cmd": "/compact", "desc": "压缩当前会话上下文为摘要", "mid_turn": False},
]


def command_head(text: str) -> str:
    """取命令头：'/use <id>' 与 '/use w1:abc' 都归一到 '/use'；非命令返回 ''"""
    s = str(text).lstrip()
    if not s.startswith("/"):
        return ""
    return (s.split() or [""])[0]


def may_insert_mid_turn(text: str) -> bool:
    """该条消息能否在 AI 工具轮进行中直接插入本轮上下文。

    - 普通消息：恒可（设计 docs/group_world/design/group_world_design.md §7.7）
    - 已声明命令：按 mid_turn 决定
    - 未声明的斜杠命令：保守当作"必须等待"（宁可让用户多等，也不误插）
    """
    head = command_head(text)
    if not head:
        return True
    for spec in COMMAND_SPECS:
        if command_head(spec["cmd"]) == head:
            return bool(spec.get("mid_turn"))
    return False


async def run_slash_command(world_repo: WorldRepository, world, cmd_text: str, user_id: int | None = None) -> str | None:
    """执行斜杠命令，返回结果 note；非命令返回 None（调用方继续走 LLM 流）"""
    from app.models.world import WorldChatMessage

    if cmd_text.startswith("/clear"):
        from sqlalchemy import delete as sa_delete
        from app.services.world.world_chat_service import session_id_for_db, session_key
        sid_db = session_id_for_db(world)
        q = sa_delete(WorldChatMessage).where(WorldChatMessage.world_id == world.id)
        if sid_db is None:
            q = q.where(WorldChatMessage.session_id.is_(None))
        else:
            q = q.where(WorldChatMessage.session_id == sid_db)
        await world_repo.execute(q)
        cfg = dict(world.config or {})
        summaries = dict(cfg.get("chat_summaries") or {})
        summaries.pop(session_key(world), None)
        cfg["chat_summaries"] = summaries
        cfg["workflow_memory"] = None
        world.config = cfg
        await world_repo.commit()
        return "已清空当前会话上下文（历史消息+摘要+工作流记忆），其他会话保留；长期记忆保留——AI 将从记忆恢复工作状态。"

    if cmd_text.startswith("/compact"):
        from app.services.world.world_tools import _do_execute
        result = await _do_execute(world_repo, world, "compact_context", "{}")
        if result.get("success"):
            return (f"上下文已压缩：{result.get('before_tokens')} → "
                    f"{result.get('after_tokens')} tokens"
                    f"（压缩率 {result.get('compression_ratio_pct')}%）")
        return f"⚠️ 压缩未执行：{result.get('error', '未知原因')}"

    if cmd_text.startswith("/new"):
        from app.services.world.world_chat_service import new_session_id
        cfg = dict(world.config or {})
        sid = new_session_id(world)
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        sessions = dict(cfg.get("sessions") or {})
        sessions[sid] = {"created_at": now, "last_active_at": now}
        cfg["current_session"] = sid
        cfg["sessions"] = sessions
        world.config = cfg
        await world_repo.commit()
        return f"已开新对话（会话 {sid}）。旧对话已保存：/sessions 查看列表，/use <id> 切回继续。"

    if cmd_text.startswith("/sessions"):
        cfg = world.config or {}
        sessions = cfg.get("sessions") or {}
        cur = cfg.get("current_session") or "default"
        lines = []
        for sid, meta in sessions.items():
            mark = " ← 当前" if sid == cur else ""
            pinned = " 📌" if (meta or {}).get("pinned_by") else ""
            la = str((meta or {}).get("last_active_at") or "?")[:16].replace("T", " ")
            lines.append(f"`{sid}`{mark}{pinned}（{la}）")
        if not lines:
            return "还没有 /new 会话（当前是默认会话）。用 /new 开新对话。"
        return "会话列表：\n" + "\n".join(lines[-20:])

    if cmd_text.startswith("/use "):
        target = cmd_text[5:].strip()
        cfg = dict(world.config or {})
        sessions = cfg.get("sessions") or {}
        if target not in sessions:
            return f"会话不存在：`{target}`。用 /sessions 查看。"
        cfg["current_session"] = target
        world.config = cfg
        await world_repo.commit()
        return f"已切换到会话 `{target}`（id 一致，上下文按会话隔离，可继续对话）。"

    if cmd_text.startswith("/pin") or cmd_text.startswith("/unpin"):
        if not user_id:
            return "无法识别用户，收藏失败。"
        is_pin = cmd_text.startswith("/pin")
        cfg = dict(world.config or {})
        sessions = dict(cfg.get("sessions") or {})
        key = cfg.get("current_session") or "default"
        meta = dict(sessions.get(key) or {})
        pinned = list(meta.get("pinned_by") or [])
        if is_pin:
            if user_id in pinned:
                return "该会话已收藏。"
            if len(pinned) >= MAX_PINNED_PER_USER:
                return f"收藏已达上限（{MAX_PINNED_PER_USER} 个），请先取消其他收藏。"
            pinned.append(user_id)
        else:
            if user_id not in pinned:
                return "该会话未收藏。"
            pinned.remove(user_id)
        meta["pinned_by"] = pinned
        sessions[key] = meta
        cfg["sessions"] = sessions
        world.config = cfg
        await world_repo.commit()
        return f"已{'📌 收藏' if is_pin else '取消收藏'}会话 `{key}`（{len(pinned)}/{MAX_PINNED_PER_USER}）。收藏的会话不会被自动清理。"

    return None
