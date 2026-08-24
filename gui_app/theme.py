"""
AIsChat 启动器设计令牌（Design Tokens）
=======================================
双主题色系统（对齐前端品牌）：
- purple：紫金（默认）—— 与前端 primary #8B5CF6 同款
- teal  ：青碧（第二主题色）—— 原有 #2eb8a6

颜色通过模块级动态属性读取（`theme.PRIMARY` 等），
`theme.switch(name)` 切换后，调用方重新应用即可全局换肤。
字体 / 圆角 / 服务地址为静态常量。
"""
from __future__ import annotations

# ── 主题调色板 ──
PALETTES: dict[str, dict[str, str]] = {
    # ── 紫金（默认，对齐前端 tailwind primary 紫 + slate 中性色）──
    "purple": {
        # 品牌主色
        "PRIMARY": "#8B5CF6",
        "PRIMARY_HOVER": "#7C3AED",
        "PRIMARY_PRESSED": "#6D28D9",
        "PRIMARY_SOFT": "#F5F3FF",
        "PRIMARY_SOFT_TEXT": "#6D28D9",
        # 危险 / 停止（前端 rose 系）
        "DANGER": "#E84A69",
        "DANGER_HOVER": "#BE123C",
        "DANGER_SOFT": "#FDE8EE",
        # 状态色（语义色，两主题共用）
        "STATUS_RUNNING": "#10B981",
        "STATUS_STARTING": "#F59E0B",
        "STATUS_STOPPED": "#94A3B8",
        "STATUS_FAILED": "#E84A69",
        # 中性色（浅色主题，slate 系）
        "CANVAS": "#F8FAFC",
        "SURFACE": "#FFFFFF",
        "ELEVATED": "#F1F5F9",
        "BORDER": "#E2E8F0",
        "BORDER_STRONG": "#CBD5E1",
        "TEXT_PRIMARY": "#0F172A",
        "TEXT_SECONDARY": "#475569",
        "TEXT_MUTED": "#94A3B8",
        # 日志配色
        "LOG_DEFAULT": "#334155",
        "LOG_OK": "#047857",
        "LOG_WARN": "#B45309",
        "LOG_ERROR": "#DC2626",
    },
    # ── 青碧（第二主题色）──
    "teal": {
        "PRIMARY": "#2EB8A6",
        "PRIMARY_HOVER": "#249B8B",
        "PRIMARY_PRESSED": "#1D8A7D",
        "PRIMARY_SOFT": "#E0F4F1",
        "PRIMARY_SOFT_TEXT": "#0E7C6E",
        "DANGER": "#E8445E",
        "DANGER_HOVER": "#D63655",
        "DANGER_SOFT": "#FDE8EC",
        "STATUS_RUNNING": "#10B981",
        "STATUS_STARTING": "#F59E0B",
        "STATUS_STOPPED": "#94A3B8",
        "STATUS_FAILED": "#E8445E",
        "CANVAS": "#F4F7F9",
        "SURFACE": "#FFFFFF",
        "ELEVATED": "#EEF2F6",
        "BORDER": "#E2E8F0",
        "BORDER_STRONG": "#CBD5E1",
        "TEXT_PRIMARY": "#0F172A",
        "TEXT_SECONDARY": "#475569",
        "TEXT_MUTED": "#94A3B8",
        "LOG_DEFAULT": "#334155",
        "LOG_OK": "#0F766E",
        "LOG_WARN": "#B45309",
        "LOG_ERROR": "#DC2626",
    },
}

# ── 主题元信息 ──
THEME_NAMES = ["purple", "teal"]
THEME_LABELS = {"purple": "紫金 · 默认", "teal": "青碧"}
DEFAULT_THEME = "purple"

_active_theme = DEFAULT_THEME


def active_name() -> str:
    """当前主题名。"""
    return _active_theme


def switch(name: str) -> None:
    """切换当前主题；未知名称忽略。"""
    global _active_theme
    if name in PALETTES:
        _active_theme = name


def __getattr__(name: str):
    """动态颜色属性：theme.PRIMARY → 当前主题的 PRIMARY。"""
    palette = PALETTES[_active_theme]
    if name in palette:
        return palette[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── 静态常量 ──

# 字体
FONT_UI = "Microsoft YaHei UI"
FONT_UI_FALLBACK = "Microsoft YaHei"
FONT_MONO = "Consolas"

# 圆角（对齐前端 rounded-xl / rounded-2xl / 胶囊）
RADIUS_CARD = 16
RADIUS_BUTTON = 12
RADIUS_PILL = 999
RADIUS_TEXTBOX = 12
RADIUS_CHIP = 999

# 服务地址
BASE_URL = "http://127.0.0.1:8000"
HEALTH_URL = BASE_URL + "/health"


def is_brief_error(msg: str) -> bool:
    """简要模式下额外展示的原始日志：仅错误/失败类（供非专业用户发现问题）。"""
    return any(k in msg for k in ("ERROR", "Error", "Traceback", "Exception", "失败", "错误"))


def classify_log(msg: str) -> str:
    """日志级别分类 → 着色标签：error / warn / ok / info。"""
    if any(k in msg for k in ("ERROR", "Error", "Traceback", "Exception", "失败", "错误")):
        return "error"
    if any(k in msg for k in ("WARNING", "Warning", "WARN")):
        return "warn"
    if any(k in msg for k in ("就绪", "启动完成", "成功", "已启动", "正常运行")):
        return "ok"
    return "info"
