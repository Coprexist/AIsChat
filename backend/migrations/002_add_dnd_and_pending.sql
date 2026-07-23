-- ============================================================
-- 迁移 002: 消息免打扰 + 消息聚合 + 摘要缓存
-- 执行方式: docker compose exec postgres psql -U ai_chat -d ai_group_chat -f /docker-entrypoint-initdb.d/../migrations/002_add_dnd_and_pending.sql
-- 幂等性: 所有操作使用 IF NOT EXISTS / IF EXISTS 保证可重复执行
-- ============================================================

BEGIN;

-- 1. group_members 加 DND 列
--    NULL = 永久免打扰; 有值 = 临时免打扰截止时间
ALTER TABLE group_members ADD COLUMN IF NOT EXISTS dnd_until TIMESTAMP NULL;

-- 2. agents 加意愿评分和暂停字段
ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_paused BOOLEAN DEFAULT FALSE;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS auto_dnd_threshold INT DEFAULT 20;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS auto_dnd_duration INT DEFAULT 5;

-- 3. 暂存消息表（AI 离线/免打扰/暂停期间的消息积压）
CREATE TABLE IF NOT EXISTS pending_messages (
    id SERIAL PRIMARY KEY,
    agent_id INT REFERENCES agents(id) ON DELETE CASCADE,
    group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    message_id INT REFERENCES messages(id) ON DELETE CASCADE,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pending_msg_agent ON pending_messages(agent_id, is_read);
CREATE INDEX IF NOT EXISTS idx_pending_msg_group ON pending_messages(agent_id, group_id, is_read);

-- 4. 摘要缓存表
--    key = agent_id + group_id; 过期时间 10 分钟
CREATE TABLE IF NOT EXISTS unread_summary_cache (
    id SERIAL PRIMARY KEY,
    agent_id INT REFERENCES agents(id) ON DELETE CASCADE,
    group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    message_count INT,
    last_message_at TIMESTAMP,
    cached_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '10 minutes')
);
CREATE INDEX IF NOT EXISTS idx_summary_cache_lookup
    ON unread_summary_cache(agent_id, group_id, expires_at);

-- 定期清理过期缓存（可选：通过 pg_cron 或应用层定时任务）
-- 如果不用 pg_cron，应用层在查询时自动过滤 expires_at < NOW()

COMMIT;

-- 验证
SELECT 'Migration 002 completed' AS status;
