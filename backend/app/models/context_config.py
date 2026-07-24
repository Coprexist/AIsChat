from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class SegmentConfig:
    name: str
    enabled: bool = True
    weight: float = 1.0
    max_tokens: Optional[int] = None
    cacheable: bool = True


@dataclass
class MessageWindowConfig:
    max_messages: int = 50
    max_tokens: int = 5000
    min_unread_messages: int = 3
    max_unread_messages: int = 20


@dataclass
class MemoryConfig:
    enabled: bool = True
    top_k: int = 5
    max_tokens: int = 1000


@dataclass
class SkillInjectionConfig:
    enabled: bool = True


@dataclass
class WorkspaceConfig:
    enabled: bool = True


@dataclass
class StateStackConfig:
    enabled: bool = True


@dataclass
class CrossConversationConfig:
    enabled: bool = False
    max_sessions: int = 10
    max_messages_per_session: int = 1


@dataclass
class ImageInjectionConfig:
    enabled: bool = True
    max_size_kb: int = 4096
    only_last_message: bool = True


@dataclass
class ContextConfig:
    segment_order: List[str] = field(default_factory=lambda: [
        "core_identity",
        "protocol",
        "personality",
        "tools",
        "injected_skills",
    ])
    
    segments: Dict[str, SegmentConfig] = field(default_factory=lambda: {
        "core_identity": SegmentConfig(name="core_identity", enabled=True, weight=1.0, cacheable=True),
        "protocol": SegmentConfig(name="protocol", enabled=True, weight=1.0, cacheable=True),
        "personality": SegmentConfig(name="personality", enabled=True, weight=1.0, cacheable=False),
        "tools": SegmentConfig(name="tools", enabled=True, weight=1.0, cacheable=False),
        "injected_skills": SegmentConfig(name="injected_skills", enabled=True, weight=1.0, cacheable=False),
    })
    
    message_window: MessageWindowConfig = field(default_factory=MessageWindowConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    skill_injection: SkillInjectionConfig = field(default_factory=SkillInjectionConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    state_stack: StateStackConfig = field(default_factory=StateStackConfig)
    cross_conversation: CrossConversationConfig = field(default_factory=CrossConversationConfig)
    image_injection: ImageInjectionConfig = field(default_factory=ImageInjectionConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextConfig":
        config = cls()
        
        if "segment_order" in data:
            config.segment_order = data["segment_order"]
        
        if "segments" in data:
            for name, seg_data in data["segments"].items():
                if name in config.segments:
                    config.segments[name] = SegmentConfig(
                        name=name,
                        enabled=seg_data.get("enabled", True),
                        weight=seg_data.get("weight", 1.0),
                        max_tokens=seg_data.get("max_tokens"),
                        cacheable=seg_data.get("cacheable", True),
                    )
        
        if "message_window" in data:
            mw = data["message_window"]
            config.message_window = MessageWindowConfig(
                max_messages=mw.get("max_messages", 50),
                max_tokens=mw.get("max_tokens", 5000),
                min_unread_messages=mw.get("min_unread_messages", 3),
                max_unread_messages=mw.get("max_unread_messages", 20),
            )
        
        if "memory" in data:
            mem = data["memory"]
            config.memory = MemoryConfig(
                enabled=mem.get("enabled", True),
                top_k=mem.get("top_k", 5),
                max_tokens=mem.get("max_tokens", 1000),
            )
        
        if "skill_injection" in data:
            config.skill_injection = SkillInjectionConfig(
                enabled=data["skill_injection"].get("enabled", True),
            )
        
        if "workspace" in data:
            config.workspace = WorkspaceConfig(
                enabled=data["workspace"].get("enabled", True),
            )
        
        if "state_stack" in data:
            config.state_stack = StateStackConfig(
                enabled=data["state_stack"].get("enabled", True),
            )
        
        if "cross_conversation" in data:
            cc = data["cross_conversation"]
            config.cross_conversation = CrossConversationConfig(
                enabled=cc.get("enabled", False),
                max_sessions=cc.get("max_sessions", 10),
                max_messages_per_session=cc.get("max_messages_per_session", 1),
            )
        
        if "image_injection" in data:
            img = data["image_injection"]
            config.image_injection = ImageInjectionConfig(
                enabled=img.get("enabled", True),
                max_size_kb=img.get("max_size_kb", 4096),
                only_last_message=img.get("only_last_message", True),
            )
        
        return config

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_order": self.segment_order,
            "segments": {
                name: {
                    "enabled": seg.enabled,
                    "weight": seg.weight,
                    "max_tokens": seg.max_tokens,
                    "cacheable": seg.cacheable,
                }
                for name, seg in self.segments.items()
            },
            "message_window": {
                "max_messages": self.message_window.max_messages,
                "max_tokens": self.message_window.max_tokens,
                "min_unread_messages": self.message_window.min_unread_messages,
                "max_unread_messages": self.message_window.max_unread_messages,
            },
            "memory": {
                "enabled": self.memory.enabled,
                "top_k": self.memory.top_k,
                "max_tokens": self.memory.max_tokens,
            },
            "skill_injection": {"enabled": self.skill_injection.enabled},
            "workspace": {"enabled": self.workspace.enabled},
            "state_stack": {"enabled": self.state_stack.enabled},
            "cross_conversation": {
                "enabled": self.cross_conversation.enabled,
                "max_sessions": self.cross_conversation.max_sessions,
                "max_messages_per_session": self.cross_conversation.max_messages_per_session,
            },
            "image_injection": {
                "enabled": self.image_injection.enabled,
                "max_size_kb": self.image_injection.max_size_kb,
                "only_last_message": self.image_injection.only_last_message,
            },
        }