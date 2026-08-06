"""
世界事件钩子 — 群消息 → 世界程序感知

设计（珑哥 2026-08-05 定）：
- 群消息入库后**异步喂给绑定世界的入口**（main.py handle(event)），
  处理不处理由世界程序自己决定（平台只喂，不干预）。
- 节流合并：同世界一个窗口（默认 2 秒，worlds.config.group_trigger_interval 可配；
  0 = 每条触发）内的消息合并成一条 event.messages，避免群消息爆发把沙箱跑死。
- 防死循环：世界程序自己发的消息（create_message source="world"）不触发。
- 触发不影响世界 status：沉睡世界也能感知；唤醒仍保持手动（AUTO_MANAGE=False）。

event 结构（世界代码在 handle(event) 里收到）：
{
  "type": "group_message",
  "group_id": 5,
  "source": "group",
  "messages": [
    {"message_id": 1, "sender_id": 2, "sender_name": "张三",
     "sender_type": "human", "content": "hi", "created_at": "2026-08-05T12:00:00"}
  ]
}
"""
import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 2.0  # 默认节流窗口（秒）


@dataclass
class _Pending:
    world_id: int
    group_id: int
    msgs: list = field(default_factory=list)
    task: asyncio.Task | None = None


_pending: dict[int, _Pending] = {}


async def notify_group_message(db, group_id: int, message, source: str) -> None:
    """群消息钩子（create_message 落库后调用）。

    - source="world"（世界程序自己发的消息）不触发，防死循环
    - 查绑定该群的世界 → 消息入队节流窗口（异步触发，不阻塞消息发送）
    """
    if source == "world":
        return
    from sqlalchemy import select
    from app.models.world import WorldBinding

    rows = (await db.execute(
        select(WorldBinding).where(
            WorldBinding.entity_type == "group",
            WorldBinding.entity_id == group_id,
        )
    )).scalars().all()
    if not rows:
        return
    for row in rows:
        await _enqueue(db, row.world_id, group_id, message)


async def _enqueue(db, world_id: int, group_id: int, message) -> None:
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        return
    interval = float((world.config or {}).get("group_trigger_interval", DEFAULT_INTERVAL))
    msg = {
        "message_id": message.id,
        "sender_id": message.sender_id,
        "sender_type": message.sender_type,
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }
    p = _pending.get(world_id)
    if p is None:
        p = _Pending(world_id=world_id, group_id=group_id)
        _pending[world_id] = p
    p.msgs.append(msg)
    if p.task is None or p.task.done():
        if interval <= 0:
            # 0 = 每条立即触发，不合并
            await _flush(world_id)
        else:
            p.task = asyncio.create_task(_flush_after(p, interval))
            logger.info(f"🌐 世界 #{world_id} 群消息钩子：{interval}s 窗口合并中（{len(p.msgs)} 条）")


async def _flush_after(p: _Pending, interval: float) -> None:
    try:
        await asyncio.sleep(interval)
        await _flush(p.world_id)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"🌐 世界 #{p.world_id} 群消息钩子异常: {e}")


async def _flush(world_id: int) -> None:
    """窗口到点：取缓冲消息 → 查发件人名字 → 触发世界入口 handle(event)"""
    p = _pending.pop(world_id, None)
    if p is None or not p.msgs:
        return
    from app.database import async_session
    from sqlalchemy import select
    from app.models.user import User

    try:
        async with async_session() as db:
            from app.models.world import World
            world = await db.get(World, world_id)
            if world is None:
                return
            # 批量查发件人名字
            sender_ids = {m["sender_id"] for m in p.msgs}
            name_map: dict[int, str] = {}
            if sender_ids:
                u_res = await db.execute(select(User.id, User.username).where(User.id.in_(sender_ids)))
                name_map = dict(u_res.all())
            for m in p.msgs:
                m["sender_name"] = name_map.get(m["sender_id"], f"#{m['sender_id']}")
            event = {
                "type": "group_message",
                "group_id": p.group_id,
                "source": "group",
                "messages": p.msgs,
            }
            # 2.5：常驻世界 → 投递常驻进程（进程内队列）；非常驻/未在跑 → 临时触发
            from app.services.world.world_resident import manager
            if manager.is_resident(world) and await manager.dispatch(world.id, event):
                return
            from app.services.world.world_sandbox import run_world_trigger
            # 确保沙箱 env 注入 WORLD_API_TOKEN / WORLD_API_BASE（懒生成）
            from app.routers.world_proxy import ensure_world_api_token
            await ensure_world_api_token(db, world)
            await db.commit()
            result = await run_world_trigger(world, event=event, background=True)
            if not result.get("success"):
                logger.info(f"🌐 世界 #{world_id} 群消息感知：程序未处理（{result.get('reason', '')[:80]}）")
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 群消息钩子执行异常: {e}")
