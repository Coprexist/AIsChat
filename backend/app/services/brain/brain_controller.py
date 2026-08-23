"""
薄大脑控制系统核心 — 只维持生命体征，不做具体决策

大脑只做 4 件事：
  1. 心跳 — 周期性健康检查（heartbeat_manager）
  2. 状态保持 — 维护全局状态机（state_stack_manager + agents.state）
  3. 冲突仲裁 — 多个 Skill 同时想说话时决定谁先说（conflict_arbiter）
  4. 人格锚点 — 核心身份和基本设定，只读不可被 Skill 修改

其余一切决策（消息分类、意愿评分、工具选择、记忆管理…）下放给各 Skill。
"""
import logging
from sqlalchemy import select

from app.repositories.agent_repo import AgentRepository
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
        self._initialized = False

    async def initialize(self) -> None:
        """初始化薄大脑：启动心跳循环（幂等）"""
        if self._initialized:
            return
        await self.heartbeat_manager.start()
        self._initialized = True
        logger.info("✅ 薄大脑控制系统初始化完成")

    async def shutdown(self) -> None:
        """停止薄大脑"""
        self.heartbeat_manager.stop()
        self._initialized = False

    # ── 事件 ──

    async def process_event(self, event: dict) -> None:
        """处理事件 — 分发到 Skill 事件总线（通知制，不做决策）"""
        await self.event_bus.publish(event)

    # ── 冲突仲裁 ──

    async def arbitrate_speech(self, speech_requests: list) -> list:
        """冲突仲裁 — 多个 Skill 同时想说话时决定谁先说"""
        return await self.conflict_arbiter.arbitrate(speech_requests)

    # ── 资源调度 ──

    async def check_resource_availability(self, skill_name: str, priority: int, resource_type: str, **kwargs) -> bool:
        """检查资源可用性"""
        return await self.resource_manager.request_resource(skill_name, priority, resource_type, **kwargs)

    # ── 人格锚点（只读） ──

    async def get_personality_anchor(self, repo: AgentRepository, agent_id: int) -> dict | None:
        """获取人格锚点（只读，任何 Skill 都不可修改）"""
        from app.models.personality_anchor import PersonalityAnchor

        result = await repo.execute(
            select(PersonalityAnchor).where(PersonalityAnchor.agent_id == agent_id)
        )
        anchor = result.scalar_one_or_none()
        if anchor is None:
            return None
        return {
            "agent_id": anchor.agent_id,
            "name": anchor.name,
            "identity": anchor.identity,
            "personality": anchor.personality,
            "core_values": _parse_core_values(anchor.core_values),
            "consistency_coefficient": float(anchor.consistency_coefficient or 0.7),
            "updated_at": anchor.updated_at.isoformat() if anchor.updated_at else None,
        }

    async def upsert_personality_anchor(
        self,
        repo: AgentRepository,
        agent_id: int,
        name: str,
        identity: str,
        personality: str,
        core_values: list[str] | None = None,
        consistency_coefficient: float = 0.7,
    ) -> dict:
        """创建或更新人格锚点（仅管理员/主人可调用，AI 自身不可改）"""
        from app.models.personality_anchor import PersonalityAnchor

        result = await repo.execute(
            select(PersonalityAnchor).where(PersonalityAnchor.agent_id == agent_id)
        )
        anchor = result.scalar_one_or_none()

        # 一致性系数收敛到设计文档的三档语义（0.3/0.7/1.0），越界值取最近档
        consistency_coefficient = _normalize_coefficient(consistency_coefficient)

        if anchor is None:
            anchor = PersonalityAnchor(
                agent_id=agent_id,
                name=name,
                identity=identity,
                personality=personality,
                core_values="\n".join(core_values or []),
                consistency_coefficient=consistency_coefficient,
            )
            repo.add(anchor)
        else:
            anchor.name = name
            anchor.identity = identity
            anchor.personality = personality
            anchor.core_values = "\n".join(core_values or [])
            anchor.consistency_coefficient = consistency_coefficient

        repo.flush()
        return await self.get_personality_anchor(repo, agent_id)


def _parse_core_values(raw: str | None) -> list[str]:
    """core_values 存储为换行分隔文本 → 列表"""
    if not raw:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _normalize_coefficient(value: float) -> float:
    """一致性系数归一化到 {0.3, 0.7, 1.0} 三档"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.7
    if v >= 0.9:
        return 1.0
    if v <= 0.4:
        return 0.3
    return 0.7


brain_controller = BrainController()
