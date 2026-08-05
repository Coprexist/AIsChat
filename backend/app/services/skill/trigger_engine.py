"""
触发器引擎 — 多维触发的执行引擎

设计文档 skill_manager_design.md 七、多维触发器：
  ① time        — 时间触发：condition.wake_at 到点即触发
  ② event       — 事件触发：event.type == condition.on_event
  ③ semantic    — 语义触发：消息内容包含 condition.topic_match 中任一主题
  ④ relational  — 关系触发：消息发送者在 condition.on_user_message 列表中
  ⑤ state       — 状态触发：事件携带的状态变化匹配 condition.on_state_change
  ⑥ composite   — 复合触发：condition.operator(AND/OR) + conditions 递归组合

事件格式约定（统一规范化）：
  {"type": "message_received", "data": {"content": "...", "sender_id": 1, "group_id": 2}}
  读取字段时兼容扁平写法（content/sender_id 直接在顶层）。
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VALID_TRIGGER_TYPES = {"time", "event", "semantic", "relational", "state", "composite"}


def _parse_dt(value) -> datetime | None:
    """解析 ISO 时间字符串 → 带时区的 datetime"""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _event_field(event: dict, key: str):
    """从事件中取字段：兼容顶层与 data 子对象两种写法"""
    if key in event:
        return event.get(key)
    data = event.get("data") or {}
    if isinstance(data, dict) and key in data:
        return data.get(key)
    return None


class TriggerEngine:
    """多维触发器引擎 — 注册/注销/检查/触发"""

    # ── 注册与注销 ──

    async def register_trigger(self, db: AsyncSession, agent_id: int, trigger: dict) -> dict:
        """注册触发器，返回创建后的记录"""
        from app.models.agent_trigger import AgentTrigger

        trigger_type = trigger.get("trigger_type", "event")
        if trigger_type not in VALID_TRIGGER_TYPES:
            raise ValueError(f"无效触发器类型: {trigger_type}，可选: {'/'.join(sorted(VALID_TRIGGER_TYPES))}")

        condition = trigger.get("condition") or {}
        if trigger_type == "composite":
            self._validate_composite(condition)

        new_trigger = AgentTrigger(
            agent_id=agent_id,
            trigger_type=trigger_type,
            task=trigger.get("task", ""),
            status="pending",
            expires_at=_parse_dt(trigger.get("expires_at")),
            max_fires=int(trigger.get("max_fires", -1)),
            fire_count=0,
            condition=condition,
        )
        db.add(new_trigger)
        await db.flush()
        await db.refresh(new_trigger)
        logger.info(f"AI({agent_id}) 注册触发器 #{new_trigger.id} [{trigger_type}]: {new_trigger.task[:40]}")
        return self._to_dict(new_trigger)

    async def unregister_trigger(self, db: AsyncSession, agent_id: int, trigger_id: int) -> None:
        """注销触发器（物理删除）"""
        from app.models.agent_trigger import AgentTrigger

        await db.execute(
            AgentTrigger.__table__.delete().where(
                AgentTrigger.agent_id == agent_id,
                AgentTrigger.id == trigger_id,
            )
        )
        await db.flush()

    async def cancel_trigger(self, db: AsyncSession, agent_id: int, trigger_id: int) -> None:
        """取消触发器（软删除：状态置为 cancelled）"""
        from app.models.agent_trigger import AgentTrigger

        result = await db.execute(
            select(AgentTrigger).where(
                AgentTrigger.agent_id == agent_id,
                AgentTrigger.id == trigger_id,
            )
        )
        trigger = result.scalar_one_or_none()
        if trigger is not None:
            trigger.status = "cancelled"
            await db.flush()

    async def list_triggers(self, db: AsyncSession, agent_id: int, include_fired: bool = True) -> list[dict]:
        """触发器列表"""
        from app.models.agent_trigger import AgentTrigger

        query = select(AgentTrigger).where(AgentTrigger.agent_id == agent_id)
        if not include_fired:
            query = query.where(AgentTrigger.status != "fired")
        result = await db.execute(query.order_by(AgentTrigger.id.desc()))
        return [self._to_dict(t) for t in result.scalars()]

    # ── 检查与触发 ──

    async def check_triggers(self, db: AsyncSession, event: dict | None = None) -> list[dict]:
        """
        检查哪些触发器被触发。

        - event 为 None 时：仅检查到期的 time 触发器（周期扫描用）
        - event 提供时：检查 time（到期）+ 其余各维度的匹配
        """
        from app.models.agent_trigger import AgentTrigger

        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(AgentTrigger).where(AgentTrigger.status == "pending")
        )
        matched = []
        for t in result.scalars():
            # 过期检查
            if t.expires_at is not None:
                exp = t.expires_at if t.expires_at.tzinfo else t.expires_at.replace(tzinfo=timezone.utc)
                if exp < now:
                    t.status = "cancelled"
                    continue

            if self.matches(t, event, now=now):
                matched.append(self._to_dict(t))

        if matched:
            await db.flush()
        return matched

    async def fire_trigger(self, db: AsyncSession, agent_id: int, trigger_id: int) -> dict:
        """触发触发器：fire_count+1，达到 max_fires 后置为 fired"""
        from app.models.agent_trigger import AgentTrigger

        result = await db.execute(
            select(AgentTrigger).where(
                AgentTrigger.agent_id == agent_id,
                AgentTrigger.id == trigger_id,
                AgentTrigger.status == "pending",
            )
        )
        trigger = result.scalar_one_or_none()
        if trigger is None:
            raise ValueError(f"触发器 {trigger_id} 不存在或已结束")

        trigger.fire_count += 1
        if trigger.max_fires > 0 and trigger.fire_count >= trigger.max_fires:
            trigger.status = "fired"
        await db.flush()
        return self._to_dict(trigger)

    # ── 匹配逻辑 ──

    def matches(self, trigger, event: dict | None, now: datetime | None = None) -> bool:
        """六维匹配。event 为 None 时只评估 time 维度。"""
        trigger_type = trigger.trigger_type
        condition = trigger.condition or {}

        if trigger_type == "time":
            wake_at = _parse_dt(condition.get("wake_at"))
            return wake_at is not None and wake_at <= (now or datetime.now(timezone.utc))

        if event is None:
            return False  # 非时间触发需要事件上下文

        if trigger_type == "event":
            return _event_field(event, "type") == condition.get("on_event")

        if trigger_type == "semantic":
            topics = condition.get("topic_match") or []
            content = str(_event_field(event, "content") or "")
            lowered = content.lower()
            return any(str(t).lower() in lowered for t in topics if t)

        if trigger_type == "relational":
            allowed = condition.get("on_user_message") or []
            sender = _event_field(event, "sender_id")
            return sender in allowed

        if trigger_type == "state":
            wanted = condition.get("on_state_change")
            current = _event_field(event, "state") or _event_field(event, "state_change")
            return current == wanted

        if trigger_type == "composite":
            return self._match_composite(condition, event, now)

        return False

    # ── 复合触发 ──

    def _validate_composite(self, condition: dict) -> None:
        """校验复合条件结构"""
        operator = condition.get("operator", "AND")
        if operator not in ("AND", "OR"):
            raise ValueError(f"复合触发 operator 只能是 AND/OR，收到: {operator}")
        sub_conditions = condition.get("conditions") or []
        if not isinstance(sub_conditions, list) or not sub_conditions:
            raise ValueError("复合触发需要非空 conditions 列表")
        for sub in sub_conditions:
            if not isinstance(sub, dict) or "trigger_type" not in sub:
                raise ValueError(f"复合触发子条件必须是 {VALID_TRIGGER_TYPES} 结构")
            if sub.get("trigger_type") == "composite":
                self._validate_composite(sub)

    def _match_composite(self, condition: dict, event: dict, now: datetime | None) -> bool:
        """递归匹配复合条件（子条件按 trigger_type + 自身 condition 评估）"""
        from app.models.agent_trigger import AgentTrigger

        operator = condition.get("operator", "AND")
        results = []
        for sub in condition.get("conditions") or []:
            fake = AgentTrigger(
                agent_id=0,
                trigger_type=sub.get("trigger_type", "event"),
                condition=sub.get("condition") or {},
                task="",
            )
            results.append(self.matches(fake, event, now=now))
        return all(results) if operator == "AND" else any(results)

    # ── 序列化 ──

    @staticmethod
    def _to_dict(t) -> dict:
        return {
            "id": t.id,
            "agent_id": t.agent_id,
            "trigger_type": t.trigger_type,
            "task": t.task,
            "status": t.status,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            "max_fires": t.max_fires,
            "fire_count": t.fire_count,
            "condition": t.condition or {},
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }


trigger_engine = TriggerEngine()
