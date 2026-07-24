"""
Skill 事件总线（兼容层）

已委托给 event_bus.py，此处仅做兼容导出。
"""

from app.services.brain.event_bus import event_bus


class SkillEventBus:
    def subscribe(self, event_type: str, skill_name: str) -> None:
        event_bus.subscribe(event_type, skill_name)

    def unsubscribe(self, event_type: str, skill_name: str) -> None:
        event_bus.unsubscribe(event_type, skill_name)

    async def publish(self, event: dict) -> None:
        await event_bus.publish(event)


skill_event_bus = SkillEventBus()