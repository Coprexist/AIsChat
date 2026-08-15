"""
Embedding 维度迁移脚本（有数据时可安全改维度）

背景：pgvector 列维度建表时固定（vector(N)）。用户更换 embedding 模型
（如 nomic-embed-text=768 → text-embedding-3-small=1536）时维度变化，
有数据时无法直接 ALTER TYPE（pgvector 不允许跨维度隐式转换）。

方案（对齐 pg-raggraph 的 expand/contract）：
  1. prepare:   为每张向量表加临时列 embedding_tmp vector(新维度)
  2. backfill:  读取每行文本 → 用当前 embedding provider 生成新向量 → 写入临时列
                （幂等：只填 NULL，可中断重跑）
  3. cutover:   短暂锁内切换：删旧索引 → 删旧列 → 临时列改名 → 重建索引
  4. finalize:  清理残留（可选）

用法：
  python scripts/migrate_embedding_dimension.py prepare --dim 768
  python scripts/migrate_embedding_dimension.py backfill --dim 768
  python scripts/migrate_embedding_dimension.py cutover --dim 768
  # 或一键（内部按序执行 prepare → backfill → cutover）
  python scripts/migrate_embedding_dimension.py all --dim 768

前置：EMBEDDING_BACKEND/BASE_URL/MODEL 已配置（生成新向量的 provider），
      DATABASE_URL 已设置（连接生产库）。
安全：backfill 阶段应用可继续运行（旧列不受影响）；
      cutover 阶段需短暂停机（秒级）。
"""
import argparse
import asyncio
import logging
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncpg  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("embed_migrate")

# 每张向量表的文本来源（生成新向量时拼接什么文本）
#   table: 表名
#   id_col: 主键
#   text_sql: 取文本的 SQL（须返回 (id, text) 两列）
#   index: 该表 embedding 列的 HNSW 索引名（cutover 时删/建）
TABLES = [
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
        "text_sql": "SELECT id, (title || '\\n' || content) AS text FROM world_ai_memories",
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


async def get_current_dim(conn, table: str) -> int | None:
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


async def cmd_prepare(conn, dim: int) -> None:
    """加临时列 embedding_tmp vector(新维度)（幂等）"""
    for t in TABLES:
        cur = await get_current_dim(conn, t["table"])
        if cur is None:
            logger.info(f"  ℹ️ {t['table']} 无 embedding 列，跳过")
            continue
        if cur == dim:
            logger.info(f"  ℹ️ {t['table']} 已是 vector({dim})，跳过")
            continue
        await conn.execute(
            f"ALTER TABLE {t['table']} ADD COLUMN IF NOT EXISTS "
            f"embedding_tmp vector({dim})"
        )
        logger.info(f"  ✅ prepare {t['table']}: embedding_tmp vector({dim}) 已添加")


async def cmd_backfill(conn, dim: int, batch_size: int = 50) -> None:
    """用当前 provider 重生成向量写入 embedding_tmp（幂等，只填 NULL）"""
    from app.embedding_providers import get_embedding_provider

    provider = get_embedding_provider()
    if not provider.is_available():
        logger.error("  ❌ 当前 embedding provider 不可用，请检查 EMBEDDING_BACKEND 等配置")
        return

    for t in TABLES:
        cur = await get_current_dim(conn, t["table"])
        if cur is None or cur == dim:
            continue
        # 只处理还需要回填的行（embedding_tmp IS NULL）
        rows = await conn.fetch(
            f"SELECT {t['id_col']} AS id, text FROM ("
            f"  {t['text_sql']}"
            f") sub WHERE embedding_tmp IS NULL ORDER BY id LIMIT {batch_size}"
        )
        done = 0
        while rows:
            for r in rows:
                vec = await provider.embed(str(r["text"]))
                if vec:
                    # pgvector 接受 '[0.1,0.2,...]' 文本格式
                    vec_text = "[" + ",".join(repr(float(x)) for x in vec) + "]"
                    await conn.execute(
                        f"UPDATE {t['table']} SET embedding_tmp = $1::vector WHERE {t['id_col']} = $2",
                        vec_text,
                        r["id"],
                    )
                    done += 1
                else:
                    logger.warning(f"  ⚠️ {t['table']} id={r['id']} embed 失败（跳过）")
            rows = await conn.fetch(
                f"SELECT {t['id_col']} AS id, text FROM ("
                f"  {t['text_sql']}"
                f") sub WHERE embedding_tmp IS NULL ORDER BY id LIMIT {batch_size}"
            )
        logger.info(f"  ✅ backfill {t['table']}: {done} 行已回填")


async def cmd_cutover(conn, dim: int) -> None:
    """切换：删旧索引 → 删旧列 → 临时列改名 → 重建索引（需短暂停机）"""
    for t in TABLES:
        cur = await get_current_dim(conn, t["table"])
        if cur is None or cur == dim:
            continue
        # 1. 删旧 HNSW 索引
        if t["index"]:
            await conn.execute(f"DROP INDEX IF EXISTS {t['index']}")
        # 2. 删旧列（表需无依赖；embedding_tmp 已就绪）
        await conn.execute(f"ALTER TABLE {t['table']} DROP COLUMN IF EXISTS embedding")
        # 3. 临时列改名
        await conn.execute(
            f"ALTER TABLE {t['table']} RENAME COLUMN embedding_tmp TO embedding"
        )
        # 4. 重建 HNSW 索引（新维度）
        if t["index"]:
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS {t['index']} "
                f"ON {t['table']} USING hnsw (embedding vector_cosine_ops)"
            )
        logger.info(f"  ✅ cutover {t['table']}: 已切换到 vector({dim})")


async def cmd_cleanup(conn) -> None:
    """清理残留的 embedding_tmp 列（可选）"""
    for t in TABLES:
        await conn.execute(
            f"ALTER TABLE {t['table']} DROP COLUMN IF EXISTS embedding_tmp"
        )
        logger.info(f"  ✅ cleanup {t['table']}: 已删除 embedding_tmp")


async def main():
    parser = argparse.ArgumentParser(description="Embedding 维度迁移")
    parser.add_argument("cmd", choices=["prepare", "backfill", "cutover", "all", "cleanup"])
    parser.add_argument("--dim", type=int, default=None, help="目标维度")
    parser.add_argument("--batch", type=int, default=50, help="回填批次大小")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC", "")
    if not url:
        logger.error("未设置 DATABASE_URL")
        sys.exit(1)
    if args.cmd != "cleanup" and not args.dim:
        logger.error("需要 --dim 指定目标维度")
        sys.exit(1)

    dim = args.dim
    cfg = parse_db_url(url)
    conn = await asyncpg.connect(**cfg)
    try:
        if args.cmd in ("prepare", "all"):
            await cmd_prepare(conn, dim)
        if args.cmd in ("backfill", "all"):
            await cmd_backfill(conn, dim, args.batch)
        if args.cmd in ("cutover", "all"):
            await cmd_cutover(conn, dim)
        if args.cmd == "cleanup":
            await cmd_cleanup(conn)
        if args.cmd == "all":
            logger.info("🎉 全部完成：维度已切换，可重启应用（记得确认 EMBEDDING_DIMENSION 配置一致）")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
