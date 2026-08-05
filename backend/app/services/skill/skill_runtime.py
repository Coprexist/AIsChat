"""
Skill 运行时 — 自治 Skill 的执行引擎

事件流（设计文档：事件总线 → 通知制 → Skill 自治）：
  1. 消息入口 publish `message_received` 事件到 SkillEventBus
  2. dispatcher 找到订阅该事件类型的 Skill
  3. 对每个**启用该 Skill 的 AI**（agent_skill_relations，缺省 opt-in）：
     a. 注意力前置过滤（AgentAttention，命中 ignore 直接剔除）
     b. skill.should_act(event, state) → 决策
     c. 决策通过 → skill.act(event, decision, state) → 输出
  4. 输出处理：
     - memory_updates → 写入记忆系统
     - messages_to_send → 进冲突仲裁 → 发言

安全原则：技能默认 opt-in（无 relation 记录 = 不启用），
避免新 Skill 上线即对所有 AI 生效，符合渐进式迁移。
"""
import logging
from dataclasses import dataclass, field

from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class SkillRunResult:
    """一次 Skill 执行的结果汇总"""
    agent_id: int
    skill_name: str
    acted: bool = False
    decision: dict | None = None
    memory_updates: list = field(default_factory=list)
    speech_requests: list = field(default_factory=list)


class SkillRuntime:
    """技能运行时 — 单例，注册为 SkillEventBus 的 dispatcher"""

    async def init_dispatcher(self) -> None:
        """把自己注册为 SkillEventBus 的派发器，并把所有 Skill 的
        subscribed_events 声明同步到事件总线订阅表（幂等）"""
        from app.services.brain.skill_event_bus import skill_event_bus
        from app.skills.base import SkillRegistry

        for info in SkillRegistry.list_skills():
            for event_type in info.get("subscribed_events", []):
                skill_event_bus.subscribe(event_type, info["name"])

        skill_event_bus.set_dispatcher(self.handle_skill_event)
        logger.info(
            f"🔌 Skill 运行时就绪: {len(SkillRegistry.list_skills())} 个技能, "
            f"订阅事件: {list(skill_event_bus.subscribers.keys())}"
        )

    async def handle_skill_event(self, skill_name: str, event: dict) -> None:
        """SkillEventBus 派发入口：对每个启用该 Skill 的 AI 执行"""
        from app.database import async_session
        from app.skills.base import SkillRegistry

        skill_cls = SkillRegistry.get(skill_name)
        if skill_cls is None:
            logger.warning(f"未知技能: {skill_name}，跳过")
            return

        event_type = event.get("type")
        event_data = event.get("data") or {}

        # 该 AI 是否启用此技能（无记录 = 未启用，opt-in）
        enabled_agents = await self._get_enabled_agents(skill_name)

        for agent_id in enabled_agents:
            try:
                async with async_session() as db:
                    await self._run_for_agent(db, agent_id, skill_cls, event_type, event_data, event)
            except Exception as e:
                logger.exception(f"技能执行失败: {skill_name} agent={agent_id}: {e}")

    # ── 单 AI 执行 ──

    async def _run_for_agent(self, db, agent_id: int, skill_cls, event_type: str, data: dict, event: dict) -> SkillRunResult:
        from app.skills.base import ActDecision
        from app.services.skill.attention_system import attention_system

        # 注意力前置过滤
        if event_type == "message_received":
            action = await attention_system.check_attention(
                db, agent_id,
                group_id=data.get("group_id"),
                message_content=data.get("content", ""),
                sender_id=data.get("sender_id"),
            )
            if action == "ignore":
                return SkillRunResult(agent_id, skill_cls.name, acted=False)

        # 实例化 Skill，注入依赖（db / agent）
        from app.models.agent import Agent as AgentModel

        skill = skill_cls()
        agent = await db.get(AgentModel, agent_id)
        skill.deps = {"db": db, "agent": agent} if agent else {"db": db}

        # should_act：state 先给空（State Skill 注入留到声明式依赖阶段）
        decision = await skill.should_act(event, {})
        if not decision or not getattr(decision, "should_act", False):
            return SkillRunResult(agent_id, skill_cls.name, acted=False)

        # act
        output = await skill.act(event, decision, {})
        result = SkillRunResult(
            agent_id=agent_id,
            skill_name=skill_cls.name,
            acted=True,
            decision=decision.to_dict() if hasattr(decision, "to_dict") else None,
            memory_updates=list(getattr(output, "memory_updates", []) or []),
        )

        # 处理记忆输出
        for mem in result.memory_updates:
            await self._apply_memory(db, agent_id, mem, data)
        await db.commit()

        logger.info(f"🧩 Skill({skill_cls.name}) agent={agent_id} 执行: {decision.reason}")
        return result

    # ── 输出应用 ──

    async def _apply_memory(self, db, agent_id: int, mem: dict, event_data: dict) -> None:
        """把 skill 输出的记忆更新写入记忆系统"""
        from app.services.memory.memory_service import auto_store_memory

        title = mem.get("title") or str(mem.get("content", ""))[:30]
        content = mem.get("content", "")
        scope = mem.get("scope", "private")
        group_id = mem.get("group_id", event_data.get("group_id"))

        try:
            await auto_store_memory(
                db, agent_id, group_id, title, content, scope=scope,
            )
        except Exception as e:
            logger.warning(f"技能记忆写入失败 agent={agent_id}: {e}")

    # ── 工具 ──

    async def _get_enabled_agents(self, skill_name: str) -> list[int]:
        """查询启用该技能的 AI 列表（agent_skill_relations，is_enabled=true）"""
        from app.database import async_session
        from app.models.agent_skill_relation import AgentSkillRelation

        async with async_session() as db:
            result = await db.execute(
                select(AgentSkillRelation.agent_id).where(
                    AgentSkillRelation.skill_name == skill_name,
                    AgentSkillRelation.is_enabled.is_(True),
                )
            )
            return [row[0] for row in result.all()]


skill_runtime = SkillRuntime()
