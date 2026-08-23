import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import urllib.request
import webbrowser

import logging_utils
from server_core import run_server


class AIsChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AIsChat 启动器")
        self.root.geometry("720x520")
        self.root.resizable(True, True)

        # 使用 ttk 主题
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # 设置字体和颜色
        self.root.configure(bg="#f0f0f0")
        style.configure("TLabel", font=("微软雅黑", 11), background="#f0f0f0")
        style.configure("TButton", font=("微软雅黑", 10), padding=6)
        style.configure("Header.TLabel", font=("微软雅黑", 13, "bold"), background="#f0f0f0")

        self.server_thread = None
        self.server = None
        self.server_running = False
        self.detailed_log = False
        self.all_logs = []  # 缓存所有日志

        # 顶部状态
        self.status_var = tk.StringVar(value="状态：未启动")
        ttk.Label(self.root, textvariable=self.status_var, style="Header.TLabel").pack(pady=5)

        # 按钮区
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=5)

        self.start_stop_btn = ttk.Button(btn_frame, text="启动服务", command=self.toggle_server, width=16)
        self.start_stop_btn.grid(row=0, column=0, padx=4)

        self.open_btn = ttk.Button(btn_frame, text="打开浏览器", command=self.open_browser, state=tk.DISABLED, width=16)
        self.open_btn.grid(row=0, column=1, padx=4)

        self.detail_btn = ttk.Button(btn_frame, text="显示详细日志", command=self.toggle_detail, width=16)
        self.detail_btn.grid(row=0, column=2, padx=4)

        # 日志区域
        self.log_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, width=90, height=22,
                                                  font=("Consolas", 10), bg="#ffffff", fg="#333333")
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_area.configure(state=tk.DISABLED)

        self.root.after(200, self.auto_start)

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
        self.start_stop_btn.config(text="停止服务")
        self.open_btn.config(state=tk.DISABLED)
        self.status_var.set("状态：启动中...")
        self.log_message("正在启动后端服务...")
        logging_utils.setup_logging()
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        self.process_log_queue()
        self.check_ready()

    def _run_server(self):
        run_server(log_level="info", log_config=None)

    def check_ready(self):
        if not self.server_running:
            return
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
            self.status_var.set("状态：服务已启动")
            self.open_btn.config(state=tk.NORMAL)
            self.log_message("服务已就绪，正在打开浏览器...")
            self.open_browser()
            return
        except Exception:
            self.status_var.set("状态：启动中...")
            self.root.after(2000, self.check_ready)

    def open_browser(self):
        webbrowser.open("http://127.0.0.1:8000")

    def stop_server(self):
        # 停止服务：直接退出程序（线程守护，关闭窗口即退出）
        if messagebox.askokcancel("确认退出", "停止服务将退出程序，确定吗？"):
            self.root.destroy()
            os._exit(0)

    def toggle_detail(self):
        self.detailed_log = not self.detailed_log
        self.detail_btn.config(text="显示简要状态" if self.detailed_log else "显示详细日志")
        self.refresh_log_view()

    def should_show_in_brief(self, msg):
        keywords = ("服务就绪", "启动完成", "数据库连接正常", "错误", "Error", "Traceback", "启动", "停止")
        return any(kw in msg for kw in keywords)

    def refresh_log_view(self):
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        for msg in self.all_logs:
            if self.detailed_log or self.should_show_in_brief(msg):
                self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state=tk.DISABLED)

    def process_log_queue(self):
        try:
            while True:
                msg = logging_utils.log_queue.get_nowait()
                self.all_logs.append(msg)
                if self.detailed_log or self.should_show_in_brief(msg):
                    self.log_area.configure(state=tk.NORMAL)
                    self.log_area.insert(tk.END, msg + "\n")
                    self.log_area.see(tk.END)
                    self.log_area.configure(state=tk.DISABLED)
        except Exception:
            pass
        self.root.after(200, self.process_log_queue)

    def log_message(self, msg):
        self.all_logs.append(msg)
        if self.detailed_log or self.should_show_in_brief(msg):
            self.log_area.configure(state=tk.NORMAL)
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
            self.log_area.configure(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()
