"""
Embedding Provider 包（Embedding Backend Providers）

DSH seam 思想的 Python 版：把"文本 → 向量"做成可替换能力。
与 db_providers（存储后端）同构，配置独立于 chat，未来转 JS 契约不变。

    ┌─────────────────────────────┐
    │  EmbeddingProvider (接口)    │
    │  · name                      │
    │  · embed(text) → vector|None │
    │  · dimension() → int|None    │
    └──────────┬──────────────────┘
      ┌────────┼─────────┐
  ollama    api      local     disabled
  Provider  Provider  Provider  Provider(默认降级)

用法：
    from app.embedding_providers import get_embedding_provider
    provider = get_embedding_provider()       # 按 settings.embedding_backend 选择
    vec = await provider.embed("你好")          # None = 降级文本检索
"""

from app.embedding_providers.base import (
    EmbeddingProvider,
    EmbeddingUnavailableError,
)
from app.embedding_providers.registry import (
    get_embedding_provider,
    list_embedding_providers,
)

__all__ = [
    "EmbeddingProvider",
    "EmbeddingUnavailableError",
    "get_embedding_provider",
    "list_embedding_providers",
]
