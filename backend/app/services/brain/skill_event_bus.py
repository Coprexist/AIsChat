"""
Skill 事件总线 — Skill 间通信通道

与全局 EventBus（handler 注册制）不同，这里按 **Skill 名** 登记订阅关系：
  - subscribe(event_type, skill_name)：Skill 声明关心某类事件
  - publish(event)：把事件派发给所有订阅了该类型的 Skill

派发是「通知制」：Skill 收到事件后由自己的 should_act 决定是否行动，
事件总线不做任何决策（极薄大脑原则）。

扩展点：set_dispatcher() 允许 Skill 层注入真正的派发实现，
默认实现仅记录日志，保证未接线时静默安全。
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Dispatcher = Callable[[str, dict], Awaitable[None]]


class SkillEventBus:
    """Skill 事件总线 — event_type → [skill_name] 订阅注册表"""

    def __init__(self) -> None:
        self.subscribers: dict[str, list[str]] = {}
        self._dispatcher: Dispatcher | None = None

    # ── 订阅 ──

    def subscribe(self, event_type: str, skill_name: str) -> None:
        """订阅事件：Skill 声明关心某类事件"""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        if skill_name not in self.subscribers[event_type]:
            self.subscribers[event_type].append(skill_name)
            logger.debug(f"Skill 订阅事件: {skill_name} -> {event_type}")

    def unsubscribe(self, event_type: str, skill_name: str) -> None:
        """取消订阅"""
        if event_type in self.subscribers:
            self.subscribers[event_type] = [
                s for s in self.subscribers[event_type] if s != skill_name
            ]

    # ── 发布 ──

    async def publish(self, event: dict) -> None:
        """发布事件到所有订阅者（通知制，不做决策）"""
        event_type = event.get("type")
        if not event_type:
            logger.warning("事件缺少 type 字段，已丢弃: %s", event)
            return

        skills = self.subscribers.get(event_type, [])
        if not skills:
            return

        logger.debug(f"事件派发: {event_type} -> {skills}")
        for skill_name in skills:
            await self._dispatch(skill_name, event)

    # ── 派发钩子 ──

    def set_dispatcher(self, dispatcher: Dispatcher) -> None:
        """注入 Skill 层的真实派发实现（skill_name, event）→ 通知 Skill"""
        self._dispatcher = dispatcher

    async def _dispatch(self, skill_name: str, event: dict) -> None:
        """单个 Skill 派发 — 错误隔离，单个失败不影响其他 Skill"""
        try:
            if self._dispatcher is not None:
                await self._dispatcher(skill_name, event)
            else:
                logger.debug(f"Skill({skill_name}) 收到事件 {event.get('type')}（无派发器，忽略）")
        except Exception as e:
            logger.exception(f"派发事件给 Skill({skill_name}) 失败: {e}")


skill_event_bus = SkillEventBus()
