"""
日志配置模块 — 从 main.py 拆出的独立日志初始化

原则：
- 使用 logging.config.dictConfig 显式配置（不依赖 basicConfig 的"仅首次生效"语义）
- 日志级别通过 LOG_LEVEL 环境变量动态调整（默认 INFO）
- 滚动文件日志避免 app.log 无限增长（单文件 10MB，保留 5 份）
- 配置 uvicorn 日志格式统一（避免默认格式冲突）
- 多进程部署时 RotatingFileHandler 可能交错写——单 worker 部署无此问题，
  多 worker 生产环境建议用 stdout 由 ELK/Loki 收集
- 日志 emoji 是信息设计（✅⚠️💥 是锚点，不是装饰）
"""
import logging
import logging.config
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 日志级别：支持运行时调整（如 LOG_LEVEL=DEBUG）
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# uvicorn access 日志级别（默认 WARNING，减少健康检查刷屏）
_ACCESS_LOG_LEVEL = os.environ.get("UVICORN_ACCESS_LOG_LEVEL", "WARNING").upper()

# 日志文件路径（默认 backend/app.log，可通过 LOG_FILE 覆盖）
_LOG_FILE = os.environ.get(
    "LOG_FILE",
    str(Path(__file__).resolve().parent.parent / "app.log"),
)


def setup_logging() -> None:
    """初始化日志配置（必须在任何项目模块 import 之前调用）"""
    # 确保日志文件父目录存在；创建失败则降级为仅控制台输出
    _use_file = True
    log_dir = os.path.dirname(_LOG_FILE)
    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            print(f"[WARN] 日志目录创建失败: {e}，降级为仅控制台输出")
            _use_file = False

    handlers: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "level": _LOG_LEVEL,
            "formatter": "standard",
        },
    }
    root_handlers = ["console"]

    if _use_file:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": _LOG_LEVEL,
            "formatter": "standard",
            "filename": _LOG_FILE,
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8",
        }
        root_handlers.append("file")

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,  # 保留已有 logger（如第三方库）
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
            },
        },
        "handlers": handlers,
        "loggers": {
            # 统一 uvicorn 日志格式（与应用日志一致）
            "uvicorn": {
                "handlers": list(handlers.keys()),
                "level": _LOG_LEVEL,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": list(handlers.keys()),
                "level": _LOG_LEVEL,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": list(handlers.keys()),
                "level": _ACCESS_LOG_LEVEL,
                "propagate": False,
            },
            # 应用 logger
            "app": {
                "handlers": list(handlers.keys()),
                "level": _LOG_LEVEL,
                "propagate": False,
            },
        },
        "root": {
            "level": _LOG_LEVEL,
            "handlers": root_handlers,
        },
    })
