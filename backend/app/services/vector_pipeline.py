"""兼容重导出层 — 原 vector_pipeline.py 已迁移至 app.services.memory.vector_pipeline"""
import importlib as _il
_real = _il.import_module("app.services.memory.vector_pipeline")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
