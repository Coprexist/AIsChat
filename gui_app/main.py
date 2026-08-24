"""
AIsChat 桌面启动器主窗口
=======================
品牌风格对齐前端：紫色系（默认）+ 青碧第二主题色。
单窗口视图切换：主页 ↔ 设置页，顶栏常驻。
功能：最小化到托盘、开机自启、端口设置。
"""
from __future__ import annotations

import sys
import time
import threading
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

POLL_INTERVAL_MS = 250
AUTO_START_DELAY_MS = 600
CLOSE_GRACE_SECONDS = 3.0

# 注册表自启动路径
_AUTO_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTO_RUN_NAME = "AIsChatLauncher"


def _candidate_logo_paths() -> list[Path]:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
        return [
            base / "frontend" / "public" / "logo-transparent.ico",
            base / "frontend" / "dist" / "logo-transparent.ico",
            base / "frontend" / "dist" / "logo-transparent.png",
            base / "frontend" / "public" / "logo-transparent.png",
        ]
    root = Path(__file__).resolve().parent.parent
    return [
        root / "frontend" / "public" / "logo-transparent.ico",
        root / "frontend" / "dist" / "logo-transparent.ico",
        root / "frontend" / "dist" / "logo-transparent.png",
        root / "frontend" / "public" / "logo-transparent.png",
    ]


def _get_exe_path() -> str:
    """获取当前可执行文件路径（打包后 / 源码运行）。"""
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(__file__).resolve().parent.parent / "run_packaged.py")


def _set_auto_start(enabled: bool) -> None:
    """写入/删除 Windows 注册表开机自启动项。"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTO_RUN_KEY, 0,
                             winreg.KEY_SET_VALUE | winreg.KEY_READ)
        if enabled:
            exe = _get_exe_path()
            # 打包后用 --minimized 参数静默启动
            cmd = f'"{exe}" --minimized' if getattr(sys, "frozen", False) else f'"{exe}"'
            winreg.SetValueEx(key, _AUTO_RUN_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, _AUTO_RUN_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def _is_auto_start() -> bool:
    """检查是否已设置开机自启动。"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTO_RUN_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _AUTO_RUN_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


