"""
后端服务生命周期控制器
=======================
与界面解耦：只负责 启动 / 停止 / 健康轮询 / 日志泵，
通过 `poll()` 返回状态迁移事件，由主窗口驱动 UI 刷新。
"""
from __future__ import annotations

import threading
import time
import urllib.request

import logging_utils
from .theme import HEALTH_URL

# 注意：server_core 在导入时会加载整个后端（FastAPI 应用），
# 因此改为在启动线程内延迟导入，保证启动器窗口能立刻出现。

# ── 服务状态 ──
STATE_STOPPED = "stopped"      # 已停止
STATE_STARTING = "starting"    # 启动中
STATE_RUNNING = "running"      # 运行中
STATE_STOPPING = "stopping"    # 停止中

# ── 迁移事件（poll 返回值）──
EVENT_STARTED = STATE_RUNNING          # 启动完成 → 运行中
EVENT_STOPPED = STATE_STOPPED          # 停止完成
EVENT_FAILED = "failed"                # 启动失败
EVENT_CRASHED = "crashed"              # 运行中异常退出

_ACTIVE_STATES = (STATE_STARTING, STATE_RUNNING, STATE_STOPPING)


class ServerController:
    """服务状态机：stopped → starting → running → stopping → stopped。"""

    def __init__(self):
        self.server = None
        self.thread: threading.Thread | None = None
        self.state = STATE_STOPPED

        self._health_ok = False
        self._last_health_check = 0.0
        self._health_interval = 1.0   # 健康检查最小间隔（秒）

    # ── 状态查询 ──

    def is_active(self) -> bool:
        return self.state in _ACTIVE_STATES

    def is_running(self) -> bool:
        return self.state == STATE_RUNNING

    # ── 启动 / 停止 ──

    def start(self) -> None:
        """启动后端服务（幂等：已在运行则忽略）。

        后端导入较重（FastAPI 应用），放入工作线程执行，
        主线程（界面）立即返回，窗口不会卡在“启动中”。
        """
        if self.state in _ACTIVE_STATES:
            return
        self.state = STATE_STARTING
        self._health_ok = False
        self._last_health_check = 0.0

        logging_utils.setup_logging()
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def _run_server(self) -> None:
        """工作线程：延迟导入后端并运行服务；异常时线程退出由 poll() 判定失败。"""
        try:
            from server_core import create_server
            # 后端导入时会执行自己的 dictConfig 日志配置，清掉 GUI 的队列处理器；
            # 这里补挂回去（与后端的文件/控制台处理器共存），保证日志进面板。
            logging_utils.attach_queue_handler()
            server = create_server(log_level="info", log_config=None)
            self.server = server
            # 导入期间用户已要求停止 → 启动后立即退出
            if self.state != STATE_STARTING:
                server.should_exit = True
            server.run()
        except Exception:
            # 把真实报错送进日志队列（界面可见）+ 标准错误（打包调试可见），
            # 避免“启动失败”却看不到原因的尴尬。
            import sys as _sys
            import traceback as _traceback
            tb = _traceback.format_exc()
            for line in tb.splitlines():
                logging_utils.log_queue.put(line)
            if _sys.stderr is not None:
                _sys.stderr.write("\n".join(tb.splitlines()) + "\n")
                _sys.stderr.flush()
            return

    def stop(self) -> None:
        """请求优雅停止（仅对启动中 / 运行中生效）。"""
        if self.state not in (STATE_STARTING, STATE_RUNNING):
            return
        self.state = STATE_STOPPING
        if self.server is not None:
            self.server.should_exit = True

    # ── 周期推进（由界面定时调用）──

    def poll(self) -> str | None:
        """
        推进状态机；发生状态迁移时返回事件名，否则返回 None。
        事件：EVENT_STARTED / EVENT_STOPPED / EVENT_FAILED / EVENT_CRASHED
        """
        now = time.monotonic()

        if self.state == STATE_STARTING:
            # 节流健康检查，避免高频请求
            if not self._health_ok and now - self._last_health_check < self._health_interval:
                return None
            self._last_health_check = now
            try:
                urllib.request.urlopen(HEALTH_URL, timeout=2)
                self._health_ok = True
                self.state = STATE_RUNNING
                return EVENT_STARTED
            except Exception:
                if self.thread is not None and not self.thread.is_alive():
                    # 线程已退出且健康检查未通过 → 启动失败
                    self.state = STATE_STOPPED
                    return EVENT_FAILED
                return None

        if self.state == STATE_RUNNING:
            # 运行中线程意外退出 → 服务崩溃
            if self.thread is not None and not self.thread.is_alive():
                self.state = STATE_STOPPED
                return EVENT_CRASHED
            return None

        if self.state == STATE_STOPPING:
            if self.thread is not None and not self.thread.is_alive():
                self.state = STATE_STOPPED
                return EVENT_STOPPED
            return None

        return None

    # ── 日志泵 ──

    def pump_logs(self) -> list[str]:
        """排空日志队列，返回新产生的日志行列表。"""
        msgs: list[str] = []
        try:
            while True:
                msgs.append(logging_utils.log_queue.get_nowait())
        except Exception:
            pass
        return msgs
