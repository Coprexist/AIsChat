"""
本地 Embedding Provider — fastembed 离线向量（不依赖任何外部服务）

- 依赖：fastembed（ONNX CPU 推理，无需 torch）
- 首次使用自动下载模型（如 BAAI/bge-small-zh-v1.5，约 100MB），之后离线可用
- 适用：无 Ollama、不想接外部 API、数据不出本机的场景
- 注意：fastembed 是同步库，用 asyncio.to_thread 包一层避免阻塞事件循环
"""

import asyncio
import logging

from app.embedding_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)

# 延迟加载的 fastembed 实例（单例，避免重复加载模型）
_TextEmbedding = None
_embedder_instance = None


def _get_embedder(model: str):
    """懒加载 fastembed.TextEmbedding（同步，仅首次慢）"""
    global _TextEmbedding, _embedder_instance
    if _embedder_instance is not None:
        return _embedder_instance
    try:
        from fastembed import TextEmbedding
    except ImportError:
        logger.warning(
            "[embedding:local] fastembed 未安装，local 后端不可用。"
            "请执行: pip install fastembed"
        )
        return None
    _TextEmbedding = TextEmbedding
    try:
        _embedder_instance = TextEmbedding(model_name=model)
        logger.info(f"[embedding:local] fastembed 加载完成: {model}")
    except Exception as e:
        logger.warning(f"[embedding:local] 模型加载失败: {e}")
        _embedder_instance = None
    return _embedder_instance


class LocalProvider(EmbeddingProvider):
    name = "local"
    requires_service = False

    def __init__(self, model: str = "BAAI/bge-small-zh-v1.5"):
        self.model = model
        self._dimension: int | None = None

    def is_available(self) -> bool:
        try:
            import fastembed  # noqa: F401
            return True
        except ImportError:
            return False

    async def embed(self, text: str) -> list[float] | None:
        embedder = _get_embedder(self.model)
        if embedder is None:
            return None
        try:
            # fastembed 是同步库：丢到线程池，避免阻塞事件循环
            vec = await asyncio.to_thread(
                lambda: next(iter(embedder.embed([text])), None)
            )
            if vec is None:
                return None
            if self._dimension is None:
                self._dimension = len(vec)
            return [float(x) for x in vec]
        except Exception as e:
            logger.warning(f"[embedding:local] embed 失败: {e}")
            return None
