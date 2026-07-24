"""
薄大脑控制系统核心 — 只维持生命体征，不做具体决策

大脑只做 4 件事：
  1. 心跳 — 周期性健康检查
  2. 状态保持 — 维护全局状态机
  3. 冲突仲裁 — 多个 Skill 同时想说话时决定谁先说
  4. 人格锚点 — 核心身份和基本设定（只读）
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.brain.heartbeat_manager import heartbeat_manager
from app.services.brain.state_stack_manager import state_stack_manager
from app.services.brain.conflict_arbiter import conflict_arbiter
from app.services.brain.resource_manager import resource_manager
from app.services.brain.skill_event_bus import skill_event_bus

logger = logging.getLogger(__name__)


class BrainController:
    def __init__(self):
        self.heartbeat_manager = heartbeat_manager
        self.state_stack_manager = state_stack_manager
        self.conflict_arbiter = conflict_arbiter
        self.resource_manager = resource_manager
        self.event_bus = skill_event_bus

    async def initialize(self, db: AsyncSession):
        """初始化薄大脑"""
        await self.heartbeat_manager.start()
        logger.info("✅ 薄大脑控制系统初始化完成")

    async def process_event(self, db: AsyncSession, event: dict):
        """处理事件 — 分发到事件总线"""
        await self.event_bus.publish(event)

    async def arbitrate_speech(self, db: AsyncSession, speech_requests: list):
        """冲突仲裁 — 多个 Skill 同时想说话时决定谁先说"""
        return await self.conflict_arbiter.arbitrate(db, speech_requests)

    async def check_resource_availability(self, skill_name: str, priority: int, resource_type: str, **kwargs):
        """检查资源可用性"""
        return await self.resource_manager.request_resource(skill_name, priority, resource_type, **kwargs)

    async def get_personality_anchor(self, db: AsyncSession, agent_id: int):
        """获取人格锚点（只读）"""
        from app.models.personality_anchor import PersonalityAnchor
        result = await db.execute(PersonalityAnchor.__table__.select().where(PersonalityAnchor.agent_id == agent_id))
        anchor = result.first()
        if anchor:
            return {
                "agent_id": anchor.agent_id,
                "name": anchor.name,
                "identity": anchor.identity,
                "personality": anchor.personality,
                "core_values": anchor.core_values,
            }
        return None


brain_controller = BrainController()