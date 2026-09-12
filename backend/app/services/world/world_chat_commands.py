"""
世界对话斜杠命令 — 用户输入，不走 LLM（从 world_chat_service 拆分）

命令的**能力声明与执行分发集中在下方 _COMMANDS 一张表**：
  · 执行分发   run_slash_command() 按命令头查表
  · 排队分流   world_turn.enqueue() → may_insert_mid_turn()
  · 前端补全   GET /worlds/{id}/chat 的 commands 字段（COMMAND_SPECS 由同一张表派生）
新增一条命令 = 表里加一行 + 写一个 handler，三处自动跟上，不会再出现"某处漏改"。

命令消息与结果落库（role=tool），调用方负责 yield [TOOL]/[DONE]。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.repositories.world_repo import WorldRepository

logger = logging.getLogger(__name__)


MAX_PINNED_PER_USER = 16


@dataclass
class CmdContext:
    """一次命令执行的全部输入——handler 只依赖它，便于单独测试"""
    world_repo: WorldRepository
    world: Any
    cmd_text: str          # 原始输入，如 "/use w1:abc"
    user_id: int | None
    args: str              # 命令头之后的参数（已 strip），如 "w1:abc"


CmdHandler = Callable[[CmdContext], Awaitable["str | None"]]


# ═══════════════════════════════════════════════════════════════
# handlers（每个命令一段，互不干扰）
# ═══════════════════════════════════════════════════════════════

async def _cmd_clear(ctx: CmdContext) -> str:
    """清空当前会话上下文（历史+摘要+工作流记忆），长期记忆与其他会话保留"""
    from sqlalchemy import delete as sa_delete
    from app.models.world import WorldChatMessage
    from app.services.world.world_chat_service import session_id_for_db, session_key

    world = ctx.world
    sid_db = session_id_for_db(world)
    q = sa_delete(WorldChatMessage).where(WorldChatMessage.world_id == world.id)
    if sid_db is None:
        q = q.where(WorldChatMessage.session_id.is_(None))
    else:
        q = q.where(WorldChatMessage.session_id == sid_db)
    await ctx.world_repo.execute(q)
    cfg = dict(world.config or {})
    summaries = dict(cfg.get("chat_summaries") or {})
    summaries.pop(session_key(world), None)
    cfg["chat_summaries"] = summaries
    cfg["workflow_memory"] = None
    world.config = cfg
    await ctx.world_repo.commit()
    return "已清空当前会话上下文（历史消息+摘要+工作流记忆），其他会话保留；长期记忆保留——AI 将从记忆恢复工作状态。"


async def _cmd_compact(ctx: CmdContext) -> str:
    """压缩当前会话上下文为摘要（复用主对话的压缩服务）"""
    from app.services.world.world_tools import _do_execute

    result = await _do_execute(ctx.world_repo, ctx.world, "compact_context", "{}")
    if result.get("success"):
        return (f"上下文已压缩：{result.get('before_tokens')} → "
                f"{result.get('after_tokens')} tokens"
                f"（压缩率 {result.get('compression_ratio_pct')}%）")
    return f"⚠️ 压缩未执行：{result.get('error', '未知原因')}"


async def _cmd_new(ctx: CmdContext) -> str:
    """开新会话（旧会话保存，可用 /use 切回）"""
    from app.services.world.world_chat_service import new_session_id

    world = ctx.world
    cfg = dict(world.config or {})
    sid = new_session_id(world)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    sessions = dict(cfg.get("sessions") or {})
    sessions[sid] = {"created_at": now, "last_active_at": now}
    cfg["current_session"] = sid
    cfg["sessions"] = sessions
    world.config = cfg
    await ctx.world_repo.commit()
    return f"已开新对话（会话 {sid}）。旧对话已保存：/sessions 查看列表，/use <id> 切回继续。"


async def _cmd_sessions(ctx: CmdContext) -> str:
    """列出所有会话（id + 时间 + 收藏标记）"""
    cfg = ctx.world.config or {}
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


async def _cmd_use(ctx: CmdContext) -> "str | None":
    """切换到指定会话。

    无参数时返回 None = 不是命令 → 调用方当普通消息继续走 LLM
    （保持原 startswith("/use ") 的语义："/use" 单独输入不匹配）。
    """
    if not ctx.args:
        return None
    world = ctx.world
    cfg = dict(world.config or {})
    sessions = cfg.get("sessions") or {}
    if ctx.args not in sessions:
        return f"会话不存在：`{ctx.args}`。用 /sessions 查看。"
    cfg["current_session"] = ctx.args
    world.config = cfg
    await ctx.world_repo.commit()
    return f"已切换到会话 `{ctx.args}`（id 一致，上下文按会话隔离，可继续对话）。"


async def _set_pin(ctx: CmdContext, is_pin: bool) -> str:
    """收藏 / 取消收藏当前会话（每用户上限 MAX_PINNED_PER_USER）"""
    if not ctx.user_id:
        return "无法识别用户，收藏失败。"
    world = ctx.world
    cfg = dict(world.config or {})
    sessions = dict(cfg.get("sessions") or {})
    key = cfg.get("current_session") or "default"
    meta = dict(sessions.get(key) or {})
    pinned = list(meta.get("pinned_by") or [])
    if is_pin:
        if ctx.user_id in pinned:
            return "该会话已收藏。"
        if len(pinned) >= MAX_PINNED_PER_USER:
            return f"收藏已达上限（{MAX_PINNED_PER_USER} 个），请先取消其他收藏。"
        pinned.append(ctx.user_id)
    else:
        if ctx.user_id not in pinned:
            return "该会话未收藏。"
        pinned.remove(ctx.user_id)
    meta["pinned_by"] = pinned
    sessions[key] = meta
    cfg["sessions"] = sessions
    world.config = cfg
    await ctx.world_repo.commit()
    return f"已{'📌 收藏' if is_pin else '取消收藏'}会话 `{key}`（{len(pinned)}/{MAX_PINNED_PER_USER}）。收藏的会话不会被自动清理。"


async def _cmd_pin(ctx: CmdContext) -> str:
    return await _set_pin(ctx, True)


async def _cmd_unpin(ctx: CmdContext) -> str:
    return await _set_pin(ctx, False)


# ═══════════════════════════════════════════════════════════════
# 命令注册表 —— **唯一来源**
#   usage/desc/mid_turn → 前端补全 + 排队分流；handler → 执行分发
#   mid_turn：False（默认）= 必须等当前轮次结束；True = 允许工具轮进行中直接插入本轮
# ═══════════════════════════════════════════════════════════════
_COMMANDS: dict[str, dict] = {
    "/new":      {"usage": "/new",      "desc": "开新对话（旧对话保存，可切回）",      "mid_turn": False, "handler": _cmd_new},
    "/sessions": {"usage": "/sessions", "desc": "列出所有会话（id + 时间 + 收藏）",     "mid_turn": False, "handler": _cmd_sessions},
    "/use":      {"usage": "/use <id>", "desc": "切回指定会话继续对话",                "mid_turn": False, "handler": _cmd_use},
    "/pin":      {"usage": "/pin",      "desc": "收藏当前会话（最多 16 个，不被清理）",  "mid_turn": False, "handler": _cmd_pin},
    "/unpin":    {"usage": "/unpin",    "desc": "取消收藏当前会话",                    "mid_turn": False, "handler": _cmd_unpin},
    "/clear":    {"usage": "/clear",    "desc": "清空当前会话上下文（保留长期记忆）",    "mid_turn": False, "handler": _cmd_clear},
    "/compact":  {"usage": "/compact",  "desc": "压缩当前会话上下文为摘要",             "mid_turn": False, "handler": _cmd_compact},
}

# 前端视图：handler 不可 JSON 序列化，从同一张表派生（新增命令无需改这里）
COMMAND_SPECS: list[dict] = [
    {"cmd": v["usage"], "desc": v["desc"], "mid_turn": v["mid_turn"]}
    for v in _COMMANDS.values()
]


def command_head(text: str) -> str:
    """取命令头：'/use <id>' 与 '/use w1:abc' 都归一到 '/use'；非命令返回 ''"""
    s = str(text).lstrip()
    if not s.startswith("/"):
        return ""
    return (s.split() or [""])[0]


def command_args(text: str) -> str:
    """取命令头之后的参数（已 strip）；无参数返回 ''"""
    parts = str(text).lstrip().split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


def may_insert_mid_turn(text: str) -> bool:
    """该条消息能否在 AI 工具轮进行中直接插入本轮上下文。

    - 普通消息：恒可（设计 docs/group_world/design/group_world_design.md §7.7）
    - 已注册命令：按 mid_turn 决定
    - 未注册的斜杠命令：保守当作"必须等待"（宁可让用户多等，也不误插）
    """
    head = command_head(text)
    if not head:
        return True
    entry = _COMMANDS.get(head)
    return bool(entry and entry["mid_turn"])


async def run_slash_command(world_repo: WorldRepository, world, cmd_text: str, user_id: int | None = None) -> str | None:
    """执行斜杠命令，返回结果 note；非命令 / 未注册命令返回 None（调用方继续走 LLM 流）"""
    head = command_head(cmd_text)
    entry = _COMMANDS.get(head) if head else None
    if entry is None:
        return None
    ctx = CmdContext(
        world_repo=world_repo, world=world,
        cmd_text=str(cmd_text), user_id=user_id, args=command_args(cmd_text),
    )
    return await entry["handler"](ctx)
