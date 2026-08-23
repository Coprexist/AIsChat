"""
EXE 打包专用启动入口：图形化界面（tkinter）。
- 导入 server_core 获取 FastAPI 应用和启动函数
- 自动启动后端
- 缓存所有日志，可切换简要/详细显示
- 后端就绪后自动打开浏览器
- 支持停止后重新启动
"""
import logging
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext
import urllib.request
import webbrowser

from server_core import app, run_server


#  日志队列与处理器 
log_queue = queue.Queue()

class QueueLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_queue.put(msg)
        except Exception:
            pass


def setup_logging():
    handler = QueueLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)


#  GUI 启动器 
class AIsChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AIsChat 启动器")
        self.root.geometry("680x500")
        self.root.resizable(True, True)

        self.server_thread = None
        self.server_running = False
        self.detailed_log = False
        self.all_logs = []  # 缓存所有日志

        # 顶部状态
        self.status_var = tk.StringVar(value="状态：未启动")
        tk.Label(self.root, textvariable=self.status_var, font=("微软雅黑", 12, "bold")).pack(pady=5)

        # 按钮区
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=5)

        self.start_btn = tk.Button(btn_frame, text="启动服务", command=self.start_server, width=14)
        self.start_btn.grid(row=0, column=0, padx=3)

        self.open_btn = tk.Button(btn_frame, text="打开浏览器", command=self.open_browser, state=tk.DISABLED, width=14)
        self.open_btn.grid(row=0, column=1, padx=3)

        self.detail_btn = tk.Button(btn_frame, text="显示详细日志", command=self.toggle_detail, width=14)
        self.detail_btn.grid(row=0, column=2, padx=3)

        self.stop_btn = tk.Button(btn_frame, text="停止服务", command=self.stop_server, state=tk.DISABLED, width=14)
        self.stop_btn.grid(row=0, column=3, padx=3)

        # 日志区域
        self.log_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, width=80, height=22)
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_area.configure(state=tk.DISABLED)

        self.root.after(200, self.auto_start)

    def auto_start(self):
        self.start_server()

    def toggle_detail(self):
        self.detailed_log = not self.detailed_log
        self.detail_btn.config(text="显示简要状态" if self.detailed_log else "显示详细日志")
        self.refresh_log_view()

    def refresh_log_view(self):
        """根据当前模式重新渲染日志区域。"""
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        for msg in self.all_logs:
            if self.detailed_log:
                self.log_area.insert(tk.END, msg + "\n")
            else:
                if any(kw in msg for kw in ("服务就绪", "启动完成", "数据库连接正常", "错误", "Error", "Traceback")):
                    self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state=tk.DISABLED)

    def process_log_queue(self):
        """从队列中取出新日志，追加到缓存并刷新显示。"""
        try:
            while True:
                msg = log_queue.get_nowait()
                self.all_logs.append(msg)
                # 如果当前模式需要显示该行，则刷新；否则仅缓存，等切换模式时显示
                if self.detailed_log or any(kw in msg for kw in ("服务就绪", "启动完成", "数据库连接正常", "错误", "Error", "Traceback")):
                    self.log_area.configure(state=tk.NORMAL)
                    self.log_area.insert(tk.END, msg + "\n")
                    self.log_area.see(tk.END)
                    self.log_area.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(200, self.process_log_queue)

    def start_server(self):
        if self.server_running:
            return
        self.server_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.open_btn.config(state=tk.DISABLED)
        self.status_var.set("状态：启动中...")
        self.log_message("正在自动启动后端服务...")
        # 如果日志系统尚未配置，先配置
        setup_logging()
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
        if not self.server_running:
            return
        self.server_running = False
        # 由于 uvicorn 运行在守护线程，无法直接停止，我们通过设置标志并等待线程退出
        # 简单方式：关闭整个程序，因为线程是守护的，关闭窗口后会自动结束
        self.status_var.set("状态：已停止")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.open_btn.config(state=tk.DISABLED)
        self.log_message("服务已停止。如需重新启动，请点击启动服务。")

    def log_message(self, msg):
        self.all_logs.append(msg)
        # 仅当需要显示时刷新
        if self.detailed_log or any(kw in msg for kw in ("服务就绪", "启动完成", "数据库连接正常", "错误", "Error", "Traceback")):
            self.log_area.configure(state=tk.NORMAL)
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
            self.log_area.configure(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    gui = AIsChatGUI()
    gui.run()
