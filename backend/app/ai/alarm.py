# 从 services/alarm_service.py 搬迁而来
"""
Agent 闹钟服务
AI 可以为自己设定闹钟，到时间后自动唤醒并执行预设任务。
这是"心跳机制"的第一种形态：AI 自主决定何时醒来、醒来做什么。

v0.5.0: 事件驱动调度 — 用 asyncio.Event 替代 5 秒轮询，
       set/cancel/update 后唤醒调度器精确等待。
"""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alarm import AgentAlarm

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 事件驱动信号（被 alarm_scheduler 等待）
# ══════════════════════════════════════════════════════════════

_alarm_wake_event: asyncio.Event = asyncio.Event()


def notify_alarm_changed():
    """当闹钟被设置/修改/取消时调用，唤醒调度器重新计算等待时间"""
    _alarm_wake_event.set()


async def set_alarm(
    db: AsyncSession,
    agent_id: int,
    wake_at: datetime,
    task: str,
) -> dict:
    """
    为 AI 设定一个闹钟。

    参数:
        agent_id: AI 的 agent ID
        wake_at: 唤醒时间（offset-aware datetime）
        task: 唤醒后要执行的任务描述

    返回:
        {"id": int, "wake_at": str, "task": str}
    """
    alarm = AgentAlarm(
        agent_id=agent_id,
        wake_at=wake_at,
        task=task,
        status="pending",
        created_at=datetime.utcnow(),  # ⚠️ TIMESTAMP WITHOUT TIME ZONE
    )
    db.add(alarm)
    await db.flush()

    # 唤醒调度器重新计算等待时间
    notify_alarm_changed()

    logger.info(f"⏰ AI({agent_id}) 设了闹钟 #{alarm.id}: {wake_at.isoformat()} — 「{task[:80]}」")
    return {
        "id": alarm.id,
        "wake_at": alarm.wake_at.isoformat(),
        "task": alarm.task,
    }


async def cancel_alarm(db: AsyncSession, agent_id: int, alarm_id: int) -> dict:
    """
    取消一个闹钟。

    返回:
        成功: {"success": True, "message": "..."}
        失败: {"error": True, "message": "..."}
    """
    result = await db.execute(
        select(AgentAlarm).where(
            and_(
                AgentAlarm.id == alarm_id,
                AgentAlarm.agent_id == agent_id,
            )
        )
    )
    alarm = result.scalar_one_or_none()

    if alarm is None:
        return {"error": True, "message": f"闹钟 #{alarm_id} 不存在或不属于你"}

    if alarm.status != "pending":
        return {"error": True, "message": f"闹钟 #{alarm_id} 已经是 {alarm.status} 状态，无法取消"}

    alarm.status = "cancelled"
    await db.flush()

    # 唤醒调度器重新计算等待时间
    notify_alarm_changed()

    logger.info(f"⏰ AI({agent_id}) 取消了闹钟 #{alarm_id}: 「{alarm.task[:80]}」")
    return {"success": True, "message": f"已取消闹钟 #{alarm_id}"}


async def update_alarm(
    db: AsyncSession,
    agent_id: int,
    alarm_id: int,
    wake_at: datetime | None = None,
    task: str | None = None,
) -> dict:
    """
    修改一个闹钟的唤醒时间或任务描述。

    返回:
        成功: {"success": True, "alarm": {...}}
        失败: {"error": True, "message": "..."}
    """
    result = await db.execute(
        select(AgentAlarm).where(
            and_(
                AgentAlarm.id == alarm_id,
                AgentAlarm.agent_id == agent_id,
            )
        )
    )
    alarm = result.scalar_one_or_none()

    if alarm is None:
        return {"error": True, "message": f"闹钟 #{alarm_id} 不存在或不属于你"}

    if alarm.status != "pending":
        return {"error": True, "message": f"闹钟 #{alarm_id} 已经是 {alarm.status} 状态，无法修改"}

    changed = []
    if wake_at is not None:
        alarm.wake_at = wake_at
        changed.append("时间")
    if task is not None and task.strip():
        alarm.task = task.strip()
        changed.append("任务")

    if not changed:
        return {"error": True, "message": "没有需要修改的内容"}

    await db.flush()

    # 唤醒调度器重新计算等待时间
    notify_alarm_changed()

    logger.info(f"⏰ AI({agent_id}) 修改了闹钟 #{alarm.id}: {', '.join(changed)}")
    return {
        "success": True,
        "id": alarm.id,
        "wake_at": alarm.wake_at.isoformat(),
        "task": alarm.task,
        "changed": changed,
    }


async def list_alarms(db: AsyncSession, agent_id: int) -> dict:
    """
    列出 AI 的所有闹钟。

    返回:
        {"alarms": [...], "total": int}
    """
    result = await db.execute(
        select(AgentAlarm)
        .where(
            and_(
                AgentAlarm.agent_id == agent_id,
                AgentAlarm.status == "pending",
            )
        )
        .order_by(AgentAlarm.wake_at.asc())
    )
    alarms = result.scalars().all()

    return {
        "alarms": [
            {
                "id": a.id,
                "wake_at": a.wake_at.isoformat(),
                "task": a.task,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alarms
        ],
        "total": len(alarms),
    }


async def get_due_alarms(db: AsyncSession) -> list[AgentAlarm]:
    """
    获取所有到期的闹钟（wake_at <= now 且 status='pending'）。

    由后台调度器定期调用。
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(AgentAlarm).where(
            and_(
                AgentAlarm.wake_at <= now,
                AgentAlarm.status == "pending",
            )
        )
    )
    return list(result.scalars().all())


async def fire_alarm(db: AsyncSession, alarm: AgentAlarm) -> None:
    """将闹钟标记为已触发"""
    alarm.status = "fired"
    alarm.fired_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info(f"⏰ 闹钟 #{alarm.id} (AI:{alarm.agent_id}) 已触发: 「{alarm.task[:80]}」")


async def get_next_alarm_time(db: AsyncSession) -> datetime | None:
    """
    获取最近一个闹钟的唤醒时间（SELECT MIN(wake_at) WHERE status='pending'）。
    用于事件驱动调度器精确等待。
    """
    result = await db.execute(
        select(func.min(AgentAlarm.wake_at)).where(
            AgentAlarm.status == "pending"
        )
    )
    return result.scalar()
