"""
AIsChat 桌面启动器 GUI 包
=========================
分层结构：
- theme        设计令牌（青碧色品牌色 / 圆角 / 字体）
- widgets      可复用组件（状态点 / 卡片 / 日志面板 / 模式切换）
- controller   后端服务生命周期（启动 / 停止 / 健康轮询 / 日志泵）
- main         主窗口（AIsChatGUI）

对外公开入口保持 `from gui import AIsChatGUI` 兼容不变。
"""
from .main import AIsChatGUI

__all__ = ["AIsChatGUI"]
