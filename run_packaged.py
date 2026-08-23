"""
EXE 打包专用启动入口：
- 强制使用 SQLite
- 自动创建数据目录（exe 同级 data/）
- 挂载前端构建产物（frontend/dist）
- 图形化界面（tkinter）控制后端启动/停止，自动打开浏览器
"""
import os
import sys
import time
import threading
from pathlib import Path

import uvicorn

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).resolve().parent
    BACKEND_DIR = BASE_DIR
else:
    BASE_DIR = Path(__file__).resolve().parent
    APP_DIR = BASE_DIR
    BACKEND_DIR = BASE_DIR / "backend"

DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TMP_DIR = DATA_DIR / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

os.environ["DB_BACKEND"] = "sqlite"
os.environ["SQLITE_DB_PATH"] = str(DATA_DIR / "aischat.db")
os.environ["ENVIRONMENT"] = "development"
os.environ["MAINTENANCE_DIR"] = str(TMP_DIR)
os.environ["LOG_LEVEL"] = "INFO"

STATIC_DIR = BASE_DIR / "frontend/dist"
if not STATIC_DIR.exists():
    STATIC_DIR = APP_DIR / "frontend/dist"
if not STATIC_DIR.exists():
    STATIC_DIR = APP_DIR / "_internal/frontend/dist"

sys.path.insert(0, str(BACKEND_DIR))

from app.main import app

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


def _replace_root_route(app):
    """递归查找并替换根路由处理函数，使 / 返回前端 index.html。"""
    def _walk(routes):
        for route in routes:
            if getattr(route, "path", None) == "/" and "GET" in getattr(route, "methods", set()):
                return route
            sub_routes = getattr(route, "routes", None)
            if sub_routes:
                found = _walk(sub_routes)
                if found:
                    return found
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                found = _walk(original_router.routes)
                if found:
                    return found
        return None

    root_route = _walk(app.router.routes)
    if root_route:
        async def index():
            return FileResponse(STATIC_DIR / "index.html")
        root_route.endpoint = index


_replace_root_route(app)

app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    file_path = STATIC_DIR / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(STATIC_DIR / "index.html")


#  GUI 启动器 
import tkinter as tk
from tkinter import scrolledtext, messagebox
import webbrowser
import urllib.request


class AIsChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AIsChat 启动器")
        self.root.geometry("500x400")
        self.root.resizable(False, False)

        self.server_thread = None
        self.server_running = False

        self.status_label = tk.Label(self.root, text="状态：未启动", font=("微软雅黑", 12))
        self.status_label.pack(pady=10)

        self.start_btn = tk.Button(self.root, text="启动服务", command=self.start_server, width=20, height=2)
        self.start_btn.pack(pady=5)

        self.open_btn = tk.Button(self.root, text="打开浏览器", command=self.open_browser, state=tk.DISABLED, width=20, height=2)
        self.open_btn.pack(pady=5)

        self.stop_btn = tk.Button(self.root, text="停止服务", command=self.stop_server, state=tk.DISABLED, width=20, height=2)
        self.stop_btn.pack(pady=5)

        self.log_area = scrolledtext.ScrolledText(self.root, width=60, height=12, state=tk.DISABLED)
        self.log_area.pack(pady=10)

    def log(self, msg):
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state=tk.DISABLED)

    def start_server(self):
        if self.server_running:
            return
        self.log("正在启动服务...")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()

    def _run_server(self):
        self.server_running = True
        self.root.after(0, lambda: self.status_label.config(text="状态：启动中..."))
        # 注意：uvicorn.run 会阻塞当前线程，但我们在新线程中运行
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

    def check_ready(self):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
            self.status_label.config(text="状态：服务已启动")
            self.open_btn.config(state=tk.NORMAL)
            self.start_btn.config(state=tk.DISABLED)
            self.log("服务已就绪，可以打开浏览器了。")
            # 自动打开浏览器
            webbrowser.open("http://127.0.0.1:8000")
            return
        except Exception:
            pass
        # 继续轮询
        if self.server_running:
            self.root.after(1000, self.check_ready)

    def open_browser(self):
        webbrowser.open("http://127.0.0.1:8000")

    def stop_server(self):
        if self.server_running:
            self.log("正在停止服务...")
            self.server_running = False
            self.stop_btn.config(state=tk.DISABLED)
            self.open_btn.config(state=tk.DISABLED)
            self.status_label.config(text="状态：已停止")
            # 停止 uvicorn：由于 uvicorn.run 阻塞，我们无法直接停止线程。
            # 这里采用 os._exit 强制退出，或者用更优雅的方式。
            # 为了简单，我们提示用户关闭窗口即可。
            messagebox.showinfo("提示", "请直接关闭此窗口以完全退出程序。")
            self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    gui = AIsChatGUI()
    # 启动后自动轮询服务是否就绪
    gui.root.after(500, gui.check_ready)
    gui.run()
