"""
Skill 基类 — 定义自治 Skill 的接口契约

三层设计：
  1. AutonomousSkill: 基础自治 Skill
  2. AppSkill: 应用类 Skill，无状态、纯逻辑、声明式依赖
  3. StateSkill: 状态管理类 Skill，状态的唯一真实来源
"""
from typing import Dict, List, Optional


class ActDecision:
    def __init__(self, should_act: bool, priority: int = 50, action_type: str = "speak", reason: str = ""):
        self.should_act = should_act
        self.priority = priority
        self.action_type = action_type
        self.reason = reason

    def to_dict(self) -> Dict:
        return {
            "should_act": self.should_act,
            "priority": self.priority,
            "action_type": self.action_type,
            "reason": self.reason,
        }


class SkillOutput:
    def __init__(self, messages_to_send: List = None, state_changes: Dict = None, memory_updates: List = None, internal_log: str = ""):
        self.messages_to_send = messages_to_send or []
        self.state_changes = state_changes or {}
        self.memory_updates = memory_updates or []
        self.internal_log = internal_log

    def to_dict(self) -> Dict:
        return {
            "messages_to_send": self.messages_to_send,
            "state_changes": self.state_changes,
            "memory_updates": self.memory_updates,
            "internal_log": self.internal_log,
        }


class AutonomousSkill:
    name: str = ""
    description: str = ""
    segment: str = ""
    
    subscribed_events: List[str] = []
    
    resource_budget: Dict = {
        "llm_tokens_per_day": 0,
        "messages_per_day": 0,
    }

    async def should_act(self, event: Dict, state: Dict) -> ActDecision:
        """
        返回决策：
        - should_act: bool
        - priority: int 0-100
        - action_type: "speak" | "remember" | "silent" | "internal"
        - reason: str
        """
        return ActDecision(should_act=False)

    async def act(self, event: Dict, decision: ActDecision, state: Dict) -> SkillOutput:
        """
        执行动作，返回输出：
        - messages_to_send: list[Message]
        - state_changes: dict
        - memory_updates: list[Memory]
        - internal_log: str
        """
        return SkillOutput()

    async def load_state(self) -> Dict:
        """加载状态"""
        return {}

    async def save_state(self, state: Dict) -> None:
        """保存状态"""
        pass


class AppSkill(AutonomousSkill):
    required_state: Dict = {}
    
    async def should_act(self, event: Dict, state: Dict) -> ActDecision:
        return ActDecision(should_act=False)


class StateSkill(AutonomousSkill):
    async def get_state(self, query: Dict) -> Dict:
        """获取状态"""
        return {}

    async def update_state(self, updates: Dict) -> Dict:
        """更新状态"""
        return {}

    async def publish_state_change(self, change: Dict) -> None:
        """发布状态变更"""
        pass