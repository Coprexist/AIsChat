-- ============================================================
-- 迁移 007: 用户偏好（群/私信置顶、特别关心）
-- ============================================================
BEGIN;

-- 群聊置顶偏好
CREATE TABLE IF NOT EXISTS user_group_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    is_pinned BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, group_id)
);

-- 私信置顶 & 特别关心偏好
CREATE TABLE IF NOT EXISTS user_dm_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(64) NOT NULL REFERENCES dm_sessions(session_id) ON DELETE CASCADE,
    is_pinned BOOLEAN DEFAULT FALSE,
    is_special_care BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, session_id)
);

COMMIT;
