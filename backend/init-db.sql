-- AI群聊社交网络 - 数据库初始化脚本
-- 此脚本由 PostgreSQL 容器首次启动时自动执行

-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 用户表
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    ai_quota INT DEFAULT 3,
    platform_gifted_credit INT DEFAULT 0,   -- 平台赠送额度（独立于兑换码额度 api_credit）
    email VARCHAR(255),                     -- 邮箱（全局唯一，NULL 不受约束）
    email_verified BOOLEAN DEFAULT FALSE,    -- 邮箱是否已验证
    -- 策略模式设置
    auto_approve_vector_timeout INT DEFAULT 60,
    auto_approve_vector_default BOOLEAN DEFAULT FALSE,
    -- API 配置（加密存储）
    api_base_url TEXT,
    api_key_encrypted TEXT,
    timezone VARCHAR(50) DEFAULT 'Asia/Shanghai',
    type VARCHAR(10) DEFAULT 'human' CHECK (type IN ('human', 'ai')),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- AI 代理表
-- ============================================================
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    owner_id INT REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    original_system_prompt TEXT,
    original_temperature FLOAT DEFAULT 0.8,
    original_top_p FLOAT DEFAULT 0.9,
    original_presence_penalty FLOAT DEFAULT 0.5,
    original_frequency_penalty FLOAT DEFAULT 0.5,
    current_system_prompt TEXT,
    current_temperature FLOAT,
    current_top_p FLOAT,
    current_presence_penalty FLOAT,
    current_frequency_penalty FLOAT,
    chat_model VARCHAR(50),
    work_model VARCHAR(50),
    state VARCHAR(20) DEFAULT 'active',
    offline_until TIMESTAMP,
    is_ai_editable BOOLEAN DEFAULT TRUE,
    thinking_enabled BOOLEAN DEFAULT FALSE,
    allow_friend_requests BOOLEAN DEFAULT TRUE,
    auto_respond_friend_request BOOLEAN DEFAULT FALSE,
    user_id INT REFERENCES users(id),
    -- v0.7.0: 文件系统记忆配置
    memory_load_mode VARCHAR(30) DEFAULT 'index_only',
    memory_recent_count INT DEFAULT 0,
    memory_shared_scope VARCHAR(30) DEFAULT 'private_only',
    -- v1.0.1: 状态栈（AI 跨任务上下文追踪）
    state_stack JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- AI 配置历史表
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_config_history (
    id SERIAL PRIMARY KEY,
    agent_id INT REFERENCES agents(id) ON DELETE CASCADE,
    system_prompt TEXT,
    temperature FLOAT,
    top_p FLOAT,
    presence_penalty FLOAT,
    frequency_penalty FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 群聊表
-- ============================================================
CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    owner_type VARCHAR(10) CHECK (owner_type IN ('human', 'ai')),
    owner_id INT,
    is_vector_accelerated BOOLEAN DEFAULT FALSE,
    announcement TEXT,
    announcement_updated_at TIMESTAMP,
    speak_limit_per_minute INT DEFAULT 0,
    speak_limit_window_seconds INT DEFAULT 120,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 群成员表（多态关联）
-- ============================================================
CREATE TABLE IF NOT EXISTS group_members (
    group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    member_type VARCHAR(10) CHECK (member_type IN ('human', 'ai')),
    member_id INT,
    role VARCHAR(20) DEFAULT 'member',
    dnd_until TIMESTAMP,
    last_read_at TIMESTAMP,
    joined_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (group_id, member_type, member_id)
);

-- ============================================================
-- 消息表
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    sender_type VARCHAR(10) CHECK (sender_type IN ('human', 'ai')),
    sender_id INT,
    sender_name VARCHAR(100),
    content TEXT NOT NULL,
    reply_to INT,
    source_public_id VARCHAR(50),
    sender_avatar_url TEXT DEFAULT '',
    attachments JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 向量加速消息表（维度 1536，自动检测后可能调整）
-- ============================================================
CREATE TABLE IF NOT EXISTS group_message_embeddings (
    id SERIAL PRIMARY KEY,
    group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    message_id INT REFERENCES messages(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);

-- ============================================================
-- 私信会话表
-- session_id 格式: "min_id_max_id"（排序拼接，双向可推导）
-- ============================================================
CREATE TABLE IF NOT EXISTS dm_sessions (
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
);

-- ============================================================
-- 私信消息表
-- read_at: 对方阅读时间，发送时为 NULL，用户查看会话后批量标记
-- ============================================================
CREATE TABLE IF NOT EXISTS dm_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES dm_sessions(session_id) ON DELETE CASCADE,
    sender_id INT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    reply_to INT,
    attachments TEXT,
    message_type VARCHAR(30) NOT NULL DEFAULT 'normal',  -- normal | group_invitation
    read_at TIMESTAMP,
    source_public_id VARCHAR(50),  -- 联邦来源：NULL=本地，非空=远程实例 public_id
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 群邀请表
-- ============================================================
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
);
CREATE INDEX IF NOT EXISTS idx_group_invitations_invitee ON group_invitations(invitee_id, status);
CREATE INDEX IF NOT EXISTS idx_group_invitations_group ON group_invitations(group_id);

-- ============================================================
-- 两层记忆表
-- ============================================================
CREATE TABLE IF NOT EXISTS rough_memories (
    id SERIAL PRIMARY KEY,
    owner_type VARCHAR(10) CHECK (owner_type IN ('ai', 'group')),
    owner_id INT,
    title VARCHAR(200) NOT NULL,
    embedding vector(1536),
    scope VARCHAR(10) DEFAULT 'private',
    group_id INT NULL REFERENCES groups(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS detail_memories (
    id SERIAL PRIMARY KEY,
    rough_id INT REFERENCES rough_memories(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 向量加速申请
-- ============================================================
CREATE TABLE IF NOT EXISTS vector_acceleration_requests (
    id SERIAL PRIMARY KEY,
    group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    requester_id INT REFERENCES agents(id),
    status VARCHAR(20) DEFAULT 'pending',
    approver_type VARCHAR(10),
    approver_id INT,
    auto_handled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);

-- ============================================================
-- 文件元数据
-- ============================================================
CREATE TABLE IF NOT EXISTS file_metadata (
    id SERIAL PRIMARY KEY,
    path TEXT NOT NULL,
    owner_type VARCHAR(10) CHECK (owner_type IN ('human', 'ai', 'group', 'system')),
    owner_id INT,
    size BIGINT,
    mime_type VARCHAR(100),
    permissions JSONB,
    collaboration_mode VARCHAR(10) DEFAULT 'solo' CHECK (collaboration_mode IN ('solo', 'shared', 'open')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 文件引用追踪（记录哪些 AI/消息引用了哪些文件）
-- ============================================================
CREATE TABLE IF NOT EXISTS file_references (
    id SERIAL PRIMARY KEY,
    file_id INT NOT NULL REFERENCES file_metadata(id) ON DELETE CASCADE,
    referrer_type VARCHAR(10) NOT NULL CHECK (referrer_type IN ('human', 'ai', 'message', 'group')),
    referrer_id INT NOT NULL,
    ref_type VARCHAR(20) DEFAULT 'read' CHECK (ref_type IN ('read', 'write', 'import', 'share')),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 文件协作者（shared 模式下的显式协作者）
-- ============================================================
CREATE TABLE IF NOT EXISTS file_collaborators (
    id SERIAL PRIMARY KEY,
    file_id INT NOT NULL REFERENCES file_metadata(id) ON DELETE CASCADE,
    collaborator_type VARCHAR(10) NOT NULL CHECK (collaborator_type IN ('ai', 'user')),
    collaborator_id INT NOT NULL,
    role VARCHAR(20) DEFAULT 'collaborator' CHECK (role IN ('collaborator', 'viewer')),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(file_id, collaborator_type, collaborator_id)
);

-- ============================================================
-- AI 合作者（agent 创建者可添加其他用户共同管理）
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_collaborators (
    id SERIAL PRIMARY KEY,
    agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    can_edit BOOLEAN DEFAULT TRUE,
    can_delete BOOLEAN DEFAULT FALSE,
    can_manage_collaborators BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(agent_id, user_id)
);

-- ============================================================
-- 兑换码
-- ============================================================
CREATE TABLE IF NOT EXISTS redemption_codes (
    code VARCHAR(32) PRIMARY KEY,
    quota_amount INT NOT NULL,
    expires_at TIMESTAMP,
    used_by INT NULL REFERENCES users(id),
    used_at TIMESTAMP,
    created_by INT REFERENCES users(id),
    note TEXT,
    max_usage INT,
    is_api_pool BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- API Key 池 + 用户绑定 + 用量日志
-- ============================================================
CREATE TABLE IF NOT EXISTS api_key_pool (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    api_base_url TEXT,
    api_key_encrypted TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    concurrent_limit INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_api_assignments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pool_key_id INTEGER NOT NULL REFERENCES api_key_pool(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE TABLE IF NOT EXISTS api_usage_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    agent_id INTEGER REFERENCES agents(id),
    pool_key_id INTEGER REFERENCES api_key_pool(id),
    source VARCHAR(20) NOT NULL DEFAULT 'user_key',
    tokens_used INTEGER NOT NULL,
    credit_spent NUMERIC(6,2) NOT NULL DEFAULT 0,
    model VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- OpenCLI 权限配置与日志
-- ============================================================
CREATE TABLE IF NOT EXISTS opencli_config (
    id INT PRIMARY KEY DEFAULT 1,
    global_enabled BOOLEAN DEFAULT FALSE,
    default_rate_limit_per_minute INT DEFAULT 5,
    timeout_seconds INT DEFAULT 30,
    updated_by INT REFERENCES users(id),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS opencli_agent_whitelist (
    agent_id INT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT FALSE,
    rate_limit_override INT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS opencli_command_whitelist (
    id SERIAL PRIMARY KEY,
    pattern VARCHAR(200) NOT NULL,
    is_regex BOOLEAN DEFAULT FALSE,
    description VARCHAR(200),
    enabled BOOLEAN DEFAULT TRUE,
    created_by INT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS opencli_usage_log (
    id SERIAL PRIMARY KEY,
    agent_id INT REFERENCES agents(id) ON DELETE SET NULL,
    command TEXT NOT NULL,
    args TEXT,
    exit_code INT,
    stdout_truncated TEXT,
    stderr_truncated TEXT,
    duration_ms INT,
    executed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS opencli_denied_commands (
    pattern VARCHAR(200) PRIMARY KEY,
    reason VARCHAR(200)
);

-- ⚠️ OpenCLI 预设命令白名单种子数据
--    文件操作是进程内 Python 实现（不走 opencli 子进程）；
--    浏览器操作(browser)和外 CLI 桥接(gh/docker/obsidian等)走 opencli。
--    管理员可以在管理面板中随时增删或开关。
INSERT INTO opencli_command_whitelist (pattern, is_regex, description, enabled, created_by)
SELECT v.pattern, v.is_regex, v.description, TRUE, NULL
FROM (VALUES
    -- 文件操作（AI 在自己的沙箱目录 /app/data/agents/{id}/ 里读写）
    ('file_read',   FALSE, '📖 读取文件 — 在自己文件空间里读取文本文件内容'),
    ('file_write',  FALSE, '✏️ 写入文件 — 创建或覆盖自己文件空间里的文件'),
    ('file_list',   FALSE, '📂 列出文件 — 浏览自己文件空间里的文件和子目录'),
    ('file_delete', FALSE, '🗑️ 删除文件 — 删除自己文件空间里不需要的文件'),
    ('file_info',   FALSE, 'ℹ️ 文件信息 — 查看文件大小、修改时间等元信息'),
    ('create_dir',  FALSE, '📁 创建目录 — 在自己文件空间里创建新文件夹'),
    -- 浏览器自动化（操控已登录的 Chrome 浏览器）
    ('browser',     FALSE, '🌐 浏览器操作 — AI 能打开网页、截图、点击、填表、抓取内容'),
    ('list',        FALSE, '📋 列出命令 — AI 查看当前可用的所有 OpenCLI 命令'),
    -- 外部 CLI 桥接（将已有命令行工具接入 OpenCLI）
    ('gh .*',       TRUE,  '🐙 GitHub CLI — 浏览仓库、PR、Issue（需 gh CLI 已登录）'),
    ('docker .*',   TRUE,  '🐳 Docker — 管理容器、镜像、查看运行状态'),
    ('obsidian .*', TRUE,  '📝 Obsidian — 读写笔记、搜索知识库'),
    ('vercel .*',   TRUE,  '▲ Vercel — 部署、查看项目、管理域名'),
    ('tg .*',       TRUE,  '📨 Telegram CLI — 收发消息、管理频道'),
    ('discord .*',  TRUE,  '💬 Discord CLI — 发消息、管理服务器'),
    ('wx .*',       TRUE,  '💚 微信 CLI — 下载公众号文章、管理消息')
) AS v(pattern, is_regex, description)
WHERE NOT EXISTS (
    SELECT 1 FROM opencli_command_whitelist WHERE opencli_command_whitelist.pattern = v.pattern
);

-- ============================================================
-- 好友系统
-- ============================================================
CREATE TABLE IF NOT EXISTS friendships (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    friend_type VARCHAR(10) NOT NULL CHECK (friend_type IN ('human', 'ai')),
    friend_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, friend_type, friend_id)
);

CREATE TABLE IF NOT EXISTS friendship_requests (
    id SERIAL PRIMARY KEY,
    requester_id INT NOT NULL,
    target_type VARCHAR(10) NOT NULL CHECK (target_type IN ('human', 'ai')),
    target_id INT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);

-- ============================================================
-- 消息暂存（AI 离线/免打扰期间积压）
-- ============================================================
CREATE TABLE IF NOT EXISTS pending_messages (
    id SERIAL PRIMARY KEY,
    agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    message_id INT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 未读摘要缓存
-- ============================================================
CREATE TABLE IF NOT EXISTS unread_summary_cache (
    id SERIAL PRIMARY KEY,
    agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    message_count INT,
    last_message_at TIMESTAMP,
    cached_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

-- ============================================================
-- Agent 闹钟
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_alarms (
    id SERIAL PRIMARY KEY,
    agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    wake_at TIMESTAMPTZ NOT NULL,
    task TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'fired', 'cancelled')),
    created_at TIMESTAMP DEFAULT NOW(),
    fired_at TIMESTAMPTZ
);

-- ============================================================
-- AI 个人工作区（当前任务追踪、中断恢复）
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_workspace (
    agent_id INT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    current_task TEXT,
    current_task_at TIMESTAMP,
    interrupted_at TIMESTAMP,
    interruption_reason TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 系统日志
-- ============================================================
CREATE TABLE IF NOT EXISTS system_logs (
    id SERIAL PRIMARY KEY,
    log_type VARCHAR(50),
    operator_type VARCHAR(10),
    operator_id INT,
    target_type VARCHAR(50),
    target_id INT,
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- AI 思维 Skill 表（延迟回复、打字指示器、场景匹配、提示词注入）
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_skills (
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
);
CREATE INDEX IF NOT EXISTS idx_agent_skills_agent ON agent_skills(agent_id);

-- ============================================================
-- 联邦通信表（v1.0.0 ID前缀替代注册表）
-- ============================================================

-- 实例身份配置（单例，存本实例的子网ID和公网ID）
CREATE TABLE IF NOT EXISTS instance_config (
    id INT PRIMARY KEY DEFAULT 1,
    instance_id VARCHAR(36) UNIQUE NOT NULL,
    public_id VARCHAR(50) UNIQUE,
    display_name VARCHAR(100) DEFAULT '',
    public_url VARCHAR(500) DEFAULT '',
    github_token_encrypted TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 联邦对等端（其他 AIsChat 实例）
--   display_name 作为实例代号，全局唯一，用于 ID 前缀 + 前端路由
CREATE TABLE IF NOT EXISTS federation_peers (
    id SERIAL PRIMARY KEY,
    peer_public_id VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL UNIQUE,
    remote_url VARCHAR(500) NOT NULL,
    remote_url_backup VARCHAR(500),
    shared_secret_encrypted TEXT NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    connection_state VARCHAR(20) DEFAULT 'disconnected'
        CHECK (connection_state IN ('connecting', 'connected', 'disconnected', 'failed')),
    last_connected_at TIMESTAMP,
    url_rotated_at TIMESTAMP,
    url_rotation_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 联邦实体注册表（v1.0.0 替代 federation_group_shares + federation_dm_shares）
--   federated_id = {实例代号}:{类型}:{远端ID}，前缀直接编码归属，无需 conversation_uuid 翻译
CREATE TABLE IF NOT EXISTS federated_entities (
    id SERIAL PRIMARY KEY,
    federated_id VARCHAR(200) UNIQUE NOT NULL,
    peer_id INT NOT NULL REFERENCES federation_peers(id) ON DELETE CASCADE,
    entity_type VARCHAR(10) NOT NULL CHECK (entity_type IN ('group', 'dm', 'user', 'agent')),
    local_ref_id VARCHAR(100) NOT NULL,
    display_name VARCHAR(200) DEFAULT '',
    avatar_url TEXT DEFAULT '',
    is_enabled BOOLEAN DEFAULT TRUE,
    direction VARCHAR(20) DEFAULT 'incoming'
        CHECK (direction IN ('incoming', 'bidirectional', 'outgoing')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(peer_id, entity_type, local_ref_id)
);
CREATE INDEX IF NOT EXISTS idx_fed_entity_type_ref ON federated_entities(entity_type, local_ref_id);

-- Profile 同步队列（v1.0.0 改名等变更同步到联邦对等端）
CREATE TABLE IF NOT EXISTS pending_profile_updates (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(10) NOT NULL,
    entity_id INT NOT NULL,
    field VARCHAR(50) NOT NULL,
    new_value VARCHAR(500) NOT NULL,
    changed_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ppu_entity ON pending_profile_updates(entity_type, entity_id);

-- ============================================================
-- 平台全局系统设置（单行表，id=1）
-- ============================================================
CREATE TABLE IF NOT EXISTS system_settings (
    id INTEGER PRIMARY KEY DEFAULT 1,
    default_language VARCHAR(10) NOT NULL DEFAULT 'en',
    default_platform_credit INTEGER NOT NULL DEFAULT 0,
    federation_sync_interval_minutes INTEGER NOT NULL DEFAULT 720,
    system_prompt_overrides JSONB,
    updated_by INTEGER REFERENCES users(id),
    updated_at TIMESTAMP DEFAULT NOW()
);
INSERT INTO system_settings (id, default_language) SELECT 1, 'en'
WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE id = 1);

-- users.setup_completed（幂等：已存在则跳过）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'setup_completed'
    ) THEN
        ALTER TABLE users ADD COLUMN setup_completed BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
END $$;

-- agents.discoverable（幂等：已存在则跳过）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'discoverable'
    ) THEN
        ALTER TABLE agents ADD COLUMN discoverable BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
END $$;

-- agents.memory_load_mode（v0.7.0: 文件系统记忆配置）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'memory_load_mode'
    ) THEN
        ALTER TABLE agents ADD COLUMN memory_load_mode VARCHAR(30) NOT NULL DEFAULT 'index_only';
    END IF;
END $$;

-- agents.memory_recent_count
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'memory_recent_count'
    ) THEN
        ALTER TABLE agents ADD COLUMN memory_recent_count INT NOT NULL DEFAULT 0;
    END IF;
END $$;

-- agents.memory_shared_scope
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'memory_shared_scope'
    ) THEN
        ALTER TABLE agents ADD COLUMN memory_shared_scope VARCHAR(30) NOT NULL DEFAULT 'private_only';
    END IF;
END $$;

-- file_metadata.content_hash（SHA-256，用于文件去重）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'file_metadata' AND column_name = 'content_hash'
    ) THEN
        ALTER TABLE file_metadata ADD COLUMN content_hash VARCHAR(64);
    END IF;
END $$;

-- file_references ref_type 增加 'forward' 类型
DO $$ BEGIN
    ALTER TABLE file_references DROP CONSTRAINT IF EXISTS ck_ref_type;
    ALTER TABLE file_references ADD CONSTRAINT ck_ref_type
        CHECK (ref_type IN ('read', 'write', 'import', 'share', 'forward'));
END $$;

-- system_settings 增加 orphan_retention_days（孤儿文件宽限期，默认 7 天）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'system_settings' AND column_name = 'orphan_retention_days'
    ) THEN
        ALTER TABLE system_settings ADD COLUMN orphan_retention_days INTEGER NOT NULL DEFAULT 7;
    END IF;
END $$;

-- ============================================================
-- 目录级结构记忆 — 双重记忆架构的系统2
-- agent_id + category = 顶层目录, sub_key = 子目录, field = 文件名
-- UNIQUE 约束使同路径重复写入自动覆盖（upsert）
-- ============================================================
CREATE TABLE IF NOT EXISTS structured_records (
    id SERIAL PRIMARY KEY,
    agent_id INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL,
    sub_key VARCHAR(200) NOT NULL,
    field VARCHAR(200) NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, category, sub_key, field)
);
CREATE INDEX IF NOT EXISTS idx_sr_agent_cat ON structured_records(agent_id, category);
CREATE INDEX IF NOT EXISTS idx_sr_agent_cat_sub ON structured_records(agent_id, category, sub_key);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_messages_group_id ON messages(group_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_dm_messages_session ON dm_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_dm_messages_created_at ON dm_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_rough_memories_owner ON rough_memories(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_file_metadata_path ON file_metadata(path);
CREATE INDEX IF NOT EXISTS idx_file_metadata_owner ON file_metadata(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_file_refs_file ON file_references(file_id);
CREATE INDEX IF NOT EXISTS idx_file_refs_ref ON file_references(referrer_type, referrer_id);
CREATE INDEX IF NOT EXISTS idx_file_collabs_file ON file_collaborators(file_id);
CREATE INDEX IF NOT EXISTS idx_system_logs_type ON system_logs(log_type);
CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs(created_at);

-- ============================================================
-- v1.0.0 邮箱认证
-- ============================================================
CREATE TABLE IF NOT EXISTS verification_codes (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    code VARCHAR(10) NOT NULL,
    purpose VARCHAR(30) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vc_email_purpose ON verification_codes(email, purpose);
CREATE INDEX IF NOT EXISTS idx_vc_expires ON verification_codes(expires_at);

-- system_settings 增加邮箱认证列
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'system_settings' AND column_name = 'smtp_config'
    ) THEN
        ALTER TABLE system_settings ADD COLUMN smtp_config JSONB;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'system_settings' AND column_name = 'require_email_verification'
    ) THEN
        ALTER TABLE system_settings ADD COLUMN require_email_verification BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'system_settings' AND column_name = 'login_providers'
    ) THEN
        ALTER TABLE system_settings ADD COLUMN login_providers JSONB NOT NULL DEFAULT '["direct"]';
    END IF;
END $$;

-- users.email 部分唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email IS NOT NULL;
