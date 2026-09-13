"""store_memory — 存记忆

存储一条长期记忆（这个世界的重要信息，以后可以检索回忆）。世界的重要设定、用户偏好、关键事件值得存。
"""
import json
import logging

from app.tools.world.base import WorldToolPlugin, WorldToolContext


logger = logging.getLogger(__name__)


class StoreMemoryTool(WorldToolPlugin):
    name = 'store_memory'
    label = '存记忆'
    segment = 'memory'

    description = '存储一条长期记忆（这个世界的重要信息，以后可以检索回忆）。世界的重要设定、用户偏好、关键事件值得存。'

    parameters = {'title': {'type': 'string', 'description': '记忆标题（简短概括）'},
     'content': {'type': 'string', 'description': '记忆详细内容'}}

    required = ['title', 'content']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            title = str(args.get("title", "")).strip()
            content = str(args.get("content", "")).strip()
            if not title or not content:
                return {"success": False, "error": "title 和 content 不能为空"}
            from app.models.world import WorldAIMemory
            from app.utils.embedding import get_embedding
            from app.services.world.world_chat_service import _resolve_world_credentials
            api_key, api_base = await _resolve_world_credentials(ctx.world_repo, ctx.world)
            embedding = None
            try:
                embedding = await get_embedding(title + "\n" + content, api_base_url=api_base, api_key=api_key)
            except Exception as e:
                logger.warning(f"🌐 世界 #{ctx.world.id} 记忆向量化失败（将无向量存储）: {e}")
            # 同名 title 覆盖更新（记忆更新语义：执行改动/计划后用固定 title 刷新）
            from sqlalchemy import select as sa_select
            existing = (await ctx.world_repo.execute(
                sa_select(WorldAIMemory).where(
                    WorldAIMemory.world_id == ctx.world.id, WorldAIMemory.title == title
                )
            )).scalars().first()
            if existing is not None:
                existing.content = content
                existing.embedding = embedding
            else:
                ctx.world_repo.add(WorldAIMemory(world_id=ctx.world.id, title=title, content=content, embedding=embedding))
            await ctx.world_repo.flush()
            return {"success": True, "title": title, "embedded": embedding is not None, "updated": existing is not None}
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        return f"已记住「{result.get('title', '')}」" + ("（无向量）" if ok and not result.get("embedded") else "") if ok else f"记忆失败：{result.get('error', '未知错误')}"
