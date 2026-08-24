"""
AIsChat 启动器可复用 UI 组件
=============================
精致、专业的 UI 组件，细节体现品质。
"""
from __future__ import annotations

import customtkinter as ctk

from . import theme


class StatusDot(ctk.CTkFrame):
    """状态指示点（带微妙的发光效果感）。"""

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
    """白色圆角卡片（精致版）：细微边框 + 干净圆角。"""

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
    """胶囊式多选切换：精致的选中态 + 流畅的视觉反馈。"""

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
                corner_radius=theme.RADIUS_PILL, font=(theme.FONT_UI, 11),
                command=lambda v=value: self.set_value(v))
            padx = (2, 1) if i == 0 else ((1, 2) if i == len(self._items) - 1 else (1, 1))
            btn.pack(side="left", padx=padx, pady=2)
            self._buttons[value] = btn

        self.set_value(self._value, notify=False)

    def get_value(self) -> str:
        return self._value

    def set_value(self, value: str, notify: bool = True) -> None:
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
    """日志面板（精致版）：干净的标题栏 + 舒适的阅读体验。"""

    _RENDER_BATCH_LIMIT = 60

    def __init__(self, master, header_widget=None):
        super().__init__(master)
        self._lines: list[tuple[str, str, bool]] = []
        self._detailed = False
        self._batch_remaining = self._RENDER_BATCH_LIMIT

        # ── 标题栏（精致排版）──
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(12, 4))
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self.header_frame, text="运行日志",
            font=(theme.FONT_UI, 12, "bold"),
            text_color=theme.TEXT_PRIMARY, anchor="w")
        self.title_label.grid(row=0, column=0, sticky="w")

        self.hint_label = ctk.CTkLabel(
            self.header_frame, text="",
            font=(theme.FONT_UI, 10),
            text_color=theme.TEXT_MUTED, anchor="e")
        self.hint_label.grid(row=0, column=1, sticky="e", padx=(8, 0))

        if header_widget is not None:
            self.set_header_widget(header_widget)

        # ── 日志文本框（舒适阅读）──
        self._text = ctk.CTkTextbox(
            self,
            font=(theme.FONT_MONO, theme.FONT_LOG_SIZE),
            fg_color=theme.ELEVATED,
            text_color=theme.LOG_DEFAULT,
            corner_radius=theme.RADIUS_TEXTBOX,
            border_width=0,
            wrap="word",
            padx=12,
            pady=10,
        )
        self._text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._text.configure(state="disabled")

        # 日志级别着色
        for tag, color in self._tag_colors().items():
            self._text._textbox.tag_config(tag, foreground=color)

        self.set_detailed(False)

    def set_header_widget(self, widget) -> None:
        widget.grid(row=0, column=2, sticky="e", padx=(10, 0))

    def reset_batch(self) -> None:
        self._batch_remaining = self._RENDER_BATCH_LIMIT

    def append(self, msg: str, key: bool = False) -> None:
        tag = theme.classify_log(msg)
        self._lines.append((msg, tag, key))
        if self._detailed or key or theme.is_brief_error(msg):
            if self._batch_remaining > 0:
                self._raw_insert(msg, tag)
                self._batch_remaining -= 1

    def set_detailed(self, detailed: bool) -> None:
        was_detailed = self._detailed
        self._detailed = bool(detailed)
        self.hint_label.configure(
            text="全部日志" if self._detailed else "关键状态")
        if was_detailed and not self._detailed:
            self._render()
        elif not was_detailed and self._detailed:
            self._append_hidden_lines()

    def clear(self) -> None:
        self._lines.clear()
        self._render()

    def set_log_font_size(self, size: int) -> None:
        self._text.configure(font=(theme.FONT_MONO, size))

    def retheme(self) -> None:
        self.configure(fg_color=theme.SURFACE, border_color=theme.BORDER)
        self.title_label.configure(text_color=theme.TEXT_PRIMARY)
        self.hint_label.configure(text_color=theme.TEXT_MUTED)
        self._text.configure(
            fg_color=theme.ELEVATED, text_color=theme.LOG_DEFAULT)
        for tag, color in self._tag_colors().items():
            self._text._textbox.tag_config(tag, foreground=color)

    def get_all_text(self) -> str:
        return "\n".join(msg for msg, _, _ in self._lines)

    @staticmethod
    def _tag_colors() -> dict[str, str]:
        return {
            "info": theme.LOG_DEFAULT,
            "ok": theme.LOG_OK,
            "warn": theme.LOG_WARN,
            "error": theme.LOG_ERROR,
        }

    def _raw_insert(self, msg: str, tag: str) -> None:
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n", tag)
        self._text.see("end")
        self._text.configure(state="disabled")

    def _append_hidden_lines(self) -> None:
        self._text.configure(state="normal")
        for msg, tag, key in self._lines:
            if not key and not theme.is_brief_error(msg):
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
