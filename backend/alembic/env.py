"""
Alembic 迁移环境配置 — 自动检测模型变更，生成迁移脚本

用法：
  alembic revision --autogenerate -m "描述变更"
  alembic upgrade head
"""
import logging as _logging
import os
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使得 from app import ... 可工作
sys.path.insert(0, str(Path(__file__).parent.parent))

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic 配置对象
config = context.config


def _restore_app_logging() -> None:
    """恢复应用日志配置。

    fileConfig 会把根 logger 的 handler 换成 alembic.ini 的 console，
    并默认禁用已存在的 logger，导致迁移完成后应用日志全部静默
    （worker 启动、就绪提示、uvicorn 收尾日志都消失）。这里重建应用
    StreamHandler + FileHandler，保持迁移后日志不中断。
    """
    root = _logging.getLogger()
    root.handlers = []
    root.setLevel(_logging.INFO)
    log_file = os.environ.get(
        "LOG_FILE",
        str(Path(__file__).resolve().parent.parent / "app.log"),
    )
    fmt = _logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    for h in (_logging.StreamHandler(), _logging.FileHandler(log_file, encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)


# 日志配置（disable_existing_loggers=False：不禁用已存在的 app.* logger）
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
    _restore_app_logging()

# ── 从应用导入 Base 和所有模型（使 autogenerate 可检测） ──
from app.database import Base
from app.models import *  # noqa: F403 — 确保所有模型表元数据注册到 Base.metadata

target_metadata = Base.metadata

# ── 数据库 URL 从应用配置读取（避免在 .ini 中硬编码） ──
from app.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.database_url_sync)


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 脚本，不连接数据库"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
