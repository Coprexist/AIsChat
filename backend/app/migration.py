"""
数据库迁移脚本（幂等：每次启动自动执行，已迁移则跳过）

v0.2.0 迁移内容（统一用户ID + DM表）：
  1. users 表加 type 列（human/ai）
  2. agents 表加 user_id 列
  3. 为已有 agent 创建 users 条目（username = agent.name + "_agent"）
  4. 新建 dm_sessions / dm_messages 表
  5. 将历史 DM 群聊消息导入 dm_messages

v0.2.0 迁移内容（续 — 闹钟 + 工作区）：
  6. 新建 agent_alarms 表（AI 自主闹钟）
  7. 新建 agent_workspace 表（AI 当前任务追踪 / 中断恢复）
"""
import logging
from sqlalchemy import text, select
from app.database import async_session

logger = logging.getLogger(__name__)


async def run_migrations():
    """执行所有必要的迁移（幂等）"""
    logger.info("🔧 检查并执行数据库迁移...")

    async with async_session() as db:
        try:
            await _migrate_users_type(db)
            await _migrate_unify_ai_user_id(db)       # v1.0.2 全局统一AI ID为user_id
            await _migrate_conversation_logs(db)   # 必须在查询 Agent 之前添加列
            await _migrate_federation_tables(db)   # 必须在查询 Agent 之前添加列
            await _migrate_api_credit(db)          # 新增列必须在查询 Agent 之前
            await _migrate_config_profile(db)      # v0.4.0 三档配置，也要在查询 Agent 之前
            await _migrate_delay_reply_enabled(db) # v0.4.0 延迟回复开关，也要在查询 Agent 之前
            await _migrate_max_tool_rounds(db)     # v0.4.0 工具调用轮次上限
            # ⚠️ 以下三个 v0.4.0 新增列迁移必须在任何 select(Agent) ORM 查询之前
            await _migrate_ai_types(db)               # v0.4.0 三种 AI 类型 + per-user 配置隔离
            await _migrate_memory_user_isolation(db)  # v0.4.0 记忆 per-user 隔离
            await _migrate_willingness_fields(db)     # v0.4.0 意愿评分字段
            await _migrate_reminder_not_count(db)     # v0.4.1 系统提醒不计入轮次
            await _migrate_agents_user_id(db)
            await _migrate_friend_controls(db)         # v0.6.0 好友控制字段（必须在 select(Agent) 之前）
            await _migrate_memory_config_columns(db)   # v0.8.0 文件记忆配置字段（必须在 select(Agent) 之前）
            await _migrate_bio_and_status(db)     # v0.9.0 AI 简介 + 用户/AI 自定义状态（必须在 select(Agent) 之前）
            await _migrate_agent_status_color(db)     # v1.0.2 AI状态颜色（必须在 select(Agent) 之前）
            await _migrate_others_chat_controls(db)  # v0.9.0 对话权限 + 限额控制（必须在 select(Agent) 之前）
            await _migrate_email_verification(db)  # v1.0.0 邮箱认证（必须在 select(Agent) 之前）
            await _migrate_provider_config(db)      # v1.0.0 LLM 厂商预设
            await _migrate_smtp_configs_array(db)      # v1.0.0 多 SMTP 容灾：单对象 → 数组
            await _migrate_email_templates(db)          # v1.0.0 自定义邮件模板列
            await _migrate_auto_dnd_fields(db)         # v1.0.0+ 自动免打扰配置字段
            await _migrate_agent_users(db)            # 此处会 select(Agent) — 需上面列已存在
            await _migrate_create_dm_tables(db)
            await _migrate_dm_messages(db)
            await _migrate_agent_alarms(db)
            await _migrate_workspace(db)
            await _migrate_agent_skills(db)
            await _migrate_archive_friend_tables(db)  # v0.4.0 删除好友机制：归档表
            await _migrate_restore_friend_tables(db)  # v0.4.0+ 恢复好友机制：从 archived 恢复
            await _migrate_file_system(db)             # v0.5.0 文件协作系统
            await _migrate_message_attachments(db)     # v0.5.0 消息附件
            await _migrate_message_sender_name(db)     # v0.6.0 联邦消息发送者名称
            await _migrate_sender_avatar_url(db)       # v0.8.0 联邦消息头像持久化
            await _migrate_prompt_overrides(db)        # v0.8.0 系统提示词覆盖
            await _migrate_memory_archive_columns(db)  # v0.5.0 记忆延迟归档
            await _migrate_agent_metrics(db)           # v0.5.0 系统监控指标
            await _migrate_system_settings(db)          # v0.6.0 全局系统设置 + 新用户初始化向导
            await _migrate_api_key_pool_tables(db)    # v0.6.0 API Key 池 + 用户绑定 + 用量日志；v0.6.0 +concurrent_limit
            await _migrate_platform_credit(db)           # v0.6.0 平台赠送额度
            await _migrate_redemption_code_details(db)  # v0.6.0 兑换码增强
            await _migrate_federation_v1(db)             # v1.0.0 联邦 ID 前缀替代注册表
            await _migrate_agent_collaborators(db)       # v0.7.0 AI 合作者系统
            await _migrate_prompt_order(db)               # v0.7.0 系统提示词顺序可编辑
            await _fix_file_refs_referrer_type(db)      # v0.7.0+ 修复 file_references.referrer_type 缺 human
            await _fix_file_owner_type_check(db)       # v0.5.0+ 修复 file_metadata.owner_type 缺 human
            await _migrate_system_user(db)             # v0.8.0+ 系统通知用户（sender_id 外键需要）
            await _migrate_content_hash(db)          # v0.9.0 文件去重 SHA256 哈希
            await _migrate_forward_ref_type(db)     # v0.9.0 文件转发引用类型
            await _migrate_orphan_retention(db)     # v0.9.0 孤儿文件宽限期配置
            await _migrate_oracle_file_references(db) # v0.10.x: 文件引用表幂等唯一约束
            await _migrate_default_file_quota(db)   # v0.9.0 用户默认文件配额配置
            await _migrate_structured_records(db)  # v0.10.0 结构记忆表（目录级键值存储）
            await _migrate_group_members_user_id(db)  # v2.0.0 AI 群成员统一用 user_id
            await _migrate_group_invitations(db)  # v2.0.0 群邀请卡片系统
            await _migrate_group_owner_membership(db)  # v2.0.1 修复群主缺失的群成员记录
            await _migrate_fix_duplicate_owners(db)     # v2.0.2 修复错误的多群主记录
            await _migrate_fix_human_members_changed_to_ai(db)  # v1.0.2 修被误改为AI的人类成员
            await _migrate_agent_state_stack(db)       # v1.0.1 状态栈（AI 跨任务上下文追踪）
            await _migrate_multi_provider(db)          # v1.0.2 多供应商 + api_key_pool.provider_name
            await _migrate_ai_friend_user_id(db)       # v1.0.2 AI好友friend_id统一为user_id
            await _migrate_opencli_default_enabled(db) # v1.0.2 OpenCLI命令默认可用
            await _migrate_group_muted_until(db)     # v2.0.3 群聊屏蔽（比DND更强，@/公告也不穿透）
            await _migrate_group_concurrent_limit(db) # v2.0.4 群聊AI并发上限
            await _migrate_group_msg_display_len(db)   # v2.0.5 群聊消息折叠长度
            await _fix_column_types(db)  # 必须是最后一个：修复老部署的列类型不匹配
            await db.commit()
            logger.info("✅ 数据库迁移检查完成")
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ 数据库迁移失败: {e}", exc_info=True)
            raise


async def _column_exists(db, table: str, column: str) -> bool:
    """检查列是否存在（幂等判断）"""
    result = await db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
        )
    """), {"table": table, "column": column})
    return result.scalar()


async def _table_exists(db, table: str) -> bool:
    """检查表是否存在（幂等判断）"""
    result = await db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :table
        )
    """), {"table": table})
    return result.scalar()


async def _migrate_users_type(db):
    """users 表加 type 列"""
    if await _column_exists(db, "users", "type"):
        logger.info("  ⏭ users.type 已存在，跳过")
        return
    logger.info("  ➕ 添加 users.type 列")
    await db.execute(text("ALTER TABLE users ADD COLUMN type VARCHAR(10) DEFAULT 'human'"))
    await db.execute(text("UPDATE users SET type = 'human' WHERE type IS NULL"))
    await db.flush()


async def _migrate_agents_user_id(db):
    """agents 表加 user_id 列"""
    if await _column_exists(db, "agents", "user_id"):
        logger.info("  ⏭ agents.user_id 已存在，跳过")
        return
    logger.info("  ➕ 添加 agents.user_id 列")
    await db.execute(text("ALTER TABLE agents ADD COLUMN user_id INT REFERENCES users(id)"))
    await db.flush()


async def _migrate_create_dm_tables(db):
    """创建 dm_sessions / dm_messages 表"""
    if await _table_exists(db, "dm_sessions"):
        logger.info("  ⏭ dm_sessions 表已存在，跳过")
        return
    logger.info("  📦 创建 dm_sessions / dm_messages 表")
    await db.execute(text("""
        CREATE TABLE dm_sessions (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(64) UNIQUE NOT NULL,
            user1_id INT NOT NULL REFERENCES users(id),
            user2_id INT NOT NULL REFERENCES users(id),
            user1_dnd_until TIMESTAMP,
            user2_dnd_until TIMESTAMP,
            last_message_id INT,
            last_message_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user1_id, user2_id)
        )
    """))
    await db.execute(text("""
        CREATE TABLE dm_messages (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(64) NOT NULL REFERENCES dm_sessions(session_id) ON DELETE CASCADE,
            sender_id INT NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            reply_to INT,
            read_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_dm_messages_session ON dm_messages(session_id)
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_dm_messages_created_at ON dm_messages(created_at)
    """))
    await db.flush()


