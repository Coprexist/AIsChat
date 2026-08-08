"""
pop_state 工具 — 结束当前状态帧，选择性回跳

支持两种用法：
1. 不传 target_frame_id：回到上一层（LIFO）
2. 传 target_frame_id：直接回到指定状态帧，中间帧归档并在摘要中汇报
   （例如：写代码 → 回消息 → 处理闹钟，闹钟处理完想直接回写代码，
    传 file_work 帧的 id，跳过"回消息"层）
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry
from app.services.agent.state_stack_service import pop_state

logger = logging.getLogger(__name__)


class PopState(ToolPlugin):
    name = "pop_state"
    description = (
        "结束当前状态帧，回到目标状态继续之前的任务。\n"
        "两种用法：\n"
        "1. 不传 target_frame_id → 回到上一层（最近被打断的任务）\n"
        "2. 传 target_frame_id → 直接回到指定的状态帧（多层嵌套时跳过中间层，"
        "中间层会归档并在摘要里汇报——它未完成的事由你决定是否继续）\n"
        "调用后系统会告诉你回到什么任务、跳过了哪些层。"
        "如果当前任务完成想回去用这个；不做了想放弃用 close_state。"
    )
    segment = "self_management"
    parameters = {
        "target_frame_id": {
            "type": "string",
            "description": "目标状态帧 id（可选）。多层嵌套想直接回到某一层时传；"
                           "不传则回上一层。可用 list_states 查看帧 id。",
            "nullable": True,
        },
    }
    states = ["active", "dnd", "inactive"]

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        target = str(arguments.get("target_frame_id") or "").strip()
        stack, msg = await pop_state(db, agent_id, target_frame_id=target)
        await db.commit()
        return {
            "success": True,
            "message": msg,
            "remaining_depth": len(stack),
            "next_frame": stack[-1] if stack else None,
        }


ToolRegistry.register(PopState)
