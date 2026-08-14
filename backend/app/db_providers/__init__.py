"""
存储后端 Provider 包（Storage Backend Providers）

DSH seam 思想的 Python 版：把"数据库后端"做成可替换能力。

    ┌─────────────────────────────┐
    │  BaseProvider (接口)         │
    │  · engine_url               │
    │  · vector_column_type       │
    │  · vector_search_sql        │
    │  · hybrid_search_sql        │
    │  · is_available()           │
    └──────────┬──────────────────┘
      ┌────────┼─────────┐
  Postgres  SQLite   PGlite
  Provider  Provider  Provider(规划)

用法：
    from app.db_providers import get_provider
    provider = get_provider()          # 按 settings.db_backend 选择
    provider.vector_search_sql(...)    # 返回带方言的 SQL 片段
"""

from app.db_providers.base import BaseProvider
from app.db_providers.registry import get_provider, list_providers

__all__ = ["BaseProvider", "get_provider", "list_providers", "vector_column", "json_column"]


def vector_column(dimensions: int):
    """返回当前后端适用的向量列类型（供模型 Column 使用）。"""
    return get_provider().vector_column(dimensions)


def json_column():
    """返回当前后端适用的 JSON 列类型（PG→JSONB，SQLite→JSON/TEXT）。

    对齐 SQLAlchemy 惯用法：PG 上编译为 JSONB（支持 @> 等操作符），
    SQLite 上编译为 JSON（存 TEXT）。
    """
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB
    return JSON().with_variant(JSONB, "postgresql")
