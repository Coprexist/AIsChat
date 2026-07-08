"""
AI 对话日志服务
保存、查询、清理 AI 完整对话记录
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, text

from app.models.conversation_log import ConversationLogConfig, ConversationLog

logger = logging.getLogger(__name__)


# ── 保存 ──

async def save_conversation_log(
    db: AsyncSession,
    agent_id: int,
    messages: list[dict],
    conversation_type: str = "group",
    group_id: int | None = None,
    session_id: str | None = None,
    token_usage: dict | None = None,
    has_output: bool = False,
    model: str | None = None,
    thinking_enabled: bool = False,
) -> int | None:
    """保存一次完整对话，自动清理超出限制的旧记录"""
    try:
        log = ConversationLog(
            agent_id=agent_id,
            group_id=group_id,
            session_id=session_id,
            conversation_type=conversation_type,
            messages=messages,
            message_count=len(messages),
            token_usage=token_usage,
            has_output=has_output,
            model=model,
            thinking_enabled=thinking_enabled,
        )
        db.add(log)
        await db.flush()
        await db.refresh(log)

        # 清理超出限制的旧记录
        await _trim_old_logs(db, agent_id)

        return log.id
    except Exception as e:
        logger.error(f"保存对话日志失败 (agent={agent_id}): {e}")
        return None


async def _trim_old_logs(db: AsyncSession, agent_id: int):
    """保留最近 N 条日志，删除更旧的"""
    # 获取此 AI 的保留上限
    limit = await _get_agent_log_limit(db, agent_id)

    # 查询超出限制的旧记录 ID
    result = await db.execute(
        select(ConversationLog.id)
        .where(ConversationLog.agent_id == agent_id)
        .order_by(ConversationLog.created_at.desc())
        .offset(limit)
        .limit(1000)
    )
    old_ids = [row[0] for row in result.all()]
    if old_ids:
        await db.execute(
            delete(ConversationLog).where(ConversationLog.id.in_(old_ids))
        )
        logger.info(f"清理 agent={agent_id} 的 {len(old_ids)} 条旧对话日志（保留最近 {limit} 条）")


async def _get_agent_log_limit(db: AsyncSession, agent_id: int) -> int:
    """获取某个 AI 的对话日志保留上限"""
    # 先查 per-AI 设置
    from app.models.agent import Agent
    agent_result = await db.execute(
        select(Agent.conversation_logs_limit).where(Agent.id == agent_id)
    )
    agent_limit = agent_result.scalar_one_or_none()
    if agent_limit is not None:
        return agent_limit

    # 回退到全局上限
    config = await _get_config(db)
    return config.max_conversation_logs if config else 30


# ── 配置 ──

async def _get_config(db: AsyncSession) -> ConversationLogConfig:
    """获取全局配置（保证返回有效对象）"""
    result = await db.execute(select(ConversationLogConfig).where(ConversationLogConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        config = ConversationLogConfig(id=1)
        db.add(config)
        await db.flush()
    return config


async def get_config_dict(db: AsyncSession) -> dict:
    """获取全局配置（字典格式，供 API 返回）"""
    config = await _get_config(db)
    return {
        "max_conversation_logs": config.max_conversation_logs,
        "default_user_conversation_logs": config.default_user_conversation_logs,
        "default_user_log_access": config.default_user_log_access,
        "default_delay_reply_enabled": config.default_delay_reply_enabled,
    }


async def update_config(
    db: AsyncSession,
    updated_by: int,
    max_conversation_logs: int | None = None,
    default_user_conversation_logs: int | None = None,
    default_user_log_access: bool | None = None,
    default_delay_reply_enabled: bool | None = None,
) -> dict:
    """更新全局配置"""
    config = await _get_config(db)

    if max_conversation_logs is not None:
        if max_conversation_logs < 1:
            raise ValueError("全局上限至少为 1")
        config.max_conversation_logs = max_conversation_logs
    if default_user_conversation_logs is not None:
        if default_user_conversation_logs < 1:
            raise ValueError("用户默认值至少为 1")
        if default_user_conversation_logs > config.max_conversation_logs:
            raise ValueError(f"用户默认值不能超过全局上限 {config.max_conversation_logs}")
        config.default_user_conversation_logs = default_user_conversation_logs
    if default_user_log_access is not None:
        config.default_user_log_access = default_user_log_access
    if default_delay_reply_enabled is not None:
        config.default_delay_reply_enabled = default_delay_reply_enabled

    config.updated_by = updated_by
    config.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    return await get_config_dict(db)


# ── 用户设置 ──

async def get_user_log_limit(db: AsyncSession, user_id: int) -> dict:
    """获取用户的对话日志保留设置"""
    from app.models.user import User
    config = await _get_config(db)

    result = await db.execute(
        select(User.conversation_logs_limit).where(User.id == user_id)
    )
    user_limit = result.scalar_one_or_none()

    effective = user_limit if user_limit is not None else config.default_user_conversation_logs
    max_allowed = config.max_conversation_logs

    return {
        "user_limit": user_limit,
        "effective": effective,
        "max_allowed": max_allowed,
        "system_default": config.default_user_conversation_logs,
    }


async def update_user_log_limit(db: AsyncSession, user_id: int, limit: int) -> dict:
    """更新用户的对话日志保留数"""
    config = await _get_config(db)

    if limit < 1:
        raise ValueError("保留数至少为 1")
    if limit > config.max_conversation_logs:
        raise ValueError(f"不能超过管理员设定的系统上限 {config.max_conversation_logs}")

    from app.models.user import User
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    user.conversation_logs_limit = limit
    await db.flush()
    return await get_user_log_limit(db, user_id)


# ── 查询 ──

async def get_agent_logs(
    db: AsyncSession,
    agent_id: int,
    user_id: int | None = None,
    is_admin: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """获取 AI 的对话日志列表（摘要，不含完整 messages）"""
    # 权限检查
    if not is_admin:
        if not await _user_can_view_agent_logs(db, agent_id, user_id):
            raise ValueError("无权查看此 AI 的对话日志")

    # 确定有效保留数
    if is_admin:
        effective_limit = await _get_agent_log_limit(db, agent_id)
    else:
        user_limit = await get_user_log_limit(db, user_id)
        effective_limit = min(
            user_limit["effective"],
            await _get_agent_log_limit(db, agent_id),
        )

    result = await db.execute(
        select(ConversationLog)
        .where(ConversationLog.agent_id == agent_id)
        .order_by(ConversationLog.created_at.desc())
        .limit(min(limit, effective_limit))
        .offset(offset)
    )
    logs = result.scalars().all()

    return [_log_to_summary(log) for log in logs]


async def get_log_detail(
    db: AsyncSession,
    log_id: int,
    user_id: int | None = None,
    is_admin: bool = False,
) -> dict | None:
    """获取单条对话日志的完整内容（含 messages）"""
    result = await db.execute(
        select(ConversationLog).where(ConversationLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if log is None:
        return None

    if not is_admin:
        if not await _user_can_view_agent_logs(db, log.agent_id, user_id):
            raise ValueError("无权查看此对话日志")

    return _log_to_detail(log)


async def get_agent_log_stats(db: AsyncSession, agent_id: int) -> dict:
    """获取 AI 日志统计"""
    result = await db.execute(
        select(func.count(ConversationLog.id)).where(ConversationLog.agent_id == agent_id)
    )
    total = result.scalar() or 0
    limit = await _get_agent_log_limit(db, agent_id)

    return {
        "agent_id": agent_id,
        "total_logs": total,
        "retention_limit": limit,
    }


# ── Token 用量聚合查询 ──

async def get_user_agents_token_summary(
    db: AsyncSession,
    user_id: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """获取用户所有 AI 的 token 消耗汇总（按 AI+模型分组）"""
    from app.models.agent import Agent
    where_clauses = ["cl.agent_id = ag.id", "ag.owner_id = :user_id"]
    params: dict = {"user_id": user_id}
    if start_date:
        where_clauses.append("cl.created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where_clauses.append("cl.created_at <= :end_date")
        params["end_date"] = end_date
    where_sql = " AND ".join(where_clauses)

    stmt = text(f"""
        SELECT
            cl.agent_id,
            ag.name AS agent_name,
            cl.model,
            SUM(COALESCE((cl.token_usage->>'total_tokens')::int, 0)) AS total_tokens,
            SUM(COALESCE((cl.token_usage->>'prompt_tokens')::int, 0)) AS prompt_tokens,
            SUM(COALESCE((cl.token_usage->>'completion_tokens')::int, 0)) AS completion_tokens,
            SUM(COALESCE((cl.token_usage->>'reasoning_tokens')::int, 0)) AS reasoning_tokens,
            SUM(COALESCE((cl.token_usage->>'cached_tokens')::int, 0)) AS cached_tokens,
            SUM(COALESCE((cl.token_usage->>'api_calls')::int, 0)) AS total_calls
        FROM ai_conversation_logs cl
        JOIN agents ag ON ag.id = cl.agent_id
        WHERE {where_sql}
        GROUP BY cl.agent_id, ag.name, cl.model
        ORDER BY total_tokens DESC
    """)
    result = await db.execute(stmt, params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


async def get_agent_token_daily(
    db: AsyncSession,
    agent_id: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """获取单个 AI 每日 token 消耗分布"""
    where_clauses = ["agent_id = :agent_id"]
    params: dict = {"agent_id": agent_id}
    if start_date:
        where_clauses.append("created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where_clauses.append("created_at <= :end_date")
        params["end_date"] = end_date
    where_sql = " AND ".join(where_clauses)

    stmt = text(f"""
        SELECT
            DATE(created_at) AS date,
            SUM(COALESCE((token_usage->>'total_tokens')::int, 0)) AS total_tokens,
            SUM(COALESCE((token_usage->>'prompt_tokens')::int, 0)) AS prompt_tokens,
            SUM(COALESCE((token_usage->>'completion_tokens')::int, 0)) AS completion_tokens,
            SUM(COALESCE((token_usage->>'reasoning_tokens')::int, 0)) AS reasoning_tokens,
            SUM(COALESCE((token_usage->>'cached_tokens')::int, 0)) AS cached_tokens,
            SUM(COALESCE((token_usage->>'api_calls')::int, 0)) AS request_count
        FROM ai_conversation_logs
        WHERE {where_sql}
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """)
    result = await db.execute(stmt, params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


async def get_admin_global_token_stats(
    db: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """获取全站 token 消耗总览"""
    where_clauses = []
    params: dict = {}
    if start_date:
        where_clauses.append("cl.created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where_clauses.append("cl.created_at <= :end_date")
        params["end_date"] = end_date
    where_sql = " AND ".join(where_clauses)
    if where_sql:
        where_sql = "WHERE " + where_sql

    stmt = text(f"""
        SELECT
            SUM(COALESCE((cl.token_usage->>'total_tokens')::int, 0)) AS total_tokens,
            SUM(COALESCE((cl.token_usage->>'prompt_tokens')::int, 0)) AS prompt_tokens,
            SUM(COALESCE((cl.token_usage->>'completion_tokens')::int, 0)) AS completion_tokens,
            SUM(COALESCE((cl.token_usage->>'reasoning_tokens')::int, 0)) AS reasoning_tokens,
            SUM(COALESCE((cl.token_usage->>'cached_tokens')::int, 0)) AS cached_tokens,
            SUM(COALESCE((cl.token_usage->>'api_calls')::int, 0)) AS total_calls,
            COUNT(DISTINCT cl.agent_id) AS unique_agents,
            COUNT(DISTINCT ag.owner_id) AS unique_users
        FROM ai_conversation_logs cl
        JOIN agents ag ON ag.id = cl.agent_id
        {where_sql}
    """)
    result = await db.execute(stmt, params)
    row = result.mappings().first()
    if row:
        d = dict(row)
        d["total_tokens"] = d["total_tokens"] or 0
        d["prompt_tokens"] = d["prompt_tokens"] or 0
        d["completion_tokens"] = d["completion_tokens"] or 0
        d["reasoning_tokens"] = d["reasoning_tokens"] or 0
        d["cached_tokens"] = d["cached_tokens"] or 0
        d["total_calls"] = d["total_calls"] or 0
        d["unique_agents"] = d["unique_agents"] or 0
        d["unique_users"] = d["unique_users"] or 0
        return d
    return {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "reasoning_tokens": 0, "cached_tokens": 0, "total_calls": 0,
            "unique_agents": 0, "unique_users": 0}


async def get_admin_users_token_summary(
    db: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """获取按用户分组的 token 消耗明细"""
    where_clauses = []
    params: dict = {}
    if start_date:
        where_clauses.append("cl.created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where_clauses.append("cl.created_at <= :end_date")
        params["end_date"] = end_date
    where_sql = " AND ".join(where_clauses)
    if where_sql:
        where_sql = "WHERE " + where_sql

    stmt = text(f"""
        SELECT
            u.id AS user_id,
            u.username,
            cl.agent_id,
            ag.name AS agent_name,
            SUM(COALESCE((cl.token_usage->>'total_tokens')::int, 0)) AS total_tokens,
            SUM(COALESCE((cl.token_usage->>'prompt_tokens')::int, 0)) AS prompt_tokens,
            SUM(COALESCE((cl.token_usage->>'completion_tokens')::int, 0)) AS completion_tokens,
            SUM(COALESCE((cl.token_usage->>'reasoning_tokens')::int, 0)) AS reasoning_tokens,
            SUM(COALESCE((cl.token_usage->>'cached_tokens')::int, 0)) AS cached_tokens,
            SUM(COALESCE((cl.token_usage->>'api_calls')::int, 0)) AS total_calls
        FROM ai_conversation_logs cl
        JOIN agents ag ON ag.id = cl.agent_id
        JOIN users u ON u.id = ag.owner_id
        {where_sql}
        GROUP BY u.id, u.username, cl.agent_id, ag.name
        ORDER BY u.id, total_tokens DESC
    """)
    result = await db.execute(stmt, params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


# ── 权限 ──

async def _user_can_view_agent_logs(db: AsyncSession, agent_id: int, user_id: int | None) -> bool:
    """检查用户是否可以查看某 AI 的对话日志"""
    if user_id is None:
        return False

    from app.models.agent import Agent
    agent_result = await db.execute(
        select(Agent.owner_id, Agent.user_can_view_logs).where(Agent.id == agent_id)
    )
    agent_row = agent_result.one_or_none()
    if agent_row is None:
        return False

    owner_id, per_ai_flag = agent_row

    # AI 的 owner 始终可查看
    if owner_id == user_id:
        return True

    # 检查 per-AI 开关
    if per_ai_flag is not None:
        return per_ai_flag

    # 回退到全局默认
    config = await _get_config(db)
    return config.default_user_log_access


# ── Agent 管理 ──

async def get_agent_log_settings(db: AsyncSession, agent_id: int) -> dict:
    """获取某 AI 的日志设置"""
    from app.models.agent import Agent
    result = await db.execute(
        select(
            Agent.conversation_logs_limit,
            Agent.user_can_view_logs,
        ).where(Agent.id == agent_id)
    )
    row = result.one_or_none()
    if row is None:
        raise ValueError("AI 不存在")

    config = await _get_config(db)
    return {
        "agent_id": agent_id,
        "conversation_logs_limit": row[0],
        "user_can_view_logs": row[1],
        "effective_limit": row[0] if row[0] is not None else config.max_conversation_logs,
        "effective_user_access": row[1] if row[1] is not None else config.default_user_log_access,
        "system_max": config.max_conversation_logs,
        "system_default_access": config.default_user_log_access,
    }


async def update_agent_log_settings(
    db: AsyncSession,
    agent_id: int,
    conversation_logs_limit: int | None = None,
    user_can_view_logs: bool | None = None,
) -> dict:
    """更新某 AI 的日志设置"""
    from app.models.agent import Agent
    config = await _get_config(db)

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError("AI 不存在")

    if conversation_logs_limit is not None:
        if conversation_logs_limit < 1:
            raise ValueError("保留数至少为 1")
        if conversation_logs_limit > config.max_conversation_logs:
            raise ValueError(f"不能超过系统上限 {config.max_conversation_logs}")
        agent.conversation_logs_limit = conversation_logs_limit

    if user_can_view_logs is not None:
        agent.user_can_view_logs = user_can_view_logs

    await db.flush()
    return await get_agent_log_settings(db, agent_id)


# ── 内部工具 ──

def _log_to_summary(log: ConversationLog) -> dict:
    """转为摘要（不含完整 messages，前端列表用）"""
    # 取前两条和后一条消息作为预览
    msgs = log.messages or []
    preview = []
    if len(msgs) > 0:
        preview.append(_summarize_message(msgs[0]))
    if len(msgs) > 1:
        preview.append(_summarize_message(msgs[1]))
    if len(msgs) > 3:
        preview.append({"_more": f"... 共 {len(msgs)} 条消息"})
        preview.append(_summarize_message(msgs[-1]))

    return {
        "id": log.id,
        "agent_id": log.agent_id,
        "conversation_type": log.conversation_type,
        "group_id": log.group_id,
        "session_id": log.session_id,
        "message_count": log.message_count,
        "token_usage": log.token_usage,
        "has_output": log.has_output,
        "model": log.model,
        "thinking_enabled": log.thinking_enabled,
        "preview": preview,
        "created_at": str(log.created_at) if log.created_at else None,
    }


def _log_to_detail(log: ConversationLog) -> dict:
    """转为完整详情（含 messages）"""
    return {
        "id": log.id,
        "agent_id": log.agent_id,
        "conversation_type": log.conversation_type,
        "group_id": log.group_id,
        "session_id": log.session_id,
        "messages": log.messages,
        "message_count": log.message_count,
        "token_usage": log.token_usage,
        "has_output": log.has_output,
        "model": log.model,
        "thinking_enabled": log.thinking_enabled,
        "created_at": str(log.created_at) if log.created_at else None,
    }


def _summarize_message(msg: dict) -> dict:
    """将单条消息压缩为预览摘要"""
    role = msg.get("role", "?")
    content = msg.get("content", "")
    if isinstance(content, str) and len(content) > 100:
        content = content[:100] + "..."
    elif isinstance(content, list):
        content = "[multi-part content]"
    summary = {"role": role}
    if content:
        summary["content"] = content
    if msg.get("tool_calls"):
        summary["tool_calls"] = [tc.get("function", {}).get("name", "?") for tc in msg["tool_calls"]]
    if msg.get("name"):
        summary["name"] = msg["name"]
    return summary


async def get_session_token_usage(
    db: AsyncSession,
    session_id: str,
    user_id: int,
) -> dict:
    """获取指定 DM 会话的 token 消耗汇总（用于前端自费聊天显示）"""
    from app.models.conversation_log import ConversationLog
    result = await db.execute(
        text("""
            SELECT
                COALESCE(SUM((token_usage->>'total_tokens')::int), 0) AS total_tokens,
                COALESCE(SUM((token_usage->>'api_calls')::int), 0) AS api_calls
            FROM ai_conversation_logs
            WHERE session_id = :sid
        """),
        {"sid": session_id},
    )
    row = result.one()
    return {
        "total_tokens": row.total_tokens or 0,
        "api_calls": row.api_calls or 0,
        "session_id": session_id,
    }
