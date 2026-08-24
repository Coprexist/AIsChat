"""
AIsChat 启动器可复用 UI 组件
=============================
- StatusDot      圆形状态指示点
- Card           白色圆角卡片（描边容器，支持换肤）
- PillSwitch     胶囊式多选切换（日志简要/详细、主题色选择共用）
- LogPanel       带简要/详细过滤、按级别着色、支持换肤的日志面板
"""
from __future__ import annotations

import customtkinter as ctk

from . import theme


class StatusDot(ctk.CTkFrame):
    """圆形状态指示点（固定尺寸，颜色可动态切换）。"""

    def __init__(self, master, size: int = 10, color: str = theme.STATUS_STOPPED):
        super().__init__(
            master,
            width=size,
            height=size,
            corner_radius=max(1, size // 2),
            fg_color=color,
        )
        self._size = size

    def set_color(self, color: str) -> None:
        self.configure(fg_color=color)


class Card(ctk.CTkFrame):
    """白色圆角卡片：描边 + 统一圆角，作为内容容器。"""

    def __init__(self, master, corner_radius: int = theme.RADIUS_CARD, **kwargs):
        super().__init__(
            master,
            corner_radius=corner_radius,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            **kwargs,
        )

    def retheme(self) -> None:
        self.configure(fg_color=theme.SURFACE, border_color=theme.BORDER)


class PillSwitch(ctk.CTkFrame):
    """胶囊式多选切换：选中项为当前主题主色实底，未选中为白底。

    items: [(value, label), ...]；command(value) 在用户点击时回调。
    """

    _BTN_WIDTH = 64
    _BTN_HEIGHT = 28

    def __init__(self, master, items: list[tuple[str, str]], command=None,
                 btn_width: int | None = None):
        super().__init__(
            master,
            fg_color=theme.ELEVATED,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=theme.RADIUS_PILL,
        )
        self._command = command
        self._items = list(items)
        self._value = self._items[0][0]
        self._buttons: dict[str, ctk.CTkButton] = {}
        btn_width = btn_width or self._BTN_WIDTH

        for i, (value, label) in enumerate(self._items):
            btn = ctk.CTkButton(
                self, text=label, width=btn_width, height=self._BTN_HEIGHT,
                corner_radius=theme.RADIUS_PILL, font=(theme.FONT_UI, 12),
                command=lambda v=value: self.set_value(v))
            padx = (2, 1) if i == 0 else ((1, 2) if i == len(self._items) - 1 else (1, 1))
            btn.pack(side="left", padx=padx, pady=2)
            self._buttons[value] = btn

        self.set_value(self._value, notify=False)

    def get_value(self) -> str:
        return self._value

    def set_value(self, value: str, notify: bool = True) -> None:
        """切换选中态并重绘胶囊配色（换肤时 notify=False 复用）。"""
        if value not in self._buttons:
            return
        self._value = value
        for v, btn in self._buttons.items():
            if v == value:
                btn.configure(
                    fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                    text_color="#ffffff", text_color_disabled="#ffffff")
            else:
                btn.configure(
                    fg_color=theme.SURFACE, hover_color=theme.BORDER,
                    text_color=theme.TEXT_SECONDARY, text_color_disabled=theme.TEXT_MUTED)
        if notify and self._command is not None:
            self._command(value)


class LogPanel(Card):
    """日志面板：缓存全部日志行，按简要/详细过滤展示，并按级别着色。"""

    def __init__(self, master, header_widget=None):
        super().__init__(master)
        self._lines: list[tuple[str, str, bool]] = []   # (消息, 级别标签, 是否关键状态行)
        self._detailed = False

        # ── 标题行：左标题 + 右提示/右侧控件 ──
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=16, pady=(10, 2))
        self.header_frame.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(
            self.header_frame, text="运行日志", font=(theme.FONT_UI, 12, "bold"),
            text_color=theme.TEXT_PRIMARY, anchor="w")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.hint_label = ctk.CTkLabel(
            self.header_frame, text="", font=(theme.FONT_UI, 10),
            text_color=theme.TEXT_MUTED, anchor="e")
        self.hint_label.grid(row=0, column=1, sticky="e", padx=(8, 0))
        if header_widget is not None:
            self.set_header_widget(header_widget)

        # ── 日志文本框（内置滚动条，随内容自动出现）──
        self._text = ctk.CTkTextbox(
            self,
            font=(theme.FONT_MONO, 11),
            fg_color=theme.SURFACE,
            text_color=theme.LOG_DEFAULT,
            corner_radius=theme.RADIUS_TEXTBOX,
            border_width=1,
            border_color=theme.BORDER,
            wrap="word",
            padx=10,
            pady=8,
            scrollbar_button_color=theme.BORDER_STRONG,
            scrollbar_button_hover_color=theme.TEXT_MUTED,
        )
        self._text.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self._text.configure(state="disabled")

        # 日志级别着色标签（CTkTextbox 内部为 tk.Text，标签直接配置其上）
        for tag, color in self._tag_colors().items():
            self._text._textbox.tag_config(tag, foreground=color)

        self.set_detailed(False)

    # ── 对外接口 ──

    def set_header_widget(self, widget) -> None:
        """在标题行右侧放置控件（如日志模式切换）。"""
        widget.grid(row=0, column=2, sticky="e", padx=(10, 0))

    def append(self, msg: str, key: bool = False) -> None:
        """追加一条日志。

        key=True 表示界面生成的关键状态行（简要模式始终显示）；
        原始后端日志仅在详细模式显示，错误/失败类除外（简要模式也会显示）。
        """
        tag = theme.classify_log(msg)
        self._lines.append((msg, tag, key))
        if self._detailed or key or theme.is_brief_error(msg):
            self._insert_line(msg, tag)

    def set_detailed(self, detailed: bool) -> None:
        """切换简要 / 详细模式并重绘。"""
        self._detailed = bool(detailed)
        self.hint_label.configure(
            text="全部日志" if self._detailed else "关键状态")
        self._render()

    def clear(self) -> None:
        self._lines.clear()
        self._render()

    def retheme(self) -> None:
        """换肤：重读当前主题令牌并重绘全部颜色（含已存在日志行的标签色）。"""
        self.configure(fg_color=theme.SURFACE, border_color=theme.BORDER)
        self.title_label.configure(text_color=theme.TEXT_PRIMARY)
        self.hint_label.configure(text_color=theme.TEXT_MUTED)
        self._text.configure(
            fg_color=theme.SURFACE, text_color=theme.LOG_DEFAULT,
            border_color=theme.BORDER,
            scrollbar_button_color=theme.BORDER_STRONG,
            scrollbar_button_hover_color=theme.TEXT_MUTED)
        for tag, color in self._tag_colors().items():
            self._text._textbox.tag_config(tag, foreground=color)

    # ── 内部实现 ──

    @staticmethod
    def _tag_colors() -> dict[str, str]:
        return {
            "info": theme.LOG_DEFAULT,
            "ok": theme.LOG_OK,
            "warn": theme.LOG_WARN,
            "error": theme.LOG_ERROR,
        }

    def _insert_line(self, msg: str, tag: str) -> None:
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n", tag)
        self._text.see("end")
        self._text.configure(state="disabled")

    def _render(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        for msg, tag, key in self._lines:
            if self._detailed or key or theme.is_brief_error(msg):
                self._text.insert("end", msg + "\n", tag)
        self._text.see("end")
        self._text.configure(state="disabled")
