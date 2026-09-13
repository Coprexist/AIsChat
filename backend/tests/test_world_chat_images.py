"""群视界「发图给 AI」链路的端到端冒烟 —— 真的调 _prepare_world_chat，零 LLM 消耗。

为什么不是"各部件单测"：2026-09-13 那次 P0 就是这么漏过去的。
`image_attachments()` 直接迭代 `normalize_attachments()` 的返回值，而后者契约是
`list | None`，于是**没有附件的普通消息**整条路径抛 TypeError，群视界每轮必炸。
纯函数测试全绿、探针测试全绿，但"路由入参 → ChatItem → 落库 → LLM payload"
这条线没有任何一处被从头到尾走过一遍。

本文件守四件事：
1. 不带附件的普通消息不能抛（P0 本体，回归即失败）；
2. 带图消息的**最后一条** user 必须是多模态 parts 且真带 data URL —— 图片不能被静默丢弃
   （主站有过一次"能上传、能显示、能存库，模型从来没看见"的事故）；
3. 「本轮附图」便签必须与**实际注入数**一致，没图时绝不能出现 ——
   只给 image_url 不给这句话，实测模型会自称"我是文本 AI，看不到图片"；
4. 历史里的图降级成 `[图片]`、只有最新一条带字节（护 prompt cache + 防 token 爆炸）。

跑法：`python tests/run_without_pytest.py`（容器里没装 pytest），装了 pytest 时直接 pytest。
"""
from __future__ import annotations

import base64
import os
import uuid

import pytest

from app.utils.multimodal import (
    IMAGE_NOTE_PREFIX,
    VISION_UNSUPPORTED_HINT,
    injected_image_count,
    messages_have_images,
    strip_image_parts,
)

pytestmark = pytest.mark.anyio

USER_ID = 9001

# 1x1 透明 PNG：够小（远低于 4MB 上限）且是货真价实的图片
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


# ── 脚手架 ────────────────────────────────────────────────────────────────

async def _seed_world(db, *, with_image: bool) -> tuple[int, dict]:
    """建一个临时世界；with_image 时再落一张真实图片文件。返回 (world_id, 附件)。"""
    from sqlalchemy import text

    from app.config import settings
    from app.models.user import User
    from app.models.world import World

    # 每个用例从干净状态开始（测试库；run_without_pytest 的启动闸保证库名以 _test 结尾）
    await db.execute(text("TRUNCATE worlds, users CASCADE"))
    await db.commit()

    db.add(User(id=USER_ID, username="smoke-image", password_hash="x", type="human"))
    world = World(name="冒烟：发图", owner_id=USER_ID)
    db.add(world)
    await db.commit()
    await db.refresh(world)

    attachment: dict = {}
    if with_image:
        rel = os.path.join("test-smoke", f"{uuid.uuid4().hex}.png")
        physical = os.path.join(settings.data_dir, rel)
        os.makedirs(os.path.dirname(physical), exist_ok=True)
        with open(physical, "wb") as fh:
            fh.write(PNG_1PX)
        attachment = {
            "file_id": 1, "path": rel, "name": "1px.png",
            "size": len(PNG_1PX), "mime_type": "image/png",
        }
    return world.id, attachment


def _drop_image_file(attachment: dict) -> None:
    """删掉用例造的图片文件，别把 /app/data/test-smoke 越堆越大。"""
    from app.config import settings
    if not attachment:
        return
    physical = os.path.join(settings.data_dir, attachment["path"])
    if os.path.isfile(physical):
        os.remove(physical)


async def _prepare(db, world_id: int, items: list):
    """走真实链路：_prepare_world_chat 就是 stream_world_chat 的准备阶段。"""
    from app.repositories.world_repo import SQLAlchemyWorldRepository
    from app.services.world.world_chat_service import _prepare_world_chat
    return await _prepare_world_chat(SQLAlchemyWorldRepository(db), world_id, USER_ID, items)


def _last_user(messages: list[dict]) -> dict:
    """最后一条 user 消息（尾部还挂着时间/访客等 system 段，取不了 messages[-1]）。"""
    return [m for m in messages if m.get("role") == "user"][-1]


def _notes(messages: list[dict]) -> list[dict]:
    """「本轮附图」便签（必须在的情况下才该有）。"""
    return [
        m for m in messages
        if isinstance(m.get("content"), str) and m["content"].startswith(IMAGE_NOTE_PREFIX)
    ]


# ── 用例 ──────────────────────────────────────────────────────────────────

