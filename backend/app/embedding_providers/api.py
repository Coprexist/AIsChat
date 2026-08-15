"""
OpenAI 兼容 Embedding API Provider — 接入任意 /v1/embeddings 端点

- 端点：{base_url}/v1/embeddings（OpenAI 标准格式）
- 兼容：OpenAI、硅基流动（BAAI/bge-large-zh-v1.5）、智谱（embedding-2）、
  阿里云 DashScope（text-embedding-v3）等一切 OpenAI 兼容服务
- 接口语义与 dsh-mneme 的 vector 配置（enabled/baseUrl/apiKey/model）一一对应，
  未来转 JS 时配置键不变
"""

import logging

import httpx

from app.embedding_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class OpenAICompatProvider(EmbeddingProvider):
    name = "api"
    requires_service = True

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        # 支持显式传入（测试用）；默认从 settings 动态读取（含 DB 覆盖，热更新）
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self.timeout = timeout
        self._dimension: int | None = None

    @property
    def base_url(self) -> str:
        from app.config import settings as _s
        return (self._base_url or _s.embedding_base_url or "").rstrip("/")

    @property
    def model(self) -> str:
        from app.config import settings as _s
        return self._model or _s.embedding_model or "text-embedding-3-small"

    @property
    def api_key(self) -> str:
        from app.config import settings as _s
        return self._api_key if self._api_key is not None else (_s.embedding_api_key or "")

    def _embeddings_url(self) -> str:
        # 接受 "https://host/v1" 或完整 "/v1/embeddings" 路径
        if self.base_url.rstrip("/").endswith("/embeddings"):
            return self.base_url
        return f"{self.base_url}/v1/embeddings"

    def dimension(self) -> int | None:
        return self._dimension

    def is_available(self) -> bool:
        return bool(self.base_url and self.model)

    async def embed(self, text: str) -> list[float] | None:
        if not self.is_available():
            return None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self._embeddings_url(),
                    headers=headers,
                    json={"model": self.model, "input": text[:8000]},
                )
                if resp.status_code != 200:
                    logger.warning(
                        f"[embedding:{self.name}] HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    return None
                vec = resp.json().get("data", [{}])[0].get("embedding")
                if not isinstance(vec, list) or not vec:
                    logger.warning(f"[embedding:{self.name}] 响应无 embedding 字段")
                    return None
                if self._dimension is None:
                    self._dimension = len(vec)
                return [float(x) for x in vec]
        except Exception as e:
            logger.warning(f"[embedding:{self.name}] 调用失败: {e}")
            return None
