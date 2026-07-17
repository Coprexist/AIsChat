# 从 app/ai/response_worker.py 抽离 — 工具执行引擎
"""
工具执行引擎：LLM 调用 + 工具循环 + API 配置 + 额度管理。

职责：
- 执行 _tool_call_loop（AI 的核心执行循环）
- 管理 API Key 选择、速率限制、Key 错误日志
- 发送系统错误通知
- 保存对话日志
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from sqlalchemy import select
from app.config import settings
from app.database import async_session
from app.chat import chat_api

logger = logging.getLogger(__name__)

# 速率限制：{agent_id: last_call_timestamp}
_rate_limit_tracker: dict[int, float] = {}


# ============================================================
# 系统错误通知
# ============================================================

async def _send_system_error(
    db, agent, error_type: str, detail: str = "",
    conversation_type: str = "group",
    group_id: int | None = None,
    session_id: str | None = None,
):
    """发送分类系统错误通知给 AI 的 owner（走 DM）"""
    from app.models.dm import DMMessage, DMSession

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

        dm_session = await chat_api.get_or_create_dm_session(db, SYSTEM_USER_ID, owner_id)
        dm_sid = dm_session.session_id

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
            await chat_api.broadcast_to_dm(dm_sid, {
                "type": "new_dm_message",
                "message": {
                    "id": dm_msg.id,
                    "session_id": dm_sid,
                    "sender_id": SYSTEM_USER_ID,
                    "sender_name": "系统通知",
                    "sender_avatar_url": None,
                    "content": content,
                    "created_at": dm_msg.created_at.isoformat() if dm_msg.created_at else None,
                    "is_system": True,
                },
            })
        except Exception:
            pass
        logger.info(f"📬 系统通知已发送给 AI {agent.name}({agent.id}) 的 Owner({owner_id})")
    except Exception as e:
        logger.error(f"  发送系统通知失败: {e}")


# ============================================================
# API 配置获取
# ============================================================

async def _get_api_config(
    db, agent,
    exclude_pool_key_id: int | None = None,
    chatter_id: int | None = None,
    force_own_key: bool = False,
    conversation_type: str | None = None,
) -> tuple[str | None, str, str, int | None, dict]:
    """
    获取 API Key 和 Base URL（四层优先链 + 平台赠送额度）。

    Tier 1: Agent 自有 Key
    Tier 2: 账单人有可用额度 → API Key 池
    Tier 3: 账单人有 api_credit + 无绑定 → 自动选最优池 Key
    Tier 4: 账单人自有 Key

    v0.9.0: chatter_id 决定账单人（通用 AI 扣聊天者，否则扣主人）。
            force_own_key=True 时跳过 Tier 2/3，直接走账单人自有 Key。
    v1.0.2: 返回 provider_info 字典，含 thinking_supported / models / base_url。
    v1.1.0: conversation_type + group_owner_pays 控制群聊账单人。

    返回: (api_key, api_base, credit_source, pool_key_id, provider_info)
    """
    from app.utils.crypto import decrypt_api_key
    from app.models.user import User as UserModel

    api_key = None
    api_base = settings.deepseek_base_url
    credit_source = "none"
    pool_key_id = None
    provider_info = {"thinking_supported": settings.is_deepseek_api, "base_url": api_base}

    # 确定账单人
    # v1.1.0: 群聊 + group_owner_pays → 主人付（即使 AI 是通用/半通用）
    if conversation_type and conversation_type != "dm" and getattr(agent, 'group_owner_pays', True):
        bill_user_id = agent.owner_id
    elif chatter_id and agent.ai_type in ("general", "semi_general"):
        bill_user_id = chatter_id  # DM + 通用/半通用 → 聊天者付
    else:
        bill_user_id = agent.owner_id  # 其余 → 主人付

    # Tier 1: Agent 自有 Key
    if agent.api_key_encrypted:
        api_key = decrypt_api_key(agent.api_key_encrypted)
        api_base = agent.api_base_url or settings.deepseek_base_url
        credit_source = "agent_key"
        provider_info = {"thinking_supported": "deepseek.com" in api_base, "base_url": api_base}
        return api_key, api_base, credit_source, pool_key_id, provider_info

    # 查账单用户
    user_result = await db.execute(select(UserModel).where(UserModel.id == bill_user_id))
    user = user_result.scalar_one_or_none()

    if user is None:
        return api_key, api_base, credit_source, pool_key_id, provider_info

    # force_own_key: 跳过池 Key，直接走用户自有 Key
    if force_own_key:
        if user.api_key_encrypted:
            api_key = decrypt_api_key(user.api_key_encrypted)
            api_base = user.api_base_url or settings.deepseek_base_url
            credit_source = "user_key"
            provider_info = {"thinking_supported": "deepseek.com" in api_base, "base_url": api_base}
        return api_key, api_base, credit_source, pool_key_id, provider_info

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
                # v1.0.2: 获取池 Key 的供应商配置
                from app.services.system_settings_service import get_provider_for_pool_key
                pool_provider = await get_provider_for_pool_key(db, pool_key)
                provider_info = {
                    "thinking_supported": pool_provider.get("thinking_supported", "deepseek.com" in api_base),
                    "base_url": api_base,
                    "provider_name": pool_provider.get("name", ""),
                }
                return api_key, api_base, credit_source, pool_key_id, provider_info
            except Exception as e:
                logger.warning(f"  ⚠️ 池 Key {pool_key.id} 解密失败: {e}，回退到用户自有 Key")

    # Tier 4: 用户自有 Key
    if user.api_key_encrypted:
        api_key = decrypt_api_key(user.api_key_encrypted)
        api_base = user.api_base_url or settings.deepseek_base_url
        credit_source = "user_key"
        provider_info = {"thinking_supported": "deepseek.com" in api_base, "base_url": api_base}

    return api_key, api_base, credit_source, pool_key_id, provider_info


# ============================================================
# 工具调用循环
# ============================================================

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
    provider_supports_thinking: bool | None = None,
    trigger: str = "user",
    is_federated: bool = False,
):
    """
    工具调用循环：LLM 必须通过工具调用来执行所有操作（包括发消息）。

    铁律：文字不能自动发出去。想说话必须调 send_gm（群聊）或 send_dm（私信）。

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
        "manager": chat_api,  # v1.x: ChatApi 代替原 ConnectionManager
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
                current_api_key, current_api_base, current_credit_source, current_pool_key_id, _ = \
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
                if tool_name in ("send_gm", "send_dm") and trigger == "user":
                    _typing_data: dict = {"agent_id": agent.id, "agent_name": agent.name, "agent_avatar_url": agent.avatar_url, "trigger": trigger}
                    if conversation_type == "dm" and session_id:
                        _typing_data["session_id"] = session_id
                    elif group_id is not None:
                        _typing_data["group_id"] = group_id
                    _typing_event = {"type": "ai_typing", "conversation_type": conversation_type, "data": _typing_data}
                    try:
                        if conversation_type == "dm" and session_id:
                            await chat_api.broadcast_to_dm(session_id, _typing_event)
                        elif group_id is not None:
                            await chat_api.broadcast_to_group(group_id, _typing_event)
                    except Exception:
                        pass
                # 任务摘要追踪
                _work_tools = {
                    "execute_command": lambda a: f"执行命令: {a.get('command', '?')}",
                    "store_memory": lambda a: f"存储记忆: {a.get('title', '?')}",
                    "file_write": lambda a: f"写文件: {a.get('file_path', '?')}",
                    "file_read": lambda a: f"读文件: {a.get('file_path', '?')}",
                    "file_delete": lambda a: f"删除文件: {a.get('file_path', '?')}",
                    "send_gm": lambda a: f"在群聊中发言: {str(a.get('content', ''))[:40]}",
                    "send_dm": lambda a: f"发私信: {str(a.get('content', ''))[:40]}",
                    "send_friend_request": lambda a: f"发送好友申请: {a.get('message', '?')[:40]}",
                    "toggle_thinking": lambda a: f"切换深度推理: {'开启' if a.get('enabled') else '关闭'}",
                    "manage_workspace": lambda a: f"管理工作区: {a.get('action', '?')} — {a.get('section', '?')}",
                    "set_alarm": lambda a: f"设置闹钟: {a.get('reason', '?')[:40]}",
                    "push_state": lambda a: f"切换上下文: {a.get('doing', '?')[:40]}",
                    "pop_state": lambda a: "结束当前任务，恢复上一层",
                    "close_state": lambda a: "关闭状态帧",
                    "list_states": lambda a: "查看状态栈",
                    "enter_group": lambda a: f"进入群聊: {a.get('group_id', '?')}",
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
                from app.services.context_compressor import should_compress, inline_compress, get_compression_threshold
                compress_threshold = await get_compression_threshold(db)
                # 12 小时闲置强制压缩：缓存肯定过期，压缩省 token
                stale = _is_conversation_idle(messages, hours=12)
                if stale or should_compress(messages, threshold=compress_threshold):
                    logger.info(
                        f"AI {agent.name}({agent.id}) 上下文超过阈值，内联压缩中..."
                    )
                    messages, compress_stats = inline_compress(messages)
                    if compress_stats.get("compressed"):
                        logger.info(
                            f"AI {agent.name}({agent.id}) 内联压缩完成："
                            f"{compress_stats['before_tokens']} → {compress_stats['after_tokens']} tokens"
                        )
                        # 压缩时应用 lazy tag 的 pending 更改
                        try:
                            from app.services.agent_service import apply_pending_config
                            await apply_pending_config(db, agent)
                        except Exception:
                            pass
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
                            provider_supports_thinking=provider_supports_thinking,
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
        parsed_intent = None
        if content:
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "intent" in parsed:
                    parsed_intent = parsed["intent"]
            except (json.JSONDecodeError, TypeError):
                pass

        # ── end_turn / no_action：AI 明确表示本轮结束 ──
        if parsed_intent in ("end_turn", "no_action") and not tool_calls and not _pending_results:
            logger.info(
                f"AI {agent.name}({agent.id}) intent={parsed_intent}，本轮结束"
            )
            if last_task:
                try:
                    from app.services.workspace_service import save_current_task
                    from app.services.state_stack_service import persist_last_task_as_state
                    await save_current_task(db, agent.id, last_task)
                    await persist_last_task_as_state(
                        db, agent.id, last_task, group_id,
                        context_ref=f"group:{group_id}" if group_id else "",
                    )
                except Exception:
                    pass
            await _save_conversation_log_safe(
                db, agent, messages, conversation_type,
                group_id, session_id,
                has_output=bool(content), model=model,
                token_usage=total_usage,
            )
            return

        # ── 提醒：有文字但没有工具调用（兜底机制）──
        reminder_grace = getattr(agent, 'reminder_grace', 'every_time')
        if reminder_grace == 'off':
            reminder_max = 0
        elif reminder_grace == 'once':
            reminder_max = 1
        else:  # 'every_time'
            reminder_max = 10
        if content and not tool_calls and not _pending_results and _reminder_extra < reminder_max:
            logger.info(
                f"AI {agent.name}({agent.id}) 返回了文字但无工具调用"
                f"（intent={parsed_intent or '解析失败'}），"
                f"注入提醒: {content[:80]}"
            )
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
                        "文字不能自动发送——如果你想在群聊发言，请调用 send_gm 工具；私信请用 send_dm。"
                        "括号表情可以写在 send_gm/send_dm 的 content 里发出去，"
                        "但不能只返回括号文字而不调工具。"
                        "请现在就调用 send_gm/send_dm 或你需要的其他工具。"
                        "如果你决定不再继续回复，请调用 end_turn 工具来结束本轮。"
                    ),
                }, ensure_ascii=False),
            })
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
                    from app.services.state_stack_service import persist_last_task_as_state
                    await save_current_task(db, agent.id, last_task)
                    await persist_last_task_as_state(
                        db, agent.id, last_task, group_id,
                        context_ref=f"group:{group_id}" if group_id else "",
                    )
                except Exception:
                    pass
            await _save_conversation_log_safe(
                db, agent, messages, conversation_type,
                group_id, session_id,
                has_output=bool(content), model=model,
                token_usage=total_usage,
            )
            return

        # ── 有工具调用 → 执行 ──
        assistant_msg: dict = {"role": "assistant", "content": content}
        assistant_msg["tool_calls"] = tool_calls
        if response.get("reasoning_content"):
            assistant_msg["reasoning_content"] = response["reasoning_content"]
        messages.append(assistant_msg)

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
                    from app.services.state_stack_service import persist_last_task_as_state
                    await save_current_task(db, agent.id, last_task)
                    await persist_last_task_as_state(
                        db, agent.id, last_task, group_id,
                        context_ref=f"group:{group_id}" if group_id else "",
                    )
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

    # 循环耗尽
    if last_task:
        try:
            from app.services.workspace_service import save_current_task
            await save_current_task(db, agent.id, last_task)
        except Exception:
            pass
    # v0.9.0: LLM 调用后扣除额度
    if total_usage["api_calls"] > 0 and total_usage["total_tokens"] > 0:
        try:
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


