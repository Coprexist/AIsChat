"""
存储后端注册表（Registry）

按 settings.db_backend 选择当前生效的 Provider。
新增后端只需在 PROVIDERS 里登记——业务代码零改动（DSH 注册即副作用思想）。
"""

import logging

from app.config import settings
from app.db_providers.base import BaseProvider

logger = logging.getLogger(__name__)

# 已注册的 Provider（按名登记）
PROVIDERS: dict[str, BaseProvider] = {}

# 延迟导入避免循环依赖
def _register_all():
    if PROVIDERS:
        return
    from app.db_providers.postgres import postgres_provider
    from app.db_providers.sqlite import sqlite_provider
    PROVIDERS["postgres"] = postgres_provider
    PROVIDERS["sqlite"] = sqlite_provider
    # 规划中：PGlite Provider
    # from app.db_providers.pglite import pglite_provider
    # PROVIDERS["pglite"] = pglite_provider


def get_provider(name: str | None = None) -> BaseProvider:
    """获取当前生效的存储 Provider。

    未指定 name 时按 settings.db_backend 选择；
    未知后端回退到 postgres 并告警。
    """
    _register_all()
    selected = (name or settings.db_backend or "postgres").lower()
    provider = PROVIDERS.get(selected)
    if provider is None:
        logger.warning(
            f"未知数据库后端 '{selected}'，回退到 postgres"
        )
        provider = PROVIDERS["postgres"]
    return provider


def list_providers() -> list[dict]:
    """列出所有已注册后端（供设置界面/诊断展示）。"""
    _register_all()
    return [p.describe() for p in PROVIDERS.values()]
