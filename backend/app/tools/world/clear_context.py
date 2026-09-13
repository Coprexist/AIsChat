"""clear_context — 清空上下文

（内部工具，不发给 LLM）
"""
import logging

from app.tools.world.base import WorldToolPlugin, WorldToolContext


logger = logging.getLogger(__name__)


class ClearContextTool(WorldToolPlugin):
    name = 'clear_context'
    label = '清空上下文'
    segment = 'self'
    exposed = False

    async def execute(self, ctx: WorldToolContext) -> dict:
        # 清空当前会话上下文（历史消息 + 摘要 + 工作流记忆），其他会话保留；长期记忆（world_ai_memories）保留
        try:
            from app.models.world import WorldChatMessage
            from sqlalchemy import delete as sa_delete
            from app.services.world.world_chat_service import session_key, session_id_for_db
            sid_db = session_id_for_db(ctx.world)
            q = sa_delete(WorldChatMessage).where(WorldChatMessage.world_id == ctx.world.id)
            if sid_db is None:
                q = q.where(WorldChatMessage.session_id.is_(None))
            else:
                q = q.where(WorldChatMessage.session_id == sid_db)
            await ctx.world_repo.execute(q)
            cfg = dict(ctx.world.config or {})
            summaries = dict(cfg.get("chat_summaries") or {})
            summaries.pop(session_key(ctx.world), None)
            cfg["chat_summaries"] = summaries
            cfg["workflow_memory"] = None
            ctx.world.config = cfg
            # 解锁：清空 = 新对话，前缀变更（提示词/强注入/昵称）在此生效
            try:
                from app.repositories.capability_repo import SQLAlchemyCapabilityRepository
                from app.services.capability_versioning import apply_pending_changes
                await apply_pending_changes(SQLAlchemyCapabilityRepository(ctx.world_repo.session), ctx.world.config, [
                    "ai-skills",
                    f"world-prompt-{ctx.world.id}",
                    "forced-prompt",
                    f"world-name-{ctx.world.id}",
                ])
            except Exception as e:
                # 同上：清空成功但能力变更没生效
                logger.warning(f"🌐 世界 #{ctx.world.id} clear 后应用能力变更失败: {e}")
            await ctx.world_repo.commit()
            return {"success": True, "note": "当前会话上下文已清空（历史消息+摘要+工作流记忆），其他会话保留；长期记忆保留，请从记忆恢复工作状态。"}
        except Exception as e:
            logger.warning(f"🌐 世界 #{ctx.world.id} 清空上下文失败: {e}")
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            return "当前会话上下文已清空（其他会话与长期记忆保留）"
        return f"清空上下文失败：{result.get('error', '未知错误')}"