# ============================================================
# 速率限制
# ============================================================

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


# ============================================================
# Key 致命错误日志
# ============================================================

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
    except Exception as e:
        logger.error(f"记录 Key 致命错误失败: {e}")


# ============================================================
# 对话日志保存
# ============================================================

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


# ============================================================
# 检查对话是否闲置
# ============================================================

def _is_conversation_idle(messages: list[dict], hours: int = 12) -> bool:
    """检查对话最后一条消息是否超过指定小时数——缓存大概率已过期，应强制压缩"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for m in reversed(messages):
        content = m.get("content", "")
        if not isinstance(content, str):
            continue
        # 匹配 "[Shanghai 07-11 23:01]" 格式的时间戳（无年份）
        m2 = re.search(r'\[([A-Za-z_]+) (\d{2}-\d{2} \d{2}:\d{2})\]', content)
        if m2:
            time_str = m2.group(2)
            for offset in (0, -1):
                try:
                    year = now.year + offset
                    msg_time = datetime.strptime(f"{year}-{time_str}", "%Y-%m-%d %H:%M")
                    if msg_time > now and offset == 0:
                        continue
                    idle_seconds = (now - msg_time).total_seconds()
                    return idle_seconds > hours * 3600
                except ValueError:
                    pass
        break  # 只看最后一条消息
    return False
