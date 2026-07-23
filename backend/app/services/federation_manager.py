"""兼容重导出层 — 原 federation_manager.py 已迁移至 app.services.federation.federation_manager"""
import importlib as _il
_real = _il.import_module("app.services.federation.federation_manager")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
