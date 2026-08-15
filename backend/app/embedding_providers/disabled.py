"""
Disabled Embedding Provider — 默认降级（不启用向量）

- embed() 恒返回 None → 所有调用方自动走文本检索降级
- 行为与"未配置任何 embedding"完全一致，是默认后端
"""

import logging

from app.embedding_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class DisabledProvider(EmbeddingProvider):
    name = "disabled"
    requires_service = False

    async def embed(self, text: str) -> list[float] | None:
        return None

    def is_available(self) -> bool:
        return False

    def describe(self) -> dict:
        return {
            "name": self.name,
            "requires_service": False,
            "dimension": None,
            "note": "未启用向量检索，记忆使用文本检索",
        }


disabled_provider = DisabledProvider()
