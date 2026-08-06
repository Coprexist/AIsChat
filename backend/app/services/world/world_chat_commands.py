"""
世界对话斜杠命令 — 用户输入，不走 LLM（从 world_chat_service 拆分）

- /clear   清空对话上下文（历史+摘要+工作流记忆），长期记忆保留
- /compact 压缩对话上下文为摘要
命令消息与结果落库（role=tool），调用方负责 yield [TOOL]/[DONE]。
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def run_slash_command(db: AsyncSession, world, cmd_text: str) -> str | None:
    """执行斜杠命令，返回结果 note；非命令返回 None（调用方继续走 LLM 流）"""
    from app.models.world import WorldChatMessage

    if cmd_text.startswith("/clear"):
        from sqlalchemy import delete as sa_delete
        await db.execute(sa_delete(WorldChatMessage).where(WorldChatMessage.world_id == world.id))
        world.config = {
            **(world.config or {}),
            "chat_summary": None,
            "workflow_memory": None,
        }
        # 清持久化建议（clear 后应回到预设引导，而不是旧建议）
        try:
            from app.services.world.world_service import delete_world_data
            await delete_world_data(db, world.id, "ui.suggestions")
        except Exception:
            pass
        await db.commit()
        return "🧹 已清空对话上下文（历史消息+摘要+工作流记忆），长期记忆保留——AI 将从记忆恢复工作状态。"

    if cmd_text.startswith("/compact"):
        from app.services.world.world_tools import _do_execute
        result = await _do_execute(db, world, "compact_context", "{}")
        if result.get("success"):
            return (f"📦 上下文已压缩：{result.get('before_tokens')} → "
                    f"{result.get('after_tokens')} tokens"
                    f"（压缩率 {result.get('compression_ratio_pct')}%）")
        return f"⚠️ 压缩未执行：{result.get('error', '未知原因')}"

    return None
