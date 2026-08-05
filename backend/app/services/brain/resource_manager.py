"""
资源管理器 — AI 的资源配额和调度

大脑职责之一：防止 Skill 竞争资源时把系统拖垮。
实现：
  - LLM    ：额度检查（主人剩余额度）+ 全局并发信号量
  - DB     ：全局并发信号量（防止突发连接打满连接池）
  - memory ：日预算计数器（读写次数，内存态，重启清零）

额度记账不在此处重复实现，deduct_credit 委托给已有的
quota_service.deduct_credit（单一记账来源，避免双重扣费）。
"""
import asyncio
import logging
from datetime import date
from typing import Dict

logger = logging.getLogger(__name__)


class ResourceManager:
    def __init__(self) -> None:
        # 全局并发计数（LLM / DB）—— 计数式，配合 acquire/release 成对使用
        self.llm_concurrency_limit = 8
        self.db_concurrency_limit = 16
        self._llm_inflight = 0
        self._db_inflight = 0
        self._lock = asyncio.Lock()
        # 记忆日预算：{date: {agent_id: {"reads": n, "writes": n}}}
        self._memory_budget: Dict[date, Dict[int, Dict[str, int]]] = {}
        self.memory_reads_per_day = 500
        self.memory_writes_per_day = 200

    # ── 统一入口 ──

    async def request_resource(self, skill_name: str, priority: int, resource_type: str, **kwargs) -> bool:
        """
        请求资源：
        - llm    : 额度检查 + 并发槽位（kwargs: agent_id, tokens）
        - db     : 并发信号量
        - memory : 日读写预算（kwargs: agent_id, mode=read|write）
        """
        try:
            if resource_type == "llm":
                return await self._request_llm(skill_name, priority, **kwargs)
            elif resource_type == "db":
                return await self._request_db(skill_name, priority)
            elif resource_type == "memory":
                return await self._request_memory(skill_name, priority, **kwargs)
            return True
        except Exception as e:
            logger.warning(f"资源请求异常（放行）: {resource_type} {e}")
            return True

    # ── 具体资源 ──

    async def _request_llm(self, skill_name: str, priority: int, agent_id: int | None = None, tokens: int = 0, **_) -> bool:
        """LLM 资源：额度检查 + 并发槽位（占用后需成对调用 release_llm）"""
        if agent_id is not None:
            ok = await self._check_llm_quota(agent_id, tokens)
            if not ok:
                return False
        async with self._lock:
            if self._llm_inflight >= self.llm_concurrency_limit:
                return False
            self._llm_inflight += 1
        return True

    async def release_llm(self) -> None:
        """释放一个 LLM 并发槽位（调用方使用完后必须调用）"""
        async with self._lock:
            if self._llm_inflight > 0:
                self._llm_inflight -= 1

    async def acquire_db(self) -> bool:
        """占用一个 DB 并发槽位（返回 True 后需成对调用 release_db）"""
        async with self._lock:
            if self._db_inflight >= self.db_concurrency_limit:
                return False
            self._db_inflight += 1
        return True

    async def release_db(self) -> None:
        """释放一个 DB 并发槽位"""
        async with self._lock:
            if self._db_inflight > 0:
                self._db_inflight -= 1

    async def _check_llm_quota(self, agent_id: int, tokens: int) -> bool:
        """额度检查：AI 主人剩余额度是否足够"""
        from app.database import async_session
        from app.models.agent import Agent
        from app.services.infrastructure.credit_service import credit_service

        async with async_session() as db:
            agent = await db.get(Agent, agent_id)
            if agent is None:
                return True  # 未知 agent 不拦截
            try:
                return await credit_service.has_enough_credit(db, agent.owner_id, tokens)
            except Exception as e:
                logger.warning(f"Agent({agent_id}) 额度检查失败（放行）: {e}")
                return True

    async def _request_db(self, skill_name: str, priority: int) -> bool:
        """DB 资源：并发槽位（仅检查，不占用；需要占用的调用方请用 acquire_db）"""
        async with self._lock:
            return self._db_inflight < self.db_concurrency_limit

    async def _request_memory(self, skill_name: str, priority: int, agent_id: int | None = None, mode: str = "read") -> bool:
        """记忆资源：日预算计数"""
        if agent_id is None:
            return True
        today = date.today()
        bucket = self._memory_budget.setdefault(today, {}).setdefault(agent_id, {"reads": 0, "writes": 0})
        limit = self.memory_writes_per_day if mode == "write" else self.memory_reads_per_day
        if bucket[mode] >= limit:
            return False
        bucket[mode] += 1
        return True

    # ── 记账（委托，不重复实现） ──

    async def deduct_credit(self, db, user_id: int, agent_id: int, tokens_used: int, model: str) -> None:
        """扣除额度 — 委托给 quota_service（单一记账来源）"""
        from app.services.infrastructure.quota_service import deduct_credit as quota_deduct

        await quota_deduct(
            db,
            user_id=user_id,
            tokens_used=tokens_used,
            agent_id=agent_id,
            model=model,
        )


resource_manager = ResourceManager()
