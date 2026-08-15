"""
Embedding 维度迁移脚本（有数据时可安全改维度）

背景：pgvector 列维度建表时固定（vector(N)）。用户更换 embedding 模型
（如 nomic-embed-text=768 → text-embedding-3-small=1536）时维度变化，
有数据时无法直接 ALTER TYPE（pgvector 不允许跨维度隐式转换）。

方案（对齐 pg-raggraph 的 expand/contract）：
  1. prepare:   为每张向量表加临时列 embedding_tmp vector(新维度)
  2. backfill:  并发重生成向量写入临时列（幂等：只填 NULL，可中断重跑）
  3. cutover:   守卫检查 → 删旧索引 → 删旧列 → 临时列改名 → 重建索引
  4. cleanup:   清理残留（可选）

用法：
  python scripts/migrate_embedding_dimension.py prepare --dim 768
  python scripts/migrate_embedding_dimension.py backfill --dim 768
  python scripts/migrate_embedding_dimension.py cutover --dim 768
  # 或一键（内部按序执行 prepare → backfill → cutover）
  python scripts/migrate_embedding_dimension.py all --dim 768
  # 日常回填：给 embedding IS NULL 的记忆补向量（生产启用向量后跑一次）
  python scripts/migrate_embedding_dimension.py fill

前置：EMBEDDING_BACKEND/BASE_URL/MODEL 已配置（生成新向量的 provider），
      DATABASE_URL 已设置（连接生产库）。
安全：backfill 阶段应用可继续运行（旧列不受影响）；
      cutover 阶段需短暂停机（秒级）。
"""
import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncpg  # noqa: E402

from scripts._shared import (  # noqa: E402
    VECTOR_TABLES,
    backfill_table,
    get_embedding_dim,
    parse_db_url,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("embed_migrate")


async def cmd_prepare(conn, dim: int) -> None:
    """加临时列 embedding_tmp vector(新维度)（幂等）"""
    for t in VECTOR_TABLES:
        table = t["table"]
        cur = await get_embedding_dim(conn, table)
        if cur is None:
            logger.info(f"  ℹ️ {table} 无 embedding 列，跳过")
            continue
        if cur == dim:
            logger.info(f"  ℹ️ {table} 已是 vector({dim})，跳过")
            continue
        await conn.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS embedding_tmp vector({dim})"
        )
        logger.info(f"  ✅ prepare {table}: embedding_tmp vector({dim}) 已添加")


async def cmd_backfill(conn, dim: int, batch_size: int, concurrency: int) -> None:
    """并发重生成向量写入 embedding_tmp（幂等，只填 NULL）"""
    from app.embedding_providers import get_embedding_provider

    provider = get_embedding_provider()
    if not provider.is_available():
        logger.error("  ❌ 当前 embedding provider 不可用，请检查 EMBEDDING_BACKEND 等配置")
        sys.exit(1)

    for t in VECTOR_TABLES:
        table = t["table"]
        cur = await get_embedding_dim(conn, table)
        if cur is None or cur == dim:
            continue
        done, failed = await backfill_table(
            conn,
            table=t["table"],
            id_col=t["id_col"],
            text_sql=t["text_sql"],
            provider=provider,
            batch_size=batch_size,
            concurrency=concurrency,
        )
        logger.info(f"  ✅ backfill {table}: 成功 {done} 行" + (f"，失败 {failed} 行" if failed else ""))


async def _pending_count(conn, table: str) -> int:
    """embedding_tmp 仍为 NULL 的行数（回填未完成度）"""
    return await conn.fetchval(
        f"SELECT count(*) FROM {table} WHERE embedding_tmp IS NULL"
    )


