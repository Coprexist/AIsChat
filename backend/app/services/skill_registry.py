"""
技能注册表（兼容层）

已委托给 skill_service.py，此处仅做兼容导出。
"""

from app.services.skill_service import (
    list_agent_skills,
    enable_skill_for_agent,
    disable_skill_for_agent,
)


class SkillRegistry:
    def __init__(self):
        self.skills = {}

    def register(self, skill_class) -> None:
        if hasattr(skill_class, 'name') and skill_class.name:
            self.skills[skill_class.name] = skill_class

    def get_skill(self, name: str):
        return self.skills.get(name)

    def list_skills(self) -> list[str]:
        return list(self.skills.keys())

    def list_skills_by_segment(self, segment: str) -> list[str]:
        result = []
        for name, skill_class in self.skills.items():
            if getattr(skill_class, 'segment', '') == segment:
                result.append(name)
        return result

    async def enable_skill(self, db, agent_id: int, skill_name: str) -> None:
        await enable_skill_for_agent(db, agent_id, skill_name)

    async def disable_skill(self, db, agent_id: int, skill_name: str) -> None:
        await disable_skill_for_agent(db, agent_id, skill_name)

    async def get_enabled_skills(self, db, agent_id: int) -> list[str]:
        skills = await list_agent_skills(db, agent_id)
        return [s['name'] for s in skills if s.get('enabled', True)]


skill_registry = SkillRegistry()