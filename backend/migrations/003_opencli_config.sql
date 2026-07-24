-- ============================================================
-- 迁移 003: OpenCLI 权限配置表
-- 执行方式: docker compose exec postgres psql -U ai_chat -d ai_group_chat -f /docker-entrypoint-initdb.d/../migrations/003_opencli_config.sql
-- 幂等性: 所有操作使用 IF NOT EXISTS / ON CONFLICT DO NOTHING 保证可重复执行
-- ============================================================

BEGIN;

-- 1. 全局配置（单行表，id=1 固定）
CREATE TABLE IF NOT EXISTS opencli_config (
    id INT PRIMARY KEY DEFAULT 1,
    global_enabled BOOLEAN DEFAULT FALSE,
    default_rate_limit_per_minute INT DEFAULT 5,
    timeout_seconds INT DEFAULT 30,
    updated_by INT REFERENCES users(id),
    updated_at TIMESTAMP DEFAULT NOW()
);
INSERT INTO opencli_config (id, global_enabled) VALUES (1, FALSE)
  ON CONFLICT (id) DO NOTHING;

-- 2. 每个 AI 是否启用 OpenCLI（白名单）
CREATE TABLE IF NOT EXISTS opencli_agent_whitelist (
    agent_id INT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT FALSE,
    rate_limit_override INT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. 命令白名单（精确匹配或正则）
CREATE TABLE IF NOT EXISTS opencli_command_whitelist (
    id SERIAL PRIMARY KEY,
    pattern VARCHAR(200) NOT NULL,
    is_regex BOOLEAN DEFAULT FALSE,
    description VARCHAR(200),
    enabled BOOLEAN DEFAULT TRUE,
    created_by INT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. 使用日志（审计 + 速率限制辅助）
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
CREATE INDEX IF NOT EXISTS idx_opencli_log_agent_time
    ON opencli_usage_log(agent_id, executed_at);

-- 5. 默认拒绝的命令（黑名单，无法通过白名单放行）
CREATE TABLE IF NOT EXISTS opencli_denied_commands (
    pattern VARCHAR(200) PRIMARY KEY,
    reason VARCHAR(200)
);
INSERT INTO opencli_denied_commands (pattern, reason) VALUES
    ('rm', '删除文件'),
    ('sudo', '提权操作'),
    ('chmod', '修改权限'),
    ('chown', '修改所有者'),
    ('mkfs', '格式化文件系统'),
    ('dd', '磁盘写入'),
    ('shutdown', '系统关机'),
    ('reboot', '系统重启'),
    ('kill', '终止进程'),
    ('curl.*pipe.*sh', '管道执行远程脚本'),
    ('eval', '代码执行'),
    ('exec', '代码执行')
ON CONFLICT (pattern) DO NOTHING;

COMMIT;

SELECT 'Migration 003 completed' AS status;
