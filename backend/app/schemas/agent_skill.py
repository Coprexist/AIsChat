"""
思维 Skill Schema
"""
from pydantic import BaseModel, Field


class SkillConfig(BaseModel):
    """技能配置（各 skill_type 不同 schema，用 dict 承载）"""
    # delay_reply: {"delay_seconds": int, "max_delay_seconds": int | None}
    # typing_indicator: {"pattern": "always" | "keyword_match", "duration_ms": int}
    # scene_trigger: {"match_type": "keyword" | "regex", "keywords": list[str] | None, "pattern_regex": str | None, "inject_text": str}
    # inject_prompt: {"insert_text": str, "duration_seconds": int | None, "one_shot": bool}


class SkillCreate(BaseModel):
    """创建技能"""
    name: str = Field(..., min_length=1, max_length=100, description="技能名称")
    skill_type: str = Field(..., description="技能类型，如 delay_reply / inject_prompt（由 SkillRegistry 管理）")
    config: dict = Field(default_factory=dict, description="技能配置JSON")
    is_enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=0, description="优先级")


class SkillUpdate(BaseModel):
    """更新技能（全部可选）"""
    name: str | None = Field(default=None, max_length=100)
    config: dict | None = Field(default=None)
    is_enabled: bool | None = Field(default=None)
    priority: int | None = Field(default=None)


class SkillResponse(BaseModel):
    """技能响应"""
    id: int
    agent_id: int
    name: str
    skill_type: str
    is_enabled: bool
    config: dict
    priority: int
    created_at: str | None = None
    updated_at: str | None = None
