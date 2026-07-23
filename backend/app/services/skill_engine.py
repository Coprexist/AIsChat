"""兼容重导出层 — 原 skill_engine.py 已迁移至 app.services.skill.skill_engine"""
import importlib as _il
_real = _il.import_module("app.services.skill.skill_engine")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
