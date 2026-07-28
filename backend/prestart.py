"""
预启动迁移脚本——在 SQLAlchemy ORM 加载前执行 DDL。

纯函数设计：MIGRATIONS 列表是纯数据（name + SQL），run() 是编排器（连接 DB + 执行）。
此脚本完全不依赖 app 模块，避免"缺列导致 ORM 导入失败"的鸡生蛋问题。
"""
import asyncio
import asyncpg
import os
import sys
import re


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
]


# ═══════════════════════════════════════════════════════════════
# 纯函数：解析连接信息
# ═══════════════════════════════════════════════════════════════

def parse_db_url(url: str) -> dict[str, str | int]:
    """解析 postgresql://user:pass@host:port/dbname → 连接参数字典（纯函数）"""
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


# ═══════════════════════════════════════════════════════════════
# 编排器
# ═══════════════════════════════════════════════════════════════

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
    finally:
        await conn.close()

    print("Prestart: 迁移完成")


if __name__ == "__main__":
    asyncio.run(run())
