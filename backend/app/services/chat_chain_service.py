"""
兼容重导出层 — 原 chat_chain_service 已迁移至 app.ai.chat_chain
"""
from app.ai.chat_chain import (  # noqa: F401
    ChatChainManager,
    ChainNode,
    RulerTree,
    chat_chain_manager,
    MAX_CONCURRENT_PER_GROUP,
)
