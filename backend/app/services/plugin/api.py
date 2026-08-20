"""
插件公共 API — 行为插件（声明 + 行为合一）的唯一入口。

行为插件 = 插件目录 + plugin.json（展示元数据）+ plugin.py（行为入口）：

    plugins/
      my-plugin/
        plugin.json     # id/name/description/category/icon/version
        plugin.py       # 用 @skill 装饰器声明并注册行为

plugin.py 示例：

    from app.services.plugin.api import skill

    @skill(
        type="keyword_autoreply",
        category="action",
        name="关键词自动回复",
        description="命中关键词时注入回复指令",
        config_schema={"keywords": {"type": "array", "items": {"type": "string"}}},
    )
    def handle(ctx):
        # ctx: {db, agent, skill, config, result, context, ...} 由分发器按需传入
        ...

一个装饰器同时完成两件事（单一来源，无双写）：
- 元数据 → SkillRegistry（与声明式 skill.json 完全同构）
- 行为 → skill_engine 的 _ACTION_HANDLERS / _INJECT_HANDLERS（owner 并入条目）

owner 由 skill_bridge 在加载时通过 set_current_plugin() 注入：装饰器执行时读取
当前正在加载的插件 id，注册进条目。加载结束后清空，防止模块顶层误注册。

语言中立契约：handler 收到的是普通 dict/对象上下文，返回效果写入 result——
不依赖任何 Python 特定机制，未来后端换语言时契约可平移。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from app.services.skill.skill_engine import (
    register_action_handler,
    register_inject_handler,
)
from app.utils.pure.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

# 当前正在被 skill_bridge 加载的插件 id（装饰器执行时读取，作为 owner）
_current_plugin: str | None = None


def set_current_plugin(plugin_id: str | None) -> None:
    """skill_bridge 加载 plugin.py 前设置、加载后清空。"""
    global _current_plugin
    _current_plugin = plugin_id


def get_current_plugin() -> str | None:
    """当前加载上下文（测试与调试用）。"""
    return _current_plugin


def skill(
    type: str,
    category: str,
    name: str,
    description: str = "",
    config_schema: dict[str, Any] | None = None,
) -> Callable:
    """装饰器：声明一个技能类型并注册其行为处理器（一次完成）。

    :param type: 技能类型标识（唯一，与 AgentSkill.skill_type 对应）
    :param category: action（影响回复行为）或 inject（注入提示词）
    :param name: 显示名称
    :param description: 描述
    :param config_schema: 配置项 JSON Schema（前端表单用）
    """
    if category not in ("action", "inject"):
        raise ValueError(
            f"插件技能类别必须是 action 或 inject，收到 {category!r}（插件 {_current_plugin}）"
        )

    def wrapper(func: Callable) -> Callable:
        owner = _current_plugin  # skill_bridge 加载时注入；None = 非插件上下文
        SkillRegistry.register(
            type_name=type,
            name=name[:60],
            category=category,
            description=description,
            config_schema=config_schema or {},
        )
        register = register_action_handler if category == "action" else register_inject_handler
        register(type, owner=owner)(func)
        if owner:
            logger.info(f"行为插件已注册: {owner} -> {type} ({category})")
        return func

    return wrapper


__all__ = ["skill", "set_current_plugin", "get_current_plugin"]
