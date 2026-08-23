"""
技能插件桥接 — 把 skill 类插件注册进 SkillRegistry 与行为注册表

统一入口：插件的元数据与行为都从这里进出（单一来源）。

两类插件形态（同一目录契约，行为可选）：
- 声明式（skill.json）：只有元数据，无行为 —— 现有格式，完全兼容
- 行为式（plugin.py）：@skill 装饰器同时完成声明 + 行为注册 —— 新格式

规则（"装好即可用"）：
- 插件全局 enabled（管理员开关）时，其声明的技能类型对全平台可用
- 管理员关闭 / 目录消失 → 注销对应技能类型，并回收该插件注册的行为处理器
- 由插件注册的类型记录在 _from_plugins，注销时只动这些，绝不误删内置类型
- 行为处理器条目带 owner（来源插件 id），停用时精确回收，同名类型谁注册删谁
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.services.plugin.catalog import scan_disk, get_skill_defs
from app.services.skill.skill_engine import _ACTION_HANDLERS, _INJECT_HANDLERS
from app.utils.pure.skill_registry import SkillRegistry

from app.repositories.plugin_repo import PluginRepository, SQLAlchemyPluginRepository
from sqlalchemy.ext.asyncio import AsyncSession
logger = logging.getLogger(__name__)

def _ensure_repo(db_or_repo):
    """兼容旧调用：传入 AsyncSession 时包装为 SQLAlchemyPluginRepository。"""
    if isinstance(db_or_repo, AsyncSession):
        return SQLAlchemyPluginRepository(db_or_repo)
    return db_or_repo


# {plugin_id: set(type_name)} — 由声明式插件注册的技能类型（行为式插件由 owner 追踪）
_from_plugins: dict[str, set[str]] = {}


def _load_behavior_plugin(plugin_id: str, plugin_dir: Path) -> None:
    """加载行为插件：importlib 导入 plugin.py，触发 @skill 装饰器注册。

    owner 通过 api.set_current_plugin 注入，注册进注册表条目。
    加载后清空上下文，防止模块顶层误注册。
    """
    from app.services.plugin import api

    handlers_file = plugin_dir / "plugin.py"
    if not handlers_file.exists():
        return
    spec = importlib.util.spec_from_file_location(
        f"_aisc_plugin_{plugin_id}", str(handlers_file)
    )
    if spec is None or spec.loader is None:
        logger.warning(f"行为插件加载失败（无法创建模块）: {plugin_id}")
        return
    module = importlib.util.module_from_spec(spec)
    try:
        api.set_current_plugin(plugin_id)
        spec.loader.exec_module(module)
    except Exception as e:
        logger.warning(f"行为插件加载异常: {plugin_id}: {e}")
    finally:
        api.set_current_plugin(None)


def _unload_behavior_plugin(plugin_id: str) -> None:
    """回收某插件注册的全部行为处理器：从两个注册表删除 owner == plugin_id 的条目，
    并注销其注册的 SkillRegistry 元数据（行为插件元数据不经 _from_plugins 追踪）。"""
    removed: list[str] = []
    for table in (_ACTION_HANDLERS, _INJECT_HANDLERS):
        for type_name in [t for t, (owner, _fn) in table.items() if owner == plugin_id]:
            del table[type_name]
            removed.append(type_name)
    for type_name in removed:
        SkillRegistry.unregister(type_name)
    if removed:
        logger.info(f"行为处理器已回收: {plugin_id} → {sorted(removed)}")


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


def _unload_plugin(plugin_id: str) -> None:
    """完整卸载一个插件：声明元数据 + 行为处理器。"""
    _unload_behavior_plugin(plugin_id)
    _unregister_plugin_skills(plugin_id)


async def apply_skill_plugins(db) -> None:
    """按 DB 全局开关应用/回收技能插件（启动 + 开关切换后调用）"""
    db = _ensure_repo(db)
    from app.models.plugin import Plugin

    disk = scan_disk()
    result = await db.execute(select(Plugin))
    db_plugins = {p.id: p for p in result.scalars().all()}

    # 目录消失 → 回收（声明式记录 + 行为式 owner 条目）
    for plugin_id in list(_from_plugins.keys()):
        if plugin_id not in disk or plugin_id not in db_plugins:
            _unload_plugin(plugin_id)

    # 已启用的 → 加载；已停用的 → 回收
    for plugin_id, manifest in disk.items():
        if manifest.get("category") != "skill":
            continue
        row = db_plugins.get(plugin_id)
        enabled = row.enabled if row else bool(manifest.get("default_enabled", True))
        if not enabled:
            _unload_plugin(plugin_id)
            continue
        _load_behavior_plugin(plugin_id, Path(manifest["_dir"]))
        defs = get_skill_defs(manifest)
        if defs:
            _register_plugin_skills(plugin_id, defs)