async def _migrate_agent_users(db):
    """为已有 agent 创建 users 条目（幂等：检查 agent.user_id 是否为 NULL）"""
    from app.models.agent import Agent
    from app.models.user import User

    result = await db.execute(
        select(Agent).where(Agent.user_id.is_(None))
    )
    agents = result.scalars().all()

    if not agents:
        logger.info("  ⏭ 所有 agent 已有 users 条目，跳过")
        return

    logger.info(f"  👤 为 {len(agents)} 个 agent 创建 users 条目")
    for agent in agents:
        user = User(
            username=agent.name,
            type="ai",
            password_hash="",
            role="ai",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        agent.user_id = user.id
        logger.info(f"    agent {agent.name}({agent.id}) → user {user.id}")
    await db.flush()


async def _migrate_dm_messages(db):
    """将历史 DM 群聊消息导入 dm_messages（幂等：检查是否已有 dm_messages）"""
    from app.models.dm import DMMessage

    # 如果 dm_messages 表已有数据，跳过
    result = await db.execute(select(DMMessage).limit(1))
    if result.scalar_one_or_none():
        logger.info("  ⏭ dm_messages 已有数据，跳过历史导入")
        return

    # 查找所有 DM: 前缀的群聊
    from app.models.group import Group, GroupMember
    from app.models.message import Message
    from app.models.agent import Agent
    from app.models.user import User

    dm_groups = await db.execute(
        select(Group).where(Group.name.like("DM:%"))
    )
    dm_groups = dm_groups.scalars().all()

    if not dm_groups:
        logger.info("  ⏭ 无历史 DM 群聊，跳过消息导入")
        return

    logger.info(f"  📥 导入 {len(dm_groups)} 个历史 DM 群聊的消息...")
    imported_sessions = 0
    imported_messages = 0

    for group in dm_groups:
        # 获取两个成员
        members_result = await db.execute(
            select(GroupMember).where(GroupMember.group_id == group.id)
        )
        members = members_result.scalars().all()
        if len(members) != 2:
            continue

        # 解析两个成员的 users.id
        user_ids = []
        for m in members:
            if m.member_type == "human":
                user_ids.append(m.member_id)
            elif m.member_type == "ai":
                # 查 agent.user_id
                agent_result = await db.execute(
                    select(Agent.user_id).where(Agent.id == m.member_id)
                )
                agent_user_id = agent_result.scalar_one_or_none()
                if agent_user_id:
                    user_ids.append(agent_user_id)

        if len(user_ids) != 2:
            continue

        user_ids.sort()
        session_id = f"{user_ids[0]}_{user_ids[1]}"

        # 查找或创建 dm_session
        from app.models.dm import DMSession
        existing = await db.execute(
            select(DMSession).where(DMSession.session_id == session_id)
        )
        session = existing.scalar_one_or_none()
        if not session:
            session = DMSession(
                session_id=session_id,
                user1_id=user_ids[0],
                user2_id=user_ids[1],
            )
            db.add(session)
            await db.flush()
            imported_sessions += 1

        # 导入消息
        msgs_result = await db.execute(
            select(Message)
            .where(Message.group_id == group.id)
            .order_by(Message.created_at.asc())
        )
        group_messages = msgs_result.scalars().all()

        for msg in group_messages:
            # 确定 sender users.id
            if msg.sender_type == "human":
                sender_user_id = msg.sender_id
            elif msg.sender_type == "ai":
                agent_result = await db.execute(
                    select(Agent.user_id).where(Agent.id == msg.sender_id)
                )
                sender_user_id = agent_result.scalar_one_or_none()
                if not sender_user_id:
                    continue
            elif msg.sender_type == "system":
                # 系统消息跳过
                continue
            else:
                continue

            dm_msg = DMMessage(
                session_id=session_id,
                sender_id=sender_user_id,
                content=msg.content,
                created_at=msg.created_at,  # 保留原始时间
            )
            db.add(dm_msg)
            imported_messages += 1

    await db.flush()
    logger.info(f"  ✅ 导入完成: {imported_sessions} 个会话, {imported_messages} 条消息")


async def _migrate_agent_alarms(db):
    """创建 agent_alarms 表（v0.2.0）"""
    if await _table_exists(db, "agent_alarms"):
        logger.info("  ⏭ agent_alarms 表已存在，跳过")
        return
    logger.info("  ⏰ 创建 agent_alarms 表")
    await db.execute(text("""
        CREATE TABLE agent_alarms (
            id SERIAL PRIMARY KEY,
            agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            wake_at TIMESTAMPTZ NOT NULL,
            task TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'fired', 'cancelled')),
            created_at TIMESTAMP DEFAULT NOW(),
            fired_at TIMESTAMPTZ
        )
    """))
    await db.flush()
    logger.info("  ✅ agent_alarms 表创建完成")


async def _migrate_workspace(db):
    """创建/扩展 agent_workspace 表（v0.2.0 创建，v0.4.0 扩展 TODO/PLAN/JOURNAL）"""
    if not await _table_exists(db, "agent_workspace"):
        logger.info("  📋 创建 agent_workspace 表")
        await db.execute(text("""
            CREATE TABLE agent_workspace (
                agent_id INT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
                current_task TEXT,
                current_task_at TIMESTAMP,
                interrupted_at TIMESTAMP,
                interruption_reason TEXT,
                todo TEXT DEFAULT '',
                plan TEXT DEFAULT '',
                journal TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await db.flush()
        logger.info("  ✅ agent_workspace 表创建完成")
    else:
        logger.info("  ⏭ agent_workspace 表已存在，检查新列...")
        cols_added = False
        if not await _column_exists(db, "agent_workspace", "todo"):
            await db.execute(text("ALTER TABLE agent_workspace ADD COLUMN todo TEXT DEFAULT ''"))
            cols_added = True
            logger.info("  📝 添加 agent_workspace.todo 列")
        if not await _column_exists(db, "agent_workspace", "plan"):
            await db.execute(text("ALTER TABLE agent_workspace ADD COLUMN plan TEXT DEFAULT ''"))
            cols_added = True
            logger.info("  📝 添加 agent_workspace.plan 列")
        if not await _column_exists(db, "agent_workspace", "journal"):
            await db.execute(text("ALTER TABLE agent_workspace ADD COLUMN journal TEXT DEFAULT ''"))
            cols_added = True
            logger.info("  📝 添加 agent_workspace.journal 列")
        if cols_added:
            await db.flush()
            logger.info("  ✅ agent_workspace 扩展完成")
        else:
            logger.info("  ⏭ agent_workspace 新列均已存在，跳过")


async def _migrate_agent_skills(db):
    """创建 agent_skills 表（v0.2.0 Skill 系统）"""
    if await _table_exists(db, "agent_skills"):
        logger.info("  ⏭ agent_skills 表已存在，跳过")
        return
    logger.info("  🧠 创建 agent_skills 表")
    await db.execute(text("""
        CREATE TABLE agent_skills (
            id SERIAL PRIMARY KEY,
            agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            skill_type VARCHAR(30) NOT NULL,
            is_enabled BOOLEAN DEFAULT TRUE,
            config JSONB NOT NULL DEFAULT '{}',
            priority INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT ck_agent_skills_type CHECK (
                skill_type IN ('delay_reply', 'typing_indicator', 'scene_trigger', 'inject_prompt')
            )
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_agent_skills_agent ON agent_skills(agent_id)
    """))
    await db.flush()
    logger.info("  ✅ agent_skills 表创建完成")


async def _migrate_federation_tables(db):
    """创建联邦通信相关表（v0.3.0 跨实例联邦通信）"""
    created_any = False

    # 1. instance_config 表（单例，存本实例身份）
    if not await _table_exists(db, "instance_config"):
        logger.info("  🌐 创建 instance_config 表")
        await db.execute(text("""
            CREATE TABLE instance_config (
                id INT PRIMARY KEY DEFAULT 1,
                instance_id VARCHAR(36) UNIQUE NOT NULL,
                public_id VARCHAR(50) UNIQUE,
                display_name VARCHAR(100) DEFAULT '',
                public_url VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        created_any = True
    else:
        logger.info("  ⏭ instance_config 表已存在，跳过")

    # 2. federation_peers 表
    if not await _table_exists(db, "federation_peers"):
        logger.info("  🌐 创建 federation_peers 表")
        await db.execute(text("""
            CREATE TABLE federation_peers (
                id SERIAL PRIMARY KEY,
                peer_public_id VARCHAR(50) NOT NULL,
                display_name VARCHAR(100) DEFAULT '',
                remote_url VARCHAR(500) NOT NULL,
                shared_secret_encrypted TEXT NOT NULL,
                is_enabled BOOLEAN DEFAULT TRUE,
                connection_state VARCHAR(20) DEFAULT 'disconnected'
                    CHECK (connection_state IN ('connecting', 'connected', 'disconnected', 'failed')),
                last_connected_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        created_any = True
    else:
        logger.info("  ⏭ federation_peers 表已存在，跳过")

    # 3. federation_group_shares 表
    if not await _table_exists(db, "federation_group_shares"):
        logger.info("  🌐 创建 federation_group_shares 表")
        await db.execute(text("""
            CREATE TABLE federation_group_shares (
                id SERIAL PRIMARY KEY,
                group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                peer_id INT NOT NULL REFERENCES federation_peers(id) ON DELETE CASCADE,
                is_enabled BOOLEAN DEFAULT TRUE,
                remote_group_id INT,
                share_direction VARCHAR(20) DEFAULT 'bidirectional'
                    CHECK (share_direction IN ('outgoing', 'incoming', 'bidirectional')),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(group_id, peer_id)
            )
        """))
        created_any = True
    else:
        logger.info("  ⏭ federation_group_shares 表已存在，跳过")

    # 4. groups.is_federated 反范式化列
    if not await _column_exists(db, "groups", "is_federated"):
        logger.info("  🌐 添加 groups.is_federated 列")
        await db.execute(text(
            "ALTER TABLE groups ADD COLUMN is_federated BOOLEAN DEFAULT FALSE"
        ))
        created_any = True
    else:
        logger.info("  ⏭ groups.is_federated 已存在，跳过")

    # 5. messages.source_public_id 远程消息来源标记
    if not await _column_exists(db, "messages", "source_public_id"):
        logger.info("  🌐 添加 messages.source_public_id 列")
        await db.execute(text(
            "ALTER TABLE messages ADD COLUMN source_public_id VARCHAR(50)"
        ))
        created_any = True
    else:
        logger.info("  ⏭ messages.source_public_id 已存在，跳过")

    # 6. instance_config.github_token_encrypted GitHub Token（前端图形化配置）
    if not await _column_exists(db, "instance_config", "github_token_encrypted"):
        logger.info("  🌐 添加 instance_config.github_token_encrypted 列")
        await db.execute(text(
            "ALTER TABLE instance_config ADD COLUMN github_token_encrypted TEXT"
        ))
        created_any = True
    else:
        logger.info("  ⏭ instance_config.github_token_encrypted 已存在，跳过")

    # 7. federation_peers.url_rotation 动态 URL 轮换（v0.3.0）
    if not await _column_exists(db, "federation_peers", "remote_url_backup"):
        logger.info("  🌐 添加 federation_peers.remote_url_backup 列")
        await db.execute(text(
            "ALTER TABLE federation_peers ADD COLUMN remote_url_backup VARCHAR(500)"
        ))
        created_any = True
    else:
        logger.info("  ⏭ federation_peers.remote_url_backup 已存在，跳过")

    if not await _column_exists(db, "federation_peers", "url_rotated_at"):
        logger.info("  🌐 添加 federation_peers.url_rotated_at 列")
        await db.execute(text(
            "ALTER TABLE federation_peers ADD COLUMN url_rotated_at TIMESTAMP"
        ))
        created_any = True
    else:
        logger.info("  ⏭ federation_peers.url_rotated_at 已存在，跳过")

    if not await _column_exists(db, "federation_peers", "url_rotation_count"):
        logger.info("  🌐 添加 federation_peers.url_rotation_count 列")
        await db.execute(text(
            "ALTER TABLE federation_peers ADD COLUMN url_rotation_count INTEGER NOT NULL DEFAULT 0"
        ))
        created_any = True
    else:
        logger.info("  ⏭ federation_peers.url_rotation_count 已存在，跳过")

    # 8. federation_group_shares.conversation_uuid（v0.6.0 联邦对话 UUID 映射）
    if not await _column_exists(db, "federation_group_shares", "conversation_uuid"):
        logger.info("  🌐 添加 federation_group_shares.conversation_uuid 列")
        await db.execute(text(
            "ALTER TABLE federation_group_shares ADD COLUMN conversation_uuid VARCHAR(64)"
        ))
        # Populate existing rows with generated UUIDs
        await db.execute(text(
            "UPDATE federation_group_shares SET conversation_uuid = 'conv_' || gen_random_uuid()::text "
            "WHERE conversation_uuid IS NULL"
        ))
        await db.execute(text(
            "ALTER TABLE federation_group_shares ALTER COLUMN conversation_uuid SET NOT NULL"
        ))
        await db.execute(text(
            "ALTER TABLE federation_group_shares ADD CONSTRAINT uq_peer_conv_uuid UNIQUE(peer_id, conversation_uuid)"
        ))
        created_any = True
    else:
        logger.info("  ⏭ federation_group_shares.conversation_uuid 已存在，跳过")

    # 9. federation_dm_shares 表
    if not await _table_exists(db, "federation_dm_shares"):
        logger.info("  🌐 创建 federation_dm_shares 表")
        await db.execute(text("""
            CREATE TABLE federation_dm_shares (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(64) NOT NULL REFERENCES dm_sessions(session_id) ON DELETE CASCADE,
                peer_id INT NOT NULL REFERENCES federation_peers(id) ON DELETE CASCADE,
                is_enabled BOOLEAN DEFAULT TRUE,
                conversation_uuid VARCHAR(64) NOT NULL,
                share_direction VARCHAR(20) DEFAULT 'bidirectional'
                    CHECK (share_direction IN ('outgoing', 'incoming', 'bidirectional')),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(session_id, peer_id),
                UNIQUE(peer_id, conversation_uuid)
            )
        """))
        created_any = True
    else:
        logger.info("  ⏭ federation_dm_shares 表已存在，跳过")

    # 10. dm_messages.source_public_id
    if not await _column_exists(db, "dm_messages", "source_public_id"):
        logger.info("  🌐 添加 dm_messages.source_public_id 列")
        await db.execute(text(
            "ALTER TABLE dm_messages ADD COLUMN source_public_id VARCHAR(50)"
        ))
        created_any = True
    else:
        logger.info("  ⏭ dm_messages.source_public_id 已存在，跳过")

    # 11. agents.discoverable
    if not await _column_exists(db, "agents", "discoverable"):
        logger.info("  🌐 添加 agents.discoverable 列")
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN discoverable BOOLEAN NOT NULL DEFAULT TRUE"
        ))
        created_any = True
    else:
        logger.info("  ⏭ agents.discoverable 已存在，跳过")

    if created_any:
        await db.flush()


async def _migrate_conversation_logs(db):
    """对话日志系统表/列（幂等）"""
    created_any = False

    # 1. 配置表
    if not await _table_exists(db, "conversation_log_config"):
        logger.info("  ➕ 创建 conversation_log_config 表")
        await db.execute(text("""
            CREATE TABLE conversation_log_config (
                id INTEGER PRIMARY KEY DEFAULT 1,
                max_conversation_logs INTEGER DEFAULT 30,
                default_user_conversation_logs INTEGER DEFAULT 20,
                default_user_log_access BOOLEAN DEFAULT FALSE,
                updated_by INTEGER REFERENCES users(id),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            INSERT INTO conversation_log_config (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING
        """))
        created_any = True
    else:
        logger.info("  ⏭ conversation_log_config 表已存在，跳过")

    # 2. 日志表
    if not await _table_exists(db, "ai_conversation_logs"):
        logger.info("  ➕ 创建 ai_conversation_logs 表")
        await db.execute(text("""
            CREATE TABLE ai_conversation_logs (
                id SERIAL PRIMARY KEY,
                agent_id INTEGER NOT NULL REFERENCES agents(id),
                group_id INTEGER REFERENCES groups(id),
                session_id VARCHAR(50),
                conversation_type VARCHAR(10) NOT NULL DEFAULT 'group',
                messages JSONB NOT NULL,
                message_count INTEGER DEFAULT 0,
                token_usage JSONB,
                has_output BOOLEAN DEFAULT FALSE,
                model VARCHAR(50),
                thinking_enabled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_conv_logs_agent ON ai_conversation_logs(agent_id)"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_conv_logs_time ON ai_conversation_logs(created_at)"))
        created_any = True
    else:
        logger.info("  ⏭ ai_conversation_logs 表已存在，跳过")

    # 3. agents 表新列
    if not await _column_exists(db, "agents", "conversation_logs_limit"):
        logger.info("  ➕ 添加 agents.conversation_logs_limit 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN conversation_logs_limit INTEGER"))
        created_any = True
    else:
        logger.info("  ⏭ agents.conversation_logs_limit 已存在，跳过")

    if not await _column_exists(db, "agents", "user_can_view_logs"):
        logger.info("  ➕ 添加 agents.user_can_view_logs 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN user_can_view_logs BOOLEAN"))
        created_any = True
    else:
        logger.info("  ⏭ agents.user_can_view_logs 已存在，跳过")

    # 4. users 表新列
    if not await _column_exists(db, "users", "conversation_logs_limit"):
        logger.info("  ➕ 添加 users.conversation_logs_limit 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN conversation_logs_limit INTEGER"))
        created_any = True
    else:
        logger.info("  ⏭ users.conversation_logs_limit 已存在，跳过")

    if created_any:
        await db.flush()
        logger.info("  ✅ 对话日志系统迁移完成")
    else:
        logger.info("  ⏭ 对话日志系统均已存在，跳过")


async def _migrate_auto_dnd_fields(db):
    """v1.0.0+: 自动免打扰配置字段 — auto_dnd_threshold, auto_dnd_duration（幂等）"""
    created_any = False

    if not await _column_exists(db, "agents", "auto_dnd_threshold"):
        logger.info("  ➕ 添加 agents.auto_dnd_threshold 列")
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN auto_dnd_threshold INTEGER DEFAULT 20"
        ))
        created_any = True
    else:
        logger.info("  ⏭ agents.auto_dnd_threshold 已存在，跳过")

    if not await _column_exists(db, "agents", "auto_dnd_duration"):
        logger.info("  ➕ 添加 agents.auto_dnd_duration 列")
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN auto_dnd_duration INTEGER DEFAULT 5"
        ))
        created_any = True
    else:
        logger.info("  ⏭ agents.auto_dnd_duration 已存在，跳过")

    if created_any:
        await db.flush()
        logger.info("  ✅ 自动免打扰字段迁移完成")
    else:
        logger.info("  ⏭ 自动免打扰字段均已存在，跳过")


async def _migrate_api_credit(db):
    """v0.4.0 API 额度系统 + 单 AI API 覆盖 + AI 不自知 + 语言/界面设置（幂等）"""
    created_any = False

    if not await _column_exists(db, "users", "api_credit"):
        logger.info("  💰 添加 users.api_credit 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN api_credit INTEGER NOT NULL DEFAULT 0"))
        created_any = True
    else:
        logger.info("  ⏭ users.api_credit 已存在，跳过")

    if not await _column_exists(db, "users", "language"):
        logger.info("  🌐 添加 users.language 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR(10) DEFAULT 'zh'"))
        created_any = True
    else:
        logger.info("  ⏭ users.language 已存在，跳过")

    if not await _column_exists(db, "users", "ui_prefs"):
        logger.info("  🎨 添加 users.ui_prefs 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN ui_prefs JSONB DEFAULT '{}'"))
        created_any = True
    else:
        logger.info("  ⏭ users.ui_prefs 已存在，跳过")

    if not await _column_exists(db, "agents", "api_credit_cost"):
        logger.info("  💰 添加 agents.api_credit_cost 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN api_credit_cost INTEGER NOT NULL DEFAULT 0"))
        created_any = True
    else:
        logger.info("  ⏭ agents.api_credit_cost 已存在，跳过")

    if not await _column_exists(db, "agents", "api_base_url"):
        logger.info("  🔗 添加 agents.api_base_url 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN api_base_url TEXT"))
        created_any = True
    else:
        logger.info("  ⏭ agents.api_base_url 已存在，跳过")

    if not await _column_exists(db, "agents", "api_key_encrypted"):
        logger.info("  🔑 添加 agents.api_key_encrypted 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN api_key_encrypted TEXT"))
        created_any = True
    else:
        logger.info("  ⏭ agents.api_key_encrypted 已存在，跳过")

    if not await _column_exists(db, "agents", "hide_ai_identity"):
        logger.info("  🎭 添加 agents.hide_ai_identity 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN hide_ai_identity BOOLEAN NOT NULL DEFAULT FALSE"))
        created_any = True
    else:
        logger.info("  ⏭ agents.hide_ai_identity 已存在，跳过")

    if not await _column_exists(db, "agents", "avatar_url"):
        logger.info("  🖼️ 添加 agents.avatar_url 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN avatar_url TEXT"))
        created_any = True
    else:
        logger.info("  ⏭ agents.avatar_url 已存在，跳过")

    if not await _column_exists(db, "agents", "api_token"):
        logger.info("  🪙 添加 agents.api_token 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN api_token VARCHAR(64)"))
        created_any = True
    else:
        logger.info("  ⏭ agents.api_token 已存在，跳过")

    if not await _column_exists(db, "redemption_codes", "code_type"):
        logger.info("  🏷️ 添加 redemption_codes.code_type 列")
        await db.execute(text(
            "ALTER TABLE redemption_codes ADD COLUMN code_type VARCHAR(10) NOT NULL DEFAULT 'ai_quota'"
        ))
        created_any = True
    else:
        logger.info("  ⏭ redemption_codes.code_type 已存在，跳过")

    # v0.5.0 新增：AI 包断额度 + 文件配额
    if not await _column_exists(db, "users", "agent_bundle_credit"):
        logger.info("  📦 添加 users.agent_bundle_credit 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN agent_bundle_credit INTEGER NOT NULL DEFAULT 0"))
        created_any = True
    else:
        logger.info("  ⏭ users.agent_bundle_credit 已存在，跳过")

    if not await _column_exists(db, "users", "file_quota_mb"):
        logger.info("  💾 添加 users.file_quota_mb 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN file_quota_mb INTEGER NOT NULL DEFAULT 100"))
        created_any = True
    else:
        logger.info("  ⏭ users.file_quota_mb 已存在，跳过")

    if not await _column_exists(db, "users", "avatar_url"):
        logger.info("  🖼 添加 users.avatar_url 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN avatar_url TEXT"))
        created_any = True
    else:
        logger.info("  ⏭ users.avatar_url 已存在，跳过")

    if not await _column_exists(db, "users", "bio"):
        logger.info("  📝 添加 users.bio 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN bio TEXT"))
        created_any = True
    else:
        logger.info("  ⏭ users.bio 已存在，跳过")

    # 修复已有 AI 用户名：去掉 _agent 后缀
    try:
        logger.info("  🔧 移除已有 AI 用户名的 _agent 后缀")
        result = await db.execute(text(
            "UPDATE users SET username = REPLACE(username, '_agent', '') WHERE type = 'ai' AND username LIKE '%\\_agent'"
        ))
        logger.info(f"  ✅ 已更新 {result.rowcount} 个 AI 用户名")
    except Exception as e:
        logger.info(f"  ⚠ 用户名迁移跳过: {e}")

    # 更新兑换码 CHECK 约束：支持 4 种类型
    # 先迁移旧 file_size → file_quota，再改约束
    try:
        logger.info("  🔄 迁移 redemption_codes.code_type: file_size → file_quota")
        result = await db.execute(text(
            "UPDATE redemption_codes SET code_type = 'file_quota' WHERE code_type = 'file_size'"
        ))
        logger.info(f"  ✅ 已更新 {result.rowcount} 条 file_size → file_quota")
    except Exception as e:
        logger.warning(f"  ⚠️ file_size 迁移跳过: {e}")

    try:
        logger.info("  🔄 更新 redemption_codes.code_type CHECK 约束")
        await db.execute(text(
            "ALTER TABLE redemption_codes DROP CONSTRAINT IF EXISTS ck_redemption_code_type"
        ))
        await db.execute(text("""
            ALTER TABLE redemption_codes ADD CONSTRAINT ck_redemption_code_type
            CHECK (code_type IN ('ai_quota', 'api_credit', 'agent_bundle', 'file_quota'))
        """))
        await db.execute(text("ALTER TABLE redemption_codes ALTER COLUMN code_type TYPE VARCHAR(20)"))
        created_any = True
    except Exception as e:
        logger.warning(f"  ⚠️ 兑换码 CHECK 约束更新跳过: {e}")

    if created_any:
        await db.flush()
        logger.info("  ✅ API 额度/配置系统迁移完成")
    else:
        logger.info("  ⏭ API 额度/配置系统均已存在，跳过")


