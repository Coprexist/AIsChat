"""
工具插件系统 — 自动发现并注册所有工具插件

每个工具是 ToolPlugin 子类，分布在子目录中。
导入此包会自动发现所有工具模块并注册到 ToolRegistry。

添加新工具只需两步：
1. 在对应子目录创建 my_tool.py，定义 ToolPlugin 子类
2. 无需修改任何现有文件
"""
import importlib
import logging
import pathlib

logger = logging.getLogger(__name__)


def _discover_tools():
    """扫描 tools/ 子目录，自动导入所有工具模块"""
    base = pathlib.Path(__file__).parent  # backend/app/tools/
    for pyfile in sorted(base.rglob("*.py")):
        if pyfile.name in ("__init__.py", "base.py"):
            continue
        # 转换为模块导入路径：app.tools.<segment>.<module>
        rel = pyfile.relative_to(base)
        module = "app.tools." + ".".join(rel.with_suffix("").parts)
        try:
            importlib.import_module(module)
        except Exception as e:
            logger.warning(f"工具模块加载失败: {module} - {e}")


_discover_tools()
