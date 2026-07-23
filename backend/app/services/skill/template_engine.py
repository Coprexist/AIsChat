"""
模板引擎 — 零代码创建 Skill

支持三种开发方式：
  1. 模板用户（80%）：选模板、填空、保存
  2. 向导用户（15%）：可视化拖拽配置
  3. 代码开发者（5%）：手写 App Skill 代码
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class TemplateEngine:
    TEMPLATE_TYPES = {
        "trigger_action": {
            "name": "触发-动作型",
            "description": "当 X 发生时做 Y",
            "fields": [
                {"name": "trigger_condition", "type": "select", "options": ["keyword", "friend_online", "daily_time", "mention"]},
                {"name": "trigger_value", "type": "string", "description": "关键词/好友ID/时间"},
                {"name": "action_type", "type": "select", "options": ["reply_message", "store_memory", "set_alarm", "mention_user"]},
                {"name": "action_value", "type": "string", "description": "回复内容/记忆内容/闹钟时间/用户ID"},
                {"name": "max_times_per_day", "type": "int", "default": -1, "description": "-1=无限制"},
            ],
        },
        "role_template": {
            "name": "角色设定型",
            "description": "定制一个角色 Skill",
            "fields": [
                {"name": "role_name", "type": "string"},
                {"name": "role_description", "type": "textarea"},
                {"name": "speaking_style", "type": "select", "options": ["formal", "casual", "humorous", "professional"]},
                {"name": "trigger_method", "type": "select", "options": ["mention", "always", "keyword"]},
            ],
        },
        "workflow_template": {
            "name": "工作流型",
            "description": "多步骤任务流",
            "fields": [
                {"name": "steps", "type": "list", "description": "步骤列表"},
            ],
        },
    }

    def generate_skill_code(self, template_type: str, config: Dict) -> str:
        """从模板生成 Skill 代码"""
        template = self.TEMPLATE_TYPES.get(template_type)
        if not template:
            raise ValueError(f"未知模板类型: {template_type}")

        if template_type == "trigger_action":
            return self._generate_trigger_action_skill(config)
        elif template_type == "role_template":
            return self._generate_role_skill(config)
        elif template_type == "workflow_template":
            return self._generate_workflow_skill(config)
        return ""

    def _generate_trigger_action_skill(self, config: Dict) -> str:
        """生成触发-动作型 Skill 代码"""
        code = f"""from app.skills.base import AppSkill

class GeneratedTriggerActionSkill(AppSkill):
    name = "{config.get('skill_name', 'generated_trigger_action')}"
    description = "{config.get('description', '触发-动作 Skill')}"
    segment = "custom"
    
    subscribed_events = ["message_received"]
    
    required_state = {{}}
    
    async def should_act(self, event, state):
        return {{
            "should_act": True,
            "priority": 50,
            "action_type": "speak",
            "reason": "触发条件匹配",
        }}
    
    async def act(self, event, decision, state):
        return {{
            "messages_to_send": [],
            "state_changes": {{}},
            "memory_updates": [],
            "internal_log": "执行完成",
        }}
"""
        return code

    def _generate_role_skill(self, config: Dict) -> str:
        """生成角色型 Skill 代码"""
        return ""

    def _generate_workflow_skill(self, config: Dict) -> str:
        """生成工作流型 Skill 代码"""
        return ""


template_engine = TemplateEngine()