class AIsChatGUI:
    _STATE_UI = {
        STATE_STOPPED: dict(
            status="服务未启动", dot=theme.STATUS_STOPPED,
            btn_text="启动服务", btn_fg=theme.PRIMARY, btn_hover=theme.PRIMARY_HOVER,
            open_enabled=False, hint="点击启动后将自动打开浏览器"),
        STATE_STARTING: dict(
            status="正在启动…", dot=theme.STATUS_STARTING,
            btn_text="启动中…", btn_fg=theme.STATUS_STARTING, btn_hover=theme.STATUS_STARTING,
            btn_disabled=True, open_enabled=False, hint="正在初始化后端"),
        STATE_RUNNING: dict(
            status="服务运行中", dot=theme.STATUS_RUNNING,
            btn_text="停止服务", btn_fg=theme.DANGER, btn_hover=theme.DANGER_HOVER,
            open_enabled=True, hint=""),
        STATE_STOPPING: dict(
            status="正在停止…", dot=theme.STATUS_STARTING,
            btn_text="停止中…", btn_fg=theme.STATUS_STARTING, btn_hover=theme.STATUS_STARTING,
            btn_disabled=True, open_enabled=False, hint="正在优雅退出"),
        "failed": dict(
            status="启动失败", dot=theme.STATUS_FAILED,
            btn_text="重新启动", btn_fg=theme.PRIMARY, btn_hover=theme.PRIMARY_HOVER,
            open_enabled=False, hint="请查看下方日志"),
    }

    def __init__(self, auto_start: bool = True, start_minimized: bool = False):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self.root = ctk.CTk()
        self.root.title("AIsChat 启动器")
        self.root.configure(fg_color=theme.CANVAS)
        self.root.minsize(760, 560)
        self._center_window()

        self.controller = ServerController()
        self.detailed_log = False
        self._state = STATE_STOPPED
        self._current_view = "home"
        self._tray_icon = None

        self._settings = settings.load()
        theme.switch(self._settings.get("theme", theme.DEFAULT_THEME))

        # 从设置读取端口
        self._port = int(self._settings.get("port", "8000"))
        self.controller.port = self._port

        self._build_ui()
        self._apply_theme()
        self._apply_state(STATE_STOPPED)
        self._set_icon()

        # 最小化到托盘
        if self._settings.get("minimize_to_tray", True):
            self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        else:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动后台服务
        self.root.after(POLL_INTERVAL_MS, self._tick)
        if auto_start:
            self.root.after(AUTO_START_DELAY_MS, self.toggle_server)

        # 启动最小化
        if start_minimized:
            self.root.after(100, self._minimize_to_tray)

    def _build_ui(self) -> None:
        # ── 顶栏 ──
        self.header = ctk.CTkFrame(self.root, fg_color="transparent")
        self.header.pack(fill="x", padx=32, pady=(24, 0))

        brand = ctk.CTkFrame(self.header, fg_color="transparent")
        brand.pack(side="left", fill="y")

        self.logo_label = ctk.CTkLabel(
            brand, text="", font=(theme.FONT_UI, 15, "bold"),
            text_color=theme.PRIMARY)
        self.logo_label.pack(side="left", padx=(0, 12))

        title_col = ctk.CTkFrame(brand, fg_color="transparent")
        title_col.pack(side="left")
        self._title_labels = [ctk.CTkLabel(
            title_col, text="AIsChat",
            font=(theme.FONT_UI, 22, "bold"), text_color=theme.TEXT_PRIMARY)]
        self._title_labels[-1].pack(anchor="w")
        self._subtitle_labels = [ctk.CTkLabel(
            title_col, text="启动器", font=(theme.FONT_UI, 13),
            text_color=theme.TEXT_MUTED)]
        self._subtitle_labels[-1].pack(anchor="w", pady=(2, 0))

        self.gear_btn = ctk.CTkButton(
            self.header, text="设置", command=self._toggle_view,
            width=72, height=32, corner_radius=8,
            font=(theme.FONT_UI, 13),
            fg_color="transparent", hover_color=theme.ELEVATED,
            border_width=0, text_color=theme.TEXT_SECONDARY)
        self.gear_btn.pack(side="right")

        # 分隔线
        ctk.CTkFrame(self.root, height=1, fg_color=theme.BORDER).pack(
            fill="x", padx=32, pady=(16, 0))

        # 内容区
        self._content_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self._content_frame.pack(fill="both", expand=True)

        self._build_home_page()
        self._build_settings_page()
        self._show_home()

    def _build_home_page(self) -> None:
        self._home = ctk.CTkFrame(self._content_frame, fg_color="transparent")

        # 状态卡片
        self.status_card = ctk.CTkFrame(
            self._home, fg_color=theme.SURFACE,
            corner_radius=theme.RADIUS_CARD,
            border_width=1, border_color=theme.BORDER)
        self.status_card.pack(fill="x", padx=32, pady=(20, 0))

        inner = ctk.CTkFrame(self.status_card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        status_row = ctk.CTkFrame(inner, fg_color="transparent")
        status_row.pack(fill="x")

        dot_col = ctk.CTkFrame(status_row, fg_color="transparent")
        dot_col.pack(side="left", padx=(0, 12))
        self.status_dot = StatusDot(dot_col, size=10)
        self.status_dot.pack(pady=(2, 0))

        text_col = ctk.CTkFrame(status_row, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        self.status_label = ctk.CTkLabel(
            text_col, text="", font=(theme.FONT_UI, 15, "bold"),
            text_color=theme.TEXT_PRIMARY, anchor="w")
        self.status_label.pack(anchor="w")
        self.action_hint = ctk.CTkLabel(
            text_col, text="", font=(theme.FONT_UI, 12),
            text_color=theme.TEXT_MUTED, anchor="w")
        self.action_hint.pack(anchor="w", pady=(2, 0))

        self.open_btn = ctk.CTkButton(
            status_row, text="打开浏览器", command=self.open_browser,
            width=100, height=32, corner_radius=8,
            font=(theme.FONT_UI, 12),
            fg_color="transparent", hover_color=theme.ELEVATED,
            border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_SECONDARY, text_color_disabled=theme.TEXT_MUTED)
        self.open_btn.pack(side="right")

        self.url_chip = ctk.CTkLabel(
            status_row, text=f"127.0.0.1:{self._port}",
            font=(theme.FONT_MONO, 11), text_color=theme.TEXT_MUTED)
        self.url_chip.pack(side="right", padx=(0, 12))

        # 主操作按钮
        btn_frame = ctk.CTkFrame(self._home, fg_color="transparent")
        btn_frame.pack(fill="x", padx=32, pady=(20, 0))

        self.start_stop_btn = ctk.CTkButton(
            btn_frame, text="", command=self.toggle_server,
            width=320, height=48, corner_radius=12,
            font=(theme.FONT_UI, 16, "bold"),
            text_color="#ffffff", text_color_disabled="#ffffff",
            fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER)
        self.start_stop_btn.pack()

        # 日志面板
        self.log_panel = LogPanel(self._home)
        self.log_switch = PillSwitch(
            self.log_panel.header_frame, items=[("简要", "简要"), ("详细", "详细")],
            command=self._on_log_mode, btn_width=56)
        self.log_panel.set_header_widget(self.log_switch)
        self.log_panel.pack(fill="both", expand=True, padx=32, pady=(16, 12))

        # 页脚
        footer = ctk.CTkFrame(self._home, fg_color="transparent")
        footer.pack(fill="x", padx=32, pady=(0, 12))
        self.footer_left = ctk.CTkLabel(
            footer, text="AIsChat v0.4.0", font=(theme.FONT_UI, 11),
            text_color=theme.TEXT_MUTED)
        self.footer_left.pack(side="left")
        self.footer_right = ctk.CTkLabel(
            footer, text=f"localhost:{self._port}", font=(theme.FONT_MONO, 11),
            text_color=theme.TEXT_MUTED)
        self.footer_right.pack(side="right")

    def _build_settings_page(self) -> None:
        # 用可滚动框架包裹设置内容
        self._settings_page = ctk.CTkScrollableFrame(
            self._content_frame, fg_color="transparent")

        ctk.CTkLabel(
            self._settings_page, text="设置",
            font=(theme.FONT_UI, 22, "bold"), text_color=theme.TEXT_PRIMARY
        ).pack(anchor="w", padx=32, pady=(24, 20))

        card = Card(self._settings_page)
        card.pack(fill="x", padx=32)
        card.grid_columnconfigure(1, weight=1)

        # ── 主题色 ──
        ctk.CTkLabel(
            card, text="主题色", font=(theme.FONT_UI, 14),
            text_color=theme.TEXT_PRIMARY, anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=(20, 12), pady=(16, 8))
        self.theme_picker = PillSwitch(
            card,
            items=[(name, theme.THEME_LABELS[name]) for name in theme.THEME_NAMES],
            command=self._set_theme, btn_width=80)
        self.theme_picker.grid(row=0, column=1, sticky="w", pady=(16, 8))

        ctk.CTkFrame(card, height=1, fg_color=theme.BORDER).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=4)

        # ── 日志字号 ──
        ctk.CTkLabel(
            card, text="日志字号", font=(theme.FONT_UI, 14),
            text_color=theme.TEXT_PRIMARY, anchor="w"
        ).grid(row=2, column=0, sticky="w", padx=(20, 12), pady=(8, 16))
        self.font_size_picker = PillSwitch(
            card,
            items=[(key, label) for key, label, _ in theme.LOG_FONT_SIZES],
            command=self._set_log_font_size, btn_width=50)
        self.font_size_picker.grid(row=2, column=1, sticky="w", pady=(8, 16))

        ctk.CTkFrame(card, height=1, fg_color=theme.BORDER).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=4)

        # ── 服务端口 ──
        ctk.CTkLabel(
            card, text="服务端口", font=(theme.FONT_UI, 14),
            text_color=theme.TEXT_PRIMARY, anchor="w"
        ).grid(row=4, column=0, sticky="w", padx=(20, 12), pady=(8, 16))
        self.port_entry = ctk.CTkEntry(
            card, width=100, height=32, corner_radius=8,
            font=(theme.FONT_MONO, 13),
            fg_color=theme.ELEVATED, border_color=theme.BORDER,
            text_color=theme.TEXT_PRIMARY, border_width=1)
        self.port_entry.grid(row=4, column=1, sticky="w", pady=(8, 16), padx=(0, 8))
        self.port_entry.insert(0, str(self._port))
        self.port_entry.bind("<Return>", lambda e: self._apply_port())
        self.port_entry.bind("<FocusOut>", lambda e: self._apply_port())

        ctk.CTkLabel(
            card, text="改后需重启", font=(theme.FONT_UI, 10),
            text_color=theme.TEXT_MUTED, anchor="w"
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=(20, 12), pady=(0, 8))

        ctk.CTkFrame(card, height=1, fg_color=theme.BORDER).grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=20, pady=4)

        # ── 开机自启 ──
        ctk.CTkLabel(
            card, text="开机自启动", font=(theme.FONT_UI, 14),
            text_color=theme.TEXT_PRIMARY, anchor="w"
        ).grid(row=7, column=0, sticky="w", padx=(20, 12), pady=(8, 16))
        self.auto_start_switch = ctk.CTkSwitch(
            card, text="", onvalue=True, offvalue=False,
            command=self._toggle_auto_start,
            fg_color=theme.BORDER, progress_color=theme.PRIMARY,
            button_color=theme.SURFACE, button_hover_color=theme.ELEVATED)
        self.auto_start_switch.grid(row=7, column=1, sticky="w", pady=(8, 16))

        ctk.CTkFrame(card, height=1, fg_color=theme.BORDER).grid(
            row=8, column=0, columnspan=2, sticky="ew", padx=20, pady=4)

        # ── 最小化到托盘 ──
        ctk.CTkLabel(
            card, text="关闭时最小化到托盘", font=(theme.FONT_UI, 14),
            text_color=theme.TEXT_PRIMARY, anchor="w"
        ).grid(row=9, column=0, sticky="w", padx=(20, 12), pady=(8, 16))
        self.tray_switch = ctk.CTkSwitch(
            card, text="", onvalue=True, offvalue=False,
            command=self._toggle_tray,
            fg_color=theme.BORDER, progress_color=theme.PRIMARY,
            button_color=theme.SURFACE, button_hover_color=theme.ELEVATED)
        self.tray_switch.grid(row=9, column=1, sticky="w", pady=(8, 16))

        ctk.CTkFrame(card, height=1, fg_color=theme.BORDER).grid(
            row=10, column=0, columnspan=2, sticky="ew", padx=20, pady=4)

        # ── 复制日志 ──
        ctk.CTkLabel(
            card, text="日志操作", font=(theme.FONT_UI, 14),
            text_color=theme.TEXT_PRIMARY, anchor="w"
        ).grid(row=11, column=0, sticky="w", padx=(20, 12), pady=(8, 16))
        self._copy_log_btn = ctk.CTkButton(
            card, text="复制全部日志",
            width=130, height=32, corner_radius=8,
            font=(theme.FONT_UI, 12),
            fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
            text_color="#ffffff", command=self._copy_all_logs)
        self._copy_log_btn.grid(row=11, column=1, sticky="w", pady=(8, 16))

        # 提示
        ctk.CTkLabel(
            self._settings_page, text="设置会自动保存",
            font=(theme.FONT_UI, 11), text_color=theme.TEXT_MUTED
        ).pack(pady=(20, 20))

    # ── 视图切换 ──

    def _toggle_view(self) -> None:
        if self._current_view == "home":
            self._show_settings()
        else:
            self._show_home()

    def _show_home(self) -> None:
        self._settings_page.pack_forget()
        self._home.pack(fill="both", expand=True)
        self._current_view = "home"
        self.gear_btn.configure(text="设置")

    def _show_settings(self) -> None:
        self._home.pack_forget()
        self._settings_page.pack(fill="both", expand=True)
        self._current_view = "settings"
        self.gear_btn.configure(text="返回")
        # 同步控件
        self.theme_picker.set_value(theme.active_name(), notify=False)
        self.font_size_picker.set_value(
            self._settings.get("log_font_size", str(theme.FONT_LOG_SIZE)), notify=False)
        # 端口
        self.port_entry.delete(0, "end")
        self.port_entry.insert(0, str(self._port))
        # 开关
        is_auto = _is_auto_start()
        if is_auto:
            self.auto_start_switch.select()
        else:
            self.auto_start_switch.deselect()
        if self._settings.get("minimize_to_tray", True):
            self.tray_switch.select()
        else:
            self.tray_switch.deselect()

    # ── 设置操作 ──

    def _set_theme(self, name: str) -> None:
        if name == theme.active_name():
            return
        theme.switch(name)
        self._settings["theme"] = name
        settings.save(self._settings)
        self._apply_theme()
        self.log_panel.append(f"已切换主题：{theme.THEME_LABELS[name]}", key=True)

    def _set_log_font_size(self, key: str) -> None:
        self._settings["log_font_size"] = key
        settings.save(self._settings)
        try:
            size = int(key)
        except ValueError:
            size = theme.FONT_LOG_SIZE
        self.log_panel.set_log_font_size(size)

    def _apply_port(self) -> None:
        """应用端口设置（需重启生效）。"""
        raw = self.port_entry.get().strip()
        if raw.isdigit() and 1 <= int(raw) <= 65535:
            if str(self._port) != raw:
                self._port = int(raw)
                self._settings["port"] = raw
                settings.save(self._settings)
                self.url_chip.configure(text=f"127.0.0.1:{self._port}")
                self.footer_right.configure(text=f"localhost:{self._port}")
                self.log_panel.append(f"端口已改为 {self._port}，重启后生效", key=True)

    def _toggle_auto_start(self) -> None:
        enabled = self.auto_start_switch.get()
        _set_auto_start(enabled)
        self.log_panel.append("已" + ("开启" if enabled else "关闭") + "开机自启动", key=True)

    def _toggle_tray(self) -> None:
        enabled = bool(self.tray_switch.get())
        self._settings["minimize_to_tray"] = enabled
        settings.save(self._settings)
        if enabled:
            self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        else:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _copy_all_logs(self) -> None:
        text = self.log_panel.get_all_text()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._copy_log_btn.configure(text="已复制")
        self.root.after(1500, lambda: self._copy_log_btn.configure(text="复制全部日志"))

    # ── 最小化到托盘 ──

    def _minimize_to_tray(self) -> None:
        """隐藏窗口到系统托盘（需要 pystray + Pillow）。"""
        self.root.withdraw()
        if self._tray_icon is not None:
            return
        try:
            import pystray
            from PIL import Image
            logo_path = next((p for p in _candidate_logo_paths() if p.exists()), None)
            if logo_path is not None:
                tray_img = Image.open(logo_path).resize((64, 64), Image.LANCZOS)
            else:
                tray_img = Image.new("RGB", (64, 64), theme.PRIMARY.lstrip("#"))

            menu = pystray.Menu(
                pystray.MenuItem("显示", self._tray_restore, default=True),
                pystray.MenuItem("退出", self._tray_exit),
            )
            self._tray_icon = pystray.Icon(
                "AIsChat", tray_img, "AIsChat 启动器", menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        except ImportError:
            # pystray 未安装，退回到直接关闭
            self._on_close()

    def _tray_restore(self, icon=None, item=None) -> None:
        self.root.after(0, self._restore_from_tray)

    def _restore_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if self._tray_icon is not None:
            self._tray_icon.stop()
            self._tray_icon = None

    def _tray_exit(self, icon=None, item=None) -> None:
        if self._tray_icon is not None:
            self._tray_icon.stop()
            self._tray_icon = None
        self.root.after(0, self._on_close)

    # ── 窗口基础设施 ──

    def _center_window(self) -> None:
        w, h = 760, 560
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _set_icon(self) -> None:
        """设置窗口图标（Windows 用 .ico，其他平台用 PNG）。"""
        logo_path = next((p for p in _candidate_logo_paths() if p.exists()), None)
        if logo_path is None:
            return
        
        # 设置顶栏 Logo
        try:
            from PIL import Image
            img = Image.open(logo_path)
            self._logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(36, 36))
            self.logo_label.configure(image=self._logo_img, text="")
        except Exception:
            pass
        
        # 设置窗口图标（Windows 必须用 .ico）
        if logo_path.suffix.lower() == '.ico':
            # Windows: 直接用 .ico 文件
            self.root.iconbitmap(logo_path)
        else:
            # macOS/Linux: 用 iconphoto
            try:
                from PIL import ImageTk
                img = Image.open(logo_path)
                self._icon_photos = [
                    ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))
                    for size in (16, 32, 64)
                ]
                self.root.iconphoto(True, *self._icon_photos)
            except Exception:
                try:
                    import tkinter as tk
                    self._icon_photo = tk.PhotoImage(file=str(logo_path))
                    self.root.iconphoto(True, self._icon_photo)
                except Exception:
                    pass

    # ── 换肤 ──

    def _apply_theme(self) -> None:
        self.root.configure(fg_color=theme.CANVAS)
        self.logo_label.configure(text_color=theme.PRIMARY)
        for lbl in self._title_labels:
            lbl.configure(text_color=theme.TEXT_PRIMARY)
        for lbl in self._subtitle_labels:
            lbl.configure(text_color=theme.TEXT_MUTED)
        self.gear_btn.configure(
            fg_color="transparent", hover_color=theme.ELEVATED,
            text_color=theme.TEXT_SECONDARY)
        self.status_card.configure(fg_color=theme.SURFACE, border_color=theme.BORDER)
        self.url_chip.configure(text_color=theme.TEXT_MUTED)
        self.open_btn.configure(
            fg_color="transparent", hover_color=theme.ELEVATED,
            border_color=theme.BORDER, text_color=theme.TEXT_SECONDARY,
            text_color_disabled=theme.TEXT_MUTED)
        self.action_hint.configure(text_color=theme.TEXT_MUTED)
        self.footer_left.configure(text_color=theme.TEXT_MUTED)
        self.footer_right.configure(text_color=theme.TEXT_MUTED)
        self.log_switch.set_value(self.log_switch.get_value(), notify=False)
        self.log_panel.retheme()
        self.theme_picker.set_value(theme.active_name(), notify=False)
        self.font_size_picker.set_value(
            self._settings.get("log_font_size", str(theme.FONT_LOG_SIZE)), notify=False)
        self._apply_state(self._state)

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
            self.log_panel.append("服务已就绪", key=True)
            self.open_browser()
        elif event == EVENT_STOPPED:
            self._apply_state(STATE_STOPPED)
            self.log_panel.append("服务已停止", key=True)
        elif event == EVENT_FAILED:
            self._apply_state("failed")
            self.log_panel.append("启动失败", key=True)
        elif event == EVENT_CRASHED:
            self._apply_state("failed", status="异常退出")
            self.log_panel.append("服务异常退出", key=True)

    # ── 交互动作 ──

    def toggle_server(self) -> None:
        if self.controller.state == STATE_STOPPED:
            self.start_server()
        elif self.controller.state == STATE_RUNNING:
            self.stop_server()

    def start_server(self) -> None:
        self.log_panel.append("正在启动…", key=True)
        self._apply_state(STATE_STARTING)
        try:
            self.controller.start()
        except Exception as exc:
            self.controller.state = STATE_STOPPED
            self.log_panel.append(f"启动失败：{exc}", key=True)
            self._apply_state("failed")

    def stop_server(self) -> None:
        self.log_panel.append("正在停止…", key=True)
        self.controller.stop()
        self._apply_state(STATE_STOPPING)

    def open_browser(self) -> None:
        webbrowser.open(theme.build_base_url(self._port))

    def _on_log_mode(self, value: str) -> None:
        self.detailed_log = value == "详细"
        self.log_panel.set_detailed(self.detailed_log)

    # ── 关闭 ──

    def _on_close(self) -> None:
        if self.controller.is_active():
            self.controller.stop()
            deadline = time.monotonic() + CLOSE_GRACE_SECONDS
            while (time.monotonic() < deadline
                   and self.controller.thread is not None
                   and self.controller.thread.is_alive()):
                time.sleep(0.05)
        if self._tray_icon is not None:
            self._tray_icon.stop()
            self._tray_icon = None
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
