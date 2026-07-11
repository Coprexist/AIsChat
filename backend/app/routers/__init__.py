"""
API 路由 — 自动发现并注册所有路由模块

每个路由模块定义一个 router = APIRouter(...) 变量放在 routers/ 目录下。
添加新路由只需新建 .py 文件，无需修改任何现有代码。
"""
import importlib
import logging
import pathlib

logger = logging.getLogger(__name__)

# 内部存储
_discovered_routers: list = []


def _discover_routers():
    """扫描 routers/ 目录，自动导入所有路由模块"""
    base = pathlib.Path(__file__).parent  # backend/app/routers/
    for pyfile in sorted(base.rglob("*.py")):
        if pyfile.name == "__init__.py":
            continue
        mod_name = "app.routers." + pyfile.stem
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "router"):
                _discovered_routers.append(mod.router)
        except Exception as e:
            logger.warning(f"路由模块加载失败: {mod_name} - {e}")


def get_all_routers():
    """返回所有已发现的路由器实例列表（供 main.py 注册）"""
    return list(_discovered_routers)


# 包加载时自动扫描并注册所有路由
_discover_routers()
