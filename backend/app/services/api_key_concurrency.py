"""兼容重导出层 — 原 api_key_concurrency.py 已迁移至 app.services.infrastructure.api_key_concurrency"""
import importlib as _il
_real = _il.import_module("app.services.infrastructure.api_key_concurrency")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
