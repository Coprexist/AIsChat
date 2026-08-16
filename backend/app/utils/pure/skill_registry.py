"""
技能类型注册中心 — 管理所有可用的技能类型及其元数据

替代硬编码 skill_type 和 if/elif 分支，新增技能类型只需注册即可。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SkillTypeInfo:
    """技能类型的元数据"""
    def __init__(
        self,
        type_name: str,
        name: str,
        category: str,
        description: str = "",
        config_schema: dict[str, Any] | None = None,
    ):
        """
        :param type_name: 技能类型标识，如 delay_reply
        :param name: 显示名称，如 延迟回复
        :param category: 类别，action（影响回复行为）或 inject（注入提示词）
        :param description: 描述
        :param config_schema: 配置项 JSON Schema 说明
        """
        self.type_name = type_name
        self.name = name
        self.category = category
        self.description = description
        self.config_schema = config_schema or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_name": self.type_name,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "config_schema": self.config_schema,
        }


class SkillRegistry:
    """技能类型注册表 — 单例模式"""

    _types: dict[str, SkillTypeInfo] = {}

    @classmethod
    def register(
        cls,
        type_name: str,
        name: str,
        category: str,
        description: str = "",
        config_schema: dict[str, Any] | None = None,
    ) -> None:
        """注册一个技能类型"""
        info = SkillTypeInfo(type_name, name, category, description, config_schema)
        cls._types[type_name] = info
        logger.debug(f"技能类型已注册: {type_name} ({category})")

    @classmethod
    def get_info(cls, type_name: str) -> SkillTypeInfo | None:
        return cls._types.get(type_name)

    @classmethod
    def get_all_types(cls) -> dict[str, SkillTypeInfo]:
        return dict(cls._types)

    @classmethod
    def get_type_names(cls) -> list[str]:
        return list(cls._types.keys())

    @classmethod
    def get_category_types(cls, category: str) -> dict[str, SkillTypeInfo]:
        """获取指定类别的所有技能类型"""
        return {
            k: v for k, v in cls._types.items()
            if v.category == category
        }

    @classmethod
    def is_valid_type(cls, type_name: str) -> bool:
        return type_name in cls._types

    @classmethod
    def unregister(cls, type_name: str) -> None:
        """注销一个技能类型（插件停用/卸载时调用；内置类型不受影响）"""
        if type_name in cls._types:
            del cls._types[type_name]
            logger.info(f"技能类型已注销: {type_name}")


# ── 注册内置技能类型 ──

SkillRegistry.register(
    type_name="delay_reply",
    name="延迟回复",
    category="action",
    description="收到消息后等 N 秒再回复，让对话更自然",
    config_schema={
        "delay_seconds": {"type": "integer", "default": 3, "description": "延迟秒数"},
        "max_delay_seconds": {"type": "integer", "default": 30, "description": "最大延迟秒数"},
    },
)

SkillRegistry.register(
    type_name="typing_indicator",
    name="打字指示器",
    category="action",
    description="回复前显示「正在输入…」",
    config_schema={
        "pattern": {"type": "string", "default": "always", "description": "触发模式"},
        "duration_ms": {"type": "integer", "default": 2000, "description": "显示时长(毫秒)"},
    },
)

SkillRegistry.register(
    type_name="scene_trigger",
    name="场景匹配",
    category="inject",
    description="检测到特定关键词或正则时触发行为",
    config_schema={
        "match_type": {"type": "string", "default": "keyword", "description": "keyword 或 regex"},
        "keywords": {"type": "array", "default": [], "description": "关键词列表（keyword 模式）"},
        "pattern_regex": {"type": "string", "default": "", "description": "正则表达式（regex 模式）"},
        "inject_text": {"type": "string", "default": "", "description": "触发时注入的提示词"},
    },
)

SkillRegistry.register(
    type_name="inject_prompt",
    name="注入提示词",
    category="inject",
    description="临时追加一段指导到思维中",
    config_schema={
        "insert_text": {"type": "string", "default": "", "description": "注入的提示词文本"},
        "duration_seconds": {"type": "integer", "default": 300, "description": "持续时间（秒）"},
        "one_shot": {"type": "boolean", "default": False, "description": "是否一次性"},
    },
)
