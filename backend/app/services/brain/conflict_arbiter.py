"""
冲突仲裁器 — 当多个 Skill 同时想说话时，决定谁先说、说什么

设计文档 5.2 输出类型处理：
  - speak    → 进冲突仲裁队列（按 priority 排序，一轮最多 3 个）
  - remember → 直接放行，不仲裁
  - silent   → 完全忽略
  - internal → 更新 Skill 内部状态，不对外（不进入发言队列）
"""
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SpeechRequest:
    """一次 Skill 发言请求"""
    skill_name: str
    priority: int = 0                      # 0-100
    action_type: str = "speak"             # speak | remember | silent | internal
    reason: str = ""                       # 调试追踪用
    messages: list[dict] = field(default_factory=list)      # 要发送的消息
    state_changes: dict = field(default_factory=dict)       # 状态变更
    memory_updates: list[dict] = field(default_factory=list)  # 记忆更新

    @classmethod
    def from_dict(cls, data: dict) -> "SpeechRequest":
        """从 dict 构造（兼容下游传入普通 dict 的情况）"""
        return cls(
            skill_name=data.get("skill_name", "unknown"),
            priority=int(data.get("priority", 0) or 0),
            action_type=data.get("action_type", "speak"),
            reason=data.get("reason", ""),
            messages=data.get("messages", []),
            state_changes=data.get("state_changes", {}),
            memory_updates=data.get("memory_updates", []),
        )


class ConflictArbiter:
    MAX_SPEAKERS_PER_ROUND = 3

    async def arbitrate(self, speech_requests: list) -> list:
        """
        冲突仲裁：
        1. silent 完全忽略；internal 只更新内部状态，不对外
        2. remember 直接放行，不仲裁
        3. speak 按 priority 降序，取前 N 个（一轮最多 3 个）

        Args:
            speech_requests: SpeechRequest 或 dict 列表

        Returns:
            允许发言的请求列表（remember 全部 + speak 前 N）
        """
        if not speech_requests:
            return []

        # 统一为 SpeechRequest
        requests = [
            r if isinstance(r, SpeechRequest) else SpeechRequest.from_dict(r)
            for r in speech_requests
        ]

        passthrough: list[SpeechRequest] = []
        speak_queue: list[SpeechRequest] = []

        for request in requests:
            if request.action_type == "silent":
                continue
            if request.action_type == "remember":
                passthrough.append(request)  # 直接放行，不仲裁
                continue
            if request.action_type == "internal":
                # 内部状态更新不产生对外发言；state_changes 由调用方自行应用
                continue
            speak_queue.append(request)  # speak（默认）

        speak_queue.sort(key=lambda r: r.priority, reverse=True)
        return passthrough + speak_queue[: self.MAX_SPEAKERS_PER_ROUND]


conflict_arbiter = ConflictArbiter()
