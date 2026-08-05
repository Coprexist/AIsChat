"""
触发器周期扫描 worker — time 维度的执行引擎

time 触发器没有事件驱动，需要周期性扫描到期触发器并 fire。
启动时注册到 main.py lifespan，每 30 秒扫一次。

触发的任务通过事件总线通知对应 AI（fire-and-forget，不阻塞扫描循环）。
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

SCAN_INTERVAL = 30  # 秒


async def trigger_sweep_worker() -> None:
    """周期扫描到期的时间触发器"""
    while True:
        await asyncio.sleep(SCAN_INTERVAL)
        try:
            await sweep_due_time_triggers()
        except Exception as e:
            logger.warning(f"时间触发器扫描失败: {e}")


async def sweep_due_time_triggers() -> None:
    """扫描并触发所有到期的 time 触发器"""
    from app.database import async_session
    from app.services.skill.trigger_engine import trigger_engine
    from app.services.brain.skill_event_bus import skill_event_bus

    async with async_session() as db:
        due = await trigger_engine.check_triggers(db, event=None)
        fired = []
        for trigger in due:
            try:
                result = await trigger_engine.fire_trigger(db, trigger["agent_id"], trigger["id"])
                fired.append(result)
                # 通知技能层（Skill 可订阅 alarm_fired 自行响应）
                await skill_event_bus.publish({
                    "type": "alarm_fired",
                    "data": {
                        "agent_id": trigger["agent_id"],
                        "trigger_id": trigger["id"],
                        "task": trigger["task"],
                    },
                })
                # 驱动 AI 执行任务（与闹钟同机制：入队 → 唤醒 AI）
                from app.ai.response_worker import message_queue
                try:
                    message_queue.put_nowait({
                        "type": "trigger",
                        "agent_id": trigger["agent_id"],
                        "trigger_id": trigger["id"],
                        "task": trigger["task"],
                    })
                except asyncio.QueueFull:
                    logger.warning(f"⏰ 消息队列已满，触发器 #{trigger['id']} 无法推入")
            except Exception as e:
                logger.warning(f"触发触发器 #{trigger['id']} 失败: {e}")
        if fired:
            await db.commit()
            logger.info(f"⏰ 时间触发器触发 {len(fired)} 个: {[t['id'] for t in fired]}")
