"""
维护模式管理器 — 集中封装维护状态的读写与文案管理。

部署形态：单容器单进程，用文件系统标记即可满足需求：
- maintenance_startup     自动维护（启动/关闭期间），由进程自己创建和删除
- maintenance_soft        软维护（管理员手动）：API 正常但前端显示提示
- maintenance_admin_hard  硬维护（管理员手动）：503 拦截
- 文案 JSON 持久化在数据目录（docker 挂载卷，重启不丢）

历史遗留：旧版本文案写在 MAINTENANCE_DIR（容器 /tmp），首次启动自动迁移到数据目录。
"""
import json
import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_MSG = {
    "hard_title": "正在更新",
    "hard_body": "服务器正在更新，稍等一下就好~",
    "hard_color": "#f59e0b", "hard_text_color": "#ffffff",
    "hard_image": "", "hard_style": "popup",
    "soft_text": "服务器正在调整，功能可能偶尔不稳定",
    "soft_color": "#f59e0b", "soft_text_color": "#ffffff",
    "soft_style": "banner", "soft_once": False,
}


class MaintenanceManager:
    """维护模式状态与文案的统一入口（单例使用：maintenance）"""

    def __init__(self, maint_dir: str | None = None, data_dir: str | None = None):
        self._dir = maint_dir or os.environ.get("MAINTENANCE_DIR", "/tmp")
        self._auto = os.path.join(self._dir, "maintenance_startup")
        self._soft = os.path.join(self._dir, "maintenance_soft")
        self._hard = os.path.join(self._dir, "maintenance_admin_hard")
        self._msg_file = os.path.join(data_dir or settings.data_dir, "maintenance_msg.json")
        self._legacy_msg = os.path.join(self._dir, "maintenance_msg.json")
        self._migrate_legacy_msg()

    # ── 标记读写 ──

    def set_auto(self) -> None:
        """进入自动维护（启动/关闭期间）"""
        with open(self._auto, "w"):
            pass

    def clear_auto(self) -> bool:
        """退出自动维护；返回是否确实清掉了（仅清理本次进程创建的标记）"""
        if os.path.exists(self._auto):
            os.remove(self._auto)
            return True
        return False

    def is_auto(self) -> bool:
        return os.path.exists(self._auto)

    def is_soft(self) -> bool:
        return os.path.exists(self._soft)

    def is_hard(self) -> bool:
        """管理员手动硬维护"""
        return os.path.exists(self._hard)

    def hard_active(self) -> bool:
        """当前是否处于任何硬维护（自动或管理员手动）"""
        return self.is_auto() or self.is_hard()

    # ── 文案 ──

    def get_msg(self) -> dict:
        """读取自定义维护文本，不存在则返回默认"""
        try:
            if os.path.exists(self._msg_file):
                with open(self._msg_file, encoding="utf-8") as f:
                    return json.loads(f.read())
        except Exception:
            logger.warning("⚠️ 维护文案读取失败，使用默认文案", exc_info=True)
        return dict(_DEFAULT_MSG)

    def _migrate_legacy_msg(self) -> None:
        """旧版本文案在 MAINTENANCE_DIR（/tmp）→ 迁移到持久化数据目录"""
        if os.path.exists(self._msg_file) or not os.path.exists(self._legacy_msg):
            return
        try:
            Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
            with open(self._legacy_msg, encoding="utf-8") as src, \
                 open(self._msg_file, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            logger.info("📦 维护文案已从 %s 迁移到 %s", self._legacy_msg, self._msg_file)
        except Exception:
            logger.warning("⚠️ 维护文案迁移失败（忽略，使用默认文案）", exc_info=True)


# 全局单例：中间件 / lifespan / 维护路由共用
maintenance = MaintenanceManager()
