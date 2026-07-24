"""
事件总线 — 全局发布/订阅机制

提供 on/off/emit 接口，支持系统模块和插件挂接到生命周期事件。
错误隔离：单个 handler 抛异常不影响其他 handler。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


@dataclass
class Event:
    """事件对象"""
    type: str
    data: dict[str, Any] = field(default_factory=dict)


# ── 预定义事件类型 ──

class EventType:
    """系统事件类型常量"""
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    MESSAGE_BEFORE_SEND = "message.before_send"
    MESSAGE_AFTER_SEND = "message.after_send"
    AI_BEFORE_RESPONSE = "ai.before_response"
    AI_AFTER_RESPONSE = "ai.after_response"
    AI_STATE_CHANGE = "ai.state_change"
    TOOL_AFTER_EXECUTE = "tool.after_execute"


class EventBus:
    """事件总线 — 单例，管理事件订阅与发布"""

    _instance: EventBus | None = None

    def __new__(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers: dict[str, list[Handler]] = {}
        return cls._instance

    # ── 订阅 ──

    def on(self, event_type: str, handler: Handler) -> None:
        """订阅事件"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"事件处理器已注册: {event_type} -> {handler.__name__}")

    def off(self, event_type: str, handler: Handler) -> None:
        """取消订阅"""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h is not handler
            ]

    # ── 发布 ──

    async def emit(self, event_type: str, **data: Any) -> None:
        """发布事件，异步并发执行所有已注册的处理器"""
        event = Event(type=event_type, data=data)
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            return

        logger.debug(f"事件触发: {event_type} (handlers={len(handlers)})")

        # 并发执行所有处理器
        tasks = [self._safe_dispatch(h, event) for h in handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── 异步触发（不等待） ──

    def emit_async(self, event_type: str, **data: Any) -> None:
        """异步发布事件（fire-and-forget，不等待完成）"""
        asyncio.create_task(self.emit(event_type, **data))

    # ── 内部 ──

    @staticmethod
    async def _safe_dispatch(handler: Handler, event: Event) -> None:
        """安全执行单个处理器，捕获并记录异常"""
        try:
            await handler(event)
        except Exception as e:
            logger.exception(
                f"事件处理器异常: {handler.__name__} ({event.type}): {e}"
            )

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅用于测试）"""
        if cls._instance is not None:
            cls._instance._handlers.clear()
            cls._instance = None


# 全局单例
event_bus = EventBus()
