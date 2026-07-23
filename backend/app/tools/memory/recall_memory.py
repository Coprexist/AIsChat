"""
recall_memory 工具 — AI 检索相关记忆（向量搜索 + 文本关键词回退）
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class RecallMemory(ToolPlugin):
    name = "recall_memory"
    description = "检索相关记忆"
    segment = "memory"
    parameters = {
        "query": {"type": "string", "description": "搜索查询"},
        "scope": {"type": "string", "enum": ["private", "group"], "description": "搜索范围"},
        "top_k": {"type": "integer", "default": 5, "description": "返回条数（1-20）"},
    }
    required = ["query", "scope"]
    states = ["active", "dnd"]
    admin_description = "搜索并检索相关记忆。收到消息时自动触发检索，AI 也可主动调用来获取历史上下文。"
    trigger_condition = "收到消息自动检索 / AI 主动查询记忆"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.utils.embedding import get_embedding

        query = arguments["query"]
        scope = arguments["scope"]
        top_k = min(arguments.get("top_k", 5), 20)
        mem_group_id = arguments.get("group_id", group_id)

        api_key = context.get("api_key")
        api_base = context.get("api_base_url", "https://api.deepseek.com")

        memories: list[dict] = []
        embedding_failed = False

        # ═══ 第一轮：向量搜索 ═══
        try:
            query_embedding = await get_embedding(query, api_base_url=api_base, api_key=api_key)
            embedding_str = f"[{','.join(map(str, query_embedding))}]"

            if scope == "private":
                where_clause = "owner_type = 'ai' AND owner_id = :owner_id"
                params = {"embedding": embedding_str, "owner_id": agent_id, "top_k": top_k}
            else:
                where_clause = "scope = 'group' AND (group_id = :group_id OR group_id IS NULL)"
                params = {"embedding": embedding_str, "group_id": mem_group_id, "top_k": top_k}

            sql = text(f"""
                SELECT rm.id, rm.title, rm.scope,
                       1 - (rm.embedding <=> :embedding) AS similarity,
                       rm.created_at, dm.content
                FROM rough_memories rm
                LEFT JOIN detail_memories dm ON dm.rough_id = rm.id
                WHERE {where_clause}
                  AND rm.embedding IS NOT NULL
                ORDER BY rm.embedding <=> :embedding
                LIMIT :top_k
            """)

            result = await db.execute(sql, params)
            for row in result:
                memories.append({
                    "id": row.id, "title": row.title, "scope": row.scope,
                    "similarity": round(float(row.similarity), 4) if row.similarity else None,
                    "content": (row.content[:200] + "...") if row.content and len(row.content) > 200
                    else (row.content or ""),
                    "source": "vector",
                })
        except Exception as e:
            logger.warning(f"recall_memory 向量搜索失败，回退到文本搜索: {e}")
            embedding_failed = True

        # ═══ 第二轮：文本关键词回退 ═══
        if embedding_failed or not memories:
            from app.services.memory.memory_service import _text_search_memories
            text_results = await _text_search_memories(
                db, agent_id, query, top_k=top_k,
                group_id=mem_group_id if scope == "group" else None,
                scope=scope,
            )
            vector_ids = {m["id"] for m in memories}
            for tr in text_results:
                if tr["id"] not in vector_ids:
                    tr["similarity"] = None
                    tr["content"] = (tr["content"][:200] + "...") if len(tr.get("content", "") or "") > 200 else (tr.get("content", "") or "")
                    tr["source"] = "text"
                    memories.append(tr)

        if not memories:
            extra = "（Embedding API 不可用，已尝试关键词搜索）" if embedding_failed else ""
            return {"memories": [], "message": f"未找到相关记忆{extra}"}

        result = {"memories": memories}
        if embedding_failed:
            result["notice"] = "⚠️ Embedding API 当前不可用，以上结果为关键词文本匹配（非向量语义搜索）。记忆功能正常但精度略降。"
        return result


ToolRegistry.register(RecallMemory)
