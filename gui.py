"""
AIsChat 桌面启动器 GUI —— 兼容入口
==================================
界面实现已迁移至 `gui_app` 包（设计令牌 / 组件 / 服务控制器 / 主窗口分层），
本文件仅保留向后兼容的公开导入：

    from gui import AIsChatGUI

`run_packaged.py` 与 PyInstaller 打包配置无需任何改动。
"""
from gui_app.main import AIsChatGUI

__all__ = ["AIsChatGUI"]