async def _migrate_config_profile(db):
    """v0.4.0 三档 AI 配置（幂等）"""
    if await _column_exists(db, "agents", "config_profile"):
        logger.info("  ⏭ agents.config_profile 已存在，跳过")
        return
    logger.info("  🎚️ 添加 agents.config_profile 列")
    await db.execute(text(
        "ALTER TABLE agents ADD COLUMN config_profile VARCHAR(20) NOT NULL DEFAULT 'custom'"
    ))
    await db.flush()
    logger.info("  ✅ config_profile 迁移完成")


async def _migrate_delay_reply_enabled(db):
    """v0.4.0 延迟回复开关（幂等）"""
    # 1. agents.delay_reply_enabled
    if not await _column_exists(db, "agents", "delay_reply_enabled"):
        logger.info("  ⏱️ 添加 agents.delay_reply_enabled 列")
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN delay_reply_enabled BOOLEAN DEFAULT NULL"
        ))
        await db.flush()
        logger.info("  ✅ agents.delay_reply_enabled 迁移完成")
    else:
        logger.info("  ⏭ agents.delay_reply_enabled 已存在，跳过")

    # 2. conversation_log_config.default_delay_reply_enabled
    if not await _column_exists(db, "conversation_log_config", "default_delay_reply_enabled"):
        logger.info("  ⏱️ 添加 conversation_log_config.default_delay_reply_enabled 列")
        await db.execute(text(
            "ALTER TABLE conversation_log_config ADD COLUMN default_delay_reply_enabled BOOLEAN NOT NULL DEFAULT false"
        ))
        await db.flush()
        logger.info("  ✅ default_delay_reply_enabled 迁移完成")
    else:
        logger.info("  ⏭ conversation_log_config.default_delay_reply_enabled 已存在，跳过")


async def _migrate_max_tool_rounds(db):
    """v0.4.0 工具调用轮次上限（幂等）"""
    if not await _column_exists(db, "agents", "max_tool_rounds"):
        logger.info("  🔧 添加 agents.max_tool_rounds 列 (DEFAULT 3)")
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN max_tool_rounds INTEGER NOT NULL DEFAULT 3"
        ))
        await db.flush()
        logger.info("  ✅ agents.max_tool_rounds 迁移完成")
    else:
        logger.info("  ⏭ agents.max_tool_rounds 已存在，跳过")

    if not await _column_exists(db, "agents", "alarm_max_tool_rounds"):
        logger.info("  🔧 添加 agents.alarm_max_tool_rounds 列 (DEFAULT 10)")
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN alarm_max_tool_rounds INTEGER NOT NULL DEFAULT 10"
        ))
        await db.flush()
        logger.info("  ✅ agents.alarm_max_tool_rounds 迁移完成")
    else:
        logger.info("  ⏭ agents.alarm_max_tool_rounds 已存在，跳过")

    if not await _column_exists(db, "agents", "force_alarm_on_end"):
        logger.info("  🔧 添加 agents.force_alarm_on_end 列 (DEFAULT false)")
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN force_alarm_on_end BOOLEAN NOT NULL DEFAULT false"
        ))
        await db.flush()
        logger.info("  ✅ agents.force_alarm_on_end 迁移完成")
    else:
        logger.info("  ⏭ agents.force_alarm_on_end 已存在，跳过")

    if not await _column_exists(db, "agents", "max_alarms"):
        logger.info("  🔧 添加 agents.max_alarms 列 (DEFAULT 10)")
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN max_alarms INTEGER NOT NULL DEFAULT 10"
        ))
        await db.flush()
        logger.info("  ✅ agents.max_alarms 迁移完成")
    else:
        logger.info("  ⏭ agents.max_alarms 已存在，跳过")


async def _migrate_reminder_not_count(db):
    """v0.4.1: 系统提醒额外轮次模式 (every_time/once/off, 默认 every_time)"""
    if not await _column_exists(db, "agents", "reminder_grace"):
        # 如果旧列存在，先按旧列值转换
        if await _column_exists(db, "agents", "reminder_not_count"):
            logger.info("  🔧 迁移 agents.reminder_not_count → reminder_grace")
            await db.execute(text(
                "ALTER TABLE agents ADD COLUMN reminder_grace VARCHAR(10) NOT NULL DEFAULT 'every_time'"
            ))
            await db.execute(text(
                "UPDATE agents SET reminder_grace = CASE WHEN reminder_not_count THEN 'every_time' ELSE 'off' END"
            ))
            logger.info("  ✅ agents.reminder_grace 迁移完成（从旧列转换）")
        else:
            logger.info("  🔧 添加 agents.reminder_grace 列 (DEFAULT 'every_time')")
            await db.execute(text(
                "ALTER TABLE agents ADD COLUMN reminder_grace VARCHAR(10) NOT NULL DEFAULT 'every_time'"
            ))
            logger.info("  ✅ agents.reminder_grace 迁移完成")
    else:
        logger.info("  ⏭ agents.reminder_grace 已存在，跳过")

    # 清理旧列 reminder_not_count（已被 reminder_grace 取代，模型不再引用）
    if await _column_exists(db, "agents", "reminder_not_count"):
        logger.info("  🧹 清理废弃列 agents.reminder_not_count")
        await db.execute(text("ALTER TABLE agents DROP COLUMN reminder_not_count"))
        logger.info("  ✅ agents.reminder_not_count 已删除")


