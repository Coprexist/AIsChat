"""
AIsChat 桌面启动器 GUI  使用 CustomTkinter 美化。
"""
import os
import sys
import threading
import webbrowser
import urllib.request

import customtkinter as ctk

import logging_utils
from server_core import create_server

ACCENT_COLOR = "#2eb8a6"
HOVER_COLOR = "#249b8b"


class AIsChatGUI:
    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self.root = ctk.CTk()
        self.root.title("AIsChat 启动器")
        self.root.geometry("720x500")
        self.root.minsize(640, 420)

        self.server = None
        self.server_thread = None
        self.server_running = False
        self.detailed_log = False
        self.all_logs = []

        # 状态卡片
        self.status_card = ctk.CTkFrame(self.root, corner_radius=15, fg_color="#f5f7fa")
        self.status_card.pack(fill="x", padx=15, pady=(15, 5))
        self.status_var = ctk.StringVar(value="状态：未启动")
        self.status_label = ctk.CTkLabel(self.status_card, textvariable=self.status_var,
                                         font=("微软雅黑", 14, "bold"), text_color="#1a1a1a")
        self.status_label.pack(pady=10)

        # 按钮区
        btn_frame = ctk.CTkFrame(self.root, corner_radius=15, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=5)

        self.start_stop_btn = ctk.CTkButton(btn_frame, text="启动服务", command=self.toggle_server,
                                            width=160, height=36, corner_radius=18,
                                            fg_color=ACCENT_COLOR, hover_color=HOVER_COLOR)
        self.start_stop_btn.grid(row=0, column=0, padx=5)

        self.open_btn = ctk.CTkButton(btn_frame, text="打开浏览器", command=self.open_browser,
                                      state=ctk.DISABLED, width=160, height=36, corner_radius=18,
                                      fg_color="#6c757d", hover_color="#5a6268")
        self.open_btn.grid(row=0, column=1, padx=5)

        self.detail_btn = ctk.CTkButton(btn_frame, text="显示详细日志", command=self.toggle_detail,
                                        width=160, height=36, corner_radius=18,
                                        fg_color="#6c757d", hover_color="#5a6268")
        self.detail_btn.grid(row=0, column=2, padx=5)

        # 日志区域
        self.log_area = ctk.CTkTextbox(self.root, font=("Consolas", 10), text_color="#333333",
                                       fg_color="#ffffff", corner_radius=10)
        self.log_area.pack(fill="both", expand=True, padx=15, pady=(5, 15))
        self.log_area.configure(state=ctk.DISABLED)

        self.root.after(500, self.auto_start)

    def auto_start(self):
        self.toggle_server()

    def toggle_server(self):
        if self.server_running:
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        if self.server_running:
            return
        self.server_running = True
        self.start_stop_btn.configure(text="停止服务", fg_color="#dc3545", hover_color="#c82333")
        self.open_btn.configure(state=ctk.DISABLED)
        self.status_var.set("状态：启动中...")
        self.log_message("正在启动后端服务...")
        logging_utils.setup_logging()
        self.server = create_server(log_level="info", log_config=None)
        self.server_thread = threading.Thread(target=self.server.run, daemon=True)
        self.server_thread.start()
        self.process_log_queue()
        self.check_ready()

    def check_ready(self):
        if not self.server_running:
            return
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
            self.status_var.set("状态：服务已启动")
            self.open_btn.configure(state=ctk.NORMAL)
            self.log_message("服务已就绪，正在打开浏览器...")
            self.open_browser()
            return
        except Exception:
            self.status_var.set("状态：启动中...")
            self.root.after(2000, self.check_ready)

    def open_browser(self):
        webbrowser.open("http://127.0.0.1:8000")

    def stop_server(self):
        if not self.server_running:
            return
        self.server_running = False
        self.status_var.set("状态：正在停止...")
        self.start_stop_btn.configure(state=ctk.DISABLED)
        self.open_btn.configure(state=ctk.DISABLED)
        self.log_message("正在停止后端服务...")
        if self.server:
            self.server.should_exit = True
        # 等待线程退出后恢复按钮
        self.root.after(1000, self.check_stopped)

    def check_stopped(self):
        if self.server_thread and self.server_thread.is_alive():
            self.root.after(500, self.check_stopped)
        else:
            self.status_var.set("状态：已停止")
            self.start_stop_btn.configure(text="启动服务", state=ctk.NORMAL,
                                          fg_color=ACCENT_COLOR, hover_color=HOVER_COLOR)
            self.open_btn.configure(state=ctk.DISABLED)
            self.log_message("后端服务已停止，可再次启动。")

    def toggle_detail(self):
        self.detailed_log = not self.detailed_log
        self.detail_btn.configure(text="显示简要状态" if self.detailed_log else "显示详细日志")
        self.refresh_log_view()

    def should_show_in_brief(self, msg):
        keywords = ("服务就绪", "启动完成", "数据库连接正常", "错误", "Error", "Traceback", "启动", "停止")
        return any(kw in msg for kw in keywords)

    def refresh_log_view(self):
        self.log_area.configure(state=ctk.NORMAL)
        self.log_area.delete("1.0", "end")
        for msg in self.all_logs:
            if self.detailed_log or self.should_show_in_brief(msg):
                self.log_area.insert("end", msg + "\n")
        self.log_area.see("end")
        self.log_area.configure(state=ctk.DISABLED)

    def process_log_queue(self):
        try:
            while True:
                msg = logging_utils.log_queue.get_nowait()
                self.all_logs.append(msg)
                if self.detailed_log or self.should_show_in_brief(msg):
                    self.log_area.configure(state=ctk.NORMAL)
                    self.log_area.insert("end", msg + "\n")
                    self.log_area.see("end")
                    self.log_area.configure(state=ctk.DISABLED)
        except Exception:
            pass
        self.root.after(200, self.process_log_queue)

    def log_message(self, msg):
        self.all_logs.append(msg)
        if self.detailed_log or self.should_show_in_brief(msg):
            self.log_area.configure(state=ctk.NORMAL)
            self.log_area.insert("end", msg + "\n")
            self.log_area.see("end")
            self.log_area.configure(state=ctk.DISABLED)

    def run(self):
        self.root.mainloop()
