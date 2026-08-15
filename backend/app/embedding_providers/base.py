"""
Embedding 提供方抽象基类（EmbeddingProvider）

与 db_providers 同构：把"文本 → 向量"的能力封装成统一接口，
按 settings.embedding_backend 注册表切换，消费方零改动。

    ┌─────────────────────────────┐
    │  EmbeddingProvider (接口)    │
    │  · name                      │
    │  · embed(text) → vector|None │
    │  · dimension() → int|None    │
    │  · is_available() → bool     │
    └──────────┬──────────────────┘
      ┌────────┼─────────┐
  ollama    api      local     disabled
  Provider  Provider  Provider  Provider(默认降级)

设计原则（对齐 dsh-mneme 的向量哲学）：
  - 向量是"可选增强"：embed 失败返回 None，永不抛异常打断主流程
  - 配置与 chat 完全解耦：EMBEDDING_* 独立于 DEEPSEEK_BASE_URL
  - 接口语义对齐 OpenAI 兼容 /embeddings 端点（未来转 JS 契约不变）
"""

from abc import ABC, abstractmethod
from typing import Any


class EmbeddingProvider(ABC):
    """文本嵌入提供方抽象接口"""

    #: 提供方标识，如 "ollama" / "api" / "local" / "disabled"
    name: str = "base"

    #: 是否需要在外部运行一个服务（ollama 需要，local/disabled 不需要）
    requires_service: bool = False

    @abstractmethod
    async def embed(self, text: str) -> list[float] | None:
        """把一段文本转成向量。

        失败返回 None（调用方自动降级为文本检索），绝不抛异常。
        这是与旧实现的关键差异：旧实现失败抛异常，靠调用方 try/except 兜底；
        新实现把"失败无感"下沉到 Provider 层。
        """
        raise NotImplementedError

    def dimension(self) -> int | None:
        """当前模型的向量维度；未知返回 None（调用方用缓存/默认值）。"""
        return None

    def is_available(self) -> bool:
        """自检：该提供方当前是否可用（配置齐全、服务可达等）。"""
        return True

    def describe(self) -> dict:
        """提供方信息（用于诊断/设置界面展示）。"""
        return {
            "name": self.name,
            "requires_service": self.requires_service,
            "dimension": self.dimension(),
        }


class EmbeddingUnavailableError(RuntimeError):
    """Embedding 不可用（未配置 / 全部 Provider 失败）。

    供需要"必须拿到向量"的调用方（如 routers/memories.py）显式捕获，
    其余调用方自行降级。
    """
