"""
向量加速 Pipeline
后台将消息向量化存入 group_message_embeddings，提供混合检索（向量+BM25+时间衰减）
"""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import text, select
from app.database import async_session
from app.models.message import Message, GroupMessageEmbedding
from app.models.group import Group
from app.config import settings

logger = logging.getLogger(__name__)

# 全局向量化任务队列
embedding_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)


async def vector_pipeline_worker():
    """
    后台 worker：消费 embedding_queue，将消息向量化后写入 group_message_embeddings。
    在 main.py lifespan 中启动。
    """
    logger.info("📊 向量化 pipeline worker 已启动")
    while True:
        try:
            item = await embedding_queue.get()
            async with async_session() as db:
                try:
                    await _vectorize_message(db, item)
                except Exception as e:
                    logger.error(f"向量化消息失败: {e}")
            embedding_queue.task_done()
        except asyncio.CancelledError:
            logger.info("向量化 worker 正在关闭...")
            break
        except Exception as e:
            logger.error(f"向量化 worker 异常: {e}")
            await asyncio.sleep(1)


async def _vectorize_message(db, item: dict):
    """向量化单条消息"""
    group_id = item["group_id"]
    message_id = item["message_id"]

    # 检查群聊是否开启了向量加速
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()
    if not group or not group.is_vector_accelerated:
        return

    # 获取消息
    msg_result = await db.execute(select(Message).where(Message.id == message_id))
    message = msg_result.scalar_one_or_none()
    if message is None:
        return

    # 生成向量
    from app.utils.embedding import get_embedding

    try:
        embedding = await get_embedding(message.content)
    except Exception as e:
        logger.warning(f"消息 {message_id} 向量化失败: {e}")
        return

    # 存储
    emb = GroupMessageEmbedding(
        group_id=group_id,
        message_id=message_id,
        content=message.content,
        embedding=embedding,
    )
    db.add(emb)
    await db.commit()

    logger.debug(f"消息 {message_id} 已向量化存入 group_message_embeddings")


async def hybrid_search(
    db,
    group_id: int,
    query_text: str,
    top_k: int = 10,
) -> list[dict]:
    """
    混合检索：向量相似度 (0.6) + BM25 近似 (0.3) + 时间衰减 (0.1)

    使用 pgvector <=> 操作符 + PostgreSQL 全文搜索 ts_rank。
    对中文使用 simple 分词配置（后续可升级为 zhparser）。

    返回: [{"message_id": int, "content": str, "vector_score": float, "bm25_score": float, "combined_score": float, "sender_type": str, "sender_name": str, ...}]
    """
    from app.utils.embedding import get_embedding
    from app.db_providers import get_provider

    provider = get_provider()

    # ═══ 后端不支持 SQL 向量检索时（SQLite P0）：文本 + 时间衰减降级 ═══
    if not provider.supports_sql_vector_search:
        logger.debug(f"存储后端 {provider.name} 不支持向量加速，使用文本检索降级")
        return await _hybrid_search_text_fallback(db, group_id, query_text, top_k)

    # 向量化查询
    try:
        query_embedding = await get_embedding(query_text)
    except Exception as e:
        logger.warning(f"查询向量化失败: {e}")
        return []

    embedding_str = f"[{','.join(map(str, query_embedding))}]"

    vector_weight = settings.vector_weight
    bm25_weight = settings.bm25_weight
    time_weight = settings.time_decay_weight

    vector_expr = provider.vector_similarity_expr("gme.embedding", "query_emb")
    sql = text(provider.hybrid_search_sql().format(
        vector_expr=vector_expr,
        vector_weight=vector_weight,
        bm25_weight=bm25_weight,
        time_weight=time_weight,
    ))

    result = await db.execute(sql, {
        "query_emb": embedding_str,
        "query_text": query_text,
        "group_id": group_id,
        "top_k": top_k,
    })

    return [
        {
            "message_id": row.message_id,
            "content": row.content,
            "vector_score": round(float(row.vector_score), 4) if row.vector_score else 0,
            "bm25_score": round(float(row.bm25_score), 4) if row.bm25_score else 0,
            "combined_score": round(float(row.combined_score), 4) if row.combined_score else 0,
            "sender_type": row.sender_type,
            "sender_id": row.sender_id,
        }
        for row in result
    ]


async def _hybrid_search_text_fallback(
    db,
    group_id: int,
    query_text: str,
    top_k: int = 10,
) -> list[dict]:
    """
    混合检索降级实现（SQLite P0）：关键词 LIKE + 时间衰减。

    无向量相似度，纯文本匹配排序——保证功能可用，向量精度由 P1 的
    sqlite-vec 补齐。
    """
    # 提取关键词（复用 memory_service 的 ngram 分词策略，中文友好）
    from app.services.memory.memory_service import extract_keywords
    parts = extract_keywords(query_text)

    conditions = []
    params: dict = {}
    for i, kw in enumerate(parts[:8]):
        param_key = f"kw{i}"
        conditions.append(f"gme.content LIKE :{param_key}")
        params[param_key] = f"%{kw}%"

    if not conditions:
        return []

    sql = text(f"""
        SELECT
            gme.message_id,
            gme.content,
            gme.created_at,
            m.sender_type,
            m.sender_id,
            0.0 AS vector_score,
            0.0 AS bm25_score,
            0.0 AS age_days,
            1.0 AS combined_score
        FROM group_message_embeddings gme
        JOIN messages m ON gme.message_id = m.id
        WHERE gme.group_id = :group_id
          AND ({ " OR ".join(conditions) })
        ORDER BY gme.created_at DESC
        LIMIT :top_k
    """)
    params["group_id"] = group_id
    params["top_k"] = top_k

    try:
        result = await db.execute(sql, params)
    except Exception as e:
        logger.warning(f"文本降级检索失败: {e}")
        return []

    return [
        {
            "message_id": row.message_id,
            "content": row.content,
            "vector_score": 0.0,
            "bm25_score": 0.0,
            "combined_score": 0.0,
            "sender_type": row.sender_type,
            "sender_id": row.sender_id,
        }
        for row in result
    ]
