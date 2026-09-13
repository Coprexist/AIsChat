"""compact_context — 压缩上下文

压缩对话上下文：把之前的对话总结为摘要，释放上下文空间。当系统提示上下文接近上限时调用。
"""
import logging

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from sqlalchemy import select


logger = logging.getLogger(__name__)


class CompactContextTool(WorldToolPlugin):
    name = 'compact_context'
    label = '压缩上下文'
    segment = 'self'

    description = '压缩对话上下文：把之前的对话总结为摘要，释放上下文空间。当系统提示上下文接近上限时调用。'

    parameters = {}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        # 复用主对话的压缩服务：总结中间消息 → 存 worlds.config.chat_summaries[会话] → 下次只发摘要+最近 N 条
        try:
            from app.services.memory.context_compression_service import compress_messages
            from app.services.world.world_chat_service import _resolve_world_credentials, resolve_world_chat_model, get_chat_history, session_key, session_id_for_db, WORLD_CHAT_KEEP_LAST
            api_key, api_base = await _resolve_world_credentials(ctx.world_repo, ctx.world)
            from app.models.world import WorldAI
            wai = (await ctx.world_repo.execute(select(WorldAI).where(WorldAI.world_id == ctx.world.id))).scalar_one_or_none()
            model = await resolve_world_chat_model(ctx.world_repo, ctx.world, api_base, wai)
            sid_db = session_id_for_db(ctx.world)
            history = await get_chat_history(ctx.world_repo, ctx.world.id, 200, session_id=sid_db)
            msgs = [{"role": "system", "content": "世界 AI 对话"}]  # keep_system 保留
            msgs += [
                {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
                for m in history if m["role"] not in ("tool", "note")
            ]
            # 只按**真实对话条数**判断：tool/note 不进 LLM 上下文，也不算"可压缩内容"。
            # 这里必须用过滤后的条数——用原始行数会把满屏工具调用误判成"有的可压"
            real_count = len(msgs) - 1
            if real_count <= WORLD_CHAT_KEEP_LAST:
                logger.info(
                    f"🌐 世界 #{ctx.world.id} 无需压缩：真实对话 {real_count} 条 ≤ 保留窗口 {WORLD_CHAT_KEEP_LAST}"
                )
                return {
                    "success": True,          # 空操作不是失败：AI 该如实转述，不该报"执行失败"
                    "skipped": True,
                    "real_messages": real_count,
                    "keep_last": WORLD_CHAT_KEEP_LAST,
                }
            new_messages, stats = await compress_messages(
                messages=msgs,
                api_base_url=api_base,
                api_key=api_key,
                model=model,
                keep_system=True,
                keep_last_n=WORLD_CHAT_KEEP_LAST,
            )
            if not stats.get("compressed"):
                return {"success": False, "error": stats.get("reason", "压缩未执行")}
            summary = next(
                (m["content"] for m in new_messages if m.get("role") == "system" and "上下文摘要" in str(m.get("content", ""))),
                "",
            )
            if not summary:
                return {"success": False, "error": "摘要提取失败"}
            cfg = dict(ctx.world.config or {})
            summaries = dict(cfg.get("chat_summaries") or {})
            summaries[session_key(ctx.world)] = summary
            cfg["chat_summaries"] = summaries
            ctx.world.config = cfg
            # 能力懒加载：压缩后解锁，effective 全部对齐最新（提示词/强注入/昵称/技能变更在此生效）
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
                # 压缩成功但能力变更没生效 → 用户以为已生效；必须留痕
                logger.warning(f"🌐 世界 #{ctx.world.id} compact 后应用能力变更失败: {e}")
            await ctx.world_repo.flush()
            return {
                "success": True,
                "before_tokens": stats.get("before_tokens", 0),
                "after_tokens": stats.get("after_tokens", 0),
                "compression_ratio_pct": stats.get("compression_ratio_pct", 0),
            }
        except Exception as e:
            logger.warning(f"🌐 世界 #{ctx.world.id} 压缩失败: {e}")
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok and result.get("skipped"):
            return (
                f"无需压缩：当前会话只有 {result.get('real_messages', 0)} 条对话，"
                f"都还在保留窗口（最近 {result.get('keep_last', 0)} 条）内"
            )
        if ok:
            return (
                f"上下文已压缩（{result.get('before_tokens')}→{result.get('after_tokens')} tokens，"
                f"压缩 {result.get('compression_ratio_pct')}%）"
            )
        return f"上下文压缩失败：{result.get('error', '未知错误')}"
