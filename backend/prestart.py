"""
预启动迁移脚本 — 执行 Alembic schema 迁移。

PostgreSQL: 检查 alembic_version 表是否存在。
  - 存在 → 旧库，执行 alembic upgrade head
  - 不存在 → 新库，跳过（由 bootstrap.py 的 create_all + stamp head 处理）

SQLite: 跳过（由 bootstrap.py 的 create_all 处理）
"""
import asyncio
import os
import subprocess
import sys


async def _check_alembic_version(url: str) -> bool:
    """检查 alembic_version 表是否存在（asyncpg）"""
    from app.db_migrate import has_alembic_version_async
    from scripts._shared import parse_db_url
    import asyncpg

    cfg = parse_db_url(url)
    conn = await asyncpg.connect(**cfg)
    try:
        return await has_alembic_version_async(conn)
    finally:
        await conn.close()


def run():
    url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC", "")
    if not url:
        print("Prestart: 未设置 DATABASE_URL，跳过迁移")
        return

    if "postgresql" not in url:
        print("Prestart: SQLite 模式，跳过 prestart 迁移")
        return

    # 检查 alembic_version 表是否存在
    has_version = asyncio.run(_check_alembic_version(url))

    if not has_version:
        print("Prestart: 全新数据库，跳过 Alembic（由 bootstrap.py 处理）")
        return

    # 旧库：执行 Alembic 迁移
    print("Prestart: 执行 Alembic 迁移...")
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
    )
    if result.returncode != 0:
        print("Prestart: Alembic 迁移失败", file=sys.stderr)
        sys.exit(result.returncode)
    print("Prestart: Alembic 迁移完成")


if __name__ == "__main__":
    run()
