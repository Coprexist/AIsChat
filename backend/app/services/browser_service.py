"""
Chrome 共享服务 — 单例 Chromium 进程，所有 AI 共用 CDP 端口。

生命周期：FastAPI startup → 检查设置 → 启动 chrome
         管理员开关 → start/stop
         FastAPI shutdown → 清理进程
"""
import asyncio
import logging
import os
import signal
import time

logger = logging.getLogger(__name__)

CDP_PORT = 9222
CDP_ENDPOINT = f"http://127.0.0.1:{CDP_PORT}"
PID_FILE = "/tmp/chromium_cdp.pid"
CHROMIUM_BIN = "/usr/bin/chromium"

_chrome_process: asyncio.subprocess.Process | None = None


def is_running() -> bool:
    """检查 Chromium 是否在运行（通过 CDP 端口探测）"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", CDP_PORT))
        s.close()
        return result == 0
    except Exception:
        return False


async def start() -> bool:
    """启动 Chromium headless + CDP。已运行则跳过。"""
    global _chrome_process

    if is_running():
        logger.info(f"Chromium CDP 已在运行 (port {CDP_PORT})")
        return True

    if not os.path.exists(CHROMIUM_BIN):
        logger.error(f"Chromium 未安装: {CHROMIUM_BIN}")
        return False

    logger.info(f"启动 Chromium headless CDP (port {CDP_PORT})...")
    try:
        _chrome_process = await asyncio.create_subprocess_exec(
            CHROMIUM_BIN,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--no-first-run",
            "--disable-ipv6",
            "--disable-web-security",
            "--ignore-certificate-errors",
            "--disable-features=AsyncDNS,TranslateUI,VizDisplayCompositor,NetworkService",
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-allow-origins=*",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # 等待端口就绪
        for _ in range(50):  # 最多等 5 秒
            await asyncio.sleep(0.1)
            if is_running():
                logger.info(f"Chromium CDP 已就绪 (pid={_chrome_process.pid})")
                return True
        logger.warning("Chromium 启动超时，但进程可能仍在初始化")
        return is_running()
    except Exception as e:
        logger.error(f"启动 Chromium 失败: {e}")
        return False


async def stop() -> bool:
    """停止 Chromium 进程。"""
    global _chrome_process

    # 先尝试优雅关闭 CDP
    if is_running():
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/close", timeout=2)
            await asyncio.sleep(0.5)
        except Exception:
            pass

    if _chrome_process is not None and _chrome_process.returncode is None:
        try:
            _chrome_process.terminate()
            await asyncio.wait_for(_chrome_process.wait(), timeout=5)
        except asyncio.TimeoutError:
            _chrome_process.kill()
        except Exception:
            pass

    # fallback: 杀所有 chromium 进程
    if is_running():
        try:
            proc = await asyncio.create_subprocess_exec(
                "pkill", "-f", "chromium.*remote-debugging-port",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception:
            pass

    _chrome_process = None
    logger.info("Chromium CDP 已停止")
    return True