async def _migrate_archive_friend_tables(db):
    """v0.4.0: 归档好友表（已废弃 — 好友机制已恢复，此迁移不再执行）"""
    logger.info("  ⏭ 好友机制已恢复，跳过归档迁移")
    return


async def _migrate_restore_friend_tables(db):
    """v0.4.0+: 恢复好友表（好友机制回滚 — 从 archived 恢复）"""
    if not await _table_exists(db, "friendships_archived"):
        logger.info("  ⏭ friendships_archived 不存在，无需恢复")
        return
    # 如果 friendships 已存在且有数据，说明已恢复过，跳过
    if await _table_exists(db, "friendships"):
        result = await db.execute(text("SELECT COUNT(*) FROM friendships"))
        if result.scalar() > 0:
            logger.info("  ⏭ friendships 已有数据，跳过恢复")
            return
    logger.info("  🔄 恢复好友相关表...")
    try:
        # 先删掉可能被 ORM 自动创建的空表
        if await _table_exists(db, "friendships"):
            await db.execute(text("DROP TABLE IF EXISTS friendships CASCADE"))
        if await _table_exists(db, "friendship_requests"):
            await db.execute(text("DROP TABLE IF EXISTS friendship_requests CASCADE"))
        # 归档表改回原名
        await db.execute(text("ALTER TABLE friendships_archived RENAME TO friendships"))
        logger.info("  ✅ friendships_archived → friendships")
        await db.execute(text("ALTER TABLE friendship_requests_archived RENAME TO friendship_requests"))
        logger.info("  ✅ friendship_requests_archived → friendship_requests")
        await db.flush()
    except Exception as e:
        logger.warning(f"  ⚠️ 恢复好友表失败: {e}")
        await db.rollback()


async def _migrate_ai_types(db):
    """v0.4.0: 三种 AI 类型 + agent_user_configs 表"""
    logger.info("  🔧 迁移 AI 类型系统...")

    # 1. 添加 agents.ai_type 列
    if not await _column_exists(db, "agents", "ai_type"):
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN ai_type VARCHAR(20) NOT NULL DEFAULT 'resonance'"
        ))
        await db.flush()
        logger.info("  ✅ agents.ai_type 迁移完成")
    else:
        logger.info("  ⏭ agents.ai_type 已存在，跳过")

    # 2. 创建 agent_user_configs 表
    if not await _table_exists(db, "agent_user_configs"):
        await db.execute(text("""
            CREATE TABLE agent_user_configs (
                id SERIAL PRIMARY KEY,
                agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                temperature DOUBLE PRECISION,
                top_p DOUBLE PRECISION,
                presence_penalty DOUBLE PRECISION,
                frequency_penalty DOUBLE PRECISION,
                thinking_enabled BOOLEAN,
                hide_ai_identity BOOLEAN,
                system_prompt_override TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                CONSTRAINT uq_agent_user_config UNIQUE (agent_id, user_id)
            )
        """))
        await db.flush()
        logger.info("  ✅ agent_user_configs 表创建完成")
    else:
        logger.info("  ⏭ agent_user_configs 已存在，跳过")


async def _migrate_memory_user_isolation(db):
    """v0.4.0: 记忆 per-user 隔离 — rough_memories 加 user_id / scope 扩展"""
    logger.info("  🔧 迁移记忆隔离字段...")

    if not await _column_exists(db, "rough_memories", "user_id"):
        await db.execute(text(
            "ALTER TABLE rough_memories ADD COLUMN user_id INTEGER REFERENCES users(id)"
        ))
        await db.flush()
        logger.info("  ✅ rough_memories.user_id 迁移完成")
    else:
        logger.info("  ⏭ rough_memories.user_id 已存在，跳过")


async def _migrate_willingness_fields(db):
    """v0.4.0: 意愿评分字段 — agents 表加 last_willingness_score / last_willingness_reason"""
    logger.info("  🔧 迁移意愿评分字段...")

    if not await _column_exists(db, "agents", "last_willingness_score"):
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN last_willingness_score INTEGER"
        ))
        await db.flush()
        logger.info("  ✅ agents.last_willingness_score 迁移完成")
    else:
        logger.info("  ⏭ agents.last_willingness_score 已存在，跳过")

    if not await _column_exists(db, "agents", "last_willingness_reason"):
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN last_willingness_reason TEXT"
        ))
        await db.flush()
        logger.info("  ✅ agents.last_willingness_reason 迁移完成")
    else:
        logger.info("  ⏭ agents.last_willingness_reason 已存在，跳过")


async def _migrate_file_system(db):
    """v0.5.0: 文件协作系统 — file_metadata 扩展 + file_references + file_collaborators"""
    logger.info("  🔧 迁移文件协作系统...")

    # file_metadata.collaboration_mode
    if not await _column_exists(db, "file_metadata", "collaboration_mode"):
        await db.execute(text(
            "ALTER TABLE file_metadata ADD COLUMN collaboration_mode VARCHAR(10) "
            "DEFAULT 'solo' NOT NULL CHECK (collaboration_mode IN ('solo', 'shared', 'open'))"
        ))
        await db.flush()
        logger.info("  ✅ file_metadata.collaboration_mode 迁移完成")
    else:
        logger.info("  ⏭ file_metadata.collaboration_mode 已存在，跳过")

    # file_metadata.updated_at
    if not await _column_exists(db, "file_metadata", "updated_at"):
        await db.execute(text(
            "ALTER TABLE file_metadata ADD COLUMN updated_at TIMESTAMP DEFAULT NOW()"
        ))
        await db.flush()
        logger.info("  ✅ file_metadata.updated_at 迁移完成")
    else:
        logger.info("  ⏭ file_metadata.updated_at 已存在，跳过")

    # file_references 表
    if not await _table_exists(db, "file_references"):
        await db.execute(text("""
            CREATE TABLE file_references (
                id SERIAL PRIMARY KEY,
                file_id INT NOT NULL REFERENCES file_metadata(id) ON DELETE CASCADE,
                referrer_type VARCHAR(10) NOT NULL CHECK (referrer_type IN ('ai', 'message', 'group')),
                referrer_id INT NOT NULL,
                ref_type VARCHAR(20) DEFAULT 'read' CHECK (ref_type IN ('read', 'write', 'import', 'share')),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_file_refs_file ON file_references(file_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_file_refs_ref ON file_references(referrer_type, referrer_id)"
        ))
        await db.flush()
        logger.info("  ✅ file_references 表创建完成")
    else:
        logger.info("  ⏭ file_references 已存在，跳过")

    # file_collaborators 表
    if not await _table_exists(db, "file_collaborators"):
        await db.execute(text("""
            CREATE TABLE file_collaborators (
                id SERIAL PRIMARY KEY,
                file_id INT NOT NULL REFERENCES file_metadata(id) ON DELETE CASCADE,
                collaborator_type VARCHAR(10) NOT NULL CHECK (collaborator_type IN ('ai', 'user')),
                collaborator_id INT NOT NULL,
                role VARCHAR(20) DEFAULT 'collaborator' CHECK (role IN ('collaborator', 'viewer')),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(file_id, collaborator_type, collaborator_id)
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_file_collabs_file ON file_collaborators(file_id)"
        ))
        await db.flush()
        logger.info("  ✅ file_collaborators 表创建完成")
    else:
        logger.info("  ⏭ file_collaborators 已存在，跳过")

    # file_metadata 所有者索引
    await db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_file_metadata_owner ON file_metadata(owner_type, owner_id)"
    ))
    await db.flush()


async def _migrate_message_attachments(db):
    """v0.5.0: 消息附件 — messages 表加 attachments JSONB + dm_messages 加 attachments TEXT"""
    logger.info("  🔧 迁移消息附件...")

    if not await _column_exists(db, "messages", "attachments"):
        await db.execute(text(
            "ALTER TABLE messages ADD COLUMN attachments JSONB"
        ))
        await db.flush()
        logger.info("  ✅ messages.attachments 迁移完成")
    else:
        logger.info("  ⏭ messages.attachments 已存在，跳过")

    if not await _column_exists(db, "dm_messages", "attachments"):
        await db.execute(text(
            "ALTER TABLE dm_messages ADD COLUMN attachments TEXT"
        ))
        await db.flush()
        logger.info("  ✅ dm_messages.attachments 迁移完成")
    else:
        logger.info("  ⏭ dm_messages.attachments 已存在，跳过")


async def _migrate_message_sender_name(db):
    """v0.6.0: 联邦消息发送者名称 — messages 表加 sender_name VARCHAR(100)"""
    logger.info("  👤 添加 messages.sender_name 列（联邦消息发送者名称）...")

    if not await _column_exists(db, "messages", "sender_name"):
        await db.execute(text(
            "ALTER TABLE messages ADD COLUMN sender_name VARCHAR(100)"
        ))
        await db.flush()
        logger.info("  ✅ messages.sender_name 迁移完成")
    else:
        logger.info("  ⏭ messages.sender_name 已存在，跳过")


async def _migrate_sender_avatar_url(db):
    """v0.8.0: 联邦消息头像持久化 — messages 表加 sender_avatar_url TEXT"""
    logger.info("  🖼️ 添加 messages.sender_avatar_url 列（联邦消息头像持久化）...")

    if not await _column_exists(db, "messages", "sender_avatar_url"):
        await db.execute(text(
            "ALTER TABLE messages ADD COLUMN sender_avatar_url TEXT DEFAULT ''"
        ))
        await db.flush()
        logger.info("  ✅ messages.sender_avatar_url 迁移完成")
    else:
        logger.info("  ⏭ messages.sender_avatar_url 已存在，跳过")


async def _migrate_prompt_overrides(db):
    """v0.8.0: 系统提示词覆盖 — system_settings 表加 system_prompt_overrides JSONB"""
    logger.info("  📝 添加 system_settings.system_prompt_overrides 列...")

    if not await _column_exists(db, "system_settings", "system_prompt_overrides"):
        await db.execute(text(
            "ALTER TABLE system_settings ADD COLUMN system_prompt_overrides JSONB"
        ))
        await db.flush()
        logger.info("  ✅ system_settings.system_prompt_overrides 迁移完成")
    else:
        logger.info("  ⏭ system_settings.system_prompt_overrides 已存在，跳过")


async def _migrate_memory_archive_columns(db):
    """v0.5.0: 记忆延迟归档 — rough_memories 加 status 和 value_score"""
    logger.info("  🔧 迁移记忆归档字段...")

    if not await _column_exists(db, "rough_memories", "status"):
        await db.execute(text(
            "ALTER TABLE rough_memories ADD COLUMN status VARCHAR(20) DEFAULT 'active'"
        ))
        await db.execute(text(
            "ALTER TABLE rough_memories ADD CONSTRAINT ck_rough_status "
            "CHECK (status IN ('active', 'pending_archive', 'discarded'))"
        ))
        await db.flush()
        logger.info("  ✅ rough_memories.status 迁移完成")
    else:
        logger.info("  ⏭ rough_memories.status 已存在，跳过")

    if not await _column_exists(db, "rough_memories", "value_score"):
        await db.execute(text(
            "ALTER TABLE rough_memories ADD COLUMN value_score INTEGER DEFAULT 5"
        ))
        await db.flush()
        logger.info("  ✅ rough_memories.value_score 迁移完成")
    else:
        logger.info("  ⏭ rough_memories.value_score 已存在，跳过")


