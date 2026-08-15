"""
Embedding 提供方注册表（Registry）

按 settings.embedding_backend 选择当前生效的 Provider。
新增提供方只需在 PROVIDERS 里登记——业务代码零改动（同 db_providers）。

热更新支持：Provider 的 base_url/model/api_key 从 settings 动态读取
（settings 已接入 DBConfigSource，DB 覆盖 env），保存配置后无需重启，
下次 embed 自动用新配置。
"""

import logging

from app.embedding_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)

# 已注册的 Provider（按名登记，懒加载）
_PROVIDERS: dict[str, EmbeddingProvider] = {}


def _current_settings():
    """动态获取当前 settings（每次读取最新引用，支持 DB 覆盖热更新）"""
    from app.config import settings
    return settings


def _register_all() -> None:
    """延迟导入避免循环依赖（config → 本包 → provider → httpx）"""
    if _PROVIDERS:
        return
    from app.embedding_providers.ollama import OllamaProvider
    from app.embedding_providers.api import OpenAICompatProvider
    from app.embedding_providers.local import LocalProvider
    from app.embedding_providers.disabled import disabled_provider

    # Provider 实例只做一次注册；其 base_url/model/api_key 在 embed() 时
    # 通过 self.settings 动态读取（含 DB 覆盖），支持运行时热更新。
    _PROVIDERS["ollama"] = OllamaProvider()
    _PROVIDERS["api"] = OpenAICompatProvider()
    _PROVIDERS["local"] = LocalProvider()
    _PROVIDERS["disabled"] = disabled_provider


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    """获取当前生效的 Embedding Provider。

    未指定 name 时按 settings.embedding_backend 选择（DB 覆盖 > env > 默认）；
    未知后端回退到 disabled（纯文本检索）并告警。
    """
    _register_all()
    settings = _current_settings()
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
