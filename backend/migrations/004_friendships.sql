-- 好友系统
BEGIN;

CREATE TABLE IF NOT EXISTS friendships (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    friend_type VARCHAR(10) CHECK (friend_type IN ('human', 'ai')) NOT NULL,
    friend_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, friend_type, friend_id)
);

CREATE TABLE IF NOT EXISTS friendship_requests (
    id SERIAL PRIMARY KEY,
    requester_id INT REFERENCES users(id) ON DELETE CASCADE,
    target_type VARCHAR(10) CHECK (target_type IN ('human', 'ai')) NOT NULL,
    target_id INT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fr_requester ON friendship_requests(requester_id, status);
CREATE INDEX IF NOT EXISTS idx_fr_target ON friendship_requests(target_type, target_id, status);
CREATE INDEX IF NOT EXISTS idx_friends_user ON friendships(user_id);

COMMIT;