async def _migrate_agent_metrics(db):
    """v0.5.0: 系统指标表"""
    logger.info("  🔧 迁移系统指标表...")

    if not await _table_exists(db, "agent_metrics"):
        await db.execute(text("""
            CREATE TABLE agent_metrics (
                id SERIAL PRIMARY KEY,
                snapshot_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await db.flush()
        logger.info("  ✅ agent_metrics 表创建完成")
    else:
        logger.info("  ⏭ agent_metrics 已存在，跳过")


async def _migrate_system_settings(db):
    """v0.6.0: 平台全局系统设置表 + users.setup_completed 列"""
    logger.info("  ⚙️ 迁移系统设置表...")
    created_any = False

    # 1. system_settings 表
    if not await _table_exists(db, "system_settings"):
        logger.info("  ⚙️ 创建 system_settings 表")
        await db.execute(text("""
            CREATE TABLE system_settings (
                id INTEGER PRIMARY KEY DEFAULT 1,
                default_language VARCHAR(10) NOT NULL DEFAULT 'en',
                updated_by INTEGER REFERENCES users(id),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            INSERT INTO system_settings (id, default_language) VALUES (1, 'en')
            ON CONFLICT (id) DO NOTHING
        """))
        created_any = True
        logger.info("  ✅ system_settings 表创建完成（默认语言=en）")
    else:
        logger.info("  ⏭ system_settings 表已存在，跳过")

    # 2. users.setup_completed 列
    if not await _column_exists(db, "users", "setup_completed"):
        logger.info("  ✅ 添加 users.setup_completed 列（现有用户默认 TRUE）")
        await db.execute(text(
            "ALTER TABLE users ADD COLUMN setup_completed BOOLEAN NOT NULL DEFAULT TRUE"
        ))
        created_any = True
    else:
        logger.info("  ⏭ users.setup_completed 已存在，跳过")

    if created_any:
        await db.flush()
        logger.info("  ✅ 系统设置迁移完成")
    else:
        logger.info("  ⏭ 系统设置均已存在，跳过")


async def _migrate_api_key_pool_tables(db):
    """v0.6.0: API Key 池 + 用户绑定 + 用量日志"""
    logger.info("  🔧 迁移 API Key 池系统...")
    created_any = False

    if not await _table_exists(db, "api_key_pool"):
        await db.execute(text("""
            CREATE TABLE api_key_pool (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                api_base_url TEXT,
                api_key_encrypted TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        created_any = True
        logger.info("  ✅ api_key_pool 表创建完成")
    else:
        logger.info("  ⏭ api_key_pool 已存在，跳过")

    if not await _table_exists(db, "user_api_assignments"):
        await db.execute(text("""
            CREATE TABLE user_api_assignments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                pool_key_id INTEGER NOT NULL REFERENCES api_key_pool(id) ON DELETE CASCADE,
                assigned_at TIMESTAMP DEFAULT NOW(),
                last_used_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id)
            )
        """))
        created_any = True
        logger.info("  ✅ user_api_assignments 表创建完成")
    else:
        logger.info("  ⏭ user_api_assignments 已存在，跳过")

    if not await _table_exists(db, "api_usage_log"):
        await db.execute(text("""
            CREATE TABLE api_usage_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                agent_id INTEGER REFERENCES agents(id),
                pool_key_id INTEGER REFERENCES api_key_pool(id),
                source VARCHAR(20) NOT NULL DEFAULT 'user_key',
                tokens_used INTEGER NOT NULL,
                credit_spent NUMERIC(6,2) NOT NULL DEFAULT 0,
                model VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        created_any = True
        logger.info("  ✅ api_usage_log 表创建完成")
    else:
        logger.info("  ⏭ api_usage_log 已存在，跳过")

    # v0.6.0: api_key_pool.concurrent_limit
    if not await _column_exists(db, "api_key_pool", "concurrent_limit"):
        await db.execute(text(
            "ALTER TABLE api_key_pool ADD COLUMN concurrent_limit INTEGER"
        ))
        logger.info("  ✅ api_key_pool.concurrent_limit 列添加完成")
    else:
        logger.info("  ⏭ api_key_pool.concurrent_limit 列已存在，跳过")

    if created_any:
        await db.flush()


async def _migrate_platform_credit(db):
    """v0.6.0: 平台赠送额度 + system_settings 扩展"""
    logger.info("  🎁 迁移平台赠送额度系统...")

    if not await _column_exists(db, "system_settings", "default_platform_credit"):
        await db.execute(text(
            "ALTER TABLE system_settings ADD COLUMN default_platform_credit INTEGER NOT NULL DEFAULT 0"
        ))
        logger.info("  ✅ system_settings.default_platform_credit 列添加完成")
    else:
        logger.info("  ⏭ system_settings.default_platform_credit 列已存在，跳过")

    if not await _column_exists(db, "users", "platform_gifted_credit"):
        await db.execute(text(
            "ALTER TABLE users ADD COLUMN platform_gifted_credit INTEGER NOT NULL DEFAULT 0"
        ))
        logger.info("  ✅ users.platform_gifted_credit 列添加完成")
    else:
        logger.info("  ⏭ users.platform_gifted_credit 列已存在，跳过")


async def _migrate_redemption_code_details(db):
    """v0.6.0: 兑换码增强——备注、最大用量、API 池标记、创建时间"""
    logger.info("  🏷️ 迁移兑换码详细字段...")
    created_any = False

    if not await _column_exists(db, "redemption_codes", "note"):
        await db.execute(text("ALTER TABLE redemption_codes ADD COLUMN note TEXT"))
        created_any = True
        logger.info("  ✅ redemption_codes.note 列添加完成")
    else:
        logger.info("  ⏭ redemption_codes.note 已存在，跳过")

    if not await _column_exists(db, "redemption_codes", "max_usage"):
        await db.execute(text("ALTER TABLE redemption_codes ADD COLUMN max_usage INTEGER"))
        created_any = True
        logger.info("  ✅ redemption_codes.max_usage 列添加完成")
    else:
        logger.info("  ⏭ redemption_codes.max_usage 已存在，跳过")

    if not await _column_exists(db, "redemption_codes", "is_api_pool"):
        await db.execute(text(
            "ALTER TABLE redemption_codes ADD COLUMN is_api_pool BOOLEAN DEFAULT FALSE"
        ))
        created_any = True
        logger.info("  ✅ redemption_codes.is_api_pool 列添加完成")
    else:
        logger.info("  ⏭ redemption_codes.is_api_pool 已存在，跳过")

    if not await _column_exists(db, "redemption_codes", "created_at"):
        await db.execute(text(
            "ALTER TABLE redemption_codes ADD COLUMN created_at TIMESTAMP DEFAULT NOW()"
        ))
        created_any = True
        logger.info("  ✅ redemption_codes.created_at 列添加完成")
    else:
        logger.info("  ⏭ redemption_codes.created_at 已存在，跳过")

    if created_any:
        await db.flush()


async def _migrate_friend_controls(db):
    """v0.6.0: 好友控制字段——是否允许好友申请、是否自动响应"""
    logger.info("  👥 迁移好友控制字段...")
    created_any = False

    if not await _column_exists(db, "agents", "allow_friend_requests"):
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN allow_friend_requests BOOLEAN NOT NULL DEFAULT TRUE"
        ))
        created_any = True
        logger.info("  ✅ agents.allow_friend_requests 列添加完成")
    else:
        logger.info("  ⏭ agents.allow_friend_requests 已存在，跳过")

    if not await _column_exists(db, "agents", "auto_respond_friend_request"):
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN auto_respond_friend_request BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        created_any = True
        logger.info("  ✅ agents.auto_respond_friend_request 列添加完成")
    else:
        logger.info("  ⏭ agents.auto_respond_friend_request 已存在，跳过")

    if created_any:
        await db.flush()


async def _migrate_memory_config_columns(db):
    """v0.8.0: 文件记忆配置字段——加载模式、最近篇数、共享范围"""
    logger.info("  📂 迁移文件记忆配置字段...")
    created_any = False

    if not await _column_exists(db, "agents", "memory_load_mode"):
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN memory_load_mode VARCHAR(30) NOT NULL DEFAULT 'index_only'"
        ))
        created_any = True
        logger.info("  ✅ agents.memory_load_mode 列添加完成")
    else:
        logger.info("  ⏭ agents.memory_load_mode 已存在，跳过")

    if not await _column_exists(db, "agents", "memory_recent_count"):
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN memory_recent_count INT NOT NULL DEFAULT 0"
        ))
        created_any = True
        logger.info("  ✅ agents.memory_recent_count 列添加完成")
    else:
        logger.info("  ⏭ agents.memory_recent_count 已存在，跳过")

    if not await _column_exists(db, "agents", "memory_shared_scope"):
        await db.execute(text(
            "ALTER TABLE agents ADD COLUMN memory_shared_scope VARCHAR(30) NOT NULL DEFAULT 'private_only'"
        ))
        created_any = True
        logger.info("  ✅ agents.memory_shared_scope 列添加完成")
    else:
        logger.info("  ⏭ agents.memory_shared_scope 已存在，跳过")

    if created_any:
        await db.flush()


async def _fix_file_owner_type_check(db):
    """v0.5.0+: 修复 file_metadata.owner_type CHECK 约束缺少 'human'（消息附件上传需要）

    数据库中的约束可能有两种命名：SQLAlchemy ORM 显式命名的 ck_file_owner_type，
    或 init-db.sql 内联 CHECK 由 PG 自动命名的 file_metadata_owner_type_check。
    """
    # 查找 file_metadata 表上限制 owner_type 的 CHECK 约束（可能有不同命名）
    result = await db.execute(text("""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'file_metadata'::regclass AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%owner_type%'
    """))
    row = result.fetchone()
    if row is None:
        logger.info("  ⏭ file_metadata.owner_type CHECK 约束不存在，跳过")
        return
    conname, current_def = row
    if "'human'" in current_def:
        logger.info(f"  ⏭ {conname} 已包含 human，跳过")
        return
    logger.info(f"  🔧 修复 {conname}：添加 'human' 到 owner_type 约束")
    await db.execute(text(f"ALTER TABLE file_metadata DROP CONSTRAINT {conname}"))
    await db.execute(text(
        "ALTER TABLE file_metadata ADD CONSTRAINT ck_file_owner_type "
        "CHECK (owner_type IN ('human', 'ai', 'group', 'system'))"
    ))
    await db.flush()
    logger.info(f"  ✅ {conname} → ck_file_owner_type 修复完成")


async def _migrate_federation_v1(db):
    """v1.0.0: 联邦 ID 前缀替代注册表 — DROP 旧表 + CREATE 新表 + 系统设置"""
    logger.info("  🌐 v1.0.0 联邦架构迁移: ID 前缀替代注册表...")
    created_any = False

    # 1. DROP 旧共享表（用户已确认重新配置联邦）
    if await _table_exists(db, "federation_group_shares"):
        logger.info("  🗑️ 删除 federation_group_shares 表")
        await db.execute(text("DROP TABLE IF EXISTS federation_group_shares CASCADE"))
        created_any = True
    if await _table_exists(db, "federation_dm_shares"):
        logger.info("  🗑️ 删除 federation_dm_shares 表")
        await db.execute(text("DROP TABLE IF EXISTS federation_dm_shares CASCADE"))
        created_any = True

    # 2. DROP groups.is_federated 列
    if await _column_exists(db, "groups", "is_federated"):
        logger.info("  🗑️ 删除 groups.is_federated 列")
        await db.execute(text("ALTER TABLE groups DROP COLUMN is_federated"))
        created_any = True

    # 3. CREATE federated_entities 表
    if not await _table_exists(db, "federated_entities"):
        logger.info("  📦 创建 federated_entities 表")
        await db.execute(text("""
            CREATE TABLE federated_entities (
                id SERIAL PRIMARY KEY,
                federated_id VARCHAR(200) UNIQUE NOT NULL,
                peer_id INT NOT NULL REFERENCES federation_peers(id) ON DELETE CASCADE,
                entity_type VARCHAR(10) NOT NULL CHECK (entity_type IN ('group', 'dm', 'user', 'agent')),
                local_ref_id VARCHAR(100) NOT NULL,
                display_name VARCHAR(200) DEFAULT '',
                is_enabled BOOLEAN DEFAULT TRUE,
                direction VARCHAR(20) DEFAULT 'incoming'
                    CHECK (direction IN ('incoming', 'bidirectional', 'outgoing')),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(peer_id, entity_type, local_ref_id)
            )
        """))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_fed_entity_type_ref ON federated_entities(entity_type, local_ref_id)"))
        created_any = True
    else:
        logger.info("  ⏭ federated_entities 表已存在，跳过")

    if not await _column_exists(db, "federated_entities", "avatar_url"):
        logger.info("  🖼️ 添加 federated_entities.avatar_url 列")
        await db.execute(text("ALTER TABLE federated_entities ADD COLUMN avatar_url TEXT DEFAULT ''"))
        created_any = True
    else:
        logger.info("  ⏭ federated_entities.avatar_url 已存在，跳过")

    # 4. CREATE pending_profile_updates 表
    if not await _table_exists(db, "pending_profile_updates"):
        logger.info("  📝 创建 pending_profile_updates 表")
        await db.execute(text("""
            CREATE TABLE pending_profile_updates (
                id SERIAL PRIMARY KEY,
                entity_type VARCHAR(10) NOT NULL,
                entity_id INT NOT NULL,
                field VARCHAR(50) NOT NULL,
                new_value VARCHAR(500) NOT NULL,
                changed_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_ppu_entity ON pending_profile_updates(entity_type, entity_id)"))
        created_any = True
    else:
        logger.info("  ⏭ pending_profile_updates 表已存在，跳过")

    # 5. display_name UNIQUE 约束（先清空可能存在的重名旧数据，再修改列类型和加约束）
    if await _column_exists(db, "federation_peers", "display_name"):
        # 先检查是否已有 UNIQUE 约束
        result = await db.execute(text("""
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name = 'federation_peers' AND constraint_name = 'uq_peer_display_name'
        """))
        if not result.fetchone():
            # 先清空旧数据中的重名（安全措施：旧数据 display_name 可能为空或重复）
            await db.execute(text(
                "UPDATE federation_peers SET display_name = peer_public_id "
                "WHERE display_name IS NULL OR display_name = ''"
            ))
            # 修改列为 NOT NULL
            await db.execute(text(
                "ALTER TABLE federation_peers ALTER COLUMN display_name SET NOT NULL"
            ))
            # 添加唯一约束
            try:
                await db.execute(text(
                    "ALTER TABLE federation_peers ADD CONSTRAINT uq_peer_display_name UNIQUE(display_name)"
                ))
                logger.info("  ✅ federation_peers.display_name UNIQUE 约束添加完成")
            except Exception as e:
                # 如果存在重名，用临时修复再重试
                logger.warning(f"  ⚠️ UNIQUE 约束添加失败: {e}，尝试修复重名...")
                await db.execute(text(
                    "UPDATE federation_peers SET display_name = display_name || '_' || id "
                    "WHERE display_name IN (SELECT display_name FROM federation_peers GROUP BY display_name HAVING COUNT(*) > 1)"
                ))
                await db.execute(text(
                    "ALTER TABLE federation_peers ADD CONSTRAINT uq_peer_display_name UNIQUE(display_name)"
                ))
                logger.info("  ✅ federation_peers.display_name UNIQUE 约束添加完成（已修复重名）")
            created_any = True
    else:
        logger.info("  ⏭ federation_peers.display_name 不存在，跳过")

    # 6. system_settings.federation_sync_interval_minutes
    if not await _column_exists(db, "system_settings", "federation_sync_interval_minutes"):
        await db.execute(text(
            "ALTER TABLE system_settings ADD COLUMN federation_sync_interval_minutes INTEGER NOT NULL DEFAULT 720"
        ))
        logger.info("  ✅ system_settings.federation_sync_interval_minutes 列添加完成（默认 720 分钟）")
        created_any = True
    else:
        logger.info("  ⏭ system_settings.federation_sync_interval_minutes 已存在，跳过")

    if created_any:
        await db.flush()
        logger.info("  ✅ 联邦 v1.0.0 迁移完成")
    else:
        logger.info("  ⏭ 联邦 v1.0.0 迁移均已完成，跳过")


async def _migrate_agent_collaborators(db):
    """v0.7.0 AI 合作者系统 — 新建 agent_collaborators 表"""
    if await _table_exists(db, "agent_collaborators"):
        logger.info("  ⏭ agent_collaborators 已存在，跳过")
        return
    logger.info("  🤝 创建 agent_collaborators 表")
    await db.execute(text("""
        CREATE TABLE agent_collaborators (
            id SERIAL PRIMARY KEY,
            agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            can_edit BOOLEAN DEFAULT TRUE,
            can_delete BOOLEAN DEFAULT FALSE,
            can_manage_collaborators BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(agent_id, user_id)
        )
    """))
    await db.flush()
    logger.info("  ✅ agent_collaborators 表创建完成")


async def _migrate_prompt_order(db):
    """v0.7.0 系统提示词段顺序可自定义"""
    if await _column_exists(db, "system_settings", "system_prompt_order"):
        logger.info("  ⏭ system_settings.system_prompt_order 已存在，跳过")
        return
    logger.info("  📋 添加 system_settings.system_prompt_order 列")
    await db.execute(text(
        "ALTER TABLE system_settings ADD COLUMN system_prompt_order JSONB"
    ))
    await db.flush()
    logger.info("  ✅ system_settings.system_prompt_order 列添加完成")


async def _fix_file_refs_referrer_type(db):
    """v0.7.0+: 修复 file_references.referrer_type CHECK 约束缺少 'human'（用户下载附件需要）

    数据库中的约束可能有两种命名：init-db.sql 内联 CHECK 由 PG 自动命名。
    """
    result = await db.execute(text("""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'file_references'::regclass AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%referrer_type%'
    """))
    row = result.fetchone()
    if row is None:
        logger.info("  ⏭ file_references.referrer_type CHECK 约束不存在，跳过")
        return
    conname, current_def = row
    if "'human'" in current_def:
        logger.info(f"  ⏭ {conname} 已包含 human，跳过")
        return
    logger.info(f"  🔧 修复 {conname}：添加 'human' 到 referrer_type 约束")
    await db.execute(text(f"ALTER TABLE file_references DROP CONSTRAINT {conname}"))
    await db.execute(text(
        "ALTER TABLE file_references ADD CONSTRAINT ck_ref_referrer_type "
        "CHECK (referrer_type IN ('human', 'ai', 'message', 'group'))"
    ))
    await db.flush()
    logger.info("  ✅ file_references.referrer_type 约束已修复（添加 human）")


async def _migrate_content_hash(db):
    """v0.9.0: file_metadata.content_hash（SHA-256，用于文件去重）"""
    if await _column_exists(db, "file_metadata", "content_hash"):
        logger.info("  ⏭ file_metadata.content_hash 已存在，跳过")
        return
    logger.info("  🔐 添加 file_metadata.content_hash 列")
    await db.execute(text("ALTER TABLE file_metadata ADD COLUMN content_hash VARCHAR(64)"))
    await db.flush()
    logger.info("  ✅ file_metadata.content_hash 迁移完成")


async def _migrate_forward_ref_type(db):
    """v0.9.0: file_references.ref_type 增加 'forward' 类型"""
    result = await db.execute(text("""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'file_references'::regclass AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%ref_type%'
    """))
    row = result.fetchone()
    if row is None:
        logger.info("  ⏭ file_references.ref_type CHECK 约束不存在，跳过")
        return
    conname, current_def = row
    if "'forward'" in current_def:
        logger.info(f"  ⏭ {conname} 已包含 forward，跳过")
        return
    logger.info(f"  🔧 更新 {conname}：添加 'forward' 类型")
    await db.execute(text(f"ALTER TABLE file_references DROP CONSTRAINT {conname}"))
    await db.execute(text(
        "ALTER TABLE file_references ADD CONSTRAINT ck_ref_type "
        "CHECK (ref_type IN ('read', 'write', 'import', 'share', 'forward'))"
    ))
    await db.flush()
    logger.info("  ✅ file_references.ref_type 已添加 forward")


async def _migrate_orphan_retention(db):
    """v0.9.0: system_settings.orphan_retention_days（孤儿文件宽限期，默认 7 天）"""
    if await _column_exists(db, "system_settings", "orphan_retention_days"):
        logger.info("  ⏭ system_settings.orphan_retention_days 已存在，跳过")
        return
    logger.info("  🗑️ 添加 system_settings.orphan_retention_days 列")
    await db.execute(text(
        "ALTER TABLE system_settings ADD COLUMN orphan_retention_days INTEGER NOT NULL DEFAULT 7"
    ))
    await db.flush()
    logger.info("  ✅ system_settings.orphan_retention_days 迁移完成")


async def _migrate_default_file_quota(db):
    """v0.9.0: system_settings.default_file_quota_mb + users.file_quota_bonus_mb"""
    created_any = False

    if not await _column_exists(db, "system_settings", "default_file_quota_mb"):
        logger.info("  💾 添加 system_settings.default_file_quota_mb 列")
        await db.execute(text(
            "ALTER TABLE system_settings ADD COLUMN default_file_quota_mb INTEGER NOT NULL DEFAULT 100"
        ))
        created_any = True
    else:
        logger.info("  ⏭ system_settings.default_file_quota_mb 已存在，跳过")

    if not await _column_exists(db, "users", "file_quota_bonus_mb"):
        logger.info("  💾 添加 users.file_quota_bonus_mb 列（迁移已有配额中超出100的部分为加成）")
        await db.execute(text(
            "ALTER TABLE users ADD COLUMN file_quota_bonus_mb INTEGER NOT NULL DEFAULT 0"
        ))
        # 已有用户：file_quota_mb 超出 100 的部分归为兑换码加成
        await db.execute(text(
            "UPDATE users SET file_quota_bonus_mb = GREATEST(file_quota_mb - 100, 0)"
        ))
        created_any = True
    else:
        logger.info("  ⏭ users.file_quota_bonus_mb 已存在，跳过")

    if created_any:
        await db.flush()
        logger.info("  ✅ default_file_quota / file_quota_bonus 迁移完成")


async def _migrate_bio_and_status(db):
    """v0.9.0: agents.bio + users.status_text + agents.status_text"""
    created_any = False

    if not await _column_exists(db, "agents", "bio"):
        logger.info("  📝 添加 agents.bio 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN bio TEXT"))
        created_any = True
    else:
        logger.info("  ⏭ agents.bio 已存在，跳过")

    if not await _column_exists(db, "users", "status_text"):
        logger.info("  💬 添加 users.status_text 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN status_text VARCHAR(100)"))
        created_any = True
    else:
        logger.info("  ⏭ users.status_text 已存在，跳过")

    if not await _column_exists(db, "agents", "status_text"):
        logger.info("  💬 添加 agents.status_text 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN status_text VARCHAR(100)"))
        created_any = True
    else:
        logger.info("  ⏭ agents.status_text 已存在，跳过")

    if not await _column_exists(db, "users", "status_color"):
        logger.info("  🎨 添加 users.status_color 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN status_color VARCHAR(20)"))
        created_any = True
    else:
        logger.info("  ⏭ users.status_color 已存在，跳过")

    if created_any:
        await db.flush()
        logger.info("  ✅ bio/status_text 迁移完成")


async def _migrate_email_verification(db):
    """v1.0.0: 邮箱认证 — users 表 +email/+email_verified + verification_codes 表 + system_settings 扩展"""
    created_any = False

    # 1. users.email（可空，部分唯一索引）
    if not await _column_exists(db, "users", "email"):
        logger.info("  📧 添加 users.email 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
        await db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email IS NOT NULL"
        ))
        created_any = True
    else:
        logger.info("  ⏭ users.email 已存在，跳过")

    # 2. users.email_verified
    if not await _column_exists(db, "users", "email_verified"):
        logger.info("  ✅ 添加 users.email_verified 列")
        await db.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE"))
        created_any = True
    else:
        logger.info("  ⏭ users.email_verified 已存在，跳过")

    # 3. verification_codes 表
    if not await _table_exists(db, "verification_codes"):
        logger.info("  📦 创建 verification_codes 表")
        await db.execute(text("""
            CREATE TABLE verification_codes (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                code VARCHAR(10) NOT NULL,
                purpose VARCHAR(30) NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                ip_address VARCHAR(45),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_vc_email_purpose ON verification_codes(email, purpose)"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_vc_expires ON verification_codes(expires_at)"))
        created_any = True
    else:
        logger.info("  ⏭ verification_codes 表已存在，跳过")
        # 补充 ip_address 列（老版本可能没有）
        if not await _column_exists(db, "verification_codes", "ip_address"):
            await db.execute(text("ALTER TABLE verification_codes ADD COLUMN ip_address VARCHAR(45)"))
            created_any = True

    # 4. system_settings.smtp_config
    if not await _column_exists(db, "system_settings", "smtp_config"):
        logger.info("  📧 添加 system_settings.smtp_config 列")
        await db.execute(text("ALTER TABLE system_settings ADD COLUMN smtp_config JSONB"))
        created_any = True
    else:
        logger.info("  ⏭ system_settings.smtp_config 已存在，跳过")

    # 5. system_settings.require_email_verification
    if not await _column_exists(db, "system_settings", "require_email_verification"):
        logger.info("  🔒 添加 system_settings.require_email_verification 列")
        await db.execute(text(
            "ALTER TABLE system_settings ADD COLUMN require_email_verification BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        created_any = True
    else:
        logger.info("  ⏭ system_settings.require_email_verification 已存在，跳过")

    # 6. system_settings.login_providers
    if not await _column_exists(db, "system_settings", "login_providers"):
        logger.info("  🔑 添加 system_settings.login_providers 列")
        await db.execute(text(
            "ALTER TABLE system_settings ADD COLUMN login_providers JSONB NOT NULL DEFAULT '[\"direct\"]'"
        ))
        created_any = True
    else:
        logger.info("  ⏭ system_settings.login_providers 已存在，跳过")

    if created_any:
        await db.flush()
        logger.info("  ✅ 邮箱认证迁移完成")


async def _migrate_smtp_configs_array(db):
    """v1.0.0: 多 SMTP 容灾 — 将 smtp_config 从单对象迁移为数组格式

    旧格式: {"host":"...","port":587,...}
    新格式: [{"host":"...","port":587,...,"is_active":true,"priority":0}]
    """
    if not await _column_exists(db, "system_settings", "smtp_config"):
        logger.info("  ⏭ system_settings.smtp_config 列不存在，跳过多 SMTP 迁移")
        return

    # 检查是否已经是数组格式
    result = await db.execute(
        text("SELECT smtp_config FROM system_settings WHERE id = 1 AND smtp_config IS NOT NULL")
    )
    row = result.fetchone()
    if row is None:
        logger.info("  ⏭ smtp_config 为 NULL，跳过迁移")
        return

    raw = row[0]
    # 已经是列表 list → 无需迁移
    if isinstance(raw, list):
        logger.info("  ⏭ smtp_config 已是数组格式，跳过")
        return

    # 字典 → 包装为数组
    if isinstance(raw, dict):
        # JSONB 从 PG 读取自动反序列化，但有时会是 JSON 字符串
        pass
    elif isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except Exception:
            logger.warning("  ⚠️ smtp_config 解析失败，跳过迁移")
            return

    if not isinstance(raw, dict) or not raw.get("host"):
        logger.info("  ⏭ smtp_config 为空对象，设为空数组")
        await db.execute(
            text("UPDATE system_settings SET smtp_config = '[]'::jsonb WHERE id = 1")
        )
        await db.flush()
        return

    logger.info("  📦 迁移 smtp_config: 单对象 → 数组格式")
    raw.setdefault("is_active", True)
    raw.setdefault("priority", 0)
    import json
    new_value = json.dumps([raw])
    await db.execute(
        text("UPDATE system_settings SET smtp_config = CAST(:val AS jsonb) WHERE id = 1"),
        {"val": new_value},
    )
    await db.flush()
    logger.info("  ✅ smtp_config 已迁移为数组格式")


async def _migrate_email_templates(db):
    """v1.0.0: 自定义邮件模板 — system_settings 表 +email_templates JSONB 列"""
    if await _column_exists(db, "system_settings", "email_templates"):
        logger.info("  ⏭ system_settings.email_templates 已存在，跳过")
        return
    logger.info("  📧 添加 system_settings.email_templates 列")
    await db.execute(text("ALTER TABLE system_settings ADD COLUMN email_templates JSONB"))
    await db.flush()
    logger.info("  ✅ system_settings.email_templates 列添加完成")


async def _migrate_structured_records(db):
    """v0.10.0: 目录级结构记忆表（双重记忆架构的系统2）"""
    if await _table_exists(db, "structured_records"):
        logger.info("  ⏭ structured_records 表已存在，跳过")
        return
    logger.info("  🗂️ 创建 structured_records 表")
    await db.execute(text("""
        CREATE TABLE structured_records (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            category VARCHAR(100) NOT NULL,
            sub_key VARCHAR(200) NOT NULL,
            field VARCHAR(200) NOT NULL,
            value TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(agent_id, category, sub_key, field)
        )
    """))
    await db.flush()
    logger.info("  ✅ structured_records 表创建完成")


async def _migrate_oracle_file_references(db):
    """v0.10.x: file_references 表添加 UNIQUE 约束（幂等引用追踪）"""
    # 检查是否已有唯一约束
    result = await db.execute(text("""
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'file_references' AND constraint_name = 'uq_file_ref'
    """))
    if result.fetchone():
        logger.info("  ⏭ file_references.uq_file_ref 已存在，跳过")
        return

    # 清理重复行：按 (file_id, referrer_type, referrer_id) 分组，每组只保留最小 id
    logger.info("  🧹 清理 file_references 重复记录...")
    # 先查出要删的 id
    result = await db.execute(text("""
        SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY file_id, referrer_type, referrer_id
                       ORDER BY id ASC
                   ) AS rn
            FROM file_references
        ) sub WHERE rn > 1
    """))
    dup_ids = [r[0] for r in result.fetchall()]
    if dup_ids:
        # 分批删除（避免 IN 列表过长）
        for i in range(0, len(dup_ids), 500):
            batch = dup_ids[i:i + 500]
            await db.execute(
                text("DELETE FROM file_references WHERE id = ANY(:ids)"),
                {"ids": batch},
            )
        logger.info(f"  ✅ 已清理 {len(dup_ids)} 条重复记录")

    # 加唯一约束
    logger.info("  🔒 添加 file_references.uq_file_ref 约束")
    await db.execute(text("""
        ALTER TABLE file_references
        ADD CONSTRAINT uq_file_ref UNIQUE (file_id, referrer_type, referrer_id)
    """))
    await db.flush()
    logger.info("  ✅ file_references 幂等约束迁移完成")


async def _migrate_group_members_user_id(db):
    """v2.0.0: AI 群成员的 member_id 从 agent.id 统一为 agent.user_id

    使 AI 和人类用户共用 users 表 ID 空间，消除搜索/列表中的重复。
    完全幂等：多次执行安全，不会丢数据。
    """
    from app.models.agent import Agent

    # Step 0: 检查是否需要迁移（幂等判断）
    result = await db.execute(text(
        "SELECT COUNT(*) FROM group_members gm "
        "JOIN agents a ON a.id = gm.member_id "
        "WHERE gm.member_type = 'ai' AND a.user_id IS NOT NULL AND gm.member_id <> a.user_id"
    ))
    count = result.scalar()
    if count == 0:
        logger.info("  ⏭ 群成员 ID 已统一，跳过")
        return

    logger.info(f"  🔄 统一 {count} 个 AI 群成员的 member_id (agent.id → user_id)...")

    # Step 1: 同一 group 内，如果 human 和 AI 指向同一个人（user_id），合并为 AI 类型
    await db.execute(text("""
        UPDATE group_members gm_human
        SET member_type = 'ai'
        FROM agents a
        WHERE gm_human.member_type = 'human'
        AND EXISTS (
            SELECT 1 FROM group_members gm_ai
            WHERE gm_ai.group_id = gm_human.group_id
            AND gm_ai.member_type = 'ai'
            AND gm_ai.member_id = a.id
            AND a.user_id = gm_human.member_id
        )
    """))
    logger.info("    🔀 合并 human→ai 重复记录完成")

    # Step 2: 删除已被合并的旧 AI 条目（保留已改为 ai type 的条目）
    await db.execute(text("""
        DELETE FROM group_members gm
        WHERE gm.member_type = 'ai'
        AND gm.member_id IN (
            SELECT a.id FROM agents a
            WHERE EXISTS (
                SELECT 1 FROM group_members gm2
                WHERE gm2.group_id = gm.group_id
                AND gm2.member_type = 'ai'
                AND gm2.member_id = a.user_id
            )
        )
    """))
    logger.info("    🔀 旧 AI 条目清理完成")

    # Step 3: 迁移剩余 AI 条目的 member_id → user_id
    await db.execute(text("""
        UPDATE group_members gm
        SET member_id = a.user_id
        FROM agents a
        WHERE gm.member_type = 'ai'
        AND a.id = gm.member_id
        AND a.user_id IS NOT NULL
        AND gm.member_id <> a.user_id
    """))
    logger.info("    ✅ AI member_id → user_id 转换完成")

    # Step 4: 清理无主条目
    await db.execute(text("""
        DELETE FROM group_members gm
        WHERE gm.member_type = 'ai'
        AND gm.member_id NOT IN (SELECT id FROM users WHERE type = 'ai')
        AND NOT EXISTS (
            SELECT 1 FROM agents a
            WHERE a.user_id = gm.member_id
        )
    """))
    logger.info("    🧹 无主条目清理完成")

    # Step 5: 幂等验证
    verify = await db.execute(text(
        "SELECT COUNT(*) FROM group_members gm "
        "JOIN agents a ON a.id = gm.member_id "
        "WHERE gm.member_type = 'ai'"
    ))
    orphan_count = verify.scalar()
    if orphan_count > 0:
        logger.warning(f"    ⚠️ 仍有 {orphan_count} 条 AI 成员使用 agent.id（无 user_id）")

    remaining = await db.execute(text(
        "SELECT COUNT(*) FROM group_members WHERE member_type = 'ai'"
    ))
    logger.info(f"  ✅ 群成员 ID 统一完成，{remaining.scalar()} 个 AI 成员均使用 user_id")

    # Step 6: 修复被错误降级为 human 的 AI 条目（add_member 旧版本 bug）
    from app.models.agent import Agent as AgentModel
    corrupted = await db.execute(text("""
        UPDATE group_members gm
        SET member_type = 'ai'
        FROM agents a
        WHERE gm.member_type = 'human'
        AND (gm.member_id = a.user_id OR gm.member_id = a.id)
    """))
    await db.flush()
    logger.info("    🔧 AI 类型修复完成（human → ai 还原）")


async def _migrate_fix_human_members_changed_to_ai(db):
    """
    v1.0.2: 修复 _migrate_group_members_user_id 的 bug——Step 1 把人类成员误改为 AI 类型。

    逐条处理，避免 SQL 层面主键冲突。
    """
    # 查出所有被误改的记录：member_type='ai' 但 member_id 是人类的
    rows = (await db.execute(text("""
        SELECT gm.group_id, gm.member_id, gm.role
        FROM group_members gm
        JOIN users u ON u.id = gm.member_id
        WHERE gm.member_type = 'ai' AND u.type = 'human'
    """))).all()

    if not rows:
        logger.info("  ⏭ 没有被误改的人类成员，跳过")
        return

    deleted = 0
    updated = 0
    for group_id, member_id, role in rows:
        # 同群是否已有正确 human 记录
        dup = (await db.execute(text(
            "SELECT 1 FROM group_members WHERE group_id=:g AND member_type='human' AND member_id=:m"
        ), {"g": group_id, "m": member_id})).first()

        if dup:
            # 删掉误改的 ai 记录
            await db.execute(text(
                "DELETE FROM group_members WHERE group_id=:g AND member_type='ai' AND member_id=:m"
            ), {"g": group_id, "m": member_id})
            deleted += 1
        else:
            # 直接改回 human
            await db.execute(text(
                "UPDATE group_members SET member_type='human' WHERE group_id=:g AND member_type='ai' AND member_id=:m"
            ), {"g": group_id, "m": member_id})
            updated += 1

    await db.flush()
    logger.info(f"  ✅ 修复完成：删除 {deleted} 条重复 + 还原 {updated} 条人类成员")

    await db.flush()


async def _migrate_group_invitations(db):
    """v2.0.0: 群邀请卡片系统（group_invitations 表 + dm_messages.message_type 列）

    完全幂等：多次执行安全。
    """
    # 1. 创建 group_invitations 表
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS group_invitations (
            id SERIAL PRIMARY KEY,
            group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            inviter_id INT NOT NULL REFERENCES users(id),
            invitee_id INT NOT NULL REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            message TEXT,
            dm_session_id VARCHAR(64),
            dm_message_id INT,
            created_at TIMESTAMP DEFAULT NOW(),
            resolved_at TIMESTAMP,
            CONSTRAINT ck_group_invitation_status CHECK (status IN ('pending', 'accepted', 'rejected'))
        )
    """))
    logger.info("  ✅ group_invitations 表就绪")

    # 2. 添加 dm_messages.message_type 列（幂等）
    if not await _column_exists(db, "dm_messages", "message_type"):
        await db.execute(text(
            "ALTER TABLE dm_messages ADD COLUMN message_type VARCHAR(30) NOT NULL DEFAULT 'normal'"
        ))
        logger.info("  ✅ dm_messages.message_type 列已添加")
    else:
        logger.info("  ⏭ dm_messages.message_type 列已存在，跳过")

    # 3. 索引（幂等）
    await db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_group_invitations_invitee "
        "ON group_invitations(invitee_id, status)"
    ))
    await db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_group_invitations_group "
        "ON group_invitations(group_id)"
    ))

    await db.flush()
    logger.info("  ✅ 群邀请卡片系统迁移完成")


