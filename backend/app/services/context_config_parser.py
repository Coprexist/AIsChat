"""兼容重导出层 — 原 context_config_parser.py 已迁移至 app.services.memory.context_config_parser"""
import importlib as _il
_real = _il.import_module("app.services.memory.context_config_parser")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
