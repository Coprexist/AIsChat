"""
世界 AI 对话轮次管理器 — 服务器端全程执行，不依赖客户端连接

- 每个世界一个 worker：消息排队（DM 同款），逐条处理
- 每轮（turn）一个广播：多个订阅者（直播 SSE）可随时加入/离开
- 客户端断开/刷新不影响轮次执行；重连=重新订阅直播，历史补缺口

POST /worlds/{id}/chat          → enqueue，返回 turn_id
GET  /worlds/{id}/chat/stream   → 订阅指定 turn 的实时事件
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session
from app.models.world import World

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
            # 精确判断：只有存在「进行中轮次」标记才算真中断；
            # 用户发消息等 AI 回复（排队/AI 思考中）最后一条也是 user，但 active_turn 为空 → 正常状态，不动
            world = await db.get(World, world_id)
            if world is None or not (world.config or {}).get("active_turn"):
                return
            # 该轮已执行的工具摘要（role=tool 的消息）
            tools_done = [m.content for m in rows if m.role == "tool"][-10:]
            db.add(WorldChatMessage(
                world_id=world_id, user_id=None, role="ai",
                content="（对话中断：服务重启或连接中断，已记录工作流——说「继续」即可接着做）",
            ))
            if world is not None:
                cfg = dict(world.config or {})
                cfg["workflow_memory"] = {
                    "interrupted_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                    "tools_done": tools_done,
                }
                # ⚠️ 2026-08-13 修复：必须清除 active_turn——否则 status 接口
                # 一直看到残留标记返回 processing=true，前端"永远处理中"卡死。
                cfg.pop("active_turn", None)
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
        # 插入消息 turn 的代理：订阅/广播/结束转发到活跃 turn（2026-08-13 产品定，
        # 让前端订阅插入 turn 时能收到当前轮流事件——含 [INSERT] 回执和后续内容）
        self.proxy: "TurnBroadcast | None" = None

    def subscribe(self) -> asyncio.Queue:
        if self.proxy is not None:
            return self.proxy.subscribe()
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if self.proxy is not None:
            self.proxy.unsubscribe(q)
            return
        self.subscribers.discard(q)

    async def broadcast(self, event: str) -> None:
        if self.proxy is not None:
            await self.proxy.broadcast(event)
            return
        if self.ended:
            return
        for q in list(self.subscribers):
            q.put_nowait(event)

    def end(self) -> None:
        """轮次结束：通知所有订阅者（代理 turn 由活跃 turn 的 end 统一收尾）"""
        if self.proxy is not None:
            return
        self.ended = True
        for q in list(self.subscribers):
            q.put_nowait("data: [DONE]\n\n")


class WorldTurnWorker:
    """单个世界的对话 worker：消息排队 → 逐条执行（独立 DB 会话）"""

    def __init__(self, world_id: int):
        self.world_id = world_id
        self.msg_queue: asyncio.Queue = asyncio.Queue()
        self.turns: dict[str, TurnBroadcast] = {}
        # 普通消息插入通道：AI 工具轮进行中时，非命令消息直接注入下一轮 LLM 调用
        # （产品定：只有命令（/compact 等）需要等当前轮次结束再发送）
        self._inserts: list[dict] = []
        self._inserts_lock = asyncio.Lock()
        self.task = asyncio.create_task(self._run(), name=f"world-turn-{world_id}")

    async def _run(self) -> None:
        while True:
            item = await self.msg_queue.get()
            tb = self.turns.get(item["turn_id"])
            # 标记进行中的轮次（DB）：recover_orphaned_turn 据此判断真中断 vs 正常等待（排队消息/AI 思考中）
            try:
                async with async_session() as _db:
                    _w = await _db.get(World, self.world_id)
                    if _w is not None:
                        _w.config = {**(dict(_w.config or {})), "active_turn": {
                            "turn_id": item["turn_id"],
                            "started_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                        }}
                        await _db.commit()
            except Exception:
                pass
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
                # 清除 active_turn（轮次结束；无论正常/异常/中断收尾都跑）
                try:
                    async with async_session() as _db:
                        _w = await _db.get(World, self.world_id)
                        if _w is not None and (_w.config or {}).get("active_turn", {}).get("turn_id") == item["turn_id"]:
                            _cfg = dict(_w.config or {})
                            _cfg.pop("active_turn", None)
                            _w.config = _cfg
                            await _db.commit()
                except Exception:
                    pass
                if tb:
                    tb.end()
                    # 清理本 turn + 代理到它的插入 turn（插入消息广播随活跃 turn 收尾）
                    self.turns.pop(item["turn_id"], None)
                    for _tid in [t for t, _tb in self.turns.items() if _tb.proxy is tb]:
                        self.turns.pop(_tid, None)
                    # 兜底：_publish_insert 未完成（轮次先结束）的插入消息补落库 + 广播
                    # （已落库的 msg_ids 非空则跳过，避免重复）
                    try:
                        if self._inserts:
                            async with async_session() as _db:
                                from app.models.world import World, WorldChatMessage
                                from app.services.world.world_chat_service import session_id_for_db
                                world_row = await _db.get(World, self.world_id)
                                sid = session_id_for_db(world_row) if world_row else None
                                pending = self._inserts
                                self._inserts = []
                                for _it in pending:
                                    if len(_it.get("msg_ids") or []) == len([m for m in _it["messages"] if str(m).strip()]):
                                        continue  # 已由 _publish_insert 落库
                                    total = len(_it["messages"])
                                    await tb.broadcast(f"data: [INSERTED]{json.dumps({'count': total})}\n\n")
                                    for _m in _it["messages"]:
                                        _t = str(_m).strip()
                                        if not _t:
                                            continue
                                        wm = WorldChatMessage(
                                            world_id=self.world_id, user_id=_it["user_id"],
                                            role="user", content=_t, session_id=sid,
                                        )
                                        _db.add(wm)
                                        await _db.flush()
                                        await tb.broadcast(f"data: [INSERT]{json.dumps({'msg_id': wm.id, 'content': _t}, ensure_ascii=False)}\n\n")
                                await _db.commit()
                    except Exception as e:
                        logger.warning(f"🌐 世界 #{self.world_id} 残留插入消息补发失败（非致命）: {e}")

    def enqueue(self, user_id: int, message: str | list[str]) -> str:
        """消息入队（支持批量：排队消息一起发给 AI），返回 turn_id（订阅直播用）。

        产品定（2026-08-16 改）：非命令消息在 AI 工具轮进行中时**进插入队列**（
        不立即绘制气泡）；等 AI 真正收到（_inject_pending_user_messages 注入上下文）时
        才落库 + 广播 [INSERTED]/[INSERT] 绘制气泡——用户看到"已发送" = AI 已看到。
        只有命令（/ 开头，如 /compact /clear）需要当前轮次结束后再发送。
        """
        messages = message if isinstance(message, list) else [message]
        turn_id = uuid.uuid4().hex[:12]
        # 判定是否插入：基于已有 turns（不含本次新建的），排除代理 turn（插入消息的广播，无独立生命周期）
        busy = any(not tb.ended and tb.proxy is None for tb in self.turns.values())
        all_commands = all(str(m).lstrip().startswith("/") for m in messages)
        if not all_commands and busy:
            # 有正在执行的轮次 + 含普通消息 → 走插入通道（工具轮下一轮 LLM 调用前注入）
            # 插入消息的广播代理到当前活跃 turn（前端订阅插入 turn = 收到当前轮流事件含 [INSERT] 回执）
            active_tb = next((tb for tb in self.turns.values() if not tb.ended), None)
            tb = TurnBroadcast(turn_id)
            tb.proxy = active_tb
            self.turns[turn_id] = tb
            # 2026-08-16 产品定（改）：不再立即落库+广播——消息先进插入队列，
            # 等 _inject_pending_user_messages 真正注入 AI 上下文时再落库 + 广播绘制气泡。
            self._inserts.append({"user_id": user_id, "messages": messages, "msg_ids": [], "tb": tb})
            return turn_id
        self.turns[turn_id] = TurnBroadcast(turn_id)
        self.msg_queue.put_nowait({
            "turn_id": turn_id, "user_id": user_id,
            "message": messages,
        })
        return turn_id

    async def _publish_insert(self, world_id: int, tb: TurnBroadcast, user_id: int, messages: list) -> None:
        """插入消息即时落库 + 广播（2026-08-13 产品定改：发消息立即插入，不等下一轮）。
        先 [INSERTED] 信号清前端排队弹窗，再逐条落库 + [INSERT] 画真实气泡；
        落库 id 回填 _inserts（供 drain 时跳过重复落库）。"""
        try:
            await tb.broadcast(f"data: [INSERTED]{json.dumps({'count': len(messages)}, ensure_ascii=False)}\n\n")
            async with async_session() as _db:
                from app.models.world import World, WorldChatMessage
                from app.services.world.world_chat_service import session_id_for_db
                world_row = await _db.get(World, world_id)
                sid = session_id_for_db(world_row) if world_row else None
                ids: list[int] = []
                for _m in messages:
                    _t = str(_m).strip()
                    if not _t:
                        continue
                    wm = WorldChatMessage(
                        world_id=world_id, user_id=user_id, role="user",
                        content=_t, session_id=sid,
                    )
                    _db.add(wm)
                    await _db.flush()
                    ids.append(wm.id)
                    await tb.broadcast(f"data: [INSERT]{json.dumps({'msg_id': wm.id, 'content': _t}, ensure_ascii=False)}\n\n")
                await _db.commit()
                async with self._inserts_lock:
                    for _it in self._inserts:
                        if _it["user_id"] == user_id and _it["messages"] == messages:
                            _it["msg_ids"] = ids
                            break
        except Exception as e:
            logger.warning(f"🌐 世界 #{world_id} 插入消息即时落库失败（非致命）: {e}")

    async def drain_inserts(self, user_id: int | None = None) -> list[dict]:
        """取走待插入的普通消息（工具轮每轮调用前调用；user_id=None 取全部）"""
        async with self._inserts_lock:
            if user_id is None:
                items, self._inserts = self._inserts, []
            else:
                items = [i for i in self._inserts if i["user_id"] == user_id]
                self._inserts = [i for i in self._inserts if i["user_id"] != user_id]
        return items

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
