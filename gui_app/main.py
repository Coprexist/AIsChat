"""
AIsChat 桌面启动器主窗口
========================
品牌风格对齐前端：紫色系（默认，紫金 #8B5CF6）+ 青碧第二主题色（设置页切换）。
功能保持：合并启动/停止按钮、自动打开浏览器、日志简要/详细切换。
"""
from __future__ import annotations

import sys
import time
import webbrowser
from pathlib import Path

import customtkinter as ctk

from . import settings, theme
from .controller import (
    EVENT_CRASHED,
    EVENT_FAILED,
    EVENT_STARTED,
    EVENT_STOPPED,
    STATE_RUNNING,
    STATE_STARTING,
    STATE_STOPPED,
    STATE_STOPPING,
    ServerController,
)
from .widgets import Card, PillSwitch, StatusDot, LogPanel

POLL_INTERVAL_MS = 250          # 日志泵 / 状态机轮询间隔
AUTO_START_DELAY_MS = 600       # 窗口显示后自动启动的延迟
CLOSE_GRACE_SECONDS = 3.0       # 关闭窗口时等待服务退出的最长时间


def _candidate_logo_paths() -> list[Path]:
    """按运行形态解析品牌 Logo 路径（exe 打包 / 源码运行）。"""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
        return [
            base / "frontend" / "dist" / "logo-transparent.png",
            base / "frontend" / "public" / "logo-transparent.png",
        ]
    root = Path(__file__).resolve().parent.parent
    return [
        root / "frontend" / "dist" / "logo-transparent.png",
        root / "frontend" / "public" / "logo-transparent.png",
    ]


