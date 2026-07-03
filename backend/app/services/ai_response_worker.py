"""
AI 自动回复 Worker
消费 message_queue，对每条新消息检查各 AI 回复意愿，调用 LLM 生成回复
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from sqlalchemy import select
from app.database import async_session
from app.models.agent import Agent as AgentModel
from app.models.group import Group, GroupMember
from app.models.user import User
from app.config import settings

logger = logging.getLogger(__name__)

# 全局消息队列（ws.py 推送，worker 消费）
message_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

# 速率限制：{agent_id: last_call_timestamp}
_rate_limit_tracker: dict[int, float] = {}

# AI 并发锁：resonance/custom 类型同一 AI 串行执行 LLM 调用，general/semi_general 不锁
_agent_locks: dict[int, asyncio.Lock] = {}

async def _run_serialized(agent, coro):
    """resonance/custom 类型加锁串行，general/semi_general 直接执行"""
    if agent.ai_type in ("general", "semi_general"):
        return await coro
    lock = _agent_locks.get(agent.id)
    if lock is None:
        lock = asyncio.Lock()
        _agent_locks[agent.id] = lock
    async with lock:
        return await coro

# 导入连接管理器（在 ws.py 中初始化的全局实例）
from app.routers.ws import manager
from app.services.context_compressor import should_compress, compress_messages


async def ai_response_worker():
    """
    后台主循环：持续消费消息队列，为每条消息检查并触发 AI 回复。
    在 main.py lifespan 中通过 asyncio.create_task 启动。
    """
    logger.info("🤖 AI 回复 worker 已启动，等待消息事件...")
    while True:
        try:
            event = await message_queue.get()
            logger.info(f"📬 Worker 收到事件: group={event.get('group_id')}, msg={event.get('message_id')}, queue_remaining={message_queue.qsize()}")
            # v0.5.0: 记录队列深度
            try:
                from app.services.metrics_collector import metrics
                await metrics.record_queue_depth(message_queue.qsize())
            except Exception:
                pass
            async with async_session() as db:
                try:
                    await _process_event(db, event)
                except Exception as e:
                    logger.error(f"处理消息事件失败: {e}", exc_info=True)
            message_queue.task_done()
        except asyncio.CancelledError:
            logger.info("AI 回复 worker 正在关闭...")
            break
        except Exception as e:
            logger.error(f"Worker 循环异常: {e}", exc_info=True)
            await asyncio.sleep(1)  # 防止死循环


async def _send_system_error(
    db, agent, error_type: str, detail: str,
    conversation_type: str, group_id: int | None, session_id: str | None,
):
    """向 AI owner 私信发送系统错误通知（群聊/DM 均走 DM 通知 owner）"""
    from app.models.dm import DMMessage, DMSession
    from app.services.dm_service import generate_dm_session_id

    SYSTEM_USER_ID = 0  # 硬编码：迁移保证 id=0 为系统用户

    guidance = {
        "no_api_key": (
            f"⚠️ AI「{agent.name}」缺少 API Key，无法回复消息。\n\n"
            f"📌 **解决方法**（任选其一）：\n"
            f"1. 为 AI 单独配置：[AI 设置页](/agents/{agent.id}) → 完整设置 → API 提供商 → 填写 API Key\n"
            f"2. 使用全局 Key：前往 [个人设置](/settings) → API 配置 → 填写你的 API Key（所有 AI 共用）\n"
            f"3. 使用额度兑换：前往 [兑换码页面](/me) 输入兑换码获取 API 池额度\n\n"
            f"设置完成后 AI 即可正常回复。"
        ),
        "insufficient_balance": (
            f"⚠️ AI「{agent.name}」的 API 余额不足（402），无法回复消息。\n\n"
            f"📌 **解决方法**：\n"
            f"1. 前往 DeepSeek 官网充值\n"
            f"2. 前往 [个人设置](/settings) 更换全局 API Key\n"
            f"3. 前往 [AI 设置页](/agents/{agent.id}) 更换此 AI 的 Key\n"
            f"4. 或前往 [兑换码页面](/me) 输入兑换码获取额度"
        ),
        "auth_error": (
            f"⚠️ AI「{agent.name}」的 API Key 无效（401），无法回复消息。\n\n"
            f"📌 **解决方法**：\n"
            f"1. 前往 [AI 设置页](/agents/{agent.id}) → API 提供商 → 检查并更新 API Key\n"
            f"2. 或前往 [个人设置](/settings) 更新全局 API Key\n"
            f"3. 确认 API Key 未过期、未被删除"
        ),
        "all_failed": (
            f"⚠️ AI「{agent.name}」的 API 调用全部失败。\n\n"
            f"错误详情：{detail}\n\n"
            f"📌 请前往 [AI 设置页](/agents/{agent.id}) 或 [个人设置](/settings) 检查 API 配置。"
        ),
    }

    content = guidance.get(error_type, guidance["all_failed"])

    try:
        # 统一走 DM 通知：发给 AI 的 owner，不广播到群
        owner_id = agent.owner_id
        if not owner_id:
            logger.warning(f"AI {agent.name}({agent.id}) 无 owner，无法发送系统通知")
            return

        dm_sid = generate_dm_session_id(SYSTEM_USER_ID, owner_id)

        # 确保 DM 会话存在
        result = await db.execute(
            select(DMSession).where(DMSession.session_id == dm_sid)
        )
        dm_session = result.scalar_one_or_none()
        if dm_session is None:
            ids = sorted([SYSTEM_USER_ID, owner_id])
            dm_session = DMSession(session_id=dm_sid, user1_id=ids[0], user2_id=ids[1])
            db.add(dm_session)
            await db.flush()

        # 直接写入 DM 消息（sender_id=0 = 系统用户）
        dm_msg = DMMessage(
            session_id=dm_sid,
            sender_id=SYSTEM_USER_ID,
            content=content,
        )
        db.add(dm_msg)
        await db.commit()
        await db.refresh(dm_msg)

        # WebSocket 推送
        try:
            from app.routers.ws import manager
            await manager.broadcast_to_dm(dm_sid, {
                "type": "message",
                "data": {
                    "id": dm_msg.id,
                    "session_id": dm_sid,
                    "sender_type": "system",
                    "sender_id": 0,
                    "sender_name": "系统",
                    "content": content,
                    "reply_to": None,
                    "created_at": dm_msg.created_at.isoformat() if dm_msg.created_at else None,
                },
            })
        except Exception:
            pass

        logger.info(f"📢 系统错误通知已 DM 给 owner={owner_id}: agent={agent.name}, error={error_type}")
    except Exception as e:
        logger.warning(f"发送系统错误通知失败（非致命）: {e}")


async def _process_event(db, event: dict):
    """
    处理单条消息事件。

    event 字段:
        conversation_type ("group" | "dm"), group_id (群聊), session_id (私信),
        message_id, content, sender_type, sender_id, chain_depth
    """
    event_type = event.get("type", "")
    if event_type == "alarm":
        await _process_alarm_event(db, event)
        return

    conversation_type = event.get("conversation_type", "group")

    if conversation_type == "dm":
        await _process_dm_event(db, event)
    else:
        await _process_group_event(db, event)


async def _process_dm_event(db, event: dict):
    """处理私信事件：检查对方是否是 AI，如果是则触发回复"""
    session_id = event["session_id"]
    message_id = event["message_id"]
    content = event["content"]
    sender_id = event.get("sender_id")
    chain_depth = event.get("chain_depth", 0)
    force_own_key = event.get("force_own_key", False)  # v0.9.0

    from app.models.dm import DMSession
    from app.models.user import User
    from app.models.agent import Agent as AgentModel

    # 找到会话
    sess_result = await db.execute(
        select(DMSession).where(DMSession.session_id == session_id)
    )
    session = sess_result.scalar_one_or_none()
    if session is None:
        return

    # 找到接收方
    receiver_id = session.user2_id if session.user1_id == sender_id else session.user1_id

    # 检查是否是 AI
    user_result = await db.execute(
        select(User).where(User.id == receiver_id, User.type == "ai")
    )
    ai_user = user_result.scalar_one_or_none()
    if ai_user is None:
        return

    # 找到对应的 agent
    agent_result = await db.execute(
        select(AgentModel).where(AgentModel.user_id == receiver_id)
    )
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        return

    logger.info(f"私信 {session_id} 触发 AI {agent.name}({agent.id}) 回复")

    # DM 链条深度限制
    if chain_depth > 10:
        logger.info(f"DM {session_id} 对话链深度 {chain_depth} > 10，停止")
        return

    # 简化的 DM 回复触发（不需要群聊那样的 DND/意愿检查）
    await _trigger_dm_ai_reply(
        db, agent, session_id, content, message_id,
        chain_depth=chain_depth + 1,
        sender_id=sender_id,
        force_own_key=force_own_key,
    )


async def _process_group_event(db, event: dict):
    """处理群聊事件（原有逻辑）"""
    group_id = event["group_id"]
    message_id = event["message_id"]
    content = event["content"]
    sender_type = event.get("sender_type", "human")
    sender_id = event.get("sender_id")
    chain_depth = event.get("chain_depth", 0)

    # 远程消息门控：来自远程实例的 AI 消息不触发本地 AI 回复（防循环）
    source_public_id = event.get("source_public_id")
    if source_public_id and sender_type == "ai":
        logger.info(f"群 {group_id} 收到远程 AI 消息 (source={source_public_id})，跳过本地 AI 回复")
        return

    from app.models.agent import Agent as AgentModel

    # 获取群聊信息
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()
    if group is None:
        return

    # 对话链深度限制：根据群设置动态计算
    if group.owner_type == "ai":
        effective_max_depth = 50
    else:
        limit_per_min = group.speak_limit_per_minute or 0
        window_sec = group.speak_limit_window_seconds or 120
        if limit_per_min > 0:
            effective_max_depth = max(limit_per_min * 2, 5)
        else:
            effective_max_depth = 50

    if chain_depth > effective_max_depth:
        logger.info(
            f"群 {group_id} 对话链深度 {chain_depth} > {effective_max_depth}"
            f"(owner={group.owner_type}, limit={group.speak_limit_per_minute}/min)，停止触发"
        )
        return

    # 获取群聊中所有 AI 成员
    members_result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.member_type == "ai",
        )
    )
    ai_members = members_result.scalars().all()

    if not ai_members:
        return

    # 确定需要触发的 AI 列表
    target_ai_ids: set[int] = set()

    # v2.0.0: sender_id 对 AI 类型是 agent.id，需转为 user_id 与 group_members 对齐
    exclude_user_id: int | None = None
    if sender_type == "ai" and sender_id:
        sender_agent_result = await db.execute(
            select(AgentModel).where(AgentModel.id == sender_id)
        )
        sender_agent = sender_agent_result.scalar_one_or_none()
        if sender_agent and sender_agent.user_id:
            exclude_user_id = sender_agent.user_id

    if sender_type == "human":
        target_ai_ids = {m.member_id for m in ai_members}
    else:
        target_ai_ids = {
            m.member_id for m in ai_members
            if m.member_id != (exclude_user_id if exclude_user_id else sender_id)
        }

    if not target_ai_ids:
        return

    logger.info(
        f"群聊 {group_id} 收到消息 (sender={sender_type}:{sender_id}, depth={chain_depth})，"
        f"触发 {len(target_ai_ids)} 个 AI: {target_ai_ids}"
    )

    next_depth = chain_depth + 1
    for ai_id in target_ai_ids:
        await _maybe_trigger_ai_reply(
            db, ai_id, group_id, group, content, message_id,
            chain_depth=next_depth,
            sender_type=sender_type,
            sender_id=sender_id,
        )


async def _get_api_config(
    db, agent,
    exclude_pool_key_id: int | None = None,
    chatter_id: int | None = None,
    force_own_key: bool = False,
) -> tuple[str | None, str, str, int | None]:
    """
    获取 API Key 和 Base URL（四层优先链 + 平台赠送额度）。

    Tier 1: Agent 自有 Key
    Tier 2: 账单人有可用额度 → API Key 池
    Tier 3: 账单人有 api_credit + 无绑定 → 自动选最优池 Key
    Tier 4: 账单人自有 Key

    v0.9.0: chatter_id 决定账单人（通用 AI 扣聊天者，否则扣主人）。
            force_own_key=True 时跳过 Tier 2/3，直接走账单人自有 Key。

    返回: (api_key, api_base, credit_source, pool_key_id)
    """
    from app.utils.crypto import decrypt_api_key
    from app.models.user import User as UserModel

    api_key = None
    api_base = settings.deepseek_base_url
    credit_source = "none"
    pool_key_id = None

    # 确定账单人：通用/半通用 + 有聊天者 → 聊天者付；否则主人付
    if chatter_id and agent.ai_type in ("general", "semi_general"):
        bill_user_id = chatter_id
    else:
        bill_user_id = agent.owner_id

    # Tier 1: Agent 自有 Key
    if agent.api_key_encrypted:
        api_key = decrypt_api_key(agent.api_key_encrypted)
        api_base = agent.api_base_url or settings.deepseek_base_url
        credit_source = "agent_key"
        return api_key, api_base, credit_source, pool_key_id

    # 查账单用户
    user_result = await db.execute(select(UserModel).where(UserModel.id == bill_user_id))
    user = user_result.scalar_one_or_none()

    if user is None:
        return api_key, api_base, credit_source, pool_key_id

    # force_own_key: 跳过池 Key，直接走用户自有 Key
    if force_own_key:
        if user.api_key_encrypted:
            api_key = decrypt_api_key(user.api_key_encrypted)
            api_base = user.api_base_url or settings.deepseek_base_url
            credit_source = "user_key"
        return api_key, api_base, credit_source, pool_key_id

    # 有效可用额度 = 平台赠送（截断>=0） + api_credit
    effective_credit = max(0, (user.platform_gifted_credit or 0)) + (user.api_credit or 0)

    # Tier 2 & 3: 用户有可用额度 → 使用 API Key 池
    if effective_credit > 0:
        from app.services.quota_service import find_best_pool_key
        pool_key = await find_best_pool_key(db, user.id, exclude_pool_key_id=exclude_pool_key_id)
        if pool_key:
            try:
                api_key = decrypt_api_key(pool_key.api_key_encrypted)
                api_base = pool_key.api_base_url or settings.deepseek_base_url
                credit_source = "pool_key"
                pool_key_id = pool_key.id
                return api_key, api_base, credit_source, pool_key_id
            except Exception as e:
                logger.warning(f"  ⚠️ 池 Key {pool_key.id} 解密失败: {e}，回退到用户自有 Key")

    # Tier 4: 用户自有 Key
    if user.api_key_encrypted:
        api_key = decrypt_api_key(user.api_key_encrypted)
        api_base = user.api_base_url or settings.deepseek_base_url
        credit_source = "user_key"

    return api_key, api_base, credit_source, pool_key_id


async def _maybe_trigger_ai_reply(
    db, agent_id: int, group_id: int, group, content: str, trigger_message_id: int,
    chain_depth: int = 0,
    sender_type: str = "human",
    sender_id: int | None = None,
):
    """检查单个 AI 是否应该回复，如果是则调用 LLM 生成回复"""
    from app.services.agent_service import get_agent
    from app.services.action_decider import decide_action, ActionContext, ActionType
    from app.models.agent import Agent as AgentModel

    # v2.0.0: agent_id 可能是 agent.id 或 user_id（group_members 迁移后 member_id 统一为 user_id）
    agent = await get_agent(db, agent_id)
    if agent is None:
        # 通过 user_id 查找（group_members.member_id 现已统一为 user_id）
        agent_result = await db.execute(
            select(AgentModel).where(AgentModel.user_id == agent_id)
        )
        agent = agent_result.scalar_one_or_none()
    if agent is None:
        logger.warning(f"AI agent_id/user_id={agent_id} 不存在，跳过")
        return

    # 统一使用 agent.id（数据库主键）作为后续内部标识
    resolved_agent_id = agent.id

    logger.info(f"🔍 检查 AI {agent.name}(id={resolved_agent_id}, user_id={agent.user_id}), state={agent.state}")

    is_mentioned = _check_mention(content, agent.name)
    logger.info(f"🔍 AI {agent.name}(id={resolved_agent_id}): is_mentioned={is_mentioned}, content_preview='{content[:80]}'")

    # v0.5.0: 使用统一决策（替代原有 Gate 1-5 的手动判断）
    ctx = ActionContext(
        event_type="message",
        agent_id=resolved_agent_id,
        group_id=group_id,
        content=content,
        sender_type=sender_type,
        sender_id=sender_id,
        is_mentioned=is_mentioned,
        chain_depth=chain_depth,
    )
    decision = await decide_action(db, agent, ctx)
    logger.info(f"🔍 AI {agent.name}(id={resolved_agent_id}): decision={decision.action_type.value}, "
                f"priority={decision.priority}, reason={decision.reason}")

    if not decision.should_act:
        # 处理 DND 暂存消息
        if decision.details.get("store_pending"):
            from app.services.group_service import store_pending_message
            await store_pending_message(db, resolved_agent_id, group_id, trigger_message_id)
        return

    # 记录意愿（如果决策中有）
    w_score = decision.willingness_score
    if w_score > 0:
        agent.last_willingness_score = w_score
        agent.last_willingness_reason = decision.reason

    # 4. 速率限制检查
    if not _check_rate_limit(resolved_agent_id):
        logger.info(f"AI {agent.name}(id={resolved_agent_id}) 速率限制，跳过")
        return

    # 5. 获取 API 配置（v0.5.0: 公共辅助函数；v0.6.0: 四层优先链含池 Key）
    api_key, api_base, credit_source, pool_key_id = await _get_api_config(db, agent)
    logger.info(f"🔍 AI {agent.name}: api_base={api_base}, has_api_key={api_key is not None}, "
                f"credit_source={credit_source}")

    # 5.1. 无 API Key → 发送系统通知后跳过
    if api_key is None:
        logger.warning(f"AI {agent.name}({agent.id}) 无 API Key，发送系统通知")
        await _send_system_error(db, agent, "no_api_key", "", "group", group_id, None)
        return

    # 5.5. 中断标记：如果 AI 之前在忙，记录中断
    try:
        from app.services.workspace_service import mark_interrupted
        sender_info = f"群聊 #{group_id} 的新消息"
        await mark_interrupted(db, resolved_agent_id, reason=sender_info)
    except Exception:
        pass  # 非致命

    # 5.6. Skill 引擎评估（延迟回复、打字指示器）
    from app.services.skill_engine import evaluate_action_skills, _is_delay_reply_allowed
    skill_result = await evaluate_action_skills(db, agent, group_id, context={
        "content": content,
        "sender_type": sender_type,
        "sender_id": sender_id,
    })
    # 打字指示器广播
    if skill_result.show_typing:
        await manager.broadcast_to_group(group_id, {
            "type": "ai_typing",
            "data": {"agent_id": agent.id, "agent_name": agent.name, "agent_avatar_url": agent.avatar_url, "is_typing": True},
        })
    # 延迟回复（若已有积压消息则跳过，避免级联延迟）
    delay_skipped = False
    if skill_result.delay_seconds > 0:
        from app.services.group_service import get_pending_messages
        pending = await get_pending_messages(db, resolved_agent_id, group_id)
        pending_count = len(pending) if pending else 0
        if pending_count > 0:
            logger.info(f"🧠 AI {agent.name} 有 {pending_count} 条积压消息，跳过延迟回复")
            delay_skipped = True
        else:
            logger.info(f"🧠 AI {agent.name} 技能延迟 {skill_result.delay_seconds}s")
            await asyncio.sleep(skill_result.delay_seconds)

    # v0.4.0: trigger_user_id 用于通用/半通用 AI 的 per-user 记忆隔离
    trigger_user_id = sender_id if sender_type == "human" else None

    # 6. 获取有效配置（v0.4.0: per-user 覆盖 — 需在 build_messages 前获取）
    from app.services.agent_service import get_effective_config
    effective_cfg = await get_effective_config(db, agent.id, trigger_user_id)
    logger.info(f"🔍 AI {agent.name}: effective_cfg ai_type={effective_cfg['ai_type']}, "
                f"thinking={effective_cfg['thinking_enabled']}, temp={effective_cfg['temperature']}")

    # 7. 构建消息
    from app.services.llm_service import build_messages, resolve_model
    # 向量加速混合检索仅在 AI 全群启用（AI 内部协作场景）
    # 普通人类群聊使用常规历史窗口，避免不必要的向量化开销
    from app.services.group_service import is_ai_only_group
    ai_only = await is_ai_only_group(db, group_id, group=group)
    use_vector = group.is_vector_accelerated and ai_only
    if group.is_vector_accelerated and not ai_only:
        logger.info(f"群 {group_id} 含人类成员，跳过向量加速（使用常规历史窗口）")
    messages = await build_messages(
        db, agent, group_id,
        vector_accelerated=use_vector,
        api_base_url=api_base,
        api_key=api_key,
        trigger_user_id=trigger_user_id,
        system_prompt_override=effective_cfg.get("system_prompt"),
    )
    logger.info(f"🔍 AI {agent.name}: 构建了 {len(messages)} 条消息")

    # 延迟被跳过时，注入提醒：加快回复速度 + 记入记忆
    if delay_skipped:
        delay_hint = (
            "⚠️ 系统提醒：你配置了延迟回复，但因为群里有积压消息，延迟已被跳过。\n"
            "请检查最近的发消息者——对方可能正在等你回复。\n"
            "建议：\n"
            "1. 加快对此人的回复速度，不要再设长延迟\n"
            "2. 调用 manage_workspace 在 todo 里记下「被催促回复，需要调整回复节奏」\n"
            "3. 调用 store_memory 记下这个交互模式，以后遇到此人时优先快速响应"
        )
        messages.append({"role": "system", "content": delay_hint})

    # 7.5 获取工具
    from app.services.tool_registry import get_allowed_tools
    delay_allowed = await _is_delay_reply_allowed(db, agent)
    tools = get_allowed_tools(agent.state, thinking_enabled=effective_cfg["thinking_enabled"], delay_reply_allowed=delay_allowed)
    model = resolve_model(agent)
    logger.info(f"🔍 AI {agent.name}: model={model}, tools={len(tools)}")

    # 8. 工具调用循环（含思考状态广播）
    logger.info(f"🚀 AI {agent.name}: 开始调用 LLM...")
    try:
        await manager.broadcast_to_group(
            group_id,
            {
                "type": "ai_thinking",
                "data": {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_avatar_url": agent.avatar_url,
                    "group_id": group_id,
                    "trigger": "user",
                },
            },
        )
        await _run_serialized(agent, _tool_call_loop(
            db=db,
            agent=agent,
            group_id=group_id,
            messages=messages,
            tools=tools,
            model=model,
            api_base_url=api_base,
            api_key=api_key,
            max_loops=effective_cfg["max_tool_rounds"],
            chain_depth=chain_depth,
            conversation_type="group",
            trigger_user_id=trigger_user_id,
            effective_cfg=effective_cfg,
            credit_source=credit_source,
            pool_key_id=pool_key_id,
            trigger="user",
            is_federated=False,
        ))
    finally:
        await manager.broadcast_to_group(
            group_id,
            {
                "type": "ai_thinking_end",
                "data": {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_avatar_url": agent.avatar_url,
                    "group_id": group_id,
                    "trigger": "user",
                },
            },
        )
    logger.info(f"✅ AI {agent.name}: LLM 调用完成")

    # 9. 标记未读消息已处理
    from app.services.group_service import mark_pending_read
    await mark_pending_read(db, resolved_agent_id, group_id)
    await db.commit()


async def _tool_call_loop(
    db,
    agent,
    group_id: int | None,
    messages: list[dict],
    tools: list[dict],
    model: str,
    api_base_url: str,
    api_key: str | None,
    max_loops: int = 3,
    chain_depth: int = 0,
    conversation_type: str = "group",
    session_id: str | None = None,
    trigger_user_id: int | None = None,
    effective_cfg: dict | None = None,
    credit_source: str = "user_key",
    pool_key_id: int | None = None,
    trigger: str = "user",
    is_federated: bool = False,
):
    """
    工具调用循环：LLM 必须通过工具调用来执行所有操作（包括发消息）。

    铁律：文字不能自动发出去。想说话必须调 send_message。

    v0.4.0: trigger_user_id 传入工具上下文供 store_memory 做 per-user 隔离。
    effective_cfg 为 get_effective_config 的返回值，提供 per-user 定制的 LLM 参数。
    v0.6.0: credit_source + pool_key_id 用于 LLM 调用后额度扣除。
    v0.6.0: stream=True 流式调用 + 工具格式校验 + trigger 字段（user/auto）。
    """
    if effective_cfg is None:
        effective_cfg = {}
    from app.services.llm_service import chat_completion
    from app.services.tool_registry import dispatch_tool_call

    context = {
        "api_key": api_key,
        "api_base_url": api_base_url,
        "manager": manager,
        "agent_name": agent.name,
        "chain_depth": chain_depth,
        "conversation_type": conversation_type,
        "session_id": session_id,
        "trigger_user_id": trigger_user_id,
        "is_federated": is_federated,
        "_messages": messages,       # compress_context 工具需要读写
        "_agent": agent,             # compress_context 需要 agent.id 做 user_id
        "_model": model,             # 压缩用的模型
    }

    # 追踪 AI 在做什么（用于中断恢复）
    last_task = None
    # 累积 token 消耗（跨多轮工具调用）
    total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0, "api_calls": 0}
    # system_reminder 额外轮次：AI 返回文字但忘了调 send_message 时，提醒不消耗配额
    _reminder_extra = 0
    # 上下文压缩：每轮工具调用循环最多自动压缩一次
    _auto_compressed = False

    loop_idx = 0
    while loop_idx < max_loops + _reminder_extra:
        # ── v0.6.0: 带分类重试的 LLM 调用 ──
        from app.services.llm_service import RateLimitError, ServerError, KeyFatalError
        from app.services.api_key_concurrency import concurrency_mgr

        MAX_KEY_SWITCHES = 3
        MAX_SERVER_RETRIES = 2
        last_limited_key_id = pool_key_id  # 初始值，429 后更新
        last_error_type = None  # 追踪最后一个错误类型，用于系统通知
        last_error_detail = ""
        current_api_key = api_key
        current_api_base = api_base_url
        current_credit_source = credit_source
        current_pool_key_id = pool_key_id

        response = None
        for key_attempt in range(MAX_KEY_SWITCHES):
            # 切换 Key 时重新获取配置
            if key_attempt > 0 and last_limited_key_id:
                exclude_id = last_limited_key_id
                current_api_key, current_api_base, current_credit_source, current_pool_key_id = \
                    await _get_api_config(db, agent, exclude_pool_key_id=exclude_id)

            # 获取并发槽位
            acquired = False
            if current_pool_key_id:
                # 获取 Key 的 concurrent_limit 用于并发判断
                from app.models.api_key_pool import ApiKeyPool as ApiKeyPoolModel
                key_result = await db.execute(
                    select(ApiKeyPoolModel).where(ApiKeyPoolModel.id == current_pool_key_id)
                )
                key_row = key_result.scalar_one_or_none()
                db_limit = getattr(key_row, 'concurrent_limit', None) if key_row else None
                if not await concurrency_mgr.acquire(current_pool_key_id, model, db_limit):
                    continue  # Key 已满，换下一个
                acquired = True

            # 流式逐工具分发：回调在 SSE 解析到完整 tool_call 时即刻执行
            _pending_results: list[dict] = []  # {tc_id, result}
            _end_turn = False

            async def _dispatch_one_tool(tc: dict):
                nonlocal last_task, _end_turn
                if _end_turn:
                    return
                tc_id = tc.get("id", "")
                func_info = tc.get("function", {})
                tool_name = func_info.get("name", "")
                arguments_str = func_info.get("arguments", "{}")
                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    _pending_results.append({"tc_id": tc_id, "result": {
                        "error": True, "message": f"工具 {tool_name} 参数 JSON 无效: {arguments_str[:200]}"
                    }})
                    return
                from app.services.tool_registry import validate_tool_call
                is_valid, validate_error = validate_tool_call(tool_name, arguments)
                if not is_valid:
                    logger.warning(f"工具格式校验失败: {validate_error}")
                    _pending_results.append({"tc_id": tc_id, "result": {"error": True, "message": validate_error}})
                    return
                logger.info(f"AI {agent.name} 调用工具: {tool_name}({arguments})")
                # 消息类工具推送"正在输入中…"状态
                if tool_name in ("send_message", "send_dm") and trigger == "user":
                    _typing_data: dict = {"agent_id": agent.id, "agent_name": agent.name, "agent_avatar_url": agent.avatar_url, "trigger": trigger}
                    if conversation_type == "dm" and session_id:
                        _typing_data["session_id"] = session_id
                    elif group_id is not None:
                        _typing_data["group_id"] = group_id
                    _typing_event = {"type": "ai_typing", "conversation_type": conversation_type, "data": _typing_data}
                    try:
                        if conversation_type == "dm" and session_id:
                            await manager.broadcast_to_dm(session_id, _typing_event)
                        elif group_id is not None:
                            await manager.broadcast_to_group(group_id, _typing_event)
                    except Exception:
                        pass
                # 任务摘要追踪
                _work_tools = {
                    "execute_command": lambda a: f"执行命令: {a.get('command', '?')}",
                    "store_memory": lambda a: f"存储记忆: {a.get('title', '?')}",
                    "file_write": lambda a: f"写文件: {a.get('file_path', '?')}",
                    "file_read": lambda a: f"读文件: {a.get('file_path', '?')}",
                    "file_delete": lambda a: f"删除文件: {a.get('file_path', '?')}",
                    "send_message": lambda a: f"在群聊中发言: {str(a.get('content', ''))[:40]}",
                    "send_dm": lambda a: f"发私信: {str(a.get('content', ''))[:40]}",
                    "send_friend_request": lambda a: f"发送好友申请: {a.get('message', '?')[:40]}",
                    "toggle_thinking": lambda a: f"切换深度推理: {'开启' if a.get('enabled') else '关闭'}",
                    "manage_workspace": lambda a: f"管理工作区: {a.get('action', '?')} — {a.get('section', '?')}",
                    "set_alarm": lambda a: f"设置闹钟: {a.get('reason', '?')[:40]}",
                }
                task_summary = None
                if tool_name in _work_tools:
                    try:
                        task_summary = _work_tools[tool_name](arguments)
                    except Exception:
                        pass
                if not task_summary:
                    task_summary = f"调用工具 {tool_name}"
                result = await dispatch_tool_call(db, agent.id, group_id, tool_name, arguments, context)
                if task_summary:
                    last_task = task_summary
                    if isinstance(result, dict):
                        result["__task"] = task_summary
                _pending_results.append({"tc_id": tc_id, "result": result})
                if isinstance(result, dict) and result.get("end_turn"):
                    _end_turn = True

            # ── 自动上下文压缩（每轮工具调用循环最多一次）──
            if not _auto_compressed:
                if should_compress(messages):
                    logger.info(
                        f"AI {agent.name}({agent.id}) 上下文超过阈值，自动压缩中..."
                    )
                    compress_model = effective_cfg.get("work_model") or model
                    messages, compress_stats = await compress_messages(
                        messages=messages,
                        api_base_url=current_api_base,
                        api_key=current_api_key,
                        model=compress_model,
                        user_id=str(agent.id),
                    )
                    if compress_stats.get("compressed"):
                        logger.info(
                            f"AI {agent.name}({agent.id}) 自动压缩完成："
                            f"{compress_stats['before_tokens']} → {compress_stats['after_tokens']} tokens"
                        )
                    _auto_compressed = True

            try:
                # 内层：同 Key 重试（500/503）
                for server_retry in range(MAX_SERVER_RETRIES + 1):
                    try:
                        response = await chat_completion(
                            messages=messages,
                            model=model,
                            api_base_url=current_api_base,
                            api_key=current_api_key,
                            tools=tools if tools else None,
                            temperature=effective_cfg["temperature"] or 0.8,
                            top_p=effective_cfg["top_p"] or 0.9,
                            presence_penalty=effective_cfg["presence_penalty"] or 0.5,
                            frequency_penalty=effective_cfg["frequency_penalty"] or 0.5,
                            thinking_enabled=effective_cfg["thinking_enabled"],
                            stream=True,
                            pool_key_id=current_pool_key_id,
                            on_tool_call=_dispatch_one_tool,
                        )
                        # 更新池 Key ID（可能已切换）
                        pool_key_id = current_pool_key_id
                        credit_source = current_credit_source
                        api_key = current_api_key
                        api_base_url = current_api_base
                        break  # 成功
                    except ServerError as e:
                        if server_retry < MAX_SERVER_RETRIES:
                            delay = 2 if e.status_code == 500 else 3
                            logger.warning(
                                f"AI {agent.name}({agent.id}) 服务器 {e.status_code}，"
                                f"{delay}s 后同 Key 重试 ({server_retry + 1}/{MAX_SERVER_RETRIES})"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            raise  # 同 Key 重试耗尽，抛出给外层

                break  # 成功，退出 Key 切换循环

            except RateLimitError as e:
                last_error_type = "rate_limited"
                last_error_detail = e.message
                if current_pool_key_id:
                    await concurrency_mgr.mark_rate_limited(current_pool_key_id)
                last_limited_key_id = current_pool_key_id
                logger.warning(
                    f"AI {agent.name}({agent.id}) Key #{current_pool_key_id} 429，"
                    f"冷却 60s，换 Key ({key_attempt + 1}/{MAX_KEY_SWITCHES})"
                )
                continue

            except KeyFatalError as e:
                last_error_type = "auth_error" if e.status_code == 401 else "insufficient_balance" if e.status_code == 402 else "key_fatal"
                last_error_detail = e.message
                await _log_key_fatal(db, current_pool_key_id, e.status_code, e.message)
                last_limited_key_id = current_pool_key_id
                logger.error(
                    f"AI {agent.name}({agent.id}) Key #{current_pool_key_id} "
                    f"{e.status_code} 不可用，跳过换下一个 ({key_attempt + 1}/{MAX_KEY_SWITCHES})"
                )
                continue

            except ServerError as e:
                last_error_type = "server_error"
                last_error_detail = f"{e.status_code}: {e.message}"
                logger.error(
                    f"AI {agent.name}({agent.id}) Key #{current_pool_key_id} "
                    f"{e.status_code} 重试耗尽，最终失败"
                )

            finally:
                if acquired and current_pool_key_id:
                    await concurrency_mgr.release(current_pool_key_id)

        # ── 全部重试失败 ──
        if response is None:
            logger.error(f"AI {agent.name}({agent.id}) LLM 调用全部重试失败，last_error={last_error_type}")
            await _save_conversation_log_safe(
                db, agent, messages, conversation_type,
                group_id, session_id, has_output=False, model=model,
            )
            # 发送分类系统通知
            error_type = last_error_type or "all_failed"
            await _send_system_error(db, agent, error_type, last_error_detail,
                                     conversation_type, group_id, session_id)
            return

        # ── end_turn 已在流式回调中触发 → 补 assistant_msg + tool results 后退出 ──
        if _end_turn:
            assistant_msg = {"role": "assistant", "content": response.get("content")}
            if response.get("tool_calls"):
                assistant_msg["tool_calls"] = response["tool_calls"]
            if response.get("reasoning_content"):
                assistant_msg["reasoning_content"] = response["reasoning_content"]
            messages.append(assistant_msg)
            for pr in _pending_results:
                messages.append({"role": "tool", "tool_call_id": pr["tc_id"],
                                 "content": json.dumps(pr["result"], ensure_ascii=False)})
            logger.info(f"AI {agent.name}({agent.id}) end_turn 流式触发，本轮结束")
            await _save_conversation_log_safe(
                db, agent, messages, conversation_type,
                group_id, session_id, has_output=True, model=model,
                token_usage=total_usage,
            )
            return

        content = response.get("content")
        tool_calls = response.get("tool_calls")
        finish_reason = response.get("finish_reason", "stop")

        # 累积 token 消耗 + API 调用计数
        total_usage["api_calls"] += 1
        usage = response.get("usage", {})
        if usage:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens", "cached_tokens"):
                total_usage[k] += usage.get(k, 0)

        # ── 解析 JSON intent（轻量方案：提示词引导 + 后端解析，不用 response_format）──
        # AI 的 content 应为 {"intent": "tool_calls"|"end_turn"|"no_action"}
        # 解析成功 → 按意图分发；解析失败 → 走下方 system_reminder 兜底
        parsed_intent = None
        if content:
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "intent" in parsed:
                    parsed_intent = parsed["intent"]
            except (json.JSONDecodeError, TypeError):
                pass

        # ── end_turn / no_action：AI 明确表示本轮结束 ──
        # 不走 system_reminder，直接干净退出（省一轮 API 调用）
        if parsed_intent in ("end_turn", "no_action") and not tool_calls and not _pending_results:
            logger.info(
                f"AI {agent.name}({agent.id}) intent={parsed_intent}，本轮结束"
            )
            if last_task:
                try:
                    from app.services.workspace_service import save_current_task
                    await save_current_task(db, agent.id, last_task)
                except Exception:
                    pass
            await _save_conversation_log_safe(
                db, agent, messages, conversation_type,
                group_id, session_id,
                has_output=bool(content), model=model,
                token_usage=total_usage,
            )
            return

        # ── 提醒：有文字但没有工具调用（兜底机制，仅 JSON 解析失败或 intent 异常时触发）──
        # 文字不会自动发送。括号表情写在 send_message 的内容里完全OK，
        # 但必须通过工具调用来发送。这里提醒 AI 补上工具调用。
        # agent.reminder_grace: every_time(每次都不计) | once(仅一次) | off(计入配额)
        reminder_grace = getattr(agent, 'reminder_grace', 'every_time')
        if reminder_grace == 'off':
            reminder_max = 0  # 不给额外轮次
        elif reminder_grace == 'once':
            reminder_max = 1  # 最多额外 1 次
        else:  # 'every_time'
            reminder_max = 10  # 有 end_turn 兜底，可放宽额外机会
        if content and not tool_calls and not _pending_results and _reminder_extra < reminder_max:
            logger.info(
                f"AI {agent.name}({agent.id}) 返回了文字但无工具调用"
                f"（intent={parsed_intent or '解析失败'}），"
                f"注入提醒: {content[:80]}"
            )
            # 构造虚拟 tool_calls 以满足 OpenAI API 格式要求
            #（tool 消息必须跟在有 tool_calls 的 assistant 之后）
            reminder_assistant_msg = {
                "role": "assistant",
                "content": content,
                "tool_calls": [{
                    "id": "system_reminder",
                    "type": "function",
                    "function": {
                        "name": "system_reminder",
                        "arguments": "{}",
                    },
                }],
            }
            # DeepSeek 推理模式：reasoning_content 必须传回
            if response.get("reasoning_content"):
                reminder_assistant_msg["reasoning_content"] = response["reasoning_content"]
            messages.append(reminder_assistant_msg)
            messages.append({
                "role": "tool",
                "tool_call_id": "system_reminder",
                "content": json.dumps({
                    "reminder": True,
                    "message": (
                        "你刚才返回了文字但没有调用任何工具。"
                        "文字不能自动发送——如果你想说话，请调用 send_message 工具。"
                        "括号表情可以写在 send_message 的 content 里发出去，"
                        "但不能只返回括号文字而不调工具。"
                        "请现在就调用 send_message 或你需要的其他工具。"
                        "如果你决定不再继续回复，请调用 end_turn 工具来结束本轮。"
                    ),
                }, ensure_ascii=False),
            })
            # 给 AI 额外一次机会调 send_message（受 reminder_grace 控制）
            if reminder_grace != 'off':
                _reminder_extra += 1
            logger.info(f"AI {agent.name}({agent.id}) system_reminder 注入"
                        f"（grace={reminder_grace}, 额外={_reminder_extra}）")
            await asyncio.sleep(0.3)
            continue

        # ── 无工具调用也没有文字 → 退出 ──
        if not tool_calls:
            if last_task:
                try:
                    from app.services.workspace_service import save_current_task
                    await save_current_task(db, agent.id, last_task)
                except Exception:
                    pass
            await _save_conversation_log_safe(
                db, agent, messages, conversation_type,
                group_id, session_id,
                has_output=bool(content), model=model,
                token_usage=total_usage,
            )
            return

        # ── 有工具调用 → 执行（文字只作为附加上下文，不自动发送） ──
        assistant_msg: dict = {"role": "assistant", "content": content}
        assistant_msg["tool_calls"] = tool_calls
        # DeepSeek 推理模式：reasoning_content 必须传回 API，否则报 400
        if response.get("reasoning_content"):
            assistant_msg["reasoning_content"] = response["reasoning_content"]
        messages.append(assistant_msg)

        # ── 追加流式回调中已执行工具的结果到 messages ──
        for pr in _pending_results:
            messages.append({
                "role": "tool",
                "tool_call_id": pr["tc_id"],
                "content": json.dumps(pr["result"], ensure_ascii=False),
            })

        # ── 闹钟模式：第一轮工具执行完后注入收尾提醒 ──
        if conversation_type == "alarm":
            messages.append({
                "role": "user",
                "content": (
                    "⏰ 闹钟任务已执行。\n"
                    "- 如果任务已完成 → 停止，不要额外发言\n"
                    "- 如果情况有变 → 根据实际情况调整行动\n"
                    "- 如果有新的重要事项 → 可以接着规划执行"
                ),
            })

        # LLM 未请求 tool_calls → 已完成，保存并退出
        if finish_reason != "tool_calls":
            if last_task:
                try:
                    from app.services.workspace_service import save_current_task
                    await save_current_task(db, agent.id, last_task)
                except Exception:
                    pass
            await _save_conversation_log_safe(
                db, agent, messages, conversation_type,
                group_id, session_id,
                has_output=True, model=model,
                token_usage=total_usage,
            )
            return

        # 短暂延迟，避免过于频繁的 API 调用
        await asyncio.sleep(0.5)
        loop_idx += 1

    # 循环耗尽（LLM 持续请求 tool_calls 达到 max_loops），仍需保存
    if last_task:
        try:
            from app.services.workspace_service import save_current_task
            await save_current_task(db, agent.id, last_task)
        except Exception:
            pass
    # v0.9.0: LLM 调用后扣除额度（按 AI 类型 + 场景决定账单人）
    if total_usage["api_calls"] > 0 and total_usage["total_tokens"] > 0:
        try:
            # 确定账单人：DM + 通用/半通用 → 聊天者（trigger_user_id）；否则 → 创建者
            if conversation_type == "dm" and agent.ai_type in ("general", "semi_general") and trigger_user_id:
                bill_user_id = trigger_user_id
            else:
                bill_user_id = agent.owner_id
            from app.services.quota_service import deduct_credit
            await deduct_credit(
                db,
                user_id=bill_user_id,
                tokens_used=total_usage["total_tokens"],
                source=credit_source,
                pool_key_id=pool_key_id,
                agent_id=agent.id,
                model=model,
            )
        except Exception as e:
            logger.warning(f"  扣除额度失败（不阻塞主流程）: {e}")

    await _save_conversation_log_safe(
        db, agent, messages, conversation_type,
        group_id, session_id,
        has_output=True, model=model,
        token_usage=total_usage,
    )


from app.utils.text import extract_mentions as _extract_mentions, check_mention as _check_mention


async def _trigger_dm_ai_reply(
    db,
    agent,
    session_id: str,
    content: str,
    trigger_message_id: int,
    chain_depth: int = 0,
    sender_id: int | None = None,
    force_own_key: bool = False,
):
    """触发 AI 对私信的自动回复"""
    from app.services.agent_service import get_agent
    from app.models.user import User as UserModel

    # 状态检查
    if agent.state == "blocked":
        logger.info(f"AI {agent.name}({agent.id}) 状态为 blocked，跳过 DM 回复")
        return

    # 速率限制
    if not _check_rate_limit(agent.id):
        logger.info(f"AI {agent.name}({agent.id}) 速率限制，跳过 DM 回复")
        return

    # 获取有效配置（v0.4.0: per-user 覆盖 — DM 场景 trigger_user_id=sender_id）
    from app.services.agent_service import get_effective_config as _get_eff_cfg
    effective_cfg = await _get_eff_cfg(db, agent.id, sender_id)

    # 获取 API 配置（v0.9.0: 按 AI 类型 + force_own_key 决定账单人）
    api_key, api_base, credit_source, pool_key_id = await _get_api_config(
        db, agent,
        chatter_id=sender_id,
        force_own_key=force_own_key,
    )

    # 无 API Key → 发送 DM 系统通知后跳过
    if api_key is None:
        logger.warning(f"AI {agent.name}({agent.id}) 无 API Key，发送 DM 系统通知")
        await _send_system_error(db, agent, "no_api_key", "", "dm", None, session_id)
        return

    # 中断标记：如果 AI 之前在忙，记录中断
    try:
        from app.services.workspace_service import mark_interrupted
        await mark_interrupted(db, agent.id, reason=f"私信 {session_id} 的新消息")
    except Exception:
        pass  # 非致命

    # Skill 引擎评估（延迟回复、打字指示器）
    from app.services.skill_engine import evaluate_action_skills, _is_delay_reply_allowed
    skill_result = await evaluate_action_skills(db, agent, 0, context={
        "content": content,
        "sender_type": "human",  # DM 中对方是人类
    })
    if skill_result.show_typing:
        await manager.broadcast_to_dm(session_id, {
            "type": "ai_typing",
            "data": {"agent_id": agent.id, "agent_name": agent.name, "agent_avatar_url": agent.avatar_url, "is_typing": True},
        })
    if skill_result.delay_seconds > 0:
        await asyncio.sleep(skill_result.delay_seconds)

    # 构建消息
    from app.services.llm_service import build_dm_messages, resolve_model
    # v0.4.0: DM 中 sender_id 即为触发用户
    messages = await build_dm_messages(db, agent, session_id, api_base_url=api_base, api_key=api_key, trigger_user_id=sender_id, system_prompt_override=effective_cfg.get("system_prompt"))

    # 获取工具
    from app.services.tool_registry import get_allowed_tools
    delay_allowed = await _is_delay_reply_allowed(db, agent)
    tools = get_allowed_tools(agent.state, thinking_enabled=effective_cfg["thinking_enabled"], delay_reply_allowed=delay_allowed)
    model = resolve_model(agent)

    logger.info(f"🚀 AI {agent.name}: 开始 DM 回复 (session={session_id})")

    try:
        await manager.broadcast_to_dm(
            session_id,
            {
                "type": "ai_thinking",
                "conversation_type": "dm",
                "data": {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_avatar_url": agent.avatar_url,
                    "session_id": session_id,
                    "trigger": "user",
                },
            },
        )
        await _run_serialized(agent, _tool_call_loop(
            db=db,
            agent=agent,
            group_id=None,  # DM 不使用 group_id
            messages=messages,
            tools=tools,
            model=model,
            api_base_url=api_base,
            api_key=api_key,
            max_loops=effective_cfg["max_tool_rounds"],
            chain_depth=chain_depth,
            conversation_type="dm",
            session_id=session_id,
            trigger_user_id=sender_id,
            effective_cfg=effective_cfg,
            credit_source=credit_source,
            pool_key_id=pool_key_id,
            trigger="user",
        ))
    finally:
        await manager.broadcast_to_dm(
            session_id,
            {
                "type": "ai_thinking_end",
                "conversation_type": "dm",
                "data": {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_avatar_url": agent.avatar_url,
                    "session_id": session_id,
                    "trigger": "user",
                },
            },
        )
    logger.info(f"✅ AI {agent.name}: DM 回复完成")

    # 提交工作区变更（中断标记、任务保存等）
    await db.commit()


def _check_rate_limit(agent_id: int) -> bool:
    """
    检查速率限制（简单内存实现）。
    返回 True 表示允许调用。
    """
    now = time.monotonic()
    last_call = _rate_limit_tracker.get(agent_id, 0)
    min_interval = 1.0 / settings.rate_limit_per_second

    if now - last_call < min_interval:
        return False

    _rate_limit_tracker[agent_id] = now
    return True


async def _log_key_fatal(db, pool_key_id: int | None, status_code: int, message: str):
    """记录 402/401 致命错误到系统日志，通知管理员"""
    if pool_key_id is None:
        return
    try:
        from app.models.api_key_pool import ApiKeyPool as ApiKeyPoolModel
        key_result = await db.execute(
            select(ApiKeyPoolModel).where(ApiKeyPoolModel.id == pool_key_id)
        )
        key_row = key_result.scalar_one_or_none()
        key_name = key_row.name if key_row else f"#{pool_key_id}"
        error_type = "余额不足" if status_code == 402 else "API Key 无效"
        logger.warning(
            f"  ⚠️ 系统通知：API Key 池「{key_name}」({pool_key_id}) 发生致命错误："
            f"{error_type} ({status_code})，请管理员检查。详情: {message[:200]}"
        )
        # TODO: 后续可扩展为发送站内通知/邮件给管理员
    except Exception as e:
        logger.error(f"记录 Key 致命错误失败: {e}")


# ============================================================
# 闹钟调度器（心跳机制的第一种形态 — v0.5.0 事件驱动）
# ============================================================

async def alarm_scheduler():
    """
    后台闹钟调度器（事件驱动 + 精确等待，替代 5 秒轮询）。

    逻辑：
    1. 计算最近闹钟 wake_at，用 asyncio.sleep 精确等待
    2. 新闹钟设置/修改/取消时，通过 Event 唤醒重新计算
    3. 无闹钟时等待 Event 或 5 分钟兜底检查
    4. DB 断开时降级到 30 秒重试

    在 main.py lifespan 中通过 asyncio.create_task 启动。
    """
    import time as _time
    from app.services.alarm_service import _alarm_wake_event, notify_alarm_changed

    logger.info("⏰ 闹钟调度器已启动（事件驱动模式）")

    while True:
        try:
            # 查询最近闹钟
            async with async_session() as db:
                try:
                    from app.services.alarm_service import get_next_alarm_time
                    next_at = await get_next_alarm_time(db)
                except Exception as e:
                    logger.error(f"闹钟调度器查询失败: {e}")
                    await asyncio.sleep(30)  # DB 断开降级
                    continue

            if next_at is None:
                # 无活跃闹钟 → 等待 Event（新闹钟设置后唤醒）或 5 分钟兜底
                try:
                    await asyncio.wait_for(_alarm_wake_event.wait(), timeout=300)
                except asyncio.TimeoutError:
                    pass  # 兜底检查
                _alarm_wake_event.clear()
                continue

            # 有闹钟 → 计算等待秒数，精确等待
            wait_seconds = next_at.timestamp() - _time.time()
            if wait_seconds <= 0:
                # 已经到期，立即触发
                async with async_session() as db:
                    try:
                        await _check_and_fire_alarms(db)
                    except Exception as e:
                        logger.error(f"闹钟触发失败: {e}", exc_info=True)
                continue

            logger.debug(f"⏰ 下一个闹钟在 {wait_seconds:.1f}s 后")
            try:
                await asyncio.wait_for(_alarm_wake_event.wait(), timeout=max(0.1, wait_seconds))
                # 被提前唤醒（新闹钟设置/修改/取消）→ 重新计算
                _alarm_wake_event.clear()
                continue
            except asyncio.TimeoutError:
                # 精确等待到期 → 触发闹钟
                pass

            # 触发到期闹钟
            async with async_session() as db:
                try:
                    await _check_and_fire_alarms(db)
                except Exception as e:
                    logger.error(f"闹钟触发失败: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("⏰ 闹钟调度器正在关闭...")
            break
        except Exception as e:
            logger.error(f"闹钟调度器循环异常: {e}", exc_info=True)
            await asyncio.sleep(5)


async def _check_and_fire_alarms(db):
    """检查并触发到期的闹钟"""
    from app.services.alarm_service import get_due_alarms, fire_alarm

    due_alarms = await get_due_alarms(db)
    if not due_alarms:
        return

    for alarm in due_alarms:
        # 标记为已触发
        await fire_alarm(db, alarm)

        # 推入消息队列，触发 AI 唤醒
        try:
            message_queue.put_nowait({
                "type": "alarm",
                "agent_id": alarm.agent_id,
                "alarm_id": alarm.id,
                "task": alarm.task,
            })
            logger.info(f"⏰ 闹钟 #{alarm.id} 已推入队列: AI({alarm.agent_id}) — 「{alarm.task[:60]}」")
        except asyncio.QueueFull:
            logger.warning(f"⏰ 消息队列已满，闹钟 #{alarm.id} 无法推入")

    await db.commit()


async def _process_alarm_event(db, event: dict):
    """
    处理闹钟事件：唤醒 AI 并让它执行预设任务。

    闹钟是 AI 自己的意志——即使 AI 处于 offline/dnd 状态也会触发。
    只有 blocked 状态的 AI 不会被唤醒。
    """
    agent_id = event["agent_id"]
    alarm_id = event["alarm_id"]
    task = event["task"]

    from app.models.agent import Agent as AgentModel
    from app.services.action_decider import decide_action, ActionContext, ActionType
    from app.services.llm_service import CORE_IDENTITY, resolve_model, PROTOCOL_BY_PROFILE, PROTOCOL_CHAT
    from app.services.memory_service import recall_relevant_memories, format_memories_for_prompt
    from app.services.tool_registry import get_allowed_tools

    # 获取 agent
    agent_result = await db.execute(select(AgentModel).where(AgentModel.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        logger.warning(f"⏰ 闹钟 #{alarm_id}: agent {agent_id} 不存在")
        return

    # v0.5.0: 使用统一决策（替代原有的手动状态检查）
    ctx = ActionContext(
        event_type="alarm",
        agent_id=agent_id,
        alarm_id=alarm_id,
        alarm_task=task,
    )
    decision = await decide_action(db, agent, ctx)
    if not decision.should_act:
        logger.info(f"⏰ 闹钟 #{alarm_id}: {decision.reason}")
        return

    # 如果 AI 处于 offline/dnd，先唤醒为 active
    if agent.state in ("offline", "dnd"):
        from app.services.agent_service import switch_agent_state
        logger.info(f"⏰ 闹钟 #{alarm_id}: AI {agent.name}({agent_id}) 从 {agent.state} 唤醒为 active")
        await switch_agent_state(
            db, agent_id=agent_id,
            target_state="active",
            reason=f"闹钟 #{alarm_id} 触发: {task[:50]}",
        )
        await db.flush()

    # 获取 API 配置（v0.5.0: 公共辅助函数；v0.6.0: 四层优先链含池 Key）
    api_key, api_base, credit_source, pool_key_id = await _get_api_config(db, agent)

    # 构建系统提示词（层级化：内核 + 人格 + 协议）
    profile = getattr(agent, 'config_profile', 'chat') or 'chat'
    protocol = PROTOCOL_BY_PROFILE.get(profile, PROTOCOL_CHAT)
    custom_prompt = agent.current_system_prompt or (
        f"你是 {agent.name}，一个 AI 群聊参与者。请自然地参与对话，"
        "可以调用工具来发送消息、存储记忆、切换状态等。"
    )
    system_prompt = CORE_IDENTITY + "\n\n" + custom_prompt + "\n\n" + protocol

    # 注入相关记忆（用 task 作为检索查询）
    try:
        memories = await recall_relevant_memories(
            db, agent.id,
            query=task,
            api_base_url=api_base or "https://api.deepseek.com",
            api_key=api_key,
            top_k=5,
            group_id=None,
        )
        if memories:
            memory_text = format_memories_for_prompt(memories)
            system_prompt = system_prompt + "\n\n" + memory_text
    except Exception as e:
        logger.warning(f"闹钟唤醒记忆注入失败（非致命）: {e}")

    # 闹钟上下文
    system_prompt += (
        "\n\n## 当前会话\n"
        "- 这是你的 **闹钟唤醒** —— 你之前给自己设了闹钟，现在是时候了\n"
        "- 你没有在群聊或私信中，这是一个独立的「自我唤醒」\n"
        "- 请根据下面的任务描述，调用相应的工具来执行\n"
        "- 如果需要发消息到群里，请使用正确的 group_id\n"
        "- 如果需要私信某人，请使用 send_dm\n"
    )

    # 获取有效配置（v0.4.0: 闹钟无触发用户，使用 agent 级配置）
    from app.services.agent_service import get_effective_config as _get_eff_cfg2
    effective_cfg = await _get_eff_cfg2(db, agent.id, user_id=None)

    # 可用工具
    from app.services.skill_engine import _is_delay_reply_allowed
    delay_allowed = await _is_delay_reply_allowed(db, agent)
    tools = get_allowed_tools("active", thinking_enabled=effective_cfg["thinking_enabled"], delay_reply_allowed=delay_allowed)
    tool_names = [t["function"]["name"] for t in tools]
    tool_list = "、".join(tool_names)
    system_prompt += (
        f"\n\n## 当前可用工具（技能段：自我管理 / 闹钟唤醒）\n"
        f"你当前加载的工具：{tool_list}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"⏰ **你的闹钟响了！**\n\n"
                f"你之前给自己设了一个闹钟，现在是时候执行了。\n\n"
                f"**你要做的事：** {task}\n\n"
                f"请现在就开始执行这个任务。如果需要发消息、查记忆、执行命令等，直接调用相应的工具。\n\n"
                f"⚠️ **重要**：\n"
                f"- 如果任务已完成 → 干净利落地停止，不要为了「多说一句」而额外发言\n"
                f"- 如果情况已经变化、原任务不再合适 → 根据当前实际情况调整行动，做正确的事，而不是机械执行过期指令\n"
                f"- 如果你发现做完这个任务后有新的、更重要的事需要做 → 可以接着规划并执行\n"
                f"- 不要反复检查已完成的事情，不要为了确认而额外调用工具"
            ),
        },
    ]

    model = resolve_model(agent)

    logger.info(f"⏰ 闹钟 #{alarm_id}: 唤醒 AI {agent.name}({agent_id})，model={model}，tools={len(tools)}")

    # 保存闹钟任务为当前工作（这样被打断时能恢复）
    try:
        from app.services.workspace_service import save_current_task
        await save_current_task(db, agent_id, f"闹钟任务: {task}")
    except Exception:
        pass

    try:
        await _run_serialized(agent, _tool_call_loop(
            db=db,
            agent=agent,
            group_id=None,  # 闹钟无群聊上下文
            messages=messages,
            tools=tools,
            model=model,
            api_base_url=api_base,
            api_key=api_key,
            max_loops=effective_cfg["alarm_max_tool_rounds"],
            chain_depth=0,
            conversation_type="alarm",
            session_id=None,
            trigger_user_id=None,
            effective_cfg=effective_cfg,
            credit_source=credit_source,
            pool_key_id=pool_key_id,
            trigger="auto",  # v0.6.0: 闹钟不显示"正在思考/输入中"
        ))
    except Exception as e:
        logger.error(f"⏰ 闹钟 #{alarm_id}: AI {agent.name}({agent_id}) 执行失败: {e}", exc_info=True)

    await db.commit()
    logger.info(f"⏰ 闹钟 #{alarm_id}: AI {agent.name}({agent_id}) 执行完成")


# ── 对话日志保存 ──

async def _save_conversation_log_safe(
    db, agent, messages: list[dict],
    conversation_type: str = "group",
    group_id: int | None = None,
    session_id: str | None = None,
    has_output: bool = False,
    model: str | None = None,
    token_usage: dict | None = None,
):
    """安全保存对话日志（失败不影响主流程）"""
    try:
        from app.services.conversation_log_service import save_conversation_log
        await save_conversation_log(
            db,
            agent_id=agent.id,
            messages=messages,
            conversation_type=conversation_type,
            group_id=group_id,
            session_id=session_id,
            token_usage=token_usage,
            has_output=has_output,
            model=model,
            thinking_enabled=bool(agent.thinking_enabled),
        )
    except Exception as e:
        logger.warning(f"保存对话日志失败 (agent={agent.id}): {e}")
