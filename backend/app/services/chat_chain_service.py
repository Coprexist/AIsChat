"""
聊天链尺时间判定模块

v1: 有序列表 + bisect 实现，接口设计保持可替换性，后续可无痛升级为红黑树。
"""
import bisect
import logging
from time import time as now

logger = logging.getLogger(__name__)


class ChatChainManager:
    """
    管理 AI 在每个群聊中的聊天链状态。

    设计原则：
    - 接口与实现分离：外部只调用 should_wake/mark_replied 等公开方法
    - 内部 v1 用有序列表，v2 可切换为红黑树，外部无需改动
    - 纯内存存储，实例重启后清空
    """

    def __init__(self):
        # {group_id: {agent_id: {"ruler_time": int(seconds), "last_reply_at": float(timestamp)}}}
        self._agents: dict[int, dict[int, dict]] = {}

    # ── 公开接口 ──

    def register_ai(self, agent_id: int, group_id: int, ruler_time: int = 120) -> None:
        """注册 AI 到群聊的聊天链判定模块。ruler_time 单位秒，默认 120。"""
        if group_id not in self._agents:
            self._agents[group_id] = {}
        self._agents[group_id][agent_id] = {
            "ruler_time": max(10, ruler_time),  # 最小 10 秒
            "last_reply_at": 0.0,
        }
        logger.debug(f"📏 AI {agent_id} 注册到群 {group_id}，尺时间={ruler_time}s")

    def update_ruler_time(self, agent_id: int, group_id: int, new_ruler_time: int) -> bool:
        """AI 修改自己在某群的尺时间。返回是否成功。"""
        group = self._get_group(group_id)
        if group is None or agent_id not in group:
            return False
        old = group[agent_id]["ruler_time"]
        group[agent_id]["ruler_time"] = max(10, new_ruler_time)
        logger.info(f"📏 AI {agent_id} 群 {group_id} 尺时间: {old}s → {new_ruler_time}s")
        return True

    def should_wake(self, agent_id: int, group_id: int, msg_time: float | None = None) -> bool:
        """
        判定 AI 是否应该被当前消息唤醒。

        规则：距 AI 上次回复的时间 ≥ 尺时间 → 新链 → 唤醒；否则 → 同链 → 静默。

        msg_time 为消息时间戳（秒），None 则用当前时间。
        """
        if msg_time is None:
            msg_time = now()

        group = self._get_group(group_id)
        if group is None or agent_id not in group:
            # 未注册 → 首次 → 唤醒（给注册延迟的容忍）
            return True

        cfg = group[agent_id]
        gap = msg_time - cfg["last_reply_at"]
        ruler = cfg["ruler_time"]
        should = gap >= ruler

        logger.debug(
            f"📏 AI {agent_id} 群 {group_id}: gap={gap:.1f}s, ruler={ruler}s → {'唤醒' if should else '静默'}"
        )
        return should

    def mark_replied(self, agent_id: int, group_id: int) -> None:
        """记录 AI 在群聊中的回复时间，标记退出当前链。"""
        group = self._get_group(group_id)
        if group is None:
            return
        if agent_id not in group:
            self.register_ai(agent_id, group_id)
        self._agents[group_id][agent_id]["last_reply_at"] = now()
        logger.debug(f"📏 AI {agent_id} 群 {group_id} 标记已回复，退出当前链")

    def remove_ai(self, agent_id: int, group_id: int) -> None:
        """AI 退出群聊或离线时清理状态。"""
        group = self._get_group(group_id)
        if group and agent_id in group:
            del group[agent_id]
            logger.debug(f"📏 AI {agent_id} 从群 {group_id} 聊天链移除")

    def get_ruler_time(self, agent_id: int, group_id: int) -> int:
        """查询 AI 在某群的尺时间。未注册返回默认 120。"""
        group = self._get_group(group_id)
        if group and agent_id in group:
            return group[agent_id]["ruler_time"]
        return 120

    def get_group_agents(self, group_id: int) -> list[int]:
        """获取群内所有已注册的 AI ID 列表（按尺时间升序）。"""
        group = self._get_group(group_id)
        if not group:
            return []
        return sorted(group.keys(), key=lambda aid: group[aid]["ruler_time"])

    # ── 内部辅助 ──

    def _get_group(self, group_id: int) -> dict | None:
        return self._agents.get(group_id)


# 全局单例
chat_chain_manager = ChatChainManager()
