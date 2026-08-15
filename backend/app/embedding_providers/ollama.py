"""
Ollama Embedding Provider — 接入本地/远程 Ollama 实例

- 端点：{base_url}/api/embeddings（Ollama 原生格式，非 OpenAI 兼容）
- 用户已有 Ollama 时直接复用，无需额外部署
- 支持通过 EMBEDDING_BASE_URL 指向远程实例（如局域网另一台机器）
"""

import logging

import httpx

from app.embedding_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class OllamaProvider(EmbeddingProvider):
    name = "ollama"
    requires_service = True

    def __init__(self, base_url: str, model: str, timeout: float = 30.0):
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.timeout = timeout
        # 首次成功 embed 后缓存维度
        self._dimension: int | None = None

    def _embeddings_url(self) -> str:
        return f"{self.base_url}/api/embeddings"

    def dimension(self) -> int | None:
        return self._dimension

    def is_available(self) -> bool:
        return bool(self.base_url and self.model)

    async def embed(self, text: str) -> list[float] | None:
        if not self.is_available():
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self._embeddings_url(),
                    json={"model": self.model, "prompt": text},
                )
                if resp.status_code != 200:
                    logger.warning(
                        f"[embedding:{self.name}] HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    return None
                vec = resp.json().get("embedding")
                if not isinstance(vec, list) or not vec:
                    logger.warning(f"[embedding:{self.name}] 响应无 embedding 字段")
                    return None
                if self._dimension is None:
                    self._dimension = len(vec)
                return [float(x) for x in vec]
        except Exception as e:
            logger.warning(f"[embedding:{self.name}] 调用失败: {e}")
            return None
