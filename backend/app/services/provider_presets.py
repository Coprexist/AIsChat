"""兼容重导出层 — 原 provider_presets.py 已迁移至 app.services.agent.provider_presets"""
import importlib as _il
_real = _il.import_module("app.services.agent.provider_presets")


def __getattr__(name: str):
    return getattr(_real, name)


def __dir__():
    return dir(_real)
