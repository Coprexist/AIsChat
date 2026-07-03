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

    # 原栈顶 active → paused
    if stack and stack[-1].get("status") == "active":
        stack[-1]["status"] = "paused"

    frame["status"] = "active"
    stack.append(frame)

    await _set_stack(db, agent_id, stack)

    # P4: 自动写 JOURNAL
    await _auto_journal(db, agent_id, "push", frame)
    # P4: 自动追加 TODO
    await _auto_todo(db, agent_id, frame)

    logger.info(f"Agent({agent_id}) push [{frame.get('type')}]: {frame.get('doing', '')[:50]}")
    return stack, f"已压入状态帧 [{frame.get('type')}]"


async def pop_state(
    db: AsyncSession, agent_id: int,
) -> tuple[list[dict], str]:
    """
    Pop 栈顶状态帧，恢复下一层 paused → active。
    返回 (新栈, 消息)。
    """
    stack = await _get_stack(db, agent_id)

    if not stack:
        return [], "状态栈为空，无需弹出"

    popped = stack.pop()

    # 恢复下一层
    if stack and stack[-1].get("status") == "paused":
        stack[-1]["status"] = "active"

    await _set_stack(db, agent_id, stack)

    # P4: 自动写 JOURNAL
    await _auto_journal(db, agent_id, "pop", popped)

    logger.info(f"Agent({agent_id}) pop [{popped.get('type')}]: {popped.get('doing', '')[:50]}")

    if stack:
        nf = stack[-1]
        return stack, f"已弹出 [{popped.get('type')}]，恢复到 [{nf.get('type')}]: {nf.get('doing', nf.get('why', ''))}"
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


async def get_state_stack_summary(db: AsyncSession, agent_id: int) -> str:
    """获取状态栈摘要文本（注入 prompt 用）。"""
    stack = await _get_stack(db, agent_id)
    return format_state_stack_summary(stack)


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
        from app.services.workspace_service import get_workspace_file, set_workspace_file
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
        from app.services.workspace_service import get_workspace_file, set_workspace_file
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