async def _migrate_group_owner_membership(db):
    """
    v2.0.1: 修复群主缺失的群成员记录（幂等）。

    部分老数据中群主创建群后未将自身加入 group_members，
    导致 list_user_groups 返回空、群聊列表不显示。
    """
    result = await db.execute(text("""
        INSERT INTO group_members (group_id, member_type, member_id, role)
        SELECT g.id, g.owner_type, g.owner_id, 'owner'
        FROM groups g
        WHERE NOT EXISTS (
            SELECT 1 FROM group_members gm
            WHERE gm.group_id = g.id
              AND gm.member_type = g.owner_type
              AND gm.member_id = g.owner_id
        )
        RETURNING group_id, member_type, member_id
    """))
    rows = result.fetchall()
    if rows:
        logger.info(f"  ✅ 已补全 {len(rows)} 条缺失的群主成员记录")
        for row in rows:
            logger.info(f"     group={row[0]} {row[1]}={row[2]} role=owner")
    else:
        logger.info("  ⏭ 群主成员记录完整，无需修复")


async def _migrate_fix_duplicate_owners(db):
    """
    v2.0.2: 修复每个群多个 owner 的数据错误（幂等）。

    将不是 groups 表指定群主的人从 owner 降为 member。
    """
    result = await db.execute(text("""
        UPDATE group_members gm
        SET role = 'member'
        WHERE role = 'owner'
          AND (gm.member_type, gm.member_id) NOT IN (
              SELECT g.owner_type, g.owner_id FROM groups g WHERE g.id = gm.group_id
          )
        RETURNING group_id, member_type, member_id
    """))
    rows = result.fetchall()
    if rows:
        logger.info(f"  ✅ 已修复 {len(rows)} 条错误的群主记录（降为 member）")
        for row in rows:
            logger.info(f"     group={row[0]} {row[1]}={row[2]} owner→member")
    else:
        logger.info("  ⏭ 群主角色正确，无需修复")


