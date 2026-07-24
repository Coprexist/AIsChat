-- 005_backfill_friendhips.sql
-- 为已有 AI 补建好友关系（创建 AI 时自动加好友逻辑未覆盖存量数据）
BEGIN;

INSERT INTO friendships (user_id, friend_type, friend_id, created_at)
SELECT a.owner_id, 'ai', a.id, a.created_at
FROM agents a
WHERE NOT EXISTS (
    SELECT 1 FROM friendships f
    WHERE f.user_id = a.owner_id AND f.friend_type = 'ai' AND f.friend_id = a.id
);

COMMIT;
