"""兼容重导出层 — 原 skill_service.py 已迁移至 app.services.skill.skill_service"""
import importlib as _il
_real = _il.import_module("app.services.skill.skill_service")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
