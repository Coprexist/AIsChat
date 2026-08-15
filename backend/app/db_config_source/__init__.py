"""
DB 配置源（DBConfigSource）— pydantic-settings 官方扩展点

让 Settings 支持「DB 覆盖 > env > dotenv > 默认」分层，管理员可前端图形化修改。

机制（pydantic-settings 官方 customise_sources）：
    Settings.settings_customise_sources() 返回的 sources 元组中，
    插入本 Source（仅次 init），所有 settings.xxx 自动获得 DB 优先能力，零侵入。

持久 + 快：
    - 持久：覆盖值存 system_settings.embedding_config（JSONB），重启不丢
    - 快：读路径走内存缓存 _db_overrides；DB 只在启动加载 / 保存时更新
    - 兼容：DB 未覆盖的字段自动落到 env/dotenv/默认

用法：
    # 读取（现有代码零改动）
    settings.embedding_backend   # 自动：DB 覆盖 > env > 默认

    # 写入（管理 API 调用）
    await save_db_config(db, {"embedding_backend": "ollama", ...})
    await clear_db_config(db)    # 恢复默认（删除 DB 覆盖）
"""

import logging
from typing import Any

from pydantic_settings import PydanticBaseSettingsSource

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 内存缓存（读路径零 DB）
# ═══════════════════════════════════════════════════════════════

#: DB 覆盖值缓存：{field_name: value}。启动时从 system_settings 加载，
#: 保存时更新；重启后从 DB 重新加载（持久）。
_db_overrides: dict[str, Any] = {}


def get_db_override(field_name: str) -> Any | None:
    """读缓存中的 DB 覆盖值（None = 未覆盖，走 env/默认）"""
    return _db_overrides.get(field_name)


def set_db_overrides(values: dict[str, Any]) -> None:
    """整体替换缓存（启动加载 / 保存后同步）"""
    _db_overrides.clear()
    for k, v in values.items():
        if v is not None:
            _db_overrides[k] = v


def clear_db_overrides() -> None:
    """清空缓存（恢复默认时）"""
    _db_overrides.clear()


# ═══════════════════════════════════════════════════════════════
# pydantic-settings Source
# ═══════════════════════════════════════════════════════════════

class DBConfigSource(PydanticBaseSettingsSource):
    """从内存缓存读取 DB 覆盖值的 Settings Source（仅次 init 的优先级）"""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        value = _db_overrides.get(field_name)
        if value is None:
            return None, field_name, False
        return value, field_name, True

    def __call__(self) -> dict[str, Any]:
        # 只返回缓存中实际存在的字段（避免用 None 覆盖 env 值）
        return {k: v for k, v in _db_overrides.items() if v is not None}
