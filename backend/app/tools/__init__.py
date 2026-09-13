"""
工具插件系统 — 自动发现并注册所有工具插件

每个工具是 ToolPlugin 子类（世界侧是 WorldToolPlugin），分布在子目录中。
导入此包会自动发现所有工具模块并注册到注册中心。

添加新工具只需两步：
1. 在对应子目录创建 my_tool.py，定义插件子类
2. 无需修改任何现有文件

社区插件也可以放在主仓库之外：把插件目录配到 WORLD_TOOLS_DIR，启动时同样自动发现
（配置为空 = 关闭；该目录里的代码与主仓库同权限运行，只放可信代码）。
"""
import importlib
import importlib.util
import logging
import os
import pathlib
import sys

logger = logging.getLogger(__name__)


def _discover_tools():
    """扫描 tools/ 子目录，自动导入所有工具模块"""
    base = pathlib.Path(__file__).parent  # backend/app/tools/
    for pyfile in sorted(base.rglob("*.py")):
        # 框架件与下划线文件（shared/base/_template）不是工具，跳过
        if pyfile.name in ("__init__.py", "base.py", "shared.py") or pyfile.name.startswith("_"):
            continue
        # 转换为模块导入路径：app.tools.<segment>.<module>
        rel = pyfile.relative_to(base)
        module = "app.tools." + ".".join(rel.with_suffix("").parts)
        try:
            importlib.import_module(module)
        except Exception as e:
            logger.warning(f"工具模块加载失败: {module} - {e}")


def _discover_external_tools():
    """外部插件目录（WORLD_TOOLS_DIR）：一个 .py 一个工具，导入失败只记日志，不拖垮启动"""
    root = os.environ.get("WORLD_TOOLS_DIR", "").strip()
    if not root:
        return
    dirpath = pathlib.Path(root).expanduser()
    if not dirpath.is_dir():
        logger.warning(f"外部工具目录不存在，已忽略: {dirpath}")
        return
    for pyfile in sorted(dirpath.rglob("*.py")):
        if pyfile.name.startswith("_"):
            continue
        module = f"aischat_ext_tool_{pyfile.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module, pyfile)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module] = mod
            spec.loader.exec_module(mod)
            logger.info(f"外部工具已加载: {pyfile}")
        except Exception as e:                       # noqa: BLE001 —— 第三方代码，隔离失败
            sys.modules.pop(module, None)
            logger.warning(f"外部工具加载失败: {pyfile} - {e}")


_discover_tools()
_discover_external_tools()
