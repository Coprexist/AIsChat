"""
Embedding 迁移共享模块（prestart.py 与 migrate_embedding_dimension.py 共用）

集中：向量表清单、列维度查询、DB URL 解析、并发 embed 回填。
避免"加一张表/改一处逻辑要改两个文件"的 DRY 违规。
"""
import asyncio
import re

# 每张向量表的元信息：
#   table:   表名
#   id_col:  主键列
#   text_sql: 生成新向量时取的文本（须返回 (id, text) 两列）
#   index:   embedding 列的 HNSW 索引名（None = 无索引）
VECTOR_TABLES = [
    {
        "table": "rough_memories",
        "id_col": "id",
        "text_sql": "SELECT id, title AS text FROM rough_memories",
        "index": "idx_rough_memories_embedding_hnsw",
    },
    {
        "table": "detail_memories",
        "id_col": "id",
        "text_sql": "SELECT id, content AS text FROM detail_memories",
        "index": "idx_detail_memories_embedding_hnsw",
    },
    {
        "table": "world_ai_memories",
        "id_col": "id",
        "text_sql": "SELECT id, (title || '\n' || content) AS text FROM world_ai_memories",
        "index": "idx_world_ai_memories_embedding_hnsw",
    },
    {
        "table": "group_message_embeddings",
        "id_col": "id",
        "text_sql": "SELECT id, content AS text FROM group_message_embeddings",
        "index": None,  # 该表无 HNSW 索引
    },
]


def parse_db_url(url: str) -> dict:
    """解析 postgresql://user:pass@host:port/dbname → asyncpg 连接参数（纯函数）"""
    m = re.match(r'postgresql(?:://|\+asyncpg://)([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', url)
    if not m:
        raise ValueError(f"无法解析数据库 URL: {url}")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": int(m.group(4)),
        "database": m.group(5),
    }


async def get_embedding_dim(conn, table: str) -> int | None:
    """查某表 embedding 列的维度；无该列/非 vector 返回 None。"""
    row = await conn.fetchrow(
        "SELECT format_type(a.atttypid, a.atttypmod) AS t "
        "FROM pg_attribute a JOIN pg_class c ON a.attrelid = c.oid "
        "WHERE c.relname = $1 AND a.attname = 'embedding'",
        table,
    )
    if not row or not row["t"]:
        return None
    m = re.search(r'vector\((\d+)\)', row["t"])
    return int(m.group(1)) if m else None


def vec_to_text(vec: list[float]) -> str:
    """list[float] → pgvector 文本格式 '[0.1,0.2,...]'"""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


async def backfill_table(
    conn,
    table: str,
    id_col: str,
    text_sql: str,
    provider,
    batch_size: int = 50,
    concurrency: int = 8,
    target_col: str = "embedding_tmp",
) -> tuple[int, int]:
    """
    并发回填某表的向量列（只填 NULL，幂等可重入）。

    target_col:
      - "embedding_tmp": 维度迁移用（新列，原 embedding 保留）
      - "embedding":     日常回填用（给 embedding IS NULL 的记忆补向量）

    返回 (成功数, 失败数)。失败行保持 NULL，不阻塞（可重跑续传）。
    """
    def fetch_batch():
        # WHERE 放子查询内（FROM 是原表，可引用目标列），外层只做排序分页
        return conn.fetch(
            f"SELECT {id_col} AS id, text FROM ("
            f"  {text_sql} WHERE {target_col} IS NULL"
            f") sub ORDER BY {id_col} LIMIT {batch_size}"
        )
    done = failed = 0
    rows = await fetch_batch()
    while rows:
        # 并发 embed（对齐 memory_buffer 的 gather 先例）
        results = await asyncio.gather(
            *(provider.embed(str(r["text"])) for r in rows)
        )
        for r, vec in zip(rows, results):
            if vec:
                await conn.execute(
                    f"UPDATE {table} SET {target_col} = $1::vector WHERE {id_col} = $2",
                    vec_to_text(vec),
                    r["id"],
                )
                done += 1
            else:
                failed += 1
        rows = await fetch_batch()
    return done, failed
