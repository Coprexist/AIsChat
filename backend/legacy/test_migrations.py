"""
迁移幂等测试 — 防"重启就漂移"事故复发（2026-08-07/08 事故）

事故根因：_migrate_group_members_user_id / _migrate_unify_ai_user_id 把
"已是 user_id 的 member_id/sender_id" 误当 agent.id，每次重启把数据改错
（群成员 4→6→9→15 漂移；私信 sender 1→4 漂移）。

测试策略：构造"新旧混合"数据 → 跑迁移两次 → 断言数据完全不变（幂等）。
"""
import pytest

pytestmark = pytest.mark.anyio


async def _setup_fixture_data(db):
    """构造：新旧混合的群成员 + 私信/群消息（含最容易出事的 user_id 撞 agent.id 场景）"""
    from sqlalchemy import text

    # 清空相关表（测试库专用；agents/users 也清，彻底隔离跨测试残留）
    for t in ("dm_messages", "messages", "group_members", "file_metadata", "dm_sessions", "groups", "agents", "users"):
        await db.execute(text(f"TRUNCATE {t} CASCADE"))
    await db.execute(text("""
        INSERT INTO users (id, username, password_hash, type) VALUES
        (1, '测试用户', 'x', 'human'),
        (4, '涵吾珑', 'x', 'ai'),
        (6, '任熠航', 'x', 'ai'),
        (9, 'test', 'x', 'ai'),
        (15, '234', 'x', 'ai')
        ON CONFLICT (id) DO NOTHING
    """))
    await db.execute(text("""
        INSERT INTO agents (id, owner_id, name, user_id, discoverable) VALUES
        (1, 1, '涵吾珑', 4, true),
        (4, 1, '任熠航', 6, true),
        (6, 1, 'test', 9, true),
        (9, 1, '234', 15, true)
        ON CONFLICT (id) DO NOTHING
    """))
    # 群（group_members/messages 的 FK 依赖）
    await db.execute(text("""
        INSERT INTO groups (id, name, owner_type, owner_id, avatar_mode, include_ai_in_avatar) VALUES
        (101, '测试群A', 'human', 1, 'default', true),
        (102, '测试群B', 'human', 1, 'default', true),
        (103, '测试群C', 'human', 1, 'default', true)
    """))
    # 群成员：混合新旧格式
    await db.execute(text("""
        INSERT INTO group_members (group_id, member_type, member_id, role) VALUES
        (101, 'ai', 4, 'member'),   -- 新格式：涵吾珑 user_id（最易误伤）
        (101, 'human', 1, 'owner'),
        (102, 'ai', 9, 'member'),   -- 新格式：test user_id（也是 234 的 agent.id，歧义）
        (102, 'human', 1, 'owner'),
        (103, 'ai', 5, 'member')    -- 旧格式：agent.id=5（假设存在）应被转换（若无 agent 5 则跳过）
    """))
    # 私信：用户1 ↔ 涵吾珑(4)，用户发的消息 sender=1（最易被漂成 4）
    await db.execute(text("""
        INSERT INTO dm_sessions (session_id, user1_id, user2_id) VALUES
        ('1_4', 1, 4)
    """))
    await db.execute(text("""
        INSERT INTO dm_messages (session_id, sender_id, content, message_type) VALUES
        ('1_4', 1, '用户发的消息1', 'normal'),
        ('1_4', 4, '涵吾珑回复1', 'normal'),
        ('1_4', 1, '用户发的消息2', 'normal')
    """))
    # 群消息：涵吾珑发的（sender=4，ai）——不应被漂成 6
    await db.execute(text("""
        INSERT INTO messages (group_id, sender_type, sender_id, content) VALUES
        (101, 'ai', 4, '涵吾珑的群消息'),
        (101, 'human', 1, '用户的群消息')
    """))
    await db.commit()


async def _snapshot(db) -> dict:
    from sqlalchemy import text
    rows = (await db.execute(text(
        "SELECT group_id, member_type, member_id FROM group_members ORDER BY group_id, member_id"
    ))).fetchall()
    dms = (await db.execute(text(
        "SELECT session_id, sender_id, content FROM dm_messages ORDER BY id"
    ))).fetchall()
    msgs = (await db.execute(text(
        "SELECT group_id, sender_type, sender_id FROM messages ORDER BY id"
    ))).fetchall()
    return {
        "members": [tuple(r) for r in rows],
        "dm": [tuple(r) for r in dms],
        "msgs": [tuple(r) for r in msgs],
    }


async def test_group_members_migration_idempotent(migrated_db):
    """_migrate_group_members_user_id 跑两次，数据零变化（防漂移）"""
    from app.database import async_session
    from app.migration import _migrate_group_members_user_id

    async with async_session() as db:
        await _setup_fixture_data(db)
        s0 = await _snapshot(db)
        # 第一次
        await _migrate_group_members_user_id(db)
        await db.commit()
        s1 = await _snapshot(db)
        # 第二次
        await _migrate_group_members_user_id(db)
        await db.commit()
        s2 = await _snapshot(db)

    # 第二次运行绝不能改任何数据（幂等）
    assert s1 == s2, f"迁移第二次仍改了数据！\n第一次后: {s1}\n第二次后: {s2}"
    # 新格式成员（涵吾珑 4、test 9）不能被改动
    members_after = {(m[0], m[1], m[2]) for m in s2["members"]}
    assert (101, "ai", 4) in members_after, "涵吾珑(4)被迁移改掉了！"
    assert (102, "ai", 9) in members_after, "test(9)被迁移改掉了！"


async def test_unify_ai_user_id_migration_idempotent(migrated_db):
    """_migrate_unify_ai_user_id 跑两次，消息归属零变化（防私信漂移）"""
    from app.database import async_session
    from app.migration import _migrate_unify_ai_user_id

    async with async_session() as db:
        await _setup_fixture_data(db)
        s0 = await _snapshot(db)
        await _migrate_unify_ai_user_id(db)
        await db.commit()
        s1 = await _snapshot(db)
        await _migrate_unify_ai_user_id(db)
        await db.commit()
        s2 = await _snapshot(db)

    assert s1 == s2, f"迁移第二次仍改了数据！\n第一次后: {s1}\n第二次后: {s2}"
    # 用户(1)发的私信不能被改成涵吾珑(4)
    dm_after = {d for d in s2["dm"] if d[1] == 1}
    assert len(dm_after) == 2, f"用户发的私信被改掉了！剩 {dm_after}"
    # 涵吾珑(4)的群消息不能被漂成 6
    msg_after = {(m[0], m[1], m[2]) for m in s2["msgs"]}
    assert (101, "ai", 4) in msg_after, "涵吾珑群消息被漂移！"
