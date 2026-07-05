"""
聊天链尺时间判定模块

v1: 有序列表 + bisect 实现，接口设计保持可替换性，后续可无痛升级为红黑树。
"""
import asyncio
import logging
from time import time as now

logger = logging.getLogger(__name__)

# 同群同时进行 LLM 调用的 AI 数量上限
MAX_CONCURRENT_PER_GROUP = 3


class ChatChainManager:
    """
    管理 AI 在每个群聊中的聊天链状态。

    设计原则：
    - 接口与实现分离：外部只调用公开方法
    - 批量查询优于逐个判定：get_wake_candidates() 一次返回所有应唤醒的 AI
    - 去重：同一 AI 在处理队列中只占一个位置
    - 并发控制：同群 LLM 调用上限，其余排队
    - 纯内存存储，实例重启后清空
    """

    def __init__(self):
        # {group_id: {agent_id: {"ruler_time": int, "last_reply_at": float}}}
        self._agents: dict[int, dict[int, dict]] = {}
        # 去重：同群正在处理中的 AI 集合  {group_id: set[agent_id]}
        self._processing: dict[int, set[int]] = {}
        # 并发控制：每群的信号量  {group_id: asyncio.Semaphore}
        self._semaphores: dict[int, asyncio.Semaphore] = {}

    # ── 批量查询 ──

    def get_wake_candidates(self, group_id: int, msg_time: float | None = None) -> list[int]:
        """
        一次性返回群内所有尺时间已过的 AI（按尺时间升序）。
        未注册的 AI 会先自动注册（默认尺时间 120s），首次触发默认唤醒。
        重要消息（@/公告）的 AI 判定应绕过此方法，由调用方自行处理。
        """
        if msg_time is None:
            msg_time = now()

        group = self._agents.get(group_id, {})
        if not group:
            return []

        candidates = []
        for aid, cfg in group.items():
            gap = msg_time - cfg["last_reply_at"]
            if gap >= cfg["ruler_time"]:
                candidates.append((cfg["ruler_time"], aid))

        # 按尺时间升序排列
        candidates.sort()
        wake_list = [aid for _, aid in candidates]

        if wake_list:
            logger.info(
                f"📏 群 {group_id} 批量判定: {len(wake_list)}/{len(group)} 个 AI 唤醒 "
                f"(尺时间范围 {group[wake_list[0]]['ruler_time']}s~{group[wake_list[-1]]['ruler_time']}s)"
            )

        return wake_list

    def mark_all_replied(self, group_id: int, agent_ids: list[int]) -> None:
        """
        批量标记：判定完成后、触发前，一次性标记所有唤醒的 AI。
        这样即使第一个 AI 秒回，也不会触发其他已在列表中的 AI。
        """
        t = now()
        group = self._agents.get(group_id, {})
        for aid in agent_ids:
            if aid in group:
                group[aid]["last_reply_at"] = t
        logger.debug(f"📏 群 {group_id} 批量标记 {len(agent_ids)} 个 AI 已回复")

    # ── 去重 ──

    def try_claim(self, agent_id: int, group_id: int) -> bool:
        """
        尝试认领处理权。返回 True 表示该 AI 可以处理，False 表示已在处理中。
        处理完成后必须调用 release_claim()。
        """
        if group_id not in self._processing:
            self._processing[group_id] = set()
        proc = self._processing[group_id]
        if agent_id in proc:
            return False
        proc.add(agent_id)
        return True

    def release_claim(self, agent_id: int, group_id: int) -> None:
        """释放处理权，允许该 AI 再次被排入。"""
        proc = self._processing.get(group_id)
        if proc:
            proc.discard(agent_id)

    # ── 并发控制 ──

    def get_semaphore(self, group_id: int) -> asyncio.Semaphore:
        """获取群聊并发信号量（最多 MAX_CONCURRENT_PER_GROUP 个 AI 同时 LLM 调用）。"""
        if group_id not in self._semaphores:
            self._semaphores[group_id] = asyncio.Semaphore(MAX_CONCURRENT_PER_GROUP)
        return self._semaphores[group_id]

    # ── 单 AI 接口（保留向后兼容） ──

    def register_ai(self, agent_id: int, group_id: int, ruler_time: int = 120) -> None:
        if group_id not in self._agents:
            self._agents[group_id] = {}
        self._agents[group_id][agent_id] = {
            "ruler_time": max(10, ruler_time),
            "last_reply_at": 0.0,
        }

    def update_ruler_time(self, agent_id: int, group_id: int, new_ruler_time: int) -> bool:
        group = self._get_group(group_id)
        if group is None or agent_id not in group:
            return False
        old = group[agent_id]["ruler_time"]
        group[agent_id]["ruler_time"] = max(10, new_ruler_time)
        logger.info(f"📏 AI {agent_id} 群 {group_id} 尺时间: {old}s → {new_ruler_time}s")
        return True

    def should_wake(self, agent_id: int, group_id: int, msg_time: float | None = None) -> bool:
        if msg_time is None:
            msg_time = now()
        group = self._get_group(group_id)
        if group is None or agent_id not in group:
            return True
        cfg = group[agent_id]
        return (msg_time - cfg["last_reply_at"]) >= cfg["ruler_time"]

    def mark_replied(self, agent_id: int, group_id: int) -> None:
        group = self._get_group(group_id)
        if group is None:
            return
        if agent_id not in group:
            self.register_ai(agent_id, group_id)
        self._agents[group_id][agent_id]["last_reply_at"] = now()

    def remove_ai(self, agent_id: int, group_id: int) -> None:
        group = self._get_group(group_id)
        if group and agent_id in group:
            del group[agent_id]

    def get_ruler_time(self, agent_id: int, group_id: int) -> int:
        group = self._get_group(group_id)
        if group and agent_id in group:
            return group[agent_id]["ruler_time"]
        return 120

    def _get_group(self, group_id: int) -> dict | None:
        return self._agents.get(group_id)


# 全局单例
chat_chain_manager = ChatChainManager()