async def _migrate_agent_state_stack(db):
    """
    v1.0.1: agents 表新增 state_stack JSONB 列（幂等）。

    存储 AI 的跨任务上下文状态栈，支持 push/pop/close/list 操作。
    """
    if await _column_exists(db, "agents", "state_stack"):
        logger.info("  ⏭ agents.state_stack 已存在，跳过")
        return
    logger.info("  添加 agents.state_stack JSONB 列...")
    await db.execute(text("ALTER TABLE agents ADD COLUMN state_stack JSONB DEFAULT '[]'::jsonb"))
    await db.flush()
    logger.info("  ✅ agents.state_stack 添加完成")


async def _migrate_group_muted_until(db):
    """v2.0.3: group_members 添加 muted_until 列（屏蔽——比DND更强，@/公告也不穿透）"""
    if await _column_exists(db, "group_members", "muted_until"):
        logger.info("  ⏭ group_members.muted_until 已存在，跳过")
        return
    logger.info("  🔊 添加 group_members.muted_until 列")
    await db.execute(text("ALTER TABLE group_members ADD COLUMN muted_until TIMESTAMP"))
    await db.flush()
    logger.info("  ✅ group_members.muted_until 添加完成")

async def _fix_column_types(db):
    """修复老部署中列类型与新代码不匹配的问题（幂等：按需 ALTER）"""
    # system_logs.log_type：老版本可能是 VARCHAR(10)，代码写 "add_opencli_presets"（21 字符）
    await _widen_varchar(db, "system_logs", "log_type", 50)
    # system_logs.target_type：同上
    await _widen_varchar(db, "system_logs", "target_type", 50)


async def _widen_varchar(db, table: str, column: str, target_length: int):
    """如果 VARCHAR 列小于目标长度，则 ALTER 扩展它"""
    result = await db.execute(text("""
        SELECT character_maximum_length
        FROM information_schema.columns
        WHERE table_name = :table AND column_name = :column
    """), {"table": table, "column": column})
    row = result.fetchone()
    if row is None:
        return  # 列不存在，跳过
    current = row[0]
    if current is not None and current < target_length:
        logger.info(f"  🔧 ALTER {table}.{column} VARCHAR({current}) → VARCHAR({target_length})")
        await db.execute(text(
            f'ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR({target_length})'
        ))
        # 注意：不在此处 commit，由外层 db.begin() 统一提交
        await db.flush()


