"""
技能插件桥接 — 把 skill 类插件的声明注册进 SkillRegistry

规则（"装好即可用"）：
- 插件全局 enabled（管理员开关）时，其声明的技能类型对全平台可用
- 管理员关闭 / 目录消失 → 注销对应技能类型
- 由插件注册的类型记录在 _from_plugins，注销时只动这些，绝不误删内置类型
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.services.plugin.catalog import scan_disk, get_skill_defs
from app.utils.pure.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

# {plugin_id: set(type_name)} — 由插件注册的技能类型
_from_plugins: dict[str, set[str]] = {}


def _register_plugin_skills(plugin_id: str, defs: list[dict[str, Any]]) -> None:
    registered: set[str] = set()
    for skill in defs:
        type_name = str(skill.get("type", "")).strip()
        if not type_name:
            continue
        SkillRegistry.register(
            type_name=type_name,
            name=str(skill.get("name", type_name))[:60],
            category=str(skill.get("category", "inject")),
            description=str(skill.get("description", "")),
            config_schema=skill.get("config_schema") or {},
        )
        registered.add(type_name)
    _from_plugins[plugin_id] = registered
    if registered:
        logger.info(f"技能插件已注册: {plugin_id} → {sorted(registered)}")


def _unregister_plugin_skills(plugin_id: str) -> None:
    for type_name in _from_plugins.pop(plugin_id, set()):
        SkillRegistry.unregister(type_name)


async def apply_skill_plugins(db) -> None:
    """按 DB 全局开关应用/回收技能插件（启动 + 开关切换后调用）"""
    from app.models.plugin import Plugin

    disk = scan_disk()
    result = await db.execute(select(Plugin))
    db_plugins = {p.id: p for p in result.scalars().all()}

    # 目录消失 → 回收
    for plugin_id in list(_from_plugins.keys()):
        if plugin_id not in disk or plugin_id not in db_plugins:
            _unregister_plugin_skills(plugin_id)

    # 已启用的 → 注册；已停用的 → 回收
    for plugin_id, manifest in disk.items():
        if manifest.get("category") != "skill":
            continue
        row = db_plugins.get(plugin_id)
        enabled = row.enabled if row else bool(manifest.get("default_enabled", True))
        defs = get_skill_defs(manifest)
        if not defs:
            continue
        if enabled:
            _register_plugin_skills(plugin_id, defs)
        else:
            _unregister_plugin_skills(plugin_id)
