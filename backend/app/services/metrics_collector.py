"""兼容重导出层 — 原 metrics_collector.py 已迁移至 app.services.infrastructure.metrics_collector"""
import importlib as _il
_real = _il.import_module("app.services.infrastructure.metrics_collector")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