async def test_plain_text_turn_survives_the_image_path(migrated_db):
    """P0 回归：**有历史**的普通文字消息必须走通。

    曾经的失败形态：`TypeError: 'NoneType' object is not iterable`。
    `normalize_attachments()` 的契约是 `list | None`（纯文字消息落库后就是 None），
    调用方直接迭代了它 —— 所以只要**上一轮**存过一条不带附件的消息，这一轮必炸。

    必须跑到第二轮：首轮历史是空的，`None` 根本不会出现，只测首轮等于没测
    （第一版就踩了这个坑，靠"把 bug 放回去看它红不红"才发现）。
    """
    from app.database import async_session
    from app.services.world.world_chat_items import ChatItem

    async with async_session() as db:
        world_id, _ = await _seed_world(db, with_image=False)
        await _prepare(db, world_id, [ChatItem(text="第一轮")])   # 落一条 attachments=None 的历史
        ctx = await _prepare(db, world_id, [ChatItem(text="你好")])

    messages = ctx["messages"]
    assert any("第一轮" in str(m.get("content")) for m in messages), "第二轮没带上历史，等于没测"
    assert _last_user(messages)["content"] == "你好"   # 纯字符串：与不带图时 payload 完全一致
    assert not messages_have_images(messages)
    assert _notes(messages) == []                      # 没图就不能有"你能看图"的便签
    assert ctx["cmd_text"] == "你好"                   # 单条纯文本 → 照常识别命令


async def test_image_turn_injects_multimodal_parts_and_note(migrated_db):
    """带图消息：最后一条 user 是多模态 parts，便签数与**实际注入数**一致。"""
    from app.database import async_session
    from app.services.world.world_chat_items import ChatItem

    async with async_session() as db:
        world_id, attachment = await _seed_world(db, with_image=True)
        try:
            ctx = await _prepare(
                db, world_id,
                [ChatItem(text="这是什么？", attachments=(attachment,))],
            )
        finally:
            _drop_image_file(attachment)

    messages = ctx["messages"]
    body = _last_user(messages)
    assert isinstance(body["content"], list), "图片被静默丢弃了：content 本应是 parts 列表"
    assert body["content"][0] == {"type": "text", "text": "这是什么？"}
    urls = [p["image_url"]["url"] for p in body["content"] if p.get("type") == "image_url"]
    assert len(urls) == 1
    assert urls[0].startswith("data:image/png;base64,"), "必须是真的图片字节，不是占位符"

    assert injected_image_count(body["content"]) == 1
    notes = _notes(messages)
    assert len(notes) == 1, "缺「本轮附图」便签：只给 image_url 不给这句话，模型会自称看不到图"
    assert "1 张图片" in notes[0]["content"], "便签数量必须是实际注入数（写多了模型会去找不存在的图）"
    assert ctx["cmd_text"] == ""                       # 带附件 → 不当命令解析


async def test_image_turn_persists_attachments(migrated_db):
    """附件必须跟着消息落库 —— 刷新页面后前端靠它渲染缩略图。"""
    from sqlalchemy import select

    from app.database import async_session
    from app.models.world import WorldChatMessage
    from app.services.world.world_chat_items import ChatItem

    async with async_session() as db:
        world_id, attachment = await _seed_world(db, with_image=True)
        try:
            await _prepare(db, world_id, [ChatItem(text="看图", attachments=(attachment,))])
            rows = (await db.execute(
                select(WorldChatMessage).where(WorldChatMessage.world_id == world_id)
            )).scalars().all()
        finally:
            _drop_image_file(attachment)

    stored = [r for r in rows if r.role == "user"][-1]
    assert stored.content == "看图"
    assert stored.attachments and stored.attachments[0]["path"] == attachment["path"]


async def test_history_image_degrades_to_placeholder(migrated_db):
    """第二轮：历史里那张图必须变成 `[图片]` 且不再带字节（护 cache、防 token 爆炸）。"""
    from app.database import async_session
    from app.services.world.world_chat_items import ChatItem

    async with async_session() as db:
        world_id, attachment = await _seed_world(db, with_image=True)
        try:
            await _prepare(
                db, world_id,
                [ChatItem(text="这是什么？", attachments=(attachment,))],
            )
            ctx = await _prepare(db, world_id, [ChatItem(text="谢谢")])
        finally:
            _drop_image_file(attachment)

    messages = ctx["messages"]
    assert any("[图片]" in str(m.get("content")) for m in messages), "历史缺少 [图片] 占位"
    assert not messages_have_images(messages), "只有最新一条能带字节，历史必须降级"
    assert _notes(messages) == []                      # 本轮没图 → 不能再声称"你能看图"


async def test_vision_degrade_strips_images_and_note_together(migrated_db):
    """模型不吃图时：图片与「你能看图」便签必须一起消失。

    只剥图片、留下便签 = 对纯文本模型撒谎，它会照着编图片内容。
    """
    from app.database import async_session
    from app.services.world.world_chat_items import ChatItem

    async with async_session() as db:
        world_id, attachment = await _seed_world(db, with_image=True)
        try:
            ctx = await _prepare(
                db, world_id,
                [ChatItem(text="这是什么？", attachments=(attachment,))],
            )
        finally:
            _drop_image_file(attachment)

    degraded, removed = strip_image_parts(ctx["messages"])
    assert removed == 1
    assert not messages_have_images(degraded)
    assert _notes(degraded) == []
    assert any(VISION_UNSUPPORTED_HINT in str(m.get("content")) for m in degraded)
