"""兼容重导出层 — 原 opencli_service.py 已迁移至 app.services.content.opencli_service"""
import importlib as _il
_real = _il.import_module("app.services.content.opencli_service")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
