import logging
import queue

log_queue = queue.Queue()

class QueueLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_queue.put(msg)
        except Exception:
            pass

def setup_logging():
    handler = QueueLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 幂等：重复调用（如多次启动服务）不叠加队列处理器，避免日志重复
    if not any(isinstance(h, QueueLogHandler) for h in root.handlers):
        root.addHandler(handler)


def attach_queue_handler():
    """把队列处理器附加到主要 logger（与既有处理器共存，不替换）。

    后端导入时会执行自己的 dictConfig（console + 滚动文件处理器），
    把 GUI 的队列处理器清掉；此函数在导入后调用，把队列处理器补挂回去，
    保证后端日志也能进入启动器日志面板（同时保留后端的文件日志）。
    """
    handler = QueueLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    for name in ("", "app", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(h, QueueLogHandler) for h in logger.handlers):
            logger.addHandler(handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)
