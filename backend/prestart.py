"""
预启动迁移脚本——在 SQLAlchemy ORM 加载前执行 DDL。

纯函数设计：MIGRATIONS 列表是纯数据（name + SQL），run() 是编排器（连接 DB + 执行）。
此脚本完全不依赖 app 模块，避免"缺列导致 ORM 导入失败"的鸡生蛋问题。
"""
import asyncio
import asyncpg
import os
import sys


# ═══════════════════════════════════════════════════════════════
# 纯数据：DDL 迁移列表。每条 (名称, SQL, 幂等条件)
# 条件列含义：True = IF NOT EXISTS 模式（建表），False = 无条件执行
# ═══════════════════════════════════════════════════════════════

MIGRATIONS: list[tuple[str, str]] = [
    # ── v2.0.0: 群邀请卡片系统 ──
    (
        "dm_messages.message_type",
        "ALTER TABLE dm_messages ADD COLUMN IF NOT EXISTS message_type VARCHAR(30) NOT NULL DEFAULT 'normal'",
    ),
    (
        "group_invitations 表",
        """CREATE TABLE IF NOT EXISTS group_invitations (
            id SERIAL PRIMARY KEY,
            group_id INT NOT NULL,
            inviter_id INT NOT NULL,
            invitee_id INT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            message TEXT,
            dm_session_id VARCHAR(64),
            dm_message_id INT,
            created_at TIMESTAMP DEFAULT NOW(),
            resolved_at TIMESTAMP,
            CONSTRAINT ck_group_invitation_status CHECK (status IN ('pending', 'accepted', 'rejected'))
        )""",
    ),
    (
        "idx_group_invitations_invitee",
        "CREATE INDEX IF NOT EXISTS idx_group_invitations_invitee ON group_invitations(invitee_id, status)",
    ),
    (
        "idx_group_invitations_group",
        "CREATE INDEX IF NOT EXISTS idx_group_invitations_group ON group_invitations(group_id)",
    ),
    # ── v2.0.1: 补全缺失的群主成员记录 ──
    (
        "群主成员记录补全",
        """INSERT INTO group_members (group_id, member_type, member_id, role)
        SELECT g.id, g.owner_type, g.owner_id, 'owner'
        FROM groups g
        WHERE NOT EXISTS (
            SELECT 1 FROM group_members gm
            WHERE gm.group_id = g.id
              AND gm.member_type = g.owner_type
              AND gm.member_id = g.owner_id
        )""",
    ),
    # ── v0.2.1: 状态栈（AI 跨任务上下文追踪）──
    (
        "agents.state_stack",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS state_stack JSONB DEFAULT '[]'::jsonb",
    ),
    # ── v2.0.2: 修复每个群多个 owner 的错误数据 ──
    (
        "重复群主清理",
        """UPDATE group_members gm
        SET role = 'member'
        WHERE role = 'owner'
          AND (gm.member_type, gm.member_id) NOT IN (
              SELECT g.owner_type, g.owner_id FROM groups g WHERE g.id = gm.group_id
          )""",
    ),
    # ── v2.0.5: users.type 支持 'system' 类型（系统通知用户）──
    (
        "users.type CHECK 约束支持 system",
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_type_check",
    ),
    (
        "users.type CHECK 约束重建",
        "ALTER TABLE users ADD CONSTRAINT users_type_check CHECK (type IN ('human', 'ai', 'system'))",
    ),
    (
        "api_doc_sections 表",
        """CREATE TABLE IF NOT EXISTS api_doc_sections (
            id VARCHAR(4) PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            intro TEXT NOT NULL DEFAULT '',
            doc_file VARCHAR(100) NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
    ),
]


# ═══════════════════════════════════════════════════════════════
# 纯函数：解析连接信息
# ═══════════════════════════════════════════════════════════════

# 向量表清单 / 维度查询 / URL 解析集中在 scripts/_shared.py
# （与 migrate_embedding_dimension.py 共用，避免重复实现）
from scripts._shared import VECTOR_TABLES, get_embedding_dim, parse_db_url  # noqa: E402


# ═══════════════════════════════════════════════════════════════
# 编排器
# ═══════════════════════════════════════════════════════════════


async def _align_embedding_dimension(conn) -> None:
    """
    把 PG 向量列维度对齐到 EMBEDDING_DIMENSION（用户自选）。

    背景：pgvector 列维度建表时固定（vector(N)），换 embedding 模型
    （如 nomic-embed-text=768 / text-embedding-3-small=1536）需改列。

    策略：
    - 配置维度 = 列维度 → 跳过
    - 配置维度 ≠ 列维度 且 无向量数据 → 自动 ALTER（毫秒级，零数据风险）
    - 配置维度 ≠ 列维度 且 已有向量数据 → 跳过 + 明确告警
      （有向量数据需用 scripts/migrate_embedding_dimension.py 安全迁移）
    - SQLite 后端（URL 非 postgresql）→ 跳过（JsonVectorType 维度无关）
    """
    # 目标维度：DB 覆盖（前端图形化改的）优先，其次环境变量（默认 1536）
    target = None
    try:
        db_cfg = await conn.fetchval(
            "SELECT embedding_config FROM system_settings WHERE id = 1"
        )
        if db_cfg:
            import json as _json
            try:
                db_cfg_obj = _json.loads(db_cfg) if isinstance(db_cfg, str) else db_cfg
                if db_cfg_obj.get("embedding_dimension"):
                    target = db_cfg_obj["embedding_dimension"]
            except Exception:
                pass
    except Exception:
        pass
    if target is None:
        target = os.getenv("EMBEDDING_DIMENSION", "1536")
    try:
        dim = int(target)
    except ValueError:
        print(f"  ⚠️ EMBEDDING_DIMENSION 非法值 '{target}'，跳过维度对齐")
        return
    if dim <= 0:
        print(f"  ⚠️ EMBEDDING_DIMENSION 非法值 '{target}'，跳过维度对齐")
        return

    for t in VECTOR_TABLES:
        table = t["table"]
        try:
            cur_dim = await get_embedding_dim(conn, table)
        except Exception as e:
            print(f"  ⚠️ {table} 查询列类型失败: {e}")
            continue
        if cur_dim is None:
            continue  # 表/列不存在（SQLite 或未建表）
        if cur_dim == dim:
            continue

        # 维度不一致：检查是否无向量数据（NULL 时 ALTER 零风险）
        try:
            cnt = await conn.fetchval(f"SELECT count(*) FROM {table}")
            with_vec = await conn.fetchval(
                f"SELECT count(*) FROM {table} WHERE embedding IS NOT NULL"
            )
        except Exception:
            cnt, with_vec = -1, -1

        if cnt == 0 or with_vec == 0:
            await conn.execute(
                f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector({dim})"
            )
            print(f"  ✅ {table}.embedding: vector({cur_dim}) → vector({dim})"
                  f"（{cnt} 行，无向量数据，自动对齐）")
        else:
            print(
                f"  ⚠️ {table}.embedding 维度 vector({cur_dim}) ≠ 配置 {dim}，"
                f"且已有 {with_vec} 条带向量数据——跳过。"
                f"请用 scripts/migrate_embedding_dimension.py 安全迁移，"
                f"或调整 EMBEDDING_DIMENSION"
            )


async def run():
    url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC", "")
    if not url:
        print("Prestart: 未设置 DATABASE_URL，跳过迁移")
        return

    print("Prestart: 连接数据库执行迁移...")
    try:
        cfg = parse_db_url(url)
        conn = await asyncpg.connect(**cfg)
    except Exception as e:
        print(f"Prestart: 数据库连接失败（可能尚未就绪），跳过迁移: {e}")
        return

    try:
        for name, sql in MIGRATIONS:
            try:
                await conn.execute(sql)
                print(f"  ✅ {name}")
            except Exception as e:
                print(f"  ❌ {name} 失败: {e}")

        # ── Embedding 维度对齐（用户自选 EMBEDDING_DIMENSION）──
        await _align_embedding_dimension(conn)
    finally:
        await conn.close()

    print("Prestart: 迁移完成")


if __name__ == "__main__":
    asyncio.run(run())
