"""会话记录导出（Markdown / JSON）——群视界对话的「另存为」。

**只导出这场对话本身**：正文、思考、工具卡片（含报错）、附件名。
不含系统提示词、模型与实例配置、API Key、其他世界或用户的数据——导出内容与聊天面板里
看得见的东西一致，不多一个字。唯一额外的防护：世界自己的 API token（沙箱注入用）如果被 AI
打印进了工具输出，导出时**按值打码**，绝不把凭据带出实例。

渲染是纯函数（world / session / messages 进去，文本出来），路由只负责取数与下发文件。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

# 角色中文名（导出给人看）
ROLE_LABELS = {"user": "用户", "ai": "AI", "note": "思考", "tool": "工具"}
# 工具详情是给卡片展开用的，导出里也保留但封顶，别让一份记录变成几 MB
DETAIL_MAX = 4000


async def collect_messages(repo, world_id: int, session_id: str | None) -> list:
    """按时间正序取某会话的**全部**消息（导出不看对话窗口那 30 条）"""
    from sqlalchemy import select
    from app.models.world import WorldChatMessage

    q = select(WorldChatMessage).where(WorldChatMessage.world_id == world_id)
    # 默认会话在库里存的是 NULL（兼容旧数据），不是字符串 'default'
    if session_id in (None, "", "default"):
        q = q.where(WorldChatMessage.session_id.is_(None))
    else:
        q = q.where(WorldChatMessage.session_id == session_id)
    return list((await repo.execute(q.order_by(WorldChatMessage.id))).scalars().all())


def _redact(text: str, world) -> str:
    """按值打掉本世界的 API token（AI 若把它打印进工具输出，不能跟着导出泄露）"""
    token = str((world.config or {}).get("api_token") or "")
    return text.replace(token, "***") if len(token) >= 8 else text


def _stamp(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if isinstance(value, datetime) else ""


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _fence(text: str, lang: str = "text") -> str:
    """围栏代码块：内容里带三反引号也不截断（比正文更长的围栏）"""
    longest = 3
    run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    fence = "`" * (longest + 1)
    return f"{fence}{lang}\n{text}\n{fence}"


def session_label(world, session: dict) -> str:
    """列表里显示什么，导出标题就用什么（名字 → 会话 id → 默认会话）"""
    title = (session or {}).get("title")
    if title:
        return str(title)
    sid = (session or {}).get("id") or "default"
    return "默认会话" if sid == "default" else str(sid)


def render_markdown(world, session: dict, messages: list) -> str:
    """人看的版本：一场对话一份 md，思考用引用块，工具调用用围栏块"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        f"# {session_label(world, session)}",
        "",
        f"- 世界：{getattr(world, 'name', '') or ''}（#{getattr(world, 'id', '')}）",
        f"- 会话：`{(session or {}).get('id') or 'default'}`",
        f"- 消息：{len(messages)} 条",
        f"- 导出时间：{now}",
        "",
        "> 由 AIsChat 群视界导出；内容与对话面板所见一致（含思考与工具调用，不含系统提示词与配置）。",
    ]
    last_note = ""
    for m in messages:
        role, content = m.role, _redact(m.content or "", world)
        if role == "note":
            last_note = (m.content or "").strip()
            out += ["", "---", "", "**思考**", ""] + ["> " + ln for ln in content.splitlines() or [""]]
            continue
        if role == "tool":
            head = f"**工具 · {m.tool_name or '未命名'}**"
            if m.is_error:
                head += " ❌ 失败"
            out += ["", "---", "", head]
            if content:
                out += ["", _fence(content, "text")]
            if m.tool_detail:
                out += ["", "调用详情：", "", _fence(_redact(m.tool_detail, world)[:DETAIL_MAX], "text")]
            continue
        out += ["", "---", "", f"**{ROLE_LABELS.get(role, role)}**"]
        # ai 行可能挂着一份思考：与紧邻的思考条重复就不重复导出（面板里也是只显示一次）
        reasoning = _redact(m.reasoning or "", world).strip()
        if role == "ai" and reasoning and reasoning != last_note:
            out += ["", "**思考**", ""] + ["> " + ln for ln in reasoning.splitlines()]
        out += ["", content]
    return "\n".join(out).rstrip() + "\n"


def render_json(world, session: dict, messages: list) -> str:
    """机器看的版本：结构化原文，字段与库表一致（含 tool_detail / attachments / 报错标记）"""
    payload = {
        "world": {"id": getattr(world, "id", None), "name": getattr(world, "name", "") or ""},
        "session": {"id": (session or {}).get("id") or "default",
                    "title": (session or {}).get("title"),
                    "created_at": (session or {}).get("created_at"),
                    "last_active_at": (session or {}).get("last_active_at")},
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(messages),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": _redact(m.content or "", world),
                "reasoning": _redact(m.reasoning or "", world) or None,
                "tool_name": m.tool_name,
                "tool_detail": _redact(m.tool_detail or "", world) or None,
                "is_error": bool(m.is_error),
                "attachments": m.attachments,
                "created_at": _iso(m.created_at),
            }
            for m in messages
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def safe_filename(world, session: dict, ext: str) -> str:
    """下载文件名：世界名-会话名-日期.ext（文件名里的非法字符一律换掉）"""
    raw = f"{getattr(world, 'name', '') or '世界'}-{session_label(world, session)}-{datetime.now().strftime('%Y%m%d')}"
    cleaned = "".join("_" if ch in '\\/:*?"<>|\n\r\t' else ch for ch in raw).strip("_ ")
    return f"{(cleaned or '会话记录')[:80]}.{ext}"


def render(world, session: dict, messages: list, fmt: str) -> tuple[str, str, str]:
    """(正文, 媒体类型, 文件名)——路由唯一的取用处，格式判定也在这里"""
    if fmt == "json":
        return render_json(world, session, messages), "application/json; charset=utf-8", safe_filename(world, session, "json")
    return render_markdown(world, session, messages), "text/markdown; charset=utf-8", safe_filename(world, session, "md")
