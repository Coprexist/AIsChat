"""世界对话消息单元（文本 + 可选附件）。

世界对话的入队 / 插入队列 / LLM 组装都以此为单位，避免在每一层各写一遍
"字符串 or 带附件" 的分支。HTTP 入参 → ChatItem 的归一化只在路由层做一次。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.utils.message_serializer import normalize_attachments


@dataclass(frozen=True)
class ChatItem:
    """一条待发送的世界对话消息。"""

    text: str = ""
    attachments: tuple[dict, ...] = ()

    @property
    def is_empty(self) -> bool:
        """既没文字也没附件 → 丢弃。"""
        return not self.text and not self.attachments

    @classmethod
    def coerce(cls, raw) -> "ChatItem":
        """把 str / dict / ChatItem 归一化成 ChatItem（唯一入口）。"""
        if isinstance(raw, ChatItem):
            return raw
        if isinstance(raw, str):
            return cls(text=raw.strip())
        if isinstance(raw, dict):
            text = raw.get("text")
            if text is None:
                text = raw.get("message") or ""
            atts = normalize_attachments(raw.get("attachments")) or []
            return cls(
                text=str(text).strip(),
                attachments=tuple(a for a in atts if isinstance(a, dict)),
            )
        return cls(text=str(raw).strip())

    @classmethod
    def coerce_many(cls, raw_list) -> list["ChatItem"]:
        """归一化并丢弃空项（顺序不变）。"""
        return [i for i in (cls.coerce(r) for r in (raw_list or [])) if not i.is_empty]

    def to_wire(self) -> dict:
        """给前端的形态（落库 / SSE 回执用）。"""
        return {"text": self.text, "attachments": [dict(a) for a in self.attachments]}
