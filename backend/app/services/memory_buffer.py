"""兼容重导出层 — 原 memory_buffer.py 已迁移至 app.services.memory.memory_buffer"""
import importlib as _il
_real = _il.import_module("app.services.memory.memory_buffer")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
