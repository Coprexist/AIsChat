"""
上下文配置解析器 — 将声明式配置解析为上下文构建规则

负责：
  - 从 DB/配置文件加载上下文配置
  - 解析配置并生成上下文构建规则
  - 提供配置驱动的上下文构建入口
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context_config import ContextConfig

logger = logging.getLogger(__name__)


class ContextConfigParser:
    _default_config: ContextConfig = None

    @classmethod
    def get_default_config(cls) -> ContextConfig:
        if cls._default_config is None:
            cls._default_config = ContextConfig()
        return cls._default_config

    @classmethod
    async def load_config_from_db(cls, db: AsyncSession, agent_id: int) -> ContextConfig:
        try:
            from app.models.system_settings import SystemSettings
            result = await db.execute(SystemSettings.__table__.select().where(SystemSettings.id == 1))
            settings = result.first()
            if settings and settings.get("context_config"):
                return ContextConfig.from_dict(settings["context_config"])
        except Exception as e:
            logger.warning(f"从 DB 加载上下文配置失败，使用默认配置: {e}")
        return cls.get_default_config()

    @classmethod
    def parse_segment_order(cls, config: ContextConfig) -> list[str]:
        return config.segment_order

    @classmethod
    def get_enabled_segments(cls, config: ContextConfig) -> list[str]:
        return [name for name, seg in config.segments.items() if seg.enabled]

    @classmethod
    def get_segment_weight(cls, config: ContextConfig, segment_name: str) -> float:
        seg = config.segments.get(segment_name)
        return seg.weight if seg else 1.0

    @classmethod
    def should_inject_memory(cls, config: ContextConfig) -> bool:
        return config.memory.enabled

    @classmethod
    def should_inject_skills(cls, config: ContextConfig) -> bool:
        return config.skill_injection.enabled

    @classmethod
    def should_inject_workspace(cls, config: ContextConfig) -> bool:
        return config.workspace.enabled

    @classmethod
    def should_inject_state_stack(cls, config: ContextConfig) -> bool:
        return config.state_stack.enabled

    @classmethod
    def should_inject_cross_conversation(cls, config: ContextConfig) -> bool:
        return config.cross_conversation.enabled

    @classmethod
    def should_inject_image(cls, config: ContextConfig) -> bool:
        return config.image_injection.enabled

    @classmethod
    def get_message_window_config(cls, config: ContextConfig) -> Dict[str, Any]:
        mw = config.message_window
        return {
            "max_messages": mw.max_messages,
            "max_tokens": mw.max_tokens,
            "min_unread_messages": mw.min_unread_messages,
            "max_unread_messages": mw.max_unread_messages,
        }

    @classmethod
    def get_memory_config(cls, config: ContextConfig) -> Dict[str, Any]:
        mem = config.memory
        return {
            "enabled": mem.enabled,
            "top_k": mem.top_k,
            "max_tokens": mem.max_tokens,
        }

    @classmethod
    def get_image_injection_config(cls, config: ContextConfig) -> Dict[str, Any]:
        img = config.image_injection
        return {
            "enabled": img.enabled,
            "max_size_kb": img.max_size_kb,
            "only_last_message": img.only_last_message,
        }

    @classmethod
    def get_cross_conversation_config(cls, config: ContextConfig) -> Dict[str, Any]:
        cc = config.cross_conversation
        return {
            "enabled": cc.enabled,
            "max_sessions": cc.max_sessions,
            "max_messages_per_session": cc.max_messages_per_session,
        }


context_config_parser = ContextConfigParser()