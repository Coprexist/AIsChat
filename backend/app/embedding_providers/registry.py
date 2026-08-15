"""
Embedding 提供方注册表（Registry）

按 settings.embedding_backend 选择当前生效的 Provider。
新增提供方只需在 PROVIDERS 里登记——业务代码零改动（同 db_providers）。
"""

import logging

from app.config import settings
from app.embedding_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)

# 已注册的 Provider（按名登记，懒加载）
_PROVIDERS: dict[str, EmbeddingProvider] = {}


def _register_all() -> None:
    """延迟导入避免循环依赖（config → 本包 → provider → httpx）"""
    if _PROVIDERS:
        return
    from app.embedding_providers.ollama import OllamaProvider
    from app.embedding_providers.api import OpenAICompatProvider
    from app.embedding_providers.local import LocalProvider
    from app.embedding_providers.disabled import disabled_provider

    # 按后端补默认模型（配置未显式指定时）
    base_url = settings.embedding_base_url
    model = settings.embedding_model

    _PROVIDERS["ollama"] = OllamaProvider(
        base_url=base_url or "http://127.0.0.1:11434",
        model=model or "nomic-embed-text",
    )
    _PROVIDERS["api"] = OpenAICompatProvider(
        base_url=base_url,
        model=model or "text-embedding-3-small",
        api_key=settings.embedding_api_key,
    )
    _PROVIDERS["local"] = LocalProvider(model=model or "BAAI/bge-small-zh-v1.5")
    _PROVIDERS["disabled"] = disabled_provider


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    """获取当前生效的 Embedding Provider。

    未指定 name 时按 settings.embedding_backend 选择；
    未知后端回退到 disabled（纯文本检索）并告警。
    """
    _register_all()
    selected = (name or settings.embedding_backend or "disabled").lower()
    provider = _PROVIDERS.get(selected)
    if provider is None:
        logger.warning(
            f"未知 embedding 后端 '{selected}'，回退到 disabled（文本检索）"
        )
        provider = _PROVIDERS["disabled"]
    return provider


def list_embedding_providers() -> list[dict]:
    """列出所有已注册提供方（供设置界面/诊断展示）。"""
    _register_all()
    return [p.describe() for p in _PROVIDERS.values()]
