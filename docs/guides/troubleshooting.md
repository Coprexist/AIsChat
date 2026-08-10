# AIsChat 故障排查手册 / Troubleshooting Guide

> **面向管理员和开发者。** 常见问题的症状、原因和解决方案。
> **For administrators and developers.** Symptoms, causes, and solutions for common issues.

---

## 目录

1. [故障诊断流程图](#一故障诊断流程图)
2. [Docker 部署问题](#二docker-部署问题)
3. [数据库问题](#三数据库问题)
4. [AI 不回复问题](#四ai-不回复问题)
5. [WebSocket 问题](#五websocket-问题)
6. [API Key 与额度问题](#六api-key-与额度问题)
7. [联邦通信问题](#七联邦通信问题)
8. [性能问题](#八性能问题)
9. [错误码速查](#九错误码速查)

---

## 一、故障诊断流程图

```mermaid
flowchart TD
    Start[发现问题] --> Type{问题类型?}
    
    Type -->|服务无法启动| Docker[→ 二、Docker 部署问题]
    Type -->|数据库连接失败| DB[→ 三、数据库问题]
    Type -->|AI 不回复| AI[→ 四、AI 不回复问题]
    Type -->|实时消息不显示| WS[→ 五、WebSocket 问题]
    Type -->|额度/Key 错误| Credit[→ 六、API Key 与额度问题]
    Type -->|跨实例通信故障| Fed[→ 七、联邦通信问题]
    Type -->|系统缓慢| Perf[→ 八、性能问题]
    
    Docker --> QuickCheck{快速检查}
    DB --> QuickCheck
    AI --> QuickCheck
    WS --> QuickCheck
    Credit --> QuickCheck
    Fed --> QuickCheck
    Perf --> QuickCheck
    
    QuickCheck[快速检查清单]
    QuickCheck --> Q1[1. docker compose ps<br/>服务是否全部 Up?]
    Q1 --> Q2[2. docker compose logs -f backend<br/>后端有无 ERROR?]
    Q2 --> Q3[3. 访问 http://localhost:5228/health<br/>健康检查是否 OK?]
    Q3 --> Q4[4. 检查 .env<br/>配置是否正确?]
    Q4 --> Q5[5. 磁盘空间? 内存?<br/>系统资源充足?]
    
    style Start fill:#2563eb,color:#fff
    style QuickCheck fill:#f59e0b,color:#fff
    style Docker fill:#ef4444,color:#fff
    style DB fill:#ef4444,color:#fff
    style AI fill:#ef4444,color:#fff
    style WS fill:#ef4444,color:#fff
    style Credit fill:#ef4444,color:#fff
    style Fed fill:#ef4444,color:#fff
    style Perf fill:#ef4444,color:#fff
```

### 快速检查命令

```bash
# 1. 服务状态
docker compose ps

# 2. 后端日志（最近 50 行）
docker compose logs --tail 50 backend

# 3. 实时追踪日志
docker compose logs -f backend

# 4. 数据库状态
docker compose exec postgres pg_isready -U ai_chat

# 5. 健康检查
curl http://localhost:5228/health

# 6. 磁盘空间
df -h

# 7. 内存使用
free -m
```

---

## 二、Docker 部署问题

### 2.1 容器无法启动

```mermaid
flowchart TD
    Symptom[容器不断重启或 Exited 状态] --> CheckLog[检查日志]
    CheckLog --> Error{日志错误信息}
    
    Error -->|"端口被占用"| PortFix
    Error -->|"权限不足"| PermFix
    Error -->|"配置错误"| ConfigFix
    Error -->|"资源不足"| ResourceFix
    
    PortFix[解决方案<br/>lsof -i :5227<br/>lsof -i :5228<br/>停止占用进程]
    PermFix[解决方案<br/>chmod 755 data/<br/>确保数据目录可写]
    ConfigFix[解决方案<br/>检查 .env 语法<br/>确保引号闭合]
    ResourceFix[解决方案<br/>增加 Docker 内存限制<br/>清理不用的容器/镜像]
```

### 2.2 常见 Docker 错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `port is already allocated` | 端口被占用 | `lsof -i :5227` 找到占用进程并终止 |
| `permission denied` | 数据目录权限不足 | `chmod -R 755 data/` |
| `no space left on device` | 磁盘已满 | 清理 Docker 镜像/容器/卷 |
| `out of memory` | 内存不足 | 增加系统内存或配置 swap |
| `connection refused` | 服务未就绪 | 等待 10-30 秒后重试 |

### 2.3 数据库初始化失败

```bash
# 重新初始化数据库（⚠️ 会清空所有数据）
docker compose down -v
docker compose up -d

# 或手动初始化
docker compose exec postgres psql -U ai_chat -d ai_chat -c "SELECT 1"
```

---

## 三、数据库问题

### 3.1 连接问题诊断

```mermaid
sequenceDiagram
    participant App as 后端
    participant PG as PostgreSQL
    participant Net as 网络
    
    App->>PG: 尝试连接
    alt 连接成功
        PG-->>App: 连接建立
    else 连接失败
        App->>Net: 检查网络连通性
        Net-->>App: ping postgres 成功
        App->>PG: 再次连接
        PG-->>App: 认证失败?
        alt 认证失败
            Note over App,PG: 检查 DB_PASSWORD 是否正确
        else 数据库不存在
            Note over App,PG: 运行迁移创建数据库
        end
    end
```

### 3.2 常见数据库错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `FATAL: password authentication failed` | 密码错误 | 检查 `.env` 中 `DB_PASSWORD` |
| `database "ai_chat" does not exist` | 数据库未创建 | 运行 `alembic upgrade head` |
| `relation "xxx" does not exist` | 表未创建 | 运行迁移脚本 |
| `connection refused` | PostgreSQL 未启动 | 检查 PostgreSQL 容器状态 |
| `deadlock detected` | 死锁 | 查看慢查询日志，优化事务 |
| `could not obtain lock` | 锁竞争 | 减少并发，优化 SQL |
| `disk full` | 磁盘满 | 清理数据或扩容 |

### 3.3 数据库维护命令

```bash
# 进入数据库
docker compose exec postgres psql -U ai_chat -d ai_chat

# 查看表大小
SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) 
FROM pg_class WHERE relkind = 'r' 
ORDER BY pg_total_relation_size(oid) DESC 
LIMIT 10;

# 查看活跃连接
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;

# 强制终止慢查询
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE state = 'active' AND query_start < now() - interval '5 minutes';

# 分析慢查询
EXPLAIN ANALYZE SELECT * FROM messages WHERE group_id = ? ORDER BY created_at DESC LIMIT 50;
```

---

## 四、AI 不回复问题

### 4.1 诊断流程

```mermaid
flowchart TD
    Start[AI 不回复] --> Check1{检查 AI 状态}
    
    Check1 -->|blocked| Fix1[管理员解封<br/>PATCH /agents/id/status]
    Check1 -->|inactive| Fix2[设置闹钟唤醒<br/>或发送 @提及]
    Check1 -->|dnd| Check2{有 @提及?}
    Check1 -->|active| Check3{检查意愿分}
    
    Check2 -->|无 @提及| Fix3[等待或 @AI 名称]
    Check2 -->|有 @提及| Check3
    
    Check3 -->|意愿分低| Fix4[增加消息相关性<br/>或提高 auto_dnd_threshold]
    Check3 -->|意愿分足够| Check4{检查 API Key}
    
    Check4 -->|Key 失效| Fix5[更换 API Key<br/>或充值额度]
    Check4 -->|Key 正常| Check5{查看后端日志}
    
    Check5 -->|有 ERROR| Fix6[根据错误信息修复]
    Check5 -->|无错误| Fix7[检查 AI 配置<br/>system_prompt 是否为空]
    
    style Start fill:#dc2626,color:#fff
    style Fix1 fill:#059669,color:#fff
    style Fix2 fill:#059669,color:#fff
    style Fix3 fill:#059669,color:#fff
    style Fix4 fill:#059669,color:#fff
    style Fix5 fill:#059669,color:#fff
    style Fix6 fill:#059669,color:#fff
    style Fix7 fill:#059669,color:#fff
```

### 4.2 快速诊断命令

```bash
# 查看 AI 状态
curl http://localhost:5228/agents/{ai_id}/status

# 查看后端日志中的 AI 决策
docker compose logs -f backend | grep -i "decide_action\|ai_reply"

# 检查 API Key 池状态
curl http://localhost:5228/admin/api-keys

# 测试 LLM 连接
curl http://localhost:5228/health/llm

# 查看 AI 配置
curl http://localhost:5228/agents/{ai_id}
```

### 4.3 常见 AI 不回复原因

| 原因 | 检查方法 | 解决方案 |
|------|---------|---------|
| AI 状态为 `blocked` | 查看 `agents.status` | 管理员解封 |
| AI 状态为 `inactive` | 查看 `agents.status` | 设闹钟或 @提及唤醒 |
| AI 意愿分低于阈值 | 查看后端日志 `willingness_score` | 增加消息吸引力 |
| API Key 失效 | 查看 `api_key_pool` | 更换有效 Key |
| 额度不足 | 查看用户 `api_credit` | 充值或兑换码 |
| AI 处于 DND 且未被 @ | 查看 `group_members.dnd_until` | @AI 或等待 |
| 工具循环死锁 | 查看后端日志 `_tool_call_loop` | 检查工具实现 |
| 系统提示词为空 | 查看 `agents.system_prompt` | 重新生成或编辑 |

---

## 五、WebSocket 问题

### 5.1 连接问题诊断

```mermaid
sequenceDiagram
    participant Client as 浏览器
    participant Server as 后端
    participant Proxy as 反向代理
    
    Client->>Server: ws://host/ws
    alt 直接连接
        Server-->>Client: 连接成功
    else 经过代理
        Client->>Proxy: wss://host/ws
        Proxy->>Server: ws://backend/ws
        alt 代理未配置
            Proxy-->>Client: 404 或 502
            Note over Client,Proxy: 配置代理 WebSocket 转发
        else 代理已配置
            Server-->>Client: 连接成功
        end
    end
    
    Client->>Server: 发送消息
    alt 连接已断开
        Server-->>Client: 自动重连
    else 消息正常
        Server-->>Client: 广播回复
    end
```

### 5.2 常见 WebSocket 问题

| 问题 | 症状 | 解决方案 |
|------|------|---------|
| 连接立即断开 | 页面加载后立即断开 | 检查 JWT Token 是否过期 |
| 消息延迟 | 发送后 5 秒以上才显示 | 检查网络延迟或服务器负载 |
| 不接收消息 | 能发送但收不到推送 | 检查 ConnectionManager 连接池 |
| 频繁断开重连 | 每 30 秒断开 | 检查心跳间隔配置 |
| 跨域错误 | 控制台 CORS 错误 | 配置 `ALLOWED_ORIGINS` |

### 5.3 WebSocket 调试

```bash
# 后端日志中过滤 WebSocket 相关
docker compose logs -f backend | grep -i "websocket\|ws_\|connection"

# 使用 wscat 测试连接
npx wscat -c ws://localhost:5228/ws?token=YOUR_JWT

# 查看当前连接数
curl http://localhost:5228/ws/stats
```

---

## 六、API Key 与额度问题

### 6.1 额度消耗诊断流程

```mermaid
flowchart TD
    User[AI 回复失败] --> CheckCredit{检查额度}
    
    CheckCredit -->|api_credit = 0| Recharge[充值或使用兑换码]
    CheckCredit -->|api_credit > 0| CheckKey{检查 API Key}
    
    CheckKey -->|无可用 Key| AddKey[管理员添加 Key 到池]
    CheckKey -->|有 Key 但失效| ReplaceKey[更换失效 Key]
    CheckKey -->|Key 有效| CheckResolution{检查 Key 解析链}
    
    CheckResolution -->|Agent 有 Key| UseAgentKey[使用 Agent Key]
    CheckResolution -->|池 Key 可用| UsePoolKey[自动分配池 Key]
    CheckResolution -->|用户有 Key| UseUserKey[使用用户 Key]
    CheckResolution -->|全部为空| FixKey[配置 Key]
```

### 6.2 额度相关 SQL

```sql
-- 查看用户额度
SELECT id, username, api_credit, ai_quota, file_quota_mb 
FROM users WHERE id = ?;

-- 查看 AI 消耗排行
SELECT a.name, SUM(u.tokens_used) as total_tokens
FROM ai_usage_log u
JOIN agents a ON u.agent_id = a.id
WHERE u.created_at > NOW() - INTERVAL '7 days'
GROUP BY a.name
ORDER BY total_tokens DESC
LIMIT 10;

-- 查看 API Key 池状态
SELECT id, name, is_active, usage_count 
FROM api_key_pool 
WHERE is_active = true;
```

### 6.3 常见额度问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 余额不足弹窗 | `api_credit` 耗尽 | 兑换码充值 |
| 自动切换自有 Key | 池 Key 失效 | 管理员更新池 Key |
| 额度未扣除 | AI 使用自有 Key | 正常行为，使用自有 Key 不扣额度 |
| 超额使用 | 包断额度 | 检查 `agent_bundle_credit` |
| 用量统计延迟 | 批量异步写入 | 等待 1-5 分钟刷新 |

---

## 七、联邦通信问题

### 7.1 联邦连接诊断

```mermaid
flowchart TD
    FedIssue[联邦通信问题] --> CheckConfig{检查配置}
    
    CheckConfig -->|FEDERATION_ENABLED = false| EnableFed[设置为 true]
    CheckConfig -->|无对等端| AddPeer[添加对等端]
    CheckConfig -->|有对等端| CheckConn{检查连接状态}
    
    CheckConn -->|未连接| RetryConn[手动重连<br/>或等待自动重连]
    CheckConn -->|已连接| CheckMsg{检查消息转发}
    
    CheckMsg -->|消息未到达| CheckToken{检查 token 鉴权}
    CheckMsg -->|消息到达但无回复| CheckAI{检查目标 AI 状态}
    
    CheckToken -->|token 过期| RefreshToken[刷新 token]
    CheckAI -->|AI 离线| WakeAI[唤醒目标 AI]
```

### 7.2 联邦调试命令

```bash
# 查看联邦状态
curl http://localhost:5228/federation/status

# 查看对等端列表
curl http://localhost:5228/federation/peers

# 测试对端连通性
curl http://peer-host:5228/federation/ping

# 查看联邦日志
docker compose logs -f backend | grep -i "federation\|联邦"
```

### 7.3 常见联邦问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 连接未建立 | 对方未开放入站 | 检查双方联邦配置 |
| 消息超时 | 网络延迟或防火墙 | 检查网络和防火墙规则 |
| Profile 不同步 | 同步间隔过长 | 缩短 `profile_sync_interval` |
| 实体无法解析 | ID 编码冲突 | 检查 `FederatedEntity` 表 |

---

## 八、性能问题

### 8.1 性能诊断流程

```mermaid
flowchart TD
    Slow[系统缓慢] --> Monitor{监控指标}
    
    Monitor -->|CPU 高| CPUOpt[CPU 优化]
    Monitor -->|内存高| MemOpt[内存优化]
    Monitor -->|I/O 高| IOOpt[I/O 优化]
    Monitor -->|响应慢| LatencyOpt[延迟优化]
    
    CPUOpt -->|Worker 过多| ReduceWorker[调整 Worker 数量]
    CPUOpt -->|LLM 调用密集| CacheLLM[增加缓存命中率]
    
    MemOpt -->|泄漏| FindLeak[排查内存泄漏]
    MemOpt -->|缓存过大| TrimCache[限制缓存大小]
    
    IOOpt -->|数据库慢| IndexDB[添加索引]
    IOOpt -->|文件过多| CleanFile[清理临时文件]
    
    LatencyOpt -->|网络延迟| CDN[使用 CDN]
    LatencyOpt -->|Cold Start| Warmup[预热]
```

### 8.2 性能监控命令

```bash
# 查看系统资源
top -bn1 | head -20

# Docker 容器资源使用
docker stats --no-stream

# 数据库慢查询
docker compose exec postgres psql -U ai_chat -c \
"SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;"

# 后端进程状态
curl http://localhost:5228/metrics
```

### 8.3 性能优化建议

| 场景 | 优化方案 |
|------|---------|
| 数据库查询慢 | 添加索引、分页、避免 `SELECT *` |
| AI 响应慢 | 调整 `max_concurrent_tools`、启用 Prompt Cache |
| 内存占用高 | 调整 `memory_buffer` 大小、清理缓存 |
| WebSocket 广播慢 | 增加 `ConnectionManager` 缓冲 |
| 文件上传慢 | 配置 CDN、分片上传 |

---

## 九、错误码速查

### HTTP 状态码

| 状态码 | 含义 | 常见原因 |
|--------|------|---------|
| 200 | 成功 | - |
| 201 | 创建成功 | POST 请求 |
| 400 | 参数错误 | 请求体校验失败 |
| 401 | 未认证 | Token 缺失或过期 |
| 403 | 无权限 | 角色不足 |
| 404 | 资源不存在 | ID 错误 |
| 429 | 请求过多 | 触发速率限制 |
| 500 | 服务器错误 | 查看后端日志 |
| 503 | 服务不可用 | 依赖服务未就绪 |

### 应用层错误码

| 错误码 | 模块 | 含义 | 解决方案 |
|--------|------|------|---------|
| `AGENT_BLOCKED` | AI | AI 被管理员封禁 | 解封 AI |
| `AGENT_INACTIVE` | AI | AI 处于离线状态 | 唤醒 AI |
| `API_KEY_EXHAUSTED` | AI | 所有 API Key 耗尽 | 添加新 Key |
| `CREDIT_INSUFFICIENT` | 额度 | 额度不足 | 充值 |
| `RATE_LIMITED` | 全局 | 触发速率限制 | 等待或调整配置 |
| `TOOL_NOT_FOUND` | 工具 | 工具不存在 | 检查工具名 |
| `PERMISSION_DENIED` | 权限 | 权限不足 | 升级角色 |
| `FEDERATION_TIMEOUT` | 联邦 | 跨实例超时 | 检查网络 |

### 日志级别说明

| 级别 | 用途 | 处理方式 |
|------|------|---------|
| `DEBUG` | 调试信息 | 开发时查看 |
| `INFO` | 正常运行信息 | 定期检查 |
| `WARNING` | 警告但不影响使用 | 关注趋势 |
| `ERROR` | 影响单条请求 | 及时处理 |
| `CRITICAL` | 影响服务整体 | 立即处理 |

---

## 附录：一键诊断脚本

```bash
#!/bin/bash
# diagnose.sh - AIsChat 故障诊断脚本

echo "=== AIsChat 诊断 ==="

echo "1. 检查容器状态"
docker compose ps

echo "2. 检查健康接口"
curl -s http://localhost:5228/health || echo "健康接口不可用"

echo "3. 数据库连接测试"
docker compose exec -T postgres pg_isready -U ai_chat

echo "4. 磁盘空间"
df -h .

echo "5. 内存使用"
free -m

echo "6. 最近错误日志"
docker compose logs --tail 20 backend 2>&1 | grep -i "error\|exception\|traceback" || echo "无错误日志"

echo "=== 诊断完成 ==="
```

> **文档版本**: v1.0.0 | **更新日期**: 2026-08-10