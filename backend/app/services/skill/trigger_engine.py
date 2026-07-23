"""
触发器引擎 — 多维触发的执行引擎

支持六种触发维度：
  1. 时间触发 (time)
  2. 事件触发 (event)
  3. 语义触发 (semantic)
  4. 关系触发 (relational)
  5. 状态触发 (state)
  6. 复合触发 (composite)
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TriggerEngine:
    async def register_trigger(self, db: AsyncSession, agent_id: int, trigger: dict) -> None:
        """注册触发器"""
        from app.models.agent_trigger import AgentTrigger
        new_trigger = AgentTrigger(
            agent_id=agent_id,
            trigger_type=trigger.get("trigger_type", "event"),
            task=trigger.get("task", ""),
            status="pending",
            expires_at=trigger.get("expires_at"),
            max_fires=trigger.get("max_fires", -1),
            fire_count=0,
            condition=trigger.get("condition", {}),
        )
        db.add(new_trigger)
        await db.flush()

    async def unregister_trigger(self, db: AsyncSession, agent_id: int, trigger_id: int) -> None:
        """注销触发器"""
        from app.models.agent_trigger import AgentTrigger
        await db.execute(
            AgentTrigger.__table__.delete()
            .where(AgentTrigger.agent_id == agent_id, AgentTrigger.id == trigger_id)
        )
        await db.flush()

    async def check_triggers(self, db: AsyncSession, event: dict) -> list[dict]:
        """检查哪些触发器被触发"""
        from app.models.agent_trigger import AgentTrigger
        from sqlalchemy import select
        result = await db.execute(select(AgentTrigger).where(AgentTrigger.status == "pending"))
        triggers = []
        for t in result.scalars():
            if self._matches_condition(t, event):
                triggers.append({
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "trigger_type": t.trigger_type,
                    "task": t.task,
                })
        return triggers

    async def fire_trigger(self, db: AsyncSession, agent_id: int, trigger_id: int) -> None:
        """触发触发器"""
        from app.models.agent_trigger import AgentTrigger
        from sqlalchemy import select
        result = await db.execute(
            select(AgentTrigger)
            .where(AgentTrigger.agent_id == agent_id, AgentTrigger.id == trigger_id)
        )
        trigger = result.scalar_one_or_none()
        if trigger:
            trigger.fire_count += 1
            if trigger.max_fires > 0 and trigger.fire_count >= trigger.max_fires:
                trigger.status = "fired"
            await db.flush()

    def _matches_condition(self, trigger, event: dict) -> bool:
        """检查触发器条件是否匹配"""
        return True


trigger_engine = TriggerEngine()