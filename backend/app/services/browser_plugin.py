"""
浏览器服务插件 — 封装共享 Chromium CDP 服务为 ServicePlugin 接口
"""
from __future__ import annotations

import logging
from app.services.plugin_registry import ServicePlugin, PluginRegistry

logger = logging.getLogger(__name__)


class BrowserPlugin(ServicePlugin):
    id = "browser"
    name = "浏览器上网"
    description = "共享 Chromium 实例（headless + CDP），所有 AI 共用。启动后 AI 可通过 browser 命令上网查资料、访问网页、截图。"
    category = "service"

    async def get_status(self) -> dict:
        try:
            from app.services.browser_service import is_running, CDP_PORT
            running = is_running()
            return {
                "installed": True,
                "running": running,
                "port": CDP_PORT if running else None,
            }
        except Exception:
            return {"installed": False, "running": False, "port": None}

    async def start(self) -> bool:
        from app.services.browser_service import start, is_running
        if is_running():
            return True
        ok = await start()
        if ok:
            import os
            os.environ["OPENCLI_CDP_ENDPOINT"] = "http://127.0.0.1:9222"
        return ok

    async def stop(self) -> bool:
        from app.services.browser_service import stop, is_running
        if not is_running():
            return True
        await stop()
        return True


# 注册到插件注册表
PluginRegistry.register(BrowserPlugin())
