"""
世界 AI 对话轮次管理器 — 服务器端全程执行，不依赖客户端连接

- 每个世界一个 worker：消息排队（DM 同款），逐条处理
- 每轮（turn）一个广播：多个订阅者（直播 SSE）可随时加入/离开
- 客户端断开/刷新不影响轮次执行；重连=重新订阅直播，历史补缺口

POST /worlds/{id}/chat          → enqueue，返回 turn_id
GET  /worlds/{id}/chat/stream   → 订阅指定 turn 的实时事件
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session

logger = logging.getLogger(__name__)


async def recover_orphaned_turn(world_id: int) -> None:
    """重载/崩溃后回收：若世界最后一条消息不是 ai 回复（轮次未闭合），强制收尾。

    - 写闭环消息（说明中断原因，提示说「继续」）
    - 把已执行的工具摘要存进 workflow_memory（下次对话继续，不重做）
    - 幂等：已闭合（最后一条是 ai）则不动
    """
    try:
        from app.models.world import World, WorldChatMessage
        async with async_session() as db:
            rows = (await db.execute(
                select(WorldChatMessage)
                .where(WorldChatMessage.world_id == world_id)
                .order_by(WorldChatMessage.id.desc())
                .limit(30)
            )).scalars().all()
            if not rows:
                return
            rows = list(reversed(rows))
            if rows[-1].role == "ai":
                return  # 已闭合
            # 该轮已执行的工具摘要（role=tool 的消息）
            tools_done = [m.content for m in rows if m.role == "tool"][-10:]
            db.add(WorldChatMessage(
                world_id=world_id, user_id=None, role="ai",
                content="（对话中断：服务重启或连接中断，已记录工作流——说「继续」即可接着做）",
            ))
            world = await db.get(World, world_id)
            if world is not None:
                cfg = dict(world.config or {})
                cfg["workflow_memory"] = {
                    "interrupted_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                    "tools_done": tools_done,
                }
                world.config = cfg
            await db.commit()
            logger.info(f"🌐 世界 #{world_id} 回收未闭合轮次（已强制收尾 + 存工作流记忆）")
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 轮次回收失败: {e}")


class TurnBroadcast:
    """单轮对话的事件广播（发布/订阅，多订阅者可加入/离开）"""

    def __init__(self, turn_id: str):
        self.turn_id = turn_id
        self.subscribers: set[asyncio.Queue] = set()
        self.ended = False

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    async def broadcast(self, event: str) -> None:
        if self.ended:
            return
        for q in list(self.subscribers):
            q.put_nowait(event)

    def end(self) -> None:
        """轮次结束：通知所有订阅者"""
        self.ended = True
        for q in list(self.subscribers):
            q.put_nowait("data: [DONE]\n\n")


class WorldTurnWorker:
    """单个世界的对话 worker：消息排队 → 逐条执行（独立 DB 会话）"""

    def __init__(self, world_id: int):
        self.world_id = world_id
        self.msg_queue: asyncio.Queue = asyncio.Queue()
        self.turns: dict[str, TurnBroadcast] = {}
        self.task = asyncio.create_task(self._run(), name=f"world-turn-{world_id}")

    async def _run(self) -> None:
        while True:
            item = await self.msg_queue.get()
            tb = self.turns.get(item["turn_id"])
            try:
                from app.services.world.world_chat_service import stream_world_chat
                async with async_session() as db:
                    async for event in stream_world_chat(
                        db, self.world_id, item["user_id"], item["message"], item["turn_id"]
                    ):
                        if tb:
                            await tb.broadcast(event)
            except Exception as e:
                logger.warning(f"🌐 世界 #{self.world_id} 轮次执行异常: {e}")
                if tb:
                    await tb.broadcast(f"data: [ERROR]{str(e)[:150]}\n\n")
            finally:
                if tb:
                    tb.end()
                    self.turns.pop(item["turn_id"], None)

    def enqueue(self, user_id: int, message: str | list[str]) -> str:
        """消息入队（支持批量：排队消息一起发给 AI），返回 turn_id（订阅直播用）"""
        turn_id = uuid.uuid4().hex[:12]
        self.turns[turn_id] = TurnBroadcast(turn_id)
        self.msg_queue.put_nowait({
            "turn_id": turn_id, "user_id": user_id,
            "message": message if isinstance(message, list) else [message],
        })
        return turn_id

    @property
    def queue_size(self) -> int:
        return self.msg_queue.qsize()

    def subscribe(self, turn_id: str) -> TurnBroadcast | None:
        return self.turns.get(turn_id)


_workers: dict[int, WorldTurnWorker] = {}


def get_world_worker(world_id: int) -> WorldTurnWorker:
    w = _workers.get(world_id)
    if w is None or w.task.done():
        w = WorldTurnWorker(world_id)
        _workers[world_id] = w
        # 重载/崩溃后新 worker：异步回收该世界未闭合的轮次（强制收尾 + 工作流记忆）
        asyncio.create_task(recover_orphaned_turn(world_id))
    return w


async def subscribe_turn(world_id: int, turn_id: str):
    """SSE 直播生成器：订阅指定轮次，心跳保活；断开无影响（轮次在服务器继续）"""
    worker = get_world_worker(world_id)
    tb = worker.subscribe(turn_id)
    if tb is None:
        yield "data: [DONE]\n\n"
        return
    q = tb.subscribe()
    try:
        if tb.ended:
            # 轮次已结束（可能断开期间跑完）：立即收尾
            yield "data: [DONE]\n\n"
            return
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30)
            except asyncio.TimeoutError:
                if tb.ended:
                    break
                yield ": ping\n\n"  # 心跳保活
                continue
            yield event
            if event.strip() == "data: [DONE]":
                break
    finally:
        tb.unsubscribe(q)
