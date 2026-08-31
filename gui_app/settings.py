"""
启动器本地设置
==============
持久化到 `data/launcher_settings.json`（与后端数据同目录，exe / 源码运行均可用）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULTS = {"theme": "purple", "log_font_size": "13", "port": "8000",
            "auto_start": False, "minimize_to_tray": True}


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent.parent / "data"


def load() -> dict:
    """读取设置；文件缺失或损坏时回退默认值。"""
    try:
        path = _data_dir() / "launcher_settings.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return {**DEFAULTS, **data}
    except Exception:
        return dict(DEFAULTS)


def save(settings: dict) -> None:
    """写入设置；失败静默（不阻塞启动器）。"""
    try:
        path = _data_dir() / "launcher_settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
