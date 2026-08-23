"""
EXE 打包专用启动入口：
- 强制使用 SQLite
- 自动创建数据目录（exe 同级 data/）
- 挂载前端构建产物（frontend/dist）
- 启动 Uvicorn 并自动打开浏览器
"""
import os
import sys
import time
import webbrowser
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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class APIPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            request.scope["path"] = request.url.path[4:]  # 去掉 /api
        return await call_next(request)

app.add_middleware(APIPrefixMiddleware)


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


def _replace_root_route(app):
    """递归查找并替换根路由处理函数，使 / 返回前端 index.html。"""
    def _walk(routes):
        for route in routes:
            if getattr(route, "path", None) == "/" and "GET" in getattr(route, "methods", set()):
                return route
            # 检查普通子路由
            sub_routes = getattr(route, "routes", None)
            if sub_routes:
                found = _walk(sub_routes)
                if found:
                    return found
            # 检查 _IncludedRouter 的 original_router
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


def open_browser_when_ready():
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
            webbrowser.open("http://127.0.0.1:8000")
            return
        except Exception:
            time.sleep(1)
    # 如果等待超时，仍然打开浏览器
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
