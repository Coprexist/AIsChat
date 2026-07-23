"""
WebSocket 连接管理器（兼容层）

已迁移到 app/services/connection_manager.py，此处仅做兼容导出。
"""

from app.services.connection_manager import ConnectionManager, connection_manager

__all__ = ["ConnectionManager", "connection_manager"]