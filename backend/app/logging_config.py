"""
日志配置模块 — 从 main.py 拆出的独立日志初始化

原则：
- 使用 logging.config.dictConfig 显式配置（不依赖 basicConfig 的"仅首次生效"语义）
- 日志级别通过 LOG_LEVEL 环境变量动态调整（默认 INFO）
- 滚动文件日志避免 app.log 无限增长（单文件 10MB，保留 5 份）
- 多进程部署时 RotatingFileHandler 可能交错写——单 worker 部署无此问题，
  多 worker 生产环境建议用 stdout 由 ELK/Loki 收集
"""
import logging
import logging.config
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 日志级别：支持运行时调整（如 LOG_LEVEL=DEBUG）
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# 日志文件路径（默认 backend/app.log，可通过 LOG_FILE 覆盖）
_LOG_FILE = os.environ.get(
    "LOG_FILE",
    str(Path(__file__).resolve().parent.parent / "app.log"),
)


def setup_logging() -> None:
    """初始化日志配置（必须在任何项目模块 import 之前调用）"""
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,  # 保留已有 logger（如第三方库）
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": _LOG_LEVEL,
                "formatter": "standard",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": _LOG_LEVEL,
                "formatter": "standard",
                "filename": _LOG_FILE,
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": _LOG_LEVEL,
            "handlers": ["console", "file"],
        },
    })
