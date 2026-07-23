# 数据库迁移

## 迁移文件

| 文件 | 说明 | 依赖 |
|------|------|------|
| `../backend/init-db.sql` | 初始建表脚本（Docker 首次启动自动执行） | 无 |
| `002_add_dnd_and_pending.sql` | 消息免打扰 + 暂存消息 + 摘要缓存 | 001 (init-db.sql) |
| `003_opencli_config.sql` | OpenCLI 权限配置（全局开关、AI 白名单、命令白名单、使用日志、黑名单） | 002 |

## 执行方式

```bash
# 在运行的 postgres 容器中执行
docker compose exec postgres psql -U ai_chat -d ai_group_chat \
  -f /docker-entrypoint-initdb.d/../migrations/003_opencli_config.sql
```

所有迁移脚本使用 `IF NOT EXISTS` / `ON CONFLICT DO NOTHING` 保证幂等，可安全重复执行。
