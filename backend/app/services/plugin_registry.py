"""兼容重导出层 — 原 plugin_registry.py 已迁移至 app.services.infrastructure.plugin_registry"""
import importlib as _il
_real = _il.import_module("app.services.infrastructure.plugin_registry")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
