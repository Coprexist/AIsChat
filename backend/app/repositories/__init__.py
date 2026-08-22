"""
Repository 层 — 数据访问抽象。

业务服务应依赖这些接口，而不是直接使用 SQLAlchemy 的 AsyncSession。
具体实现由基础设施层提供（当前为 SQLAlchemy）。
"""
