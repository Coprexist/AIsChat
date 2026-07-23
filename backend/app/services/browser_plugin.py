"""兼容重导出层 — 原 browser_plugin.py 已迁移至 app.services.content.browser_plugin"""
import importlib as _il
_real = _il.import_module("app.services.content.browser_plugin")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
