"""
后端启动核心：设置环境、导入 FastAPI 应用、配置静态托管，并提供可优雅停止的服务器。
"""
import os
import sys
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
    # 如果路径以 api/ 开头，说明是 API 请求，不应该由静态文件处理
    if full_path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    file_path = STATIC_DIR / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(STATIC_DIR / "index.html")


def create_server(host="127.0.0.1", port=8000, log_level="info", log_config=None):
    """创建并返回一个可优雅停止的 Uvicorn 服务器实例。"""
    config = uvicorn.Config(app, host=host, port=port, log_level=log_level, log_config=log_config)
    return uvicorn.Server(config)
