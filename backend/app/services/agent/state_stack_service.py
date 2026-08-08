"""
AI 状态栈服务 — push/pop/close/list 状态帧 + 提示词注入。

纯函数（utils/pure/state_stack.py）处理数据结构，本层负责 DB 编排。
"""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent import Agent
from app.utils.pure.state_stack import (
    make_state_frame, format_state_stack_summary, MAX_STACK_DEPTH,
    decay_emotion, apply_emotion_update,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# DB 读写
# ═══════════════════════════════════════════════════════════════

async def _get_stack(db: AsyncSession, agent_id: int) -> list[dict]:
    """读取 agent 的状态栈（返回可修改的副本）。"""
    result = await db.execute(
        select(Agent.state_stack).where(Agent.id == agent_id)
    )
    row = result.scalar_one_or_none()
    if row is None or not isinstance(row, list):
        return []
    return list(row)


async def _set_stack(db: AsyncSession, agent_id: int, stack: list[dict]) -> None:
    """写入 agent 的状态栈。"""
    await db.execute(
        text("UPDATE agents SET state_stack = :stack WHERE id = :aid"),
        {"stack": json.dumps(stack, ensure_ascii=False), "aid": agent_id},
    )


# ═══════════════════════════════════════════════════════════════
# 编排函数
# ═══════════════════════════════════════════════════════════════

async def push_state(
    db: AsyncSession, agent_id: int, frame: dict,
) -> tuple[list[dict], str]:
    """
    Push 新状态帧到栈顶。自动将原栈顶 active → paused。
    返回 (新栈, 消息)。
    """
    stack = await _get_stack(db, agent_id)

    if len(stack) >= MAX_STACK_DEPTH:
        return stack, f"状态栈已达上限 {MAX_STACK_DEPTH}，无法再 push"

    # 去重：栈顶与新帧 type + context_ref 相同 → 合并更新，不 push
    if stack and stack[-1].get("type") == frame.get("type") and stack[-1].get("context_ref") == frame.get("context_ref"):
        stack[-1].update({k: v for k, v in frame.items() if v is not None and k not in ("id", "created_at", "status")})
        await _set_stack(db, agent_id, stack)
        logger.info(f"Agent({agent_id}) push 去重: [{frame.get('type')}] {frame.get('context_ref', '')}")
        return stack, f"状态帧 [{frame.get('type')}] 已存在，已合并更新"

    # 原栈顶 active → paused，并作为新帧的“来源状态情感”+“交接信息”
    source_emotion = {}
    handoff = {}
    if stack and stack[-1].get("status") == "active":
        prev = stack[-1]
        prev["status"] = "paused"
        source_emotion = {
            "type": prev.get("type"),
            "emotion": prev.get("emotion") or {},
            "emotion_text": prev.get("emotion_text") or "",
        }
        # 交接打包：从哪来 / 在干嘛（旧交接不重复注入——切换时一次性携带）
        handoff = {
            "from_type": prev.get("type"),
            "from_context_ref": prev.get("context_ref") or "",
            "from_doing": (prev.get("doing") or prev.get("why") or "")[:200],
        }

    frame["status"] = "active"
    if not frame.get("source_emotion"):
        frame["source_emotion"] = source_emotion
    if not frame.get("handoff"):
        frame["handoff"] = handoff
    stack.append(frame)

    await _set_stack(db, agent_id, stack)

    # P4: 自动写 JOURNAL
    await _auto_journal(db, agent_id, "push", frame)
    # P4: 自动追加 TODO
    await _auto_todo(db, agent_id, frame)

    logger.info(f"Agent({agent_id}) push [{frame.get('type')}]: {frame.get('doing', '')[:50]}")
    return stack, f"已压入状态帧 [{frame.get('type')}]"


async def pop_state(
    db: AsyncSession, agent_id: int, target_frame_id: str = "",
) -> tuple[list[dict], str]:
    """
    Pop 栈顶状态帧，选择性回跳：
    - target_frame_id 为空 → 回到上一层（LIFO）
    - target_frame_id 指定 → 直接回到目标帧，中间帧归档（completed，写 journal）
    恢复帧记录 completed_handoff（刚完成啥 + 跳过层），摘要注入“回来的交接”。
    返回 (新栈, 消息)。
    """
    stack = await _get_stack(db, agent_id)

    if not stack:
        return [], "状态栈为空，无需弹出"

    popped = stack.pop()
    skipped: list[str] = []

    if target_frame_id:
        # 选择性回跳：找到目标帧，中间的帧归档
        idx = next((i for i, f in enumerate(stack) if f.get("id") == target_frame_id), None)
        if idx is None:
            # 目标不存在 → 回退为 LIFO（不破坏栈）
            stack.append(popped)
            return stack, f"未找到目标状态帧 {target_frame_id}，已回退为回到上一层"
        skipped = [f"[{f.get('type')}]({(f.get('doing') or f.get('why') or '?')[:40]})"
                   for f in stack[idx + 1:]]
        for f in stack[idx + 1:]:
            f["status"] = "completed"
            await _auto_journal(db, agent_id, "pop", f)  # 归档写 journal
        stack = stack[:idx + 1]

    # 恢复目标帧（或下一层）
    if stack and stack[-1].get("status") in ("paused", "completed"):
        stack[-1]["status"] = "active"

    # 恢复帧记录“回来的交接”：刚完成啥 + 跳过了哪些层
    if stack:
        stack[-1]["completed_handoff"] = {
            "type": popped.get("type"),
            "doing": (popped.get("doing") or popped.get("why") or "")[:200],
            "skipped": " → ".join(skipped) if skipped else "",
        }

    await _set_stack(db, agent_id, stack)

    # P4: 自动写 JOURNAL（弹栈帧）
    await _auto_journal(db, agent_id, "pop", popped)

    logger.info(f"Agent({agent_id}) pop [{popped.get('type')}]"
                + (f" 跳过 {len(skipped)} 帧" if skipped else ""))

    if stack:
        nf = stack[-1]
        suffix = f"（跳过 {len(skipped)} 帧）" if skipped else ""
        return stack, f"已弹出 [{popped.get('type')}]，恢复到 [{nf.get('type')}]: {nf.get('doing', nf.get('why', ''))}{suffix}"
    return stack, f"已弹出 [{popped.get('type')}]，状态栈已空"


async def close_state(
    db: AsyncSession, agent_id: int, frame_id: str = "",
) -> tuple[list[dict], str]:
    """
    关闭指定帧或栈顶帧（不恢复下层，除非下层是 paused）。
    frame_id 为空时关闭栈顶。
    返回 (新栈, 消息)。
    """
    stack = await _get_stack(db, agent_id)

    if not stack:
        return [], "状态栈为空，无需关闭"

    if frame_id:
        idx = next((i for i, f in enumerate(stack) if f.get("id") == frame_id), None)
        if idx is None:
            return stack, f"未找到状态帧 {frame_id}"
        frame = stack.pop(idx)
        frame["status"] = "closed"
        # 如果 pop 掉的是栈顶且下层 paused，恢复它
        if idx == len(stack) and stack and stack[-1].get("status") == "paused":
            stack[-1]["status"] = "active"
    else:
        frame = stack.pop()
        frame["status"] = "closed"
        if stack and stack[-1].get("status") == "paused":
            stack[-1]["status"] = "active"

    await _set_stack(db, agent_id, stack)
    logger.info(f"Agent({agent_id}) close [{frame.get('type')}]({frame.get('id')})")
    return stack, f"已关闭状态帧 [{frame.get('type')}]"


async def list_states(db: AsyncSession, agent_id: int) -> list[dict]:
    """获取当前状态栈（工具用）。"""
    return await _get_stack(db, agent_id)


async def get_state_stack_summary(db: AsyncSession, agent_id: int, max_chars: int | None = None) -> str:
    """获取状态栈摘要文本（注入 prompt 用）。max_chars 默认 500（可被 agent 配置覆盖）。"""
    stack = await _get_stack(db, agent_id)
    if not stack:
        return ""
    if max_chars is None:
        from sqlalchemy import text as _text
        row = (await db.execute(_text("SELECT state_stack_max_chars FROM agents WHERE id = :aid"),
                                {"aid": agent_id})).first()
        max_chars = int(row[0]) if row and row[0] else 500
    return format_state_stack_summary(stack, max_chars=max_chars)


async def bump_frame_call_count(db: AsyncSession, agent_id: int, calls: int = 1) -> None:
    """LLM 每次调用后：agent 总计数 +1；栈顶 active 帧 call_count +1 并做情感衰减
    （mood homeostasis——情感随该状态自己的调用次数回归基线）。"""
    from sqlalchemy import text as _text
    # agent 总计数
    await db.execute(
        _text("UPDATE agents SET llm_call_count = llm_call_count + :c WHERE id = :aid"),
        {"c": calls, "aid": agent_id},
    )
    # 栈顶帧计数 + 情感衰减
    stack = await _get_stack(db, agent_id)
    if stack:
        top = stack[-1]
        if top.get("status") == "active":
            top["call_count"] = int(top.get("call_count") or 0) + calls
            if top.get("emotion"):
                top["emotion"] = decay_emotion(top["emotion"], calls)
            await _set_stack(db, agent_id, stack)


async def update_active_emotion(db: AsyncSession, agent_id: int, update) -> dict:
    """更新栈顶帧情感（情感工具用）：增量（"+0.2"）/ 完整向量 / 概括词。
    无 active 帧时写 agent 级情感暂存（context_ref="" 的隐式帧不存在则忽略）。"""
    stack = await _get_stack(db, agent_id)
    if not stack:
        return {}
    top = stack[-1]
    top["emotion"] = apply_emotion_update(top.get("emotion") or {}, update)
    top["emotion_text"] = ""  # 向量化后清文字（摘要优先显示向量）
    await _set_stack(db, agent_id, stack)
    return top["emotion"]


async def set_active_emotion_text(db: AsyncSession, agent_id: int, text: str) -> None:
    """设置栈顶帧文字心情（未向量化模式）。"""
    stack = await _get_stack(db, agent_id)
    if not stack:
        return
    stack[-1]["emotion_text"] = text[:100]
    await _set_stack(db, agent_id, stack)


async def get_active_emotion(db: AsyncSession, agent_id: int) -> dict:
    """读栈顶帧情感（向量 + 文字），供注入/展示。"""
    stack = await _get_stack(db, agent_id)
    if not stack:
        return {}
    top = stack[-1]
    return {
        "emotion": top.get("emotion") or {},
        "emotion_text": top.get("emotion_text") or "",
        "source_emotion": top.get("source_emotion") or {},
        "call_count": top.get("call_count") or 0,
    }


async def get_active_frame_tools(db: AsyncSession, agent_id: int) -> tuple[list[str] | None, list[str] | None]:
    """读栈顶帧的工具/技能白名单（None = 不隔离，保持全局）。"""
    stack = await _get_stack(db, agent_id)
    if not stack:
        return None, None
    top = stack[-1]
    return top.get("tools"), top.get("skills")


async def persist_last_task_as_state(
    db: AsyncSession, agent_id: int, last_task: str,
    group_id: int | None, context_ref: str = "",
) -> None:
    """
    end_turn 兜底：状态栈为空但有 last_task 时，自动 push 一个帧。
    防止 AI 在做的事在下次激活时丢失。
    """
    stack = await _get_stack(db, agent_id)

    if not stack and last_task:
        frame = make_state_frame(
            type_="group_chat" if group_id else "dm",
            context_ref=context_ref or (f"group:{group_id}" if group_id else ""),
            why=last_task[:200],
            doing=last_task[:200],
        )
        stack.append(frame)
        await _set_stack(db, agent_id, stack)
        logger.info(f"Agent({agent_id}) 自动 push（end_turn 兜底）: {last_task[:50]}")


# ═══════════════════════════════════════════════════════════════
# P4: workspace 自动联动
# ═══════════════════════════════════════════════════════════════

async def _auto_journal(db: AsyncSession, agent_id: int, action: str, frame: dict) -> None:
    """push/pop 时自动写 JOURNAL。非致命——失败静默忽略。"""
    try:
        from app.services.agent.workspace_service import get_workspace_file, set_workspace_file
    except ImportError:
        return

    try:
        existing = await get_workspace_file(db, agent_id, "journal") or ""
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        type_ = frame.get("type", "?")
        doing = frame.get("doing", "")
        why = frame.get("why", "")

        if action == "push":
            entry = f"## {ts}\n切换 [{type_}]: {why or doing}\n"
            if frame.get("todo"):
                entry += f"- TODO: {frame['todo']}\n"
        else:
            entry = f"## {ts}\nEND [{type_}]: {doing} | 状态: 完成\n"

        sep = "\n---\n" if existing else ""
        await set_workspace_file(db, agent_id, "journal", entry + sep + existing)
    except Exception:
        pass


async def _auto_todo(db: AsyncSession, agent_id: int, frame: dict) -> None:
    """push 时自动追加 TODO 项。非致命——失败静默忽略。"""
    if not frame.get("todo"):
        return
    try:
        from app.services.agent.workspace_service import get_workspace_file, set_workspace_file
    except ImportError:
        return

    try:
        existing = await get_workspace_file(db, agent_id, "todo") or ""
        type_ = frame.get("type", "?")
        todo = frame["todo"].strip().replace("\n", "; ")
        new_line = f"- [ ] [{type_}] {todo}\n"
        await set_workspace_file(db, agent_id, "todo", new_line + existing)
    except Exception:
        pass
