"""
Skill 模块 — 自治技能系统

包含：
  - base.py: AutonomousSkill 基类 + 自动注册表
  - state_skills/: State Skill 实现
  - app_skills/: App Skill 实现

导入本包即触发子目录 Skill 的自动发现（__init_subclass__ 注册）。
"""
import importlib
import logging
import pathlib

logger = logging.getLogger(__name__)

# 先加载基类（注册表定义）
from app.skills.base import (  # noqa: F401
    AutonomousSkill, AppSkill, StateSkill, SkillRegistry, ActDecision, SkillOutput,
)


# 自动发现子目录中的 Skill 实现（state_skills/ app_skills/）
def _discover_skill_modules():
    base = pathlib.Path(__file__).parent
    for sub in ("state_skills", "app_skills"):
        sub_dir = base / sub
        if not sub_dir.is_dir():
            continue
        for pyfile in sorted(sub_dir.glob("*.py")):
            if pyfile.name.startswith("_"):
                continue
            mod_name = f"app.skills.{sub}.{pyfile.stem}"
            try:
                importlib.import_module(mod_name)
            except Exception as e:
                logger.warning(f"Skill 模块加载失败: {mod_name} - {e}")


_discover_skill_modules()