class AIsChatGUI:
    """AIsChat 桌面启动器主窗口。"""

    # 状态 → 界面表现（按钮 / 状态点 / 提示文案）
    _STATE_UI = {
        STATE_STOPPED: dict(
            status="服务未启动", dot=theme.STATUS_STOPPED,
            btn_text="启动服务", btn_fg=theme.PRIMARY, btn_hover=theme.PRIMARY_HOVER,
            open_enabled=False, hint="服务启动后将自动打开浏览器"),
        STATE_STARTING: dict(
            status="正在启动服务…", dot=theme.STATUS_STARTING,
            btn_text="启动中…", btn_fg=theme.STATUS_STARTING, btn_hover=theme.STATUS_STARTING,
            btn_disabled=True, open_enabled=False, hint="正在初始化后端，请稍候…"),
        STATE_RUNNING: dict(
            status="服务运行中", dot=theme.STATUS_RUNNING,
            btn_text="停止服务", btn_fg=theme.DANGER, btn_hover=theme.DANGER_HOVER,
            open_enabled=True, hint="服务运行中，可随时停止"),
        STATE_STOPPING: dict(
            status="正在停止服务…", dot=theme.STATUS_STARTING,
            btn_text="停止中…", btn_fg=theme.STATUS_STARTING, btn_hover=theme.STATUS_STARTING,
            btn_disabled=True, open_enabled=False, hint="正在优雅退出…"),
        "failed": dict(
            status="启动失败，请查看日志", dot=theme.STATUS_FAILED,
            btn_text="重新启动", btn_fg=theme.PRIMARY, btn_hover=theme.PRIMARY_HOVER,
            open_enabled=False, hint="可点击按钮重试，或查看下方日志定位问题"),
    }

    def __init__(self, auto_start: bool = True):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self.root = ctk.CTk()
        self.root.title("AIsChat 启动器")
        self.root.configure(fg_color=theme.CANVAS)
        self.root.minsize(680, 480)
        self._center_window()

        self.controller = ServerController()
        self.detailed_log = False
        self._state = STATE_STOPPED
        self._settings_visible = False

        # 加载本地设置并应用主题（默认紫金，青碧为第二主题色）
        self._settings = settings.load()
        theme.switch(self._settings.get("theme", theme.DEFAULT_THEME))

        self._build_ui()
        self._apply_theme()
        self._apply_state(STATE_STOPPED)
        self._set_icon()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(POLL_INTERVAL_MS, self._tick)
        if auto_start:
            self.root.after(AUTO_START_DELAY_MS, self.toggle_server)

    # ── UI 构建 ──

    def _build_ui(self) -> None:
        # ── 顶栏：Logo（无色块）+ 标题 + 设置入口 ──
        self.header = ctk.CTkFrame(self.root, fg_color="transparent")
        self.header.pack(fill="x", padx=26, pady=(20, 2))
        self.logo_label = ctk.CTkLabel(
            self.header, text="AI", font=(theme.FONT_UI, 15, "bold"),
            text_color=theme.PRIMARY)   # 无底色块
        self.logo_label.pack(side="left", padx=(0, 12))
        title_block = ctk.CTkFrame(self.header, fg_color="transparent")
        title_block.pack(side="left")
        self._title_labels = []
        self._title_labels.append(ctk.CTkLabel(
            title_block, text="AIsChat 启动器",
            font=(theme.FONT_UI, 17, "bold"), text_color=theme.TEXT_PRIMARY))
        self._title_labels[-1].pack(anchor="w")
        self._subtitle_labels = [ctk.CTkLabel(
            title_block, text="本地 AI 社交网络 · 一键启动后端服务",
            font=(theme.FONT_UI, 10), text_color=theme.TEXT_MUTED)]
        self._subtitle_labels[-1].pack(anchor="w", pady=(1, 0))

        self.gear_btn = ctk.CTkButton(
            self.header, text="设置", command=self._toggle_settings,
            width=64, height=30, corner_radius=theme.RADIUS_BUTTON,
            font=(theme.FONT_UI, 12),
            fg_color=theme.SURFACE, hover_color=theme.ELEVATED,
            border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_SECONDARY)
        self.gear_btn.pack(side="right")

        # ── 设置卡片（默认隐藏，点“设置”展开）──
        self.settings_card = Card(self.root)
        self.settings_card.grid_columnconfigure(1, weight=1)
        self.settings_title = ctk.CTkLabel(
            self.settings_card, text="主题色", font=(theme.FONT_UI, 12, "bold"),
            text_color=theme.TEXT_PRIMARY, anchor="w")
        self.settings_title.grid(row=0, column=0, sticky="w", padx=(16, 12), pady=10)
        self.theme_picker = PillSwitch(
            self.settings_card,
            items=[(name, theme.THEME_LABELS[name]) for name in theme.THEME_NAMES],
            command=self._set_theme, btn_width=88)
        self.theme_picker.grid(row=0, column=1, sticky="w", pady=8)
        self.settings_close_btn = ctk.CTkButton(
            self.settings_card, text="关闭", command=self._toggle_settings,
            width=52, height=26, corner_radius=theme.RADIUS_BUTTON,
            font=(theme.FONT_UI, 11),
            fg_color=theme.SURFACE, hover_color=theme.ELEVATED,
            border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_MUTED)
        self.settings_close_btn.grid(row=0, column=2, sticky="e", padx=12)

        # ── 状态卡片：状态点 + 状态文字 + 地址 + 打开浏览器 ──
        self.status_card = Card(self.root)
        self.status_card.pack(fill="x", padx=26, pady=(8, 6))
        self.status_card.grid_columnconfigure(1, weight=1)
        self.status_dot = StatusDot(self.status_card, size=10)
        self.status_dot.grid(row=0, column=0, padx=(16, 10))
        self.status_label = ctk.CTkLabel(
            self.status_card, text="", font=(theme.FONT_UI, 13, "bold"),
            text_color=theme.TEXT_PRIMARY, anchor="w")
        self.status_label.grid(row=0, column=1, sticky="w", pady=12)
        self.url_chip = ctk.CTkLabel(
            self.status_card, text=theme.BASE_URL.replace("http://", ""),
            font=(theme.FONT_MONO, 11), text_color=theme.TEXT_SECONDARY,
            fg_color=theme.ELEVATED, corner_radius=theme.RADIUS_CHIP,
            padx=10, pady=4)
        self.url_chip.grid(row=0, column=2, sticky="e", padx=(8, 10))
        self.open_btn = ctk.CTkButton(
            self.status_card, text="打开浏览器", command=self.open_browser,
            width=104, height=30, corner_radius=theme.RADIUS_BUTTON,
            font=(theme.FONT_UI, 11),
            fg_color=theme.SURFACE, hover_color=theme.ELEVATED,
            border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_SECONDARY, text_color_disabled=theme.TEXT_MUTED)
        self.open_btn.grid(row=0, column=3, sticky="e", padx=(0, 12))

        # ── 主操作：合并启动/停止 的胶囊按钮 ──
        self.start_stop_btn = ctk.CTkButton(
            self.root, text="", command=self.toggle_server,
            width=360, height=48, corner_radius=theme.RADIUS_PILL,
            font=(theme.FONT_UI, 15, "bold"),
            text_color="#ffffff", text_color_disabled="#ffffff",
            fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER)
        self.start_stop_btn.pack(pady=(8, 2))

        self.action_hint = ctk.CTkLabel(
            self.root, text="", font=(theme.FONT_UI, 10), text_color=theme.TEXT_MUTED)
        self.action_hint.pack(pady=(0, 4))

        # ── 日志面板（模式切换在面板标题栏右侧）──
        self.log_panel = LogPanel(self.root)
        self.log_switch = PillSwitch(
            self.log_panel.header_frame, items=[("简要", "简要"), ("详细", "详细")],
            command=self._on_log_mode)
        self.log_panel.set_header_widget(self.log_switch)
        self.log_panel.pack(fill="both", expand=True, padx=26, pady=(4, 6))

        # ── 页脚 ──
        footer = ctk.CTkFrame(self.root, fg_color="transparent")
        footer.pack(fill="x", padx=26, pady=(0, 10))
        self.footer_left = ctk.CTkLabel(
            footer, text="AIsChat 桌面启动器",
            font=(theme.FONT_UI, 10), text_color=theme.TEXT_MUTED)
        self.footer_left.pack(side="left")
        self.footer_right = ctk.CTkLabel(
            footer, text="端口 8000 · 数据目录 data/",
            font=(theme.FONT_UI, 10), text_color=theme.TEXT_MUTED)
        self.footer_right.pack(side="right")

    def _center_window(self) -> None:
        w, h = 780, 560
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _set_icon(self) -> None:
        """窗口图标（多尺寸）+ 顶栏 Logo（透明 PNG，无色块）。

        找不到资源或 Pillow 不可用时逐级兜底，最后保留无底色文字徽章。
        """
        logo_path = next((p for p in _candidate_logo_paths() if p.exists()), None)
        if logo_path is None:
            return

        # 首选：PIL 缩放为多尺寸图标（16/32/64），Windows 选择最清晰的一档
        try:
            from PIL import Image, ImageTk

            img = Image.open(logo_path)

            # 顶栏 Logo
            self._logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(40, 40))
            self.logo_label.configure(image=self._logo_img, text="")

            # 窗口 / 任务栏图标
            self._icon_photos = [
                ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))
                for size in (16, 32, 64)
            ]
            self.root.iconphoto(True, *self._icon_photos)
        except Exception:
            # 兜底：PIL 不可用时直接用原图（Tk 自行缩放）
            try:
                import tkinter as tk
                self._icon_photo = tk.PhotoImage(file=str(logo_path))
                self.root.iconphoto(True, self._icon_photo)
            except Exception:
                pass  # 最后保留无底色文字徽章

    # ── 换肤 ──

    def _apply_theme(self) -> None:
        """按当前主题令牌重绘全部静态颜色（状态色由 _apply_state 负责）。"""
        self.root.configure(fg_color=theme.CANVAS)
        self.logo_label.configure(text_color=theme.PRIMARY)
        for lbl in self._title_labels:
            lbl.configure(text_color=theme.TEXT_PRIMARY)
        for lbl in self._subtitle_labels:
            lbl.configure(text_color=theme.TEXT_MUTED)
        for btn in (self.gear_btn, self.settings_close_btn):
            btn.configure(
                fg_color=theme.SURFACE, hover_color=theme.ELEVATED,
                border_color=theme.BORDER, text_color=theme.TEXT_SECONDARY)
        self.settings_close_btn.configure(text_color=theme.TEXT_MUTED)
        self.settings_title.configure(text_color=theme.TEXT_PRIMARY)
        self.settings_card.retheme()
        self.status_card.retheme()
        self.url_chip.configure(fg_color=theme.ELEVATED, text_color=theme.TEXT_SECONDARY)
        self.open_btn.configure(
            fg_color=theme.SURFACE, hover_color=theme.ELEVATED,
            border_color=theme.BORDER, text_color=theme.TEXT_SECONDARY,
            text_color_disabled=theme.TEXT_MUTED)
        self.action_hint.configure(text_color=theme.TEXT_MUTED)
        self.footer_left.configure(text_color=theme.TEXT_MUTED)
        self.footer_right.configure(text_color=theme.TEXT_MUTED)
        self.theme_picker.set_value(theme.active_name(), notify=False)
        self.log_switch.set_value(self.log_switch.get_value(), notify=False)
        self.log_panel.retheme()
        self._apply_state(self._state)

    def _set_theme(self, name: str) -> None:
        if name == theme.active_name():
            return
        theme.switch(name)
        self._settings["theme"] = name
        settings.save(self._settings)
        self._apply_theme()
        self.log_panel.append(f"已切换主题：{theme.THEME_LABELS[name]}", key=True)

    def _toggle_settings(self) -> None:
        if self._settings_visible:
            self.settings_card.pack_forget()
            self.gear_btn.configure(text="设置")
            self._settings_visible = False
        else:
            self.settings_card.pack(fill="x", padx=26, pady=(0, 6), before=self.status_card)
            self.gear_btn.configure(text="收起")
            self._settings_visible = True

    # ── 状态 → 界面 ──

    def _apply_state(self, state: str, status: str | None = None) -> None:
        self._state = state
        ui = self._STATE_UI[state]
        self.status_dot.set_color(ui["dot"])
        self.status_label.configure(text=status or ui["status"])
        self.action_hint.configure(text=ui["hint"])
        self.start_stop_btn.configure(
            text=ui["btn_text"],
            fg_color=ui["btn_fg"],
            hover_color=ui["btn_hover"],
            state=ctk.DISABLED if ui.get("btn_disabled") else ctk.NORMAL,
        )
        self.open_btn.configure(
            state=ctk.NORMAL if ui["open_enabled"] else ctk.DISABLED)

    # ── 周期轮询 ──

    def _tick(self) -> None:
        for msg in self.controller.pump_logs():
            self.log_panel.append(msg)
        event = self.controller.poll()
        if event is not None:
            self._handle_event(event)
        self.root.after(POLL_INTERVAL_MS, self._tick)

    def _handle_event(self, event: str) -> None:
        if event == EVENT_STARTED:
            self._apply_state(STATE_RUNNING)
            self.log_panel.append("服务已就绪，正在打开浏览器…", key=True)
            self.open_browser()
        elif event == EVENT_STOPPED:
            self._apply_state(STATE_STOPPED)
            self.log_panel.append("后端服务已停止，可再次启动。", key=True)
        elif event == EVENT_FAILED:
            self._apply_state("failed")
            self.log_panel.append("后端服务启动失败，请查看日志。", key=True)
        elif event == EVENT_CRASHED:
            self._apply_state("failed", status="服务异常退出，请查看日志")
            self.log_panel.append("后端服务异常退出，请查看日志。", key=True)

    # ── 交互动作 ──

    def toggle_server(self) -> None:
        if self.controller.state == STATE_STOPPED:
            self.start_server()
        elif self.controller.state == STATE_RUNNING:
            self.stop_server()
        # 启动中 / 停止中忽略点击（按钮已禁用，此处为双保险）

    def start_server(self) -> None:
        self.log_panel.append("正在启动后端服务…", key=True)
        self._apply_state(STATE_STARTING)
        try:
            self.controller.start()
        except Exception as exc:  # 同步失败（如后端导入错误）
            self.controller.state = STATE_STOPPED
            self.log_panel.append(f"启动失败：{exc}", key=True)
            self._apply_state("failed")

    def stop_server(self) -> None:
        self.log_panel.append("正在停止后端服务…", key=True)
        self.controller.stop()
        self._apply_state(STATE_STOPPING)

    def open_browser(self) -> None:
        webbrowser.open(theme.BASE_URL)

    def _on_log_mode(self, value: str) -> None:
        self.detailed_log = value == "详细"
        self.log_panel.set_detailed(self.detailed_log)

    # ── 关闭 ──

    def _on_close(self) -> None:
        """关闭窗口前优雅停止后端服务（最长等待 CLOSE_GRACE_SECONDS）。"""
        if self.controller.is_active():
            self.controller.stop()
            deadline = time.monotonic() + CLOSE_GRACE_SECONDS
            while (time.monotonic() < deadline
                   and self.controller.thread is not None
                   and self.controller.thread.is_alive()):
                time.sleep(0.05)
        self.root.destroy()

    # ── 入口 ──

    def run(self) -> None:
        self.root.mainloop()
