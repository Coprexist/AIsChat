"""
心跳管理器 — 周期性健康检查

确认 AI 「活着」：检查进程内存、LLM 额度、Skill 状态。
每个心跳周期打开独立 DB 会话，避免持有过期会话。

健康判定：
  - critical  — 额度耗尽 或 内存 ≥ 95%
  - warning   — 额度 < 20% 或 内存 ≥ 80%
  - healthy   — 其余
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict

from sqlalchemy import select

logger = logging.getLogger(__name__)


def _process_memory_usage() -> float:
    """当前进程 RSS 内存占比（0-100）。Linux 读 /proc/self/statm，失败返回 0。"""
    try:
        with open("/proc/self/statm") as f:
            total, resident = f.read().split()[:2]
        total_kb = int(total) * 4  # 页大小按 4KB 估算
        resident_kb = int(resident) * 4
        if total_kb <= 0:
            return 0.0
        return round(resident_kb / total_kb * 100, 1)
    except Exception:
        return 0.0


class HeartbeatManager:
    def __init__(self, interval: int = 60):
        self.heartbeat_interval = interval
        self.last_heartbeat: Dict[int, datetime] = {}
        self._health: Dict[int, dict] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    # ── 生命周期 ──

    async def start(self) -> None:
        """启动心跳循环（幂等）"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"✅ 心跳管理器已启动 (interval={self.heartbeat_interval}s)")

    def stop(self) -> None:
        """停止心跳循环"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    # ── 心跳循环 ──

    async def _heartbeat_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                await self._check_all_agents()
            except Exception as e:
                logger.warning(f"心跳检查失败: {e}")

    async def _check_all_agents(self) -> None:
        """检查所有活跃 AI 的健康状态，并清理已下线/删除 AI 的残留快照"""
        from app.database import async_session
        from app.models.agent import Agent

        async with async_session() as db:
            result = await db.execute(
                select(Agent.id).where(Agent.state.in_(("active", "dnd")))
            )
            agent_ids = [row[0] for row in result.all()]
            for agent_id in agent_ids:
                await self._heartbeat_check(db, agent_id)

        # 清理：不再活跃的 agent 快照从内存中移除（防残留）
        stale = set(self._health) - set(agent_ids)
        for agent_id in stale:
            self._health.pop(agent_id, None)

    # ── 单 AI 检查 ──

    async def heartbeat_check(self, agent_id: int) -> dict:
        """手动触发单个 AI 心跳检查（API 用）"""
        from app.database import async_session

        async with async_session() as db:
            return await self._heartbeat_check(db, agent_id)

    async def _heartbeat_check(self, db, agent_id: int) -> dict:
        """单个 AI 心跳检查，返回健康状态（状态变化才打日志，避免刷屏）"""
        health = await self._collect_health(db, agent_id)
        self.last_heartbeat[agent_id] = datetime.now()

        prev = self._health.get(agent_id)
        prev_status = prev.get("status") if prev else None
        new_status = health["status"]
        if new_status != prev_status:
            if new_status == "critical":
                logger.warning(f"❤️‍🩹 Agent({agent_id}) 心跳转异常: critical 额度={health['llm_quota_remaining']}% 内存={health['memory_usage']}%")
            elif new_status == "warning":
                logger.warning(f"⚠️ Agent({agent_id}) 心跳转警告: 额度={health['llm_quota_remaining']}% 内存={health['memory_usage']}%")
            elif prev_status == "critical" or prev_status == "warning":
                logger.info(f"✅ Agent({agent_id}) 心跳恢复: {new_status}")

        self._health[agent_id] = health
        return health

    async def _collect_health(self, db, agent_id: int) -> dict:
        """采集单个 AI 的健康数据"""
        from app.models.agent import Agent
        from app.models.agent_skill import AgentSkill

        agent = await db.get(Agent, agent_id)
        if agent is None:
            return {
                "agent_id": agent_id, "status": "offline",
                "memory_usage": 0.0, "llm_quota_remaining": 0.0,
                "active_skills": 0, "agent_state": "offline",
                "last_heartbeat": datetime.now().isoformat(),
            }

        # 内存（进程级，所有 AI 共享同一进程）
        memory_usage = _process_memory_usage()

        # LLM 额度（AI 主人的剩余额度）
        quota_remaining = 0.0
        monthly = 0.0
        try:
            from app.services.infrastructure.quota_service import get_user_credit_status
            quota = await get_user_credit_status(db, agent.owner_id)
            total = float(quota.get("total_effective", 0))
            monthly = float(quota.get("monthly_consumed", 0))
            # 剩余率 = 剩余额度 / (剩余额度 + 已消费)，无消费记录时视为 100%
            if total > 0:
                quota_remaining = 100.0 if monthly <= 0 else max(0.0, min(100.0, total / (total + monthly) * 100))
        except Exception as e:
            logger.warning(f"Agent({agent_id}) 额度查询失败: {e}")

        # Skill 状态
        try:
            skill_result = await db.execute(
                select(AgentSkill.id).where(
                    AgentSkill.agent_id == agent_id,
                    AgentSkill.is_enabled.is_(True),
                )
            )
            active_skills = len(skill_result.all())
        except Exception:
            active_skills = 0

        # 健康判定（内存优先；额度只降级不判死——用户可能用自有 Key）
        if memory_usage >= 95:
            status = "critical"
        elif memory_usage >= 80:
            status = "warning"
        elif quota_remaining <= 0 and monthly > 0:
            # 额度系统在用（有消费记录）但余额耗尽 → 提示充值，不判死
            status = "warning"
        else:
            status = "healthy"

        return {
            "agent_id": agent_id,
            "status": status,
            "memory_usage": memory_usage,
            "llm_quota_remaining": round(quota_remaining, 1),
            "active_skills": active_skills,
            "agent_state": agent.state,
            "last_heartbeat": datetime.now().isoformat(),
        }

    def get_health(self, agent_id: int) -> dict | None:
        """最近一次心跳结果（同步读取）"""
        return self._health.get(agent_id)

    def get_all_health(self) -> dict[int, dict]:
        """全部 AI 的最近心跳结果快照（同步读取）"""
        return dict(self._health)


heartbeat_manager = HeartbeatManager()