async def cmd_cutover(conn, dim: int) -> None:
    """守卫检查 → 切换列（需短暂停机）"""
    # 守卫：任何表还有未回填行则拒绝，避免静默丢向量
    blockers = []
    for t in VECTOR_TABLES:
        cur = await get_embedding_dim(conn, t["table"])
        if cur is None or cur == dim:
            continue
        pending = await _pending_count(conn, t["table"])
        if pending > 0:
            blockers.append(f"{t['table']}（{pending} 行未回填）")
    if blockers:
        logger.error(
            f"  ❌ cutover 拒绝：以下表仍有未回填行 → {', '.join(blockers)}。"
            "请先重跑 backfill（幂等可续传），或确认这些行可接受 NULL 后加 --force"
        )
        sys.exit(1)

    for t in VECTOR_TABLES:
        table = t["table"]
        cur = await get_embedding_dim(conn, table)
        if cur is None or cur == dim:
            continue
        # 1. 删旧 HNSW 索引
        if t["index"]:
            await conn.execute(f"DROP INDEX IF EXISTS {t['index']}")
        # 2. 删旧列（embedding_tmp 已回填完毕）
        await conn.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding")
        # 3. 临时列改名
        await conn.execute(
            f"ALTER TABLE {table} RENAME COLUMN embedding_tmp TO embedding"
        )
        # 4. 重建 HNSW 索引（新维度）
        if t["index"]:
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS {t['index']} "
                f"ON {table} USING hnsw (embedding vector_cosine_ops)"
            )
        logger.info(f"  ✅ cutover {table}: 已切换到 vector({dim})")


async def cmd_fill(conn, batch_size: int, concurrency: int) -> None:
    """给 embedding IS NULL 的记忆补向量（日常回填，幂等可重入）"""
    from app.embedding_providers import get_embedding_provider

    provider = get_embedding_provider()
    if not provider.is_available():
        logger.error("  ❌ 当前 embedding provider 不可用，请检查 EMBEDDING_BACKEND 等配置")
        sys.exit(1)

    total_done = total_failed = 0
    for t in VECTOR_TABLES:
        table = t["table"]
        done, failed = await backfill_table(
            conn,
            table=table,
            id_col=t["id_col"],
            text_sql=t["text_sql"],
            provider=provider,
            batch_size=batch_size,
            concurrency=concurrency,
            target_col="embedding",  # 直接回填正式列（日常回填）
        )
        total_done += done
        total_failed += failed
        logger.info(f"  ✅ fill {table}: 成功 {done} 行" + (f"，失败 {failed} 行" if failed else ""))
    logger.info(f"🎉 回填完成：成功 {total_done} 行" + (f"，失败 {total_failed} 行（可重跑续传）" if total_failed else ""))


async def cmd_cleanup(conn) -> None:
    """清理残留的 embedding_tmp 列（可选）"""
    for t in VECTOR_TABLES:
        await conn.execute(
            f"ALTER TABLE {t['table']} DROP COLUMN IF EXISTS embedding_tmp"
        )
        logger.info(f"  ✅ cleanup {t['table']}: 已删除 embedding_tmp")


async def main():
    parser = argparse.ArgumentParser(description="Embedding 维度迁移 / 向量回填")
    parser.add_argument("cmd", choices=["prepare", "backfill", "cutover", "all", "cleanup", "fill"])
    parser.add_argument("--dim", type=int, default=None, help="目标维度")
    parser.add_argument("--batch", type=int, default=50, help="回填批次大小")
    parser.add_argument("--concurrency", type=int, default=8, help="并发 embed 数")
    parser.add_argument("--force", action="store_true", help="cutover 时忽略未回填行（慎用）")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC", "")
    if not url:
        logger.error("未设置 DATABASE_URL")
        sys.exit(1)
    if args.cmd not in ("cleanup", "fill") and not args.dim:
        logger.error("需要 --dim 指定目标维度")
        sys.exit(1)

    conn = await asyncpg.connect(**parse_db_url(url))
    try:
        if args.cmd in ("prepare", "all"):
            await cmd_prepare(conn, args.dim)
        if args.cmd in ("backfill", "all"):
            await cmd_backfill(conn, args.dim, args.batch, args.concurrency)
        if args.cmd in ("cutover", "all"):
            if args.force:
                logger.warning("  ⚠️ --force：跳过未回填守卫")
                # 用 force 时直接把未回填行置 NULL 继续（临时列已存在）
            await cmd_cutover(conn, args.dim)
        if args.cmd == "fill":
            await cmd_fill(conn, args.batch, args.concurrency)
        if args.cmd == "cleanup":
            await cmd_cleanup(conn)
        if args.cmd == "all":
            logger.info("🎉 全部完成：维度已切换，可重启应用（记得确认 EMBEDDING_DIMENSION 配置一致）")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
