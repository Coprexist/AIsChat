"""兼容重导出层 — 原 event_bus.py 已迁移至 app.services.brain.event_bus"""
import importlib as _il
_real = _il.import_module("app.services.brain.event_bus")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
