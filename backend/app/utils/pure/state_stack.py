"""
状态栈纯函数 — 无 IO、无 DB 依赖。

make_state_frame(): 构建单个状态帧
format_state_stack_summary(): 栈 → AI 可读摘要文本
"""
from datetime import datetime, timezone
import uuid


MAX_STACK_DEPTH = 10


def make_state_frame(
    type_: str,
    context_ref: str = "",
    why: str = "",
    doing: str = "",
    todo: str = "",
    plan: str = "",
    journal: str = "",
    status: str = "active",
) -> dict:
    """构建单个状态帧（纯函数）。"""
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
    }


def format_state_stack_summary(stack: list[dict]) -> str:
    """
    纯函数：将状态栈转为 AI 可读摘要（高密度结构化，尾部放 prompt 缓存友好）。

    格式：
    📋 状态栈（底→顶）
    ▸  [type] (context): 基础状态
    ▸↑ [type] (context): 暂停的任务  TODO: xxx  PLAN: xxx
    ▸▶ [type] (context): 当前活跃任务  TODO: xxx  PLAN: xxx

    底部追加指令：请继续执行栈顶任务。
    """
    if not stack:
        return ""

    lines = ["\n\n## 📋 状态栈（底→顶）"]
    for i, frame in enumerate(stack):
        status = frame.get("status", "active")
        type_name = frame.get("type", "?")
        context = frame.get("context_ref", "")
        doing = frame.get("doing", "")
        why = frame.get("why", "")
        todo = frame.get("todo", "")
        plan = frame.get("plan", "")

        # 标记图标
        if i == len(stack) - 1 and status == "active":
            marker = "▸▶"  # 当前活跃
        elif status == "paused":
            marker = "▸↑"  # 暂停
        else:
            marker = "▸"   # 基础/已关闭

        context_str = f"({context})" if context else ""
        action = doing or why
        line = f"{marker} [{type_name}] {context_str}: {action}"
        lines.append(line)

        if todo:
            items = todo.strip().replace("\n", "; ")
            lines.append(f"   TODO: {items}")
        if plan:
            items = plan.strip().replace("\n", "; ")
            lines.append(f"   PLAN: {items}")

    # 底部指令
    active_frames = [f for f in stack if f.get("status") == "active"]
    if active_frames:
        lines.append("\n请继续执行栈顶活跃任务。完成后调用 pop_state 回到上一层，或 close_state 放弃。")

    return "\n".join(lines)