async def _migrate_provider_config(db):
    """v1.0.0: LLM 厂商预设 — system_settings 表 +provider_config JSONB"""
    if not await _column_exists(db, "system_settings", "provider_config"):
        logger.info("  🏭 添加 system_settings.provider_config 列")
        await db.execute(text("ALTER TABLE system_settings ADD COLUMN provider_config JSONB"))
        await db.commit()
    else:
        logger.info("  ⏭ system_settings.provider_config 已存在，跳过")


async def _migrate_system_user(db):
    """v0.8.0+: 确保系统通知用户 id=0 存在（硬编码 ID，不依赖 username 查询）"""
    from app.utils.auth import hash_password

    # 检查 id=0 是否已是系统用户
    result = await db.execute(text("SELECT id, username, type FROM users WHERE id = 0"))
    row = result.fetchone()
    if row and row[2] == "system":
        logger.info("  ✅ 系统用户 id=0 已存在")
        return

    # 删除旧的系统用户（可能由旧版迁移创建的非0 ID）
    await db.execute(text("DELETE FROM dm_messages WHERE sender_id IN (SELECT id FROM users WHERE type = 'system' AND id != 0)"))
    await db.execute(text("DELETE FROM dm_sessions WHERE user1_id IN (SELECT id FROM users WHERE type = 'system' AND id != 0) OR user2_id IN (SELECT id FROM users WHERE type = 'system' AND id != 0)"))
    await db.execute(text("DELETE FROM friendships WHERE user_id IN (SELECT id FROM users WHERE type = 'system' AND id != 0) OR friend_id IN (SELECT id FROM users WHERE type = 'system' AND id != 0)"))
    await db.execute(text("DELETE FROM users WHERE type = 'system' AND id != 0"))

    # 如果 id=0 存在但不是 system 类型，更新它
    if row:
        await db.execute(text("UPDATE users SET username = '系统', type = 'system', role = 'user', is_active = true WHERE id = 0"))
        logger.info("  ✅ 用户 id=0 已更新为系统用户")
    else:
        # 强制插入 id=0 的系统用户
        pw = hash_password("system_internal_no_login")
        await db.execute(text(
            "INSERT INTO users (id, username, password_hash, role, type, is_active) "
            "VALUES (0, '系统', :pw, 'user', 'system', true)"
        ), {"pw": pw})
        logger.info("  ✅ 系统用户 id=0 已创建")

    # 重置序列（确保后续 ID 不受影响）
    await db.execute(text("SELECT setval('users_id_seq', greatest(0, (SELECT COALESCE(MAX(id), 0) FROM users)))"))
    await db.flush()


async def _migrate_others_chat_controls(db):
    """v0.9.0: AI 对话权限与限额控制"""
    created_any = False

    if not await _column_exists(db, "agents", "allow_others_chat"):
        logger.info("  👥 添加 agents.allow_others_chat 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN allow_others_chat BOOLEAN NOT NULL DEFAULT TRUE"))
        created_any = True
    else:
        logger.info("  ⏭ agents.allow_others_chat 已存在，跳过")

    if not await _column_exists(db, "agents", "others_chat_mode"):
        logger.info("  📊 添加 agents.others_chat_mode 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN others_chat_mode VARCHAR(20) NOT NULL DEFAULT 'unlimited'"))
        created_any = True
    else:
        logger.info("  ⏭ agents.others_chat_mode 已存在，跳过")

    if not await _column_exists(db, "agents", "others_chat_quota"):
        logger.info("  🔢 添加 agents.others_chat_quota 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN others_chat_quota INTEGER NOT NULL DEFAULT 30"))
        created_any = True
    else:
        logger.info("  ⏭ agents.others_chat_quota 已存在，跳过")

    if not await _column_exists(db, "agents", "others_chat_used"):
        logger.info("  🔢 添加 agents.others_chat_used 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN others_chat_used INTEGER NOT NULL DEFAULT 0"))
        created_any = True
    else:
        logger.info("  ⏭ agents.others_chat_used 已存在，跳过")

    if not await _column_exists(db, "agents", "disallow_mode"):
        logger.info("  🚫 添加 agents.disallow_mode 列")
        await db.execute(text("ALTER TABLE agents ADD COLUMN disallow_mode VARCHAR(20) NOT NULL DEFAULT 'strict'"))
        created_any = True
    else:
        logger.info("  ⏭ agents.disallow_mode 已存在，跳过")

    if created_any:
        await db.flush()
        logger.info("  ✅ 对话权限/限额迁移完成")


async def _migrate_multi_provider(db):
    """v1.0.2: provider_config 单对象 → 数组 + api_key_pool 加 provider_name（幂等）"""
    import json

    # 1. 转换 provider_config：单对象 → 默认数组
    result = await db.execute(
        text("SELECT provider_config FROM system_settings WHERE id = 1 AND provider_config IS NOT NULL")
    )
    row = result.fetchone()
    if row is not None:
        raw = row[0]
        if isinstance(raw, list):
            logger.info("  ⏭ provider_config 已是数组，跳过")
        elif isinstance(raw, dict):
            # 旧单对象 → 包装为默认数组
            logger.info("  🔄 provider_config 单对象 → 默认数组")
            default_config = {
                "name": raw.get("provider", "default"),
                "provider": raw.get("provider", "deepseek"),
                "base_url": raw.get("base_url", ""),
                "chat_model": raw.get("chat_model", ""),
                "work_model": raw.get("work_model", ""),
                "embedding_model": raw.get("embedding_model", ""),
                "model_options": raw.get("model_options", []),
                "thinking_supported": raw.get("thinking_supported", False),
                "is_default": True,
            }
            await db.execute(
                text("UPDATE system_settings SET provider_config = CAST(:val AS jsonb) WHERE id = 1"),
                {"val": json.dumps([default_config])},
            )
            logger.info("  ✅ provider_config 已转为默认数组")
    else:
        logger.info("  ⏭ provider_config 为 NULL，跳过")

    # 2. api_key_pool 加 provider_name 列
    if not await _column_exists(db, "api_key_pool", "provider_name"):
        logger.info("  🏷️ 添加 api_key_pool.provider_name 列")
        await db.execute(text(
            "ALTER TABLE api_key_pool ADD COLUMN provider_name VARCHAR(100)"
        ))
        logger.info("  ✅ api_key_pool.provider_name 添加完成")
    else:
        logger.info("  ⏭ api_key_pool.provider_name 已存在，跳过")

    await db.flush()


async def _migrate_unify_ai_user_id(db):
    """
    v1.0.2: 全局统一——将所有表中的 AI ID 从 agent.id 转为 agent.user_id。
    涉及: messages, group_members, file_metadata（dm_messages 不转换——天然用 user_id）。
    """
    # 1. messages（安全：有 sender_type='ai' 过滤）
    await db.execute(text("""
        UPDATE messages SET sender_id = a.user_id
        FROM agents a
        WHERE sender_type = 'ai' AND a.id = messages.sender_id AND messages.sender_id <> a.user_id
    """))

    # 2. group_members（安全：有 member_type='ai' 过滤 + 去重）
    await db.execute(text("""
        UPDATE group_members gm SET member_id = a.user_id
        FROM agents a
        WHERE gm.member_type = 'ai' AND a.id = gm.member_id AND gm.member_id <> a.user_id
          AND NOT EXISTS (SELECT 1 FROM group_members gm2 WHERE gm2.group_id=gm.group_id AND gm2.member_type='ai' AND gm2.member_id=a.user_id)
    """))

    # 3. file_metadata（安全：有 owner_type='ai' 过滤）
    await db.execute(text("""
        UPDATE file_metadata SET owner_id = a.user_id
        FROM agents a
        WHERE owner_type = 'ai' AND a.id = file_metadata.owner_id AND file_metadata.owner_id <> a.user_id
    """))

    # 4. dm_messages 修复：sender_id 不属于会话参与者的消息
    # 策略：sender_id 落在 agent.id 范围的 → 改为 agent.user_id；
    #        仍然不对的 → 删掉（让对话自然重建）
    await db.execute(text("""
        UPDATE dm_messages dm SET sender_id = a.user_id
        FROM agents a
        WHERE a.id = dm.sender_id AND a.user_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM dm_sessions ds WHERE ds.session_id = dm.session_id AND a.user_id IN (ds.user1_id, ds.user2_id))
    """))
    # 剩下修不好的恢复为 user1（再不行就 user2）
    await db.execute(text("""
        UPDATE dm_messages dm SET sender_id = ds.user1_id
        FROM dm_sessions ds
        WHERE dm.session_id = ds.session_id AND dm.sender_id NOT IN (ds.user1_id, ds.user2_id)
    """))
    await db.execute(text("""
        UPDATE dm_messages dm SET sender_id = ds.user2_id
        FROM dm_sessions ds
        WHERE dm.session_id = ds.session_id AND dm.sender_id NOT IN (ds.user1_id, ds.user2_id)
    """))

    await db.flush()
    logger.info("  ✅ 全局 AI ID 统一为 user_id 完成")


async def _migrate_agent_status_color(db):
    """v1.0.2: agents 表加 status_color 列（幂等）"""
    if await _column_exists(db, "agents", "status_color"):
        logger.info("  ⏭ agents.status_color 已存在，跳过")
        return
    logger.info("  🎨 添加 agents.status_color 列")
    await db.execute(text("ALTER TABLE agents ADD COLUMN status_color VARCHAR(20)"))
    await db.flush()
    logger.info("  ✅ agents.status_color 添加完成")


async def _migrate_opencli_default_enabled(db):
    """v1.0.2: opencli_command_whitelist 加 default_enabled 列（幂等）"""
    if await _column_exists(db, "opencli_command_whitelist", "default_enabled"):
        logger.info("  ⏭ opencli_command_whitelist.default_enabled 已存在，跳过")
        return
    logger.info("  ➕ 添加 opencli_command_whitelist.default_enabled 列")
    await db.execute(text(
        "ALTER TABLE opencli_command_whitelist ADD COLUMN default_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    await db.flush()
    logger.info("  ✅ default_enabled 列已添加")


async def _migrate_ai_friend_user_id(db):
    """v1.0.2: friendships 表中 AI 好友的 friend_id 统一为 agent.user_id（幂等）"""
    from app.models.agent import Agent

    # 查所有 AI，构建 id→user_id 映射
    agent_result = await db.execute(select(Agent.id, Agent.user_id))
    id_to_uid = {row[0]: row[1] for row in agent_result.all() if row[1]}

    # 查所有 AI 好友记录
    friendships_result = await db.execute(
        text("SELECT id, user_id, friend_id FROM friendships WHERE friend_type = 'ai'")
    )
    f_rows = friendships_result.all()

    # 收集需要处理的
    current_set = {(r[1], r[2]) for r in f_rows}  # (user_id, friend_id)
    to_delete = []
    to_update = []

    for f_id, f_user_id, f_friend_id in f_rows:
        new_id = id_to_uid.get(f_friend_id)
        if new_id is None or new_id == f_friend_id:
            continue  # 找不到 agent 或已经正确
        if (f_user_id, new_id) in current_set:
            to_delete.append(f_id)  # 目标已存在，删旧的
        else:
            to_update.append((f_id, new_id))

    if to_delete:
        await db.execute(text(f"DELETE FROM friendships WHERE id IN ({','.join(map(str, to_delete))})"))
        logger.info(f"  🧹 删除 {len(to_delete)} 条重复 AI 好友记录")

    for f_id, new_id in to_update:
        await db.execute(text(
            "UPDATE friendships SET friend_id = :uid WHERE id = :fid"
        ), {"uid": new_id, "fid": f_id})
    if to_update:
        logger.info(f"  🔄 更新 {len(to_update)} 条 AI 好友 friend_id → user_id")

    if not to_delete and not to_update:
        logger.info("  ⏭ AI 好友 friend_id 已统一，跳过")


async def _migrate_group_concurrent_limit(db):
            await _migrate_group_msg_display_len(db)   # v2.0.5 群聊消息折叠长度
    """v2.0.4: groups 添加 concurrent_ai_limit 列（群主/管理可调的同群AI并发数）"""
    if await _column_exists(db, "groups", "concurrent_ai_limit"):
        logger.info("  ⏭ groups.concurrent_ai_limit 已存在，跳过")
        return
    logger.info("  🔧 添加 groups.concurrent_ai_limit 列")
    await db.execute(text("ALTER TABLE groups ADD COLUMN concurrent_ai_limit INTEGER DEFAULT 3"))
    await db.flush()
    logger.info("  ✅ groups.concurrent_ai_limit 添加完成")

async def _migrate_group_msg_display_len(db):
    """v2.0.5: groups 添加 max_msg_display_len 列（群聊消息截断，默认256字，0=不截断）"""
    if await _column_exists(db, "groups", "max_msg_display_len"):
        logger.info("  ⏭ groups.max_msg_display_len 已存在，跳过")
        return
    logger.info("  📏 添加 groups.max_msg_display_len 列")
    await db.execute(text("ALTER TABLE groups ADD COLUMN max_msg_display_len INTEGER DEFAULT 256"))
    await db.flush()
    logger.info("  ✅ groups.max_msg_display_len 添加完成")
