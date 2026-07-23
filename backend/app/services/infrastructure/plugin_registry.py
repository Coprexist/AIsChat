"""
服务插件注册中心 — 管理所有系统服务插件的注册、状态查询和启停

替代 admin.py 中硬编码的 PLUGIN_REGISTRY dict 和 if id != "browser" 路由检查。
新插件只需继承 ServicePlugin 并注册到 PluginRegistry，即可自动出现在插件管理列表。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ServicePlugin:
    """服务插件基类 — 每个系统服务一个子类"""

    id: str = ""
    name: str = ""
    description: str = ""
    category: str = "service"

    async def get_status(self) -> dict[str, Any]:
        """返回当前运行状态"""
        return {"installed": False, "running": False}

    async def start(self) -> bool:
        """启动服务"""
        raise NotImplementedError(f"{self.id} 未实现 start()")

    async def stop(self) -> bool:
        """停止服务"""
        raise NotImplementedError(f"{self.id} 未实现 stop()")


class PluginRegistry:
    """服务插件注册表 — 单例"""

    _plugins: dict[str, ServicePlugin] = {}

    @classmethod
    def register(cls, plugin: ServicePlugin) -> None:
        """注册一个服务插件"""
        if plugin.id in cls._plugins:
            logger.warning(f"插件 {plugin.id} 重复注册，已覆盖")
        cls._plugins[plugin.id] = plugin
        logger.info(f"服务插件已注册: {plugin.id} ({plugin.name})")

    @classmethod
    def get(cls, plugin_id: str) -> ServicePlugin | None:
        return cls._plugins.get(plugin_id)

    @classmethod
    def get_all(cls) -> list[ServicePlugin]:
        return list(cls._plugins.values())

    @classmethod
    async def get_status_all(cls) -> list[dict[str, Any]]:
        """获取所有插件的状态（供 API 返回）"""
        results = []
        for plugin in cls._plugins.values():
            try:
                status = await plugin.get_status()
            except Exception as e:
                logger.warning(f"获取插件 {plugin.id} 状态失败: {e}")
                status = {"installed": False, "running": False}
            results.append({
                "id": plugin.id,
                "name": plugin.name,
                "description": plugin.description,
                "category": plugin.category,
                **status,
            })
        return results
