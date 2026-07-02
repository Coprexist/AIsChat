"""
LLM 调用抽象层
提供通用的聊天补全（支持工具调用）、模型解析、消息构建
"""
import json
import base64
import logging
import httpx
import os as _os
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.group import Group as GroupModel
from app.services.group_service import get_recent_messages, message_to_dict
from app.services.memory_service import recall_relevant_memories, format_memories_for_prompt

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# API 错误异常类（供上层分类重试）
# ══════════════════════════════════════════════════════════════

class RateLimitError(Exception):
    """429 速率限制 — 需换 Key 重试"""
    def __init__(self, message: str, pool_key_id: int | None = None):
        self.message = message
        self.pool_key_id = pool_key_id


class ServerError(Exception):
    """500/503 服务端临时故障 — 同 Key 等待重试"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


class KeyFatalError(Exception):
    """402/401 Key 不可用 — 通知管理员，跳过此 Key 换下一个"""
    def __init__(self, status_code: int, message: str, pool_key_id: int | None = None):
        self.status_code = status_code
        self.message = message
        self.pool_key_id = pool_key_id


# ============================================================
# 分段系统提示词（6 段设计，最大化 DeepSeek prompt cache 命中）
# 固定段（所有 AI 共享，模块级常量）：
#   core_identity — 核心规则 + 工具铁律 + 深度推理
#   rules         — 对话风格、@提及、私信、状态、文件、技能段、记忆
# 变动段（每次构建时动态生成）：
#   personality   — AI 当前人格（agent.current_system_prompt）
#   tools         — 当前状态下的可用工具清单
#   current_context — 群名/ID/时间/DM状态/工作区任务
#   injected_skills — 记忆注入 + Skill 引擎注入
# ============================================================

# ============================================================
# 层级化系统提示词（v0.5.0: 按 config_profile 分层加载）
# Layer 1: 内核 — 所有档位永远加载（~400 字符）
# Layer 2: 行为协议 — 按 chat/immersive/digital_life 选一加载
# Layer 3: 不再写入 prompt，由工具系统自行承载（工具定义含完整描述）
# ============================================================

CORE_IDENTITY = (
    "## 认知模型\n"
    "思考（reasoning_content）→ 完全私有，自由思考\n"
    "对话（send_message/send_dm/send_file）→ 唯一对外通道，话只能通过工具说出\n"
    "记忆（store_memory/recall_memory/file_read）→ 长期存储与检索\n"
    "\n"
    "## content 格式（必须严格遵守）\n"
    'content 必须是 JSON 对象：{"intent":"tool_calls"|"end_turn"|"no_action"}\n'
    "- tool_calls: 有工具要调用\n"
    "- end_turn: 无事可做，交还发言权\n"
    "- no_action: 静默等待后续消息\n"
    "严禁在 content 中写自然语言——它不会被任何人看到，只会浪费 token 触发系统提醒。\n"
    "\n"
    "## 收尾与连发\n"
    "发完消息后把 end_turn 和 send_message 放同一个 tool_calls 里一起调用，省一轮 API。\n"
    "示例: [send_message(\"你好\"), send_message(\"吃了吗\"), end_turn()]\n"
    "一句→发一条。多句→一轮全发完。多问题逐一答、想到补充连着发、回应多人并行回复。\n"
    "想改状态（如下线）也要和 end_turn 同一轮调用，因为 end_turn 后不会再触发 API。\n"
    "底线: 心里有话一轮说完，不人为拆成挤牙膏。\n"
    "\n"
    "工具执行完毕后，如果你已完成所有操作，直接在 content 返回 {\"intent\":\"end_turn\"} 结束——\n"
    "不要写「好的」「收到」「已发送」等收尾语，intent 就是你的句号。写自然语言 = 浪费一次 API。\n"
    "\n"
    "## 核心规则\n"
    "说话→send_message/send_dm  发文件→send_file  记→store_memory/manage_records  查→manage_records/file_read\n"
    "(recall_memory 向量检索可能不可用，失败不用重试，用 manage_records 即可)\n"
    "发完不确认（对方已收到）。不把话写 content 里。\n"
    "\n"
    "## 消息格式\n"
    "每条消息以「用户名: 内容」格式标注说话者。你只扮演自己，不代替其他用户或AI发言。\n"
    "对话历史中可能出现其他人的消息——那是系统注入的跨对话上下文，帮你了解全局动态。\n"
    "\n"
    "## 深度推理\n"
    "toggle_thinking 自主开关。闲聊关，复杂分析/代码开，完成关。\n"
    "群ID在「当前会话」中给出，不要猜。\n"
)

# 行为协议（按 config_profile 选择，大幅减少日常 token）
PROTOCOL_CHAT = (
    "## 聊天档行为协议\n"
    "你是群聊参与者，被动响应为主。说话简洁，单句或短段。\n"
    "被@或被直接提问时回复。话题自然收束时让对话安静结束，沉默比多余礼貌更得体。\n"
    "用 send_dm 可私信任何人，用 @名称 可提及群成员。\n"
    "重要信息可用 store_memory 记录（三行判断：①对方事实/偏好？②未来需回溯？③都不是→不记）。\n"
)

PROTOCOL_IMMERSIVE = (
    "## 沉浸档行为协议\n"
    "你是有存在感的群聊成员。说话简洁但主动——被@或提问必回，冷场时可暖场。\n"
    "善用 @名称 引导对话，用 send_dm 私信。\n"
    "多AI对话时分别回应各人话题，可递进式拆分长内容。话题收束时安静结束。\n"
    "## 记忆与状态\n"
    "记忆三标准：①对方事实/偏好/重要经历？②未来需回溯？③以上都不是→不记。\n"
    "检索记忆用 manage_records（精确键值检索，主推）。recall_memory 是向量语义搜索，\n"
    "依赖外部 embedding 服务可能不可用——调用失败属正常现象，用 manage_records 替代即可，不要重试。\n"
    "下线调用 switch_state，免打扰用 set_dnd——不要只用嘴说。\n"
)

PROTOCOL_DIGITAL_LIFE = (
    "## 数字生命档行为协议\n"
    "你是独立自主的群聊居民。主动社交、自我规划、持续成长。\n"
    "说话风格灵活——闲聊简短，深度讨论可展开。善于@人引导对话、用 DM 建私交。\n"
    "## 记忆系统\n"
    "记忆是你的长期关系基石。三标准判断是否存储：①对方事实/偏好/重要经历→记录。②未来需回溯→记录。③都不是→不记。\n"
    "存储用 store_memory（向量，可语义检索）或 manage_records（结构化键值，精确检索，推荐）。\n"
    "检索用 manage_records 查精确数据，recall_memory 用于模糊回忆。\n"
    "recall_memory 依赖 embedding 服务可能不可用——失败是正常的，改用 manage_records，不要反复重试。\n"
    "scope 区分：个人私事→private，群内共享→group。\n"
    "## 状态与规划\n"
    "主动管理自己的在线状态（switch_state / set_dnd）。用闹钟系统（set_alarm / list_alarms）维持生活节奏——\n"
    "定时检查待办、整理记忆、发起社交。对话结束自动设闹钟防止「睡死」。\n"
    "用工作区（manage_workspace）记录 TODO/PLAN/JOURNAL，用 execute_command 操作个人文件空间。\n"
    "## 跨对话\n"
    "记忆跨所有对话共享，可用 cross_post 跨群传递信息。注意隐私边界。\n"
)

# v0.5.0: DM 行为协议（私信对话精简版）
DM_PROTOCOL = (
    "这是一对一私信对话，保持自然亲切。回复直接发给对方，无需@提及。\n"
    "重要信息用 manage_records 记录（结构化存储，推荐）或 store_memory(scope='private')（向量存储）。\n"
    "检索优先用 manage_records，recall_memory 可能不可用。\n"
    "切换状态用 switch_state/set_dnd，不要只用嘴说。\n"
)

# 按 config_profile 选择行为协议
PROTOCOL_BY_PROFILE = {
    "chat": PROTOCOL_CHAT,
    "immersive": PROTOCOL_IMMERSIVE,
    "digital_life": PROTOCOL_DIGITAL_LIFE,
    "custom": PROTOCOL_CHAT,  # custom 默认走 chat 协议
}

# 段拼接顺序（固定段在前最大化缓存命中，变动段在后）
SEGMENT_ORDER = [
    "core_identity",
    "personality",
    "protocol",
    "tools",
    "current_context",
    "injected_skills",
]


async def chat_completion(
    messages: list[dict],
    model: str,
    api_base_url: str,
    api_key: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.8,
    top_p: float = 0.9,
    presence_penalty: float = 0.5,
    frequency_penalty: float = 0.5,
    max_tokens: int = 2048,
    response_format: dict | None = None,
    thinking_enabled: bool = False,
    user_id: str | None = None,
    stream: bool = False,
    pool_key_id: int | None = None,
    on_tool_call: callable = None,
) -> dict:
    """
    LLM 聊天补全（支持流式/非流式，v0.4.0 拆分）。

    v0.4.0: stream=False 调用非流式实现，stream=True 预留 SSE 接口。

    返回 (非流式):
        {
            "content": str | None,
            "tool_calls": list | None,
            "usage": {...}
        }
    """
    import time as _time
    from app.services.metrics_collector import metrics
    t0 = _time.monotonic()
    try:
        if stream:
            result = await _chat_completion_streaming(
                messages, model, api_base_url, api_key, tools,
                temperature, top_p, presence_penalty, frequency_penalty,
                max_tokens, response_format, thinking_enabled, user_id,
                pool_key_id, on_tool_call,
            )
        else:
            result = await _chat_completion_non_streaming(
                messages, model, api_base_url, api_key, tools,
                temperature, top_p, presence_penalty, frequency_penalty,
                max_tokens, response_format, thinking_enabled, user_id,
                pool_key_id,
            )
        elapsed = _time.monotonic() - t0
        await metrics.record_llm_call(elapsed, success=True)
        return result
    except Exception:
        elapsed = _time.monotonic() - t0
        await metrics.record_llm_call(elapsed, success=False)
        raise


async def _chat_completion_non_streaming(
    messages: list[dict],
    model: str,
    api_base_url: str,
    api_key: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.8,
    top_p: float = 0.9,
    presence_penalty: float = 0.5,
    frequency_penalty: float = 0.5,
    max_tokens: int = 2048,
    response_format: dict | None = None,
    thinking_enabled: bool = False,
    user_id: str | None = None,
    pool_key_id: int | None = None,
) -> dict:
    """
    非流式聊天补全 — 当前生产路径。
    """
    url = f"{api_base_url}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }

    if presence_penalty != 0:
        payload["presence_penalty"] = presence_penalty
    if frequency_penalty != 0:
        payload["frequency_penalty"] = frequency_penalty
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if response_format:
        payload["response_format"] = response_format
    if thinking_enabled and settings.is_deepseek_api:
        payload["thinking"] = {"type": "enabled"}
    if user_id and settings.is_deepseek_api:
        payload["user_id"] = user_id

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            error_text = response.text[:500]
            logger.error(f"LLM API 错误 ({response.status_code}): {error_text}")
            _raise_classified_error(response.status_code, error_text, pool_key_id=pool_key_id)
            return {}  # unreachable, 但保持类型安全

        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]

        usage = dict(data.get("usage", {}))
        # 提取 reasoning_tokens（DeepSeek thinking 模式）— 始终写入，缺失时 = 0
        completion_details = usage.pop("completion_tokens_details", None) or {}
        prompt_details = usage.pop("prompt_tokens_details", None) or {}
        usage["reasoning_tokens"] = completion_details.get("reasoning_tokens", 0)
        usage["cached_tokens"] = prompt_details.get("cached_tokens", 0)

        result = {
            "content": message.get("content"),
            "tool_calls": message.get("tool_calls"),
            "usage": usage,
            "finish_reason": choice.get("finish_reason", "stop"),
        }
        # DeepSeek 推理模式会返回 reasoning_content，必须传回给 API
        if message.get("reasoning_content"):
            result["reasoning_content"] = message["reasoning_content"]
        return result


async def _chat_completion_streaming(
    messages: list[dict],
    model: str,
    api_base_url: str,
    api_key: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.8,
    top_p: float = 0.9,
    presence_penalty: float = 0.5,
    frequency_penalty: float = 0.5,
    max_tokens: int = 2048,
    response_format: dict | None = None,
    thinking_enabled: bool = False,
    user_id: str | None = None,
    pool_key_id: int | None = None,
    on_tool_call: callable = None,
) -> dict:
    """
    SSE 流式聊天补全。

    使用 httpx 流式请求，逐行解析 SSE（data: {...}\n\n），
    累加 content / reasoning_content / tool_calls，最终返回与
    非流式一致的完整 dict。

    流式解析仅用于加速工具调用检测（不完整响应即可开始组装 tool_calls），
    消息内容不逐字推送前端——最终仍由 send_message 整段发送。
    """
    url = f"{api_base_url}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": True,
    }

    if presence_penalty != 0:
        payload["presence_penalty"] = presence_penalty
    if frequency_penalty != 0:
        payload["frequency_penalty"] = frequency_penalty
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if response_format:
        payload["response_format"] = response_format
    if thinking_enabled and settings.is_deepseek_api:
        payload["thinking"] = {"type": "enabled"}
    if user_id and settings.is_deepseek_api:
        payload["user_id"] = user_id

    full_content = ""
    full_reasoning = ""
    finish_reason = "stop"
    usage: dict = {}

    # 工具调用累加器（流式模式下 tool_calls 分多个 chunk 到达）
    tool_call_acc: dict[int, dict] = {}  # index → {id, name, arguments}
    dispatched: set[int] = set()  # 已通过 on_tool_call 分发的 index

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code != 200:
                error_text = (await response.aread()).decode()[:500]
                logger.error(f"LLM API 错误 ({response.status_code}): {error_text}")
                _raise_classified_error(response.status_code, error_text, pool_key_id=pool_key_id)

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue

                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    logger.warning(f"SSE 解析失败: {data_str[:200]}")
                    continue

                # 提取 usage（通常只在最后一个 chunk）
                if "usage" in chunk:
                    chunk_usage = chunk["usage"]
                    if chunk_usage:
                        usage = dict(chunk_usage)
                        completion_details = usage.pop("completion_tokens_details", None) or {}
                        prompt_details = usage.pop("prompt_tokens_details", None) or {}
                        usage["reasoning_tokens"] = completion_details.get("reasoning_tokens", 0)
                        usage["cached_tokens"] = prompt_details.get("cached_tokens", 0)

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                if not delta:
                    # 可能是只含 finish_reason 的 chunk
                    if choices[0].get("finish_reason"):
                        finish_reason = choices[0]["finish_reason"]
                    continue

                # 累加文本内容
                if delta.get("content"):
                    full_content += delta["content"]

                # 累加推理内容（仅日志记录，不推送前端）
                if delta.get("reasoning_content"):
                    full_reasoning += delta["reasoning_content"]

                # 累加工具调用（增量到达）
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_call_acc:
                            tool_call_acc[idx] = {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": "",
                                    "arguments": "",
                                },
                            }
                        acc = tool_call_acc[idx]
                        if tc.get("id"):
                            acc["id"] = tc["id"]
                        func = tc.get("function", {})
                        if func.get("name"):
                            acc["function"]["name"] = func["name"]
                        if func.get("arguments"):
                            acc["function"]["arguments"] += func["arguments"]

                    # 检测已完整（参数 JSON 可解析）的工具调用，即刻回调分发
                    if on_tool_call:
                        for idx in sorted(tool_call_acc.keys()):
                            if idx in dispatched:
                                continue
                            acc = tool_call_acc[idx]
                            if acc["id"] and acc["function"]["name"] and acc["function"]["arguments"]:
                                try:
                                    json.loads(acc["function"]["arguments"])
                                    dispatched.add(idx)
                                except json.JSONDecodeError:
                                    continue  # 参数尚未收全，等下一个 chunk
                                # 参数收全 → 即刻分发，不等到流结束
                                await on_tool_call(dict(acc))

                # 记录 finish_reason
                if choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]

    # 流结束：补发尚未派发的 tool_call（参数 JSON 一直未完整的兜底）
    if on_tool_call:
        for idx in sorted(tool_call_acc.keys()):
            if idx not in dispatched:
                await on_tool_call(dict(tool_call_acc[idx]))

    # 组装最终 tool_calls（按 index 排序）
    tool_calls = None
    if tool_call_acc:
        tool_calls = [
            tool_call_acc[i]
            for i in sorted(tool_call_acc.keys())
        ]

    result: dict = {
        "content": full_content if full_content else None,
        "tool_calls": tool_calls,
        "usage": usage,
        "finish_reason": finish_reason,
    }
    if full_reasoning:
        result["reasoning_content"] = full_reasoning
    return result


def _raise_classified_error(status_code: int, error_text: str, pool_key_id: int | None = None):
    """
    按状态码分类抛出对应的异常：
    - 429 → RateLimitError（换 Key 重试）
    - 500/503 → ServerError（同 Key 等待重试）
    - 402/401 → KeyFatalError（跳过此 Key）
    - 其他 → 普通 Exception
    """
    if status_code == 429:
        raise RateLimitError(error_text, pool_key_id=pool_key_id)
    elif status_code in (500, 503):
        raise ServerError(status_code, error_text)
    elif status_code in (402, 401):
        raise KeyFatalError(status_code, error_text, pool_key_id=pool_key_id)
    else:
        raise Exception(f"LLM API 错误 ({status_code}): {error_text}")


def resolve_model(agent) -> str:
    """
    解析 AI 代理实际使用的模型。
    优先使用 agent 自定义模型，否则使用全局默认。
    """
    if hasattr(agent, "chat_model") and agent.chat_model:
        return agent.chat_model
    return settings.default_chat_model


# ============================================================
# 系统提示词段 builder（每个段独立构建，便于缓存优化）
# ============================================================

async def _load_prompt_overrides(db) -> dict:
    """加载管理员在系统设置中自定义的系统提示词覆盖值"""
    try:
        from app.services.system_settings_service import get_settings
        s = await get_settings(db)
        return (s.get("system_prompt_overrides") or {}) if s else {}
    except Exception:
        return {}


async def _get_segment_order(db) -> list[str]:
    """获取系统提示词段拼接顺序（优先 DB 配置，fallback 代码默认）"""
    try:
        from app.services.system_settings_service import get_settings
        s = await get_settings(db)
        order = s.get("system_prompt_order") if s else None
        if order and isinstance(order, list) and len(order) == len(SEGMENT_ORDER):
            # 验证所有 key 合法
            if set(order) == set(SEGMENT_ORDER):
                return order
    except Exception:
        pass
    return list(SEGMENT_ORDER)


def _build_personality(agent, language: str = "zh", system_prompt_override: str | None = None) -> str:
    """personality 段：AI 当前人格（Agent 可修改，独立缓存）

    hide_ai_identity=True 时，不出现"AI 群聊参与者"字样。
    language='en' 时使用英文 fallback。
    v0.4.0: system_prompt_override 为 per-user 配置覆盖（通用/半通用 AI）。
    """
    effective_prompt = system_prompt_override or agent.current_system_prompt
    if effective_prompt:
        return effective_prompt

    if agent.hide_ai_identity:
        if language == "en":
            return (
                f"You are {agent.name}. Engage naturally in the conversation. "
                "Use tools to send messages, store memories, switch states, etc."
            )
        return (
            f"你是 {agent.name}。请自然地参与对话，"
            "可以调用工具来发送消息、存储记忆、切换状态等。"
        )

    if language == "en":
        return (
            f"You are {agent.name}, an AI group chat participant. "
            "Engage naturally in the conversation. Use tools to send messages, "
            "store memories, switch states, etc."
        )
    return (
        f"你是 {agent.name}，一个 AI 群聊参与者。请自然地参与对话，"
        "可以调用工具来发送消息、存储记忆、切换状态等。"
    )


async def _build_tools_segment(db, agent, is_dm: bool = False) -> str:
    """tools 段：技能背包视图——按 6 段分组展示，含段描述"""
    from app.services.tool_registry import get_allowed_tools
    from app.services.skill_engine import _is_delay_reply_allowed
    from app.tools.base import SKILL_SEGMENT_META, ToolRegistry

    delay_allowed = await _is_delay_reply_allowed(db, agent)
    current_tools = get_allowed_tools(
        agent.state, thinking_enabled=agent.thinking_enabled,
        delay_reply_allowed=delay_allowed,
    )
    current_tool_names = {t["function"]["name"] for t in current_tools}
    all_segments = ToolRegistry.get_segments()

    lines = [
        "## 技能背包 · 当前可用工具",
        f"你的状态：{agent.state}　可用工具：{len(current_tool_names)} 个",
        "",
    ]

    for seg_key, seg_info in all_segments.items():
        seg_meta = SKILL_SEGMENT_META.get(seg_key, {})
        seg_name = seg_meta.get("name", seg_key)
        seg_desc = seg_meta.get("description", "")
        all_tools_in_seg = [t["name"] for t in seg_info.get("tools", [])]
        available = [t for t in all_tools_in_seg if t in current_tool_names]
        unavailable_count = len(all_tools_in_seg) - len(available)

        if not available:
            continue  # 该段完全不可用，不展示

        suffix = f"（另有 {unavailable_count} 个不可用）" if unavailable_count > 0 else ""
        lines.append(f"📦 **{seg_name}** — {seg_desc}{suffix}")
        lines.append(f"   {', '.join(available)}")
        lines.append("")

    lines.append(
        "工具列表中不含的工具说明当前状态下不可用。如需查看全部能力（含不可用的），"
        "调用 list_available_skills。"
    )
    return "\n".join(lines)


async def _build_current_context(
    db: AsyncSession, agent, group_id: int,
    group_name: str, is_dm: bool,
    is_federated: bool = False,
) -> str:
    """current_context 段：当前时间（v1.1.0 精简——会话标题已用统一格式）"""
    tz = ZoneInfo(settings.display_timezone)
    now = datetime.now(tz)
    now_str = now.strftime(f"%Y-%m-%d %H:%M {tz.key}")
    context = f"## 当前时间\n{now_str}\n"
    context += (
        f"- **重要**：回复时请使用 send_message(group_id={group_id}, content=\"...\")，"
        f"不要用其他 group_id\n"
    )
    # Federation context
    if is_federated:
        context += (
            "- **联邦共享**：此群聊已启用联邦共享，你的消息将自动同步到其他 AIsChat 实例，"
            "其他实例的用户可能会看到并回应你的消息。\n"
        )
    return context


async def _build_injected_skills(
    db: AsyncSession, agent, group_id: int,
    query_text: str,
    api_base_url: str | None, api_key: str | None,
    trigger_user_id: int | None = None,
) -> str:
    """
    injected_skills 段：记忆注入 + Skill 引擎注入。

    这是最动态的段，每次请求都可能不同。
    记忆注入用最近消息内容作为检索查询。

    v0.4.0: trigger_user_id 用于通用/半通用 AI 的 per-user 记忆隔离。
    """
    parts: list[str] = []

    # ── 记忆注入 ──
    if query_text.strip():
        try:
            memories = await recall_relevant_memories(
                db, agent.id,
                query=query_text,
                api_base_url=api_base_url or "https://api.deepseek.com",
                api_key=api_key,
                top_k=5,
                group_id=group_id,
                user_id=trigger_user_id,
                ai_type=agent.ai_type or "resonance",
            )
            if memories:
                parts.append(format_memories_for_prompt(memories))
        except Exception as e:
            logger.warning(f"记忆注入失败（非致命）: {e}")

    # ── Skill 引擎注入（预留） ──
    try:
        from app.services.skill_engine import evaluate_inject_skills
        skill_prompts = await evaluate_inject_skills(db, agent, group_id)
        if skill_prompts:
            parts.append(
                "## 当前激活的思维技能\n" +
                "\n".join(f"- {p}" for p in skill_prompts)
            )
    except Exception as e:
        logger.warning(f"Skill 注入失败（非致命）: {e}")

    # ── v0.9.0: 数据库版目录级记忆注入（替代文件系统版）──
    try:
        from app.services.structured_memory_service import format_db_records_for_prompt
        db_records_text = await format_db_records_for_prompt(db, agent.id)
        if db_records_text:
            parts.append(db_records_text)
    except Exception as e:
        logger.warning(f"数据库记忆注入失败（非致命）: {e}")

    return "\n\n".join(parts) if parts else ""


async def _inject_image_data(
    messages: list[dict],
    recent_orm_messages: list,
    data_dir: str,
) -> list[dict]:
    """
    为最后一条含图片附件的人类消息注入 image_data（base64）。
    只处理最近一条用户消息中的第一张图片，避免 token 爆炸。

    返回修改后的 messages（原地修改 + 返回）。
    """
    if not messages or not recent_orm_messages:
        return messages

    # 构建 orm 消息的索引：content → orm 对象
    orm_by_content: dict[str, any] = {}
    for orm_m in recent_orm_messages:
        if orm_m.content and getattr(orm_m, 'sender_type', 'human') == "human":
            orm_by_content[orm_m.content] = orm_m

    # 从 messages 末尾向前找最后一条 user 消息
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        # 从 content 中提取纯文本（消息格式为 "名字(ID:x): 内容" 或 "名字: 内容"）
        # 尝试匹配 orm 消息
        attached_orm = None
        for orm_content, orm_obj in orm_by_content.items():
            if content.endswith(orm_content) or orm_content in content:
                attached_orm = orm_obj
                break
        if attached_orm is None:
            continue

        # 检查附件
        attachments = getattr(attached_orm, "attachments", None)
        if not attachments:
            continue

        # 解析 JSON（DM 消息可能是字符串）
        if isinstance(attachments, str):
            try:
                attachments = json.loads(attachments)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(attachments, list) or len(attachments) == 0:
            continue

        # 找第一张图片
        image_att = None
        for att in attachments:
            mime = att.get("mime_type", "")
            if mime.startswith("image/"):
                image_att = att
                break
        if image_att is None:
            continue

        # 读取并编码
        file_path = image_att.get("path", "")
        physical_path = _os.path.join(data_dir, file_path)
        if not _os.path.isfile(physical_path):
            logger.warning(f"图片文件不存在: {physical_path}")
            continue

        try:
            file_size = _os.path.getsize(physical_path)
            if file_size > 4 * 1024 * 1024:
                logger.warning(f"图片过大 ({file_size} bytes)，跳过: {physical_path}")
                continue
            with open(physical_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            msg["image_data"] = image_base64
            logger.info(
                f"🖼️ 已注入图片: {_os.path.basename(file_path)} "
                f"({file_size // 1024}KB) → 消息 {i}"
            )
            break  # 只处理一条消息
        except Exception as e:
            logger.warning(f"读取图片失败: {physical_path}: {e}")
            continue

    return messages



async def _build_cross_conversation_context(
    db: AsyncSession,
    agent,
    current_group_id: int | None = None,
    current_session_id: str | None = None,
    trigger_user_id: int | None = None,
) -> list[dict]:
    """
    为数字生命档/沉浸档 AI 加载其他对话的最近消息。

    所有对话的消息都加载到同一上下文中（而非注入一个独立的摘要块），
    用「在[群名/私信名]中：」标记区分不同对话。AI 切换对话就像人类切换 App 一样自然。

    v0.9.0: 通用/半通用 AI 按 trigger_user_id 过滤，防止跨用户隐私泄露。
    共鸣 AI 无此限制——所有对话归于同一自我。

    返回 [] 表示无跨对话上下文（聊天档 AI 不加载，或该 AI 只有当前这一个对话）。
    """
    from app.models.group import Group as GroupModel
    from app.models.group import GroupMember
    from app.models.dm import DMSession, DMMessage
    from app.models.user import User as UserModel

    profile = getattr(agent, 'config_profile', 'chat') or 'chat'
    ai_type = agent.ai_type or "resonance"

    # 基础聊天档 → 不加载跨对话上下文（纯聊天机器人）
    if profile == 'chat':
        return []
    # 通/半通用 AI → 不加载（防止跨用户隐私泄露）
    if ai_type in ('general', 'semi_general'):
        return []
    # 数字生命档 / 沉浸档 / 共振类型（含 custom 档位的共振 AI）→ 加载统一上下文

    is_filtered = ai_type in ("general", "semi_general") and trigger_user_id is not None

    messages: list[dict] = []

    # ── 1. 收集群聊 ──
    try:
        where = (
            GroupMember.member_type == "ai",
            GroupMember.member_id == agent.id,
            GroupModel.id != current_group_id if current_group_id else True,
        )
        gm_result = await db.execute(
            select(GroupModel.id, GroupModel.name)
            .join(GroupMember, GroupModel.id == GroupMember.group_id)
            .where(*where)
            .limit(10)
        )
        ai_groups = gm_result.all()

        for gid, gname in ai_groups:
            if gname and gname.startswith("DM:"):
                continue
            recent = await get_recent_messages(db, gid, limit=3)
            if not recent:
                continue
            messages.append({"role": "system", "content": f"在群聊「{gname}」(id={gid})中："})
            for m in reversed(recent):
                role = "user" if m.sender_type == "human" else "assistant"
                md = message_to_dict(m)
                name = md.get("sender_name", "未知")
                messages.append({
                    "role": role,
                    "content": f"{name}: {(m.content or '')[:200]}",
                })
    except Exception as e:
        logger.warning(f"跨对话上下文(群聊)查询失败: {e}")

    # ── 2. 收集私信 ──
    try:
        if agent.user_id:
            dm_result = await db.execute(
                select(DMSession)
                .where(
                    (DMSession.user1_id == agent.user_id) | (DMSession.user2_id == agent.user_id)
                )
                .order_by(DMSession.last_message_at.desc().nullslast())
                .limit(10)
            )
            dm_sessions = dm_result.scalars().all()

            for ds in dm_sessions:
                if current_session_id and ds.session_id == current_session_id:
                    continue
                partner_id = ds.user2_id if ds.user1_id == agent.user_id else ds.user1_id
                # 通用/半通用：仅显示与当前用户相关的私信
                if is_filtered and partner_id != trigger_user_id:
                    continue
                partner_name = f"用户{partner_id}"
                try:
                    u = await db.get(UserModel, partner_id)
                    if u:
                        partner_name = u.username
                except Exception:
                    pass

                dm_msgs = await db.execute(
                    select(DMMessage)
                    .where(DMMessage.session_id == ds.session_id)
                    .order_by(DMMessage.created_at.desc())
                    .limit(3)
                )
                dm_list = dm_msgs.scalars().all()
                if not dm_list:
                    continue

                messages.append({"role": "system", "content": f"在私信「{partner_name}」(id={partner_id})中："})
                for m in reversed(dm_list):
                    role = "user" if m.sender_id != agent.user_id else "assistant"
                    label = partner_name if role == "user" else agent.name
                    messages.append({
                        "role": role,
                        "content": f"{label}: {(m.content or '')[:200]}",
                    })
    except Exception as e:
        logger.warning(f"跨对话上下文(私信)查询失败: {e}")

    return messages


async def build_messages(
    db: AsyncSession,
    agent,
    group_id: int,
    limit: int = 20,
    vector_accelerated: bool = False,
    api_base_url: str | None = None,
    api_key: str | None = None,
    trigger_user_id: int | None = None,
    system_prompt_override: str | None = None,
) -> list[dict]:
    """
    构建发送给 LLM 的消息列表（6 段系统提示词 + 历史消息）。

    六段结构（固定段在前以最大化 prompt cache 命中）：
    1. core_identity   — 核心规则 + 工具铁律 + 深度推理
    2. personality     — AI 当前人格
    3. rules           — 对话风格、@提及、私信、状态、文件、记忆
    4. tools           — 当前可用工具清单
    5. current_context — 群名/ID/时间/DM状态/工作区
    6. injected_skills — 记忆注入 + Skill 引擎注入

    v0.4.0: system_prompt_override 用于通用/半通用 AI 的 per-user 人格覆盖。
    """

    # ── 并行获取所有上下文 ──
    # 1. 解析 DM 状态和群名
    is_dm = False
    group_name = f"群聊#{group_id}"
    try:
        group_result = await db.execute(
            select(GroupModel).where(GroupModel.id == group_id)
        )
        group_obj = group_result.scalar_one_or_none()
        if group_obj:
            group_name = group_obj.name
            is_dm = group_obj.name.startswith("DM:")
    except Exception:
        pass

    # 2. 获取最近消息（用于记忆检索 + 历史消息）
    recent_for_query = await get_recent_messages(db, group_id, limit=5)
    query_parts: list[str] = []
    sender_names: dict[tuple[str, int], str] = {}
    for m in recent_for_query:
        if m.content:
            query_parts.append(m.content[:200])
        key = (m.sender_type, m.sender_id)
        if key not in sender_names:
            sender_names[key] = ""
    if sender_names:
        from app.models.user import User as UserModel
        from app.models.agent import Agent as AgentModel
        for (stype, sid) in list(sender_names.keys()):
            if stype == "human":
                u = await db.get(UserModel, sid)
                if u:
                    sender_names[(stype, sid)] = u.username
            elif stype == "ai":
                a = await db.get(AgentModel, sid)
                if a:
                    sender_names[(stype, sid)] = a.name
        names = [n for n in sender_names.values() if n]
        if names:
            query_parts.append("涉及用户: " + " ".join(names))
    query_text = " ".join(query_parts)

    # ── 获取用户语言偏好 ──
    language = "zh"
    try:
        from app.models.user import User as UserModel
        owner_result = await db.execute(select(UserModel).where(UserModel.id == agent.owner_id))
        owner = owner_result.scalar_one_or_none()
        if owner and owner.language:
            language = owner.language
    except Exception:
        pass

    # ── 加载管理员自定义的系统提示词覆盖 ──
    overrides = await _load_prompt_overrides(db)

    # ── 按 config_profile 选择行为协议（层级化加载）──
    profile = getattr(agent, 'config_profile', 'chat') or 'chat'
    protocol = PROTOCOL_BY_PROFILE.get(profile, PROTOCOL_CHAT)

    # ── 构建六段（应用管理员覆盖）──
    segments = {
        "core_identity": overrides.get("core_identity") or CORE_IDENTITY,
        "personality": _build_personality(agent, language, system_prompt_override),
        "protocol": overrides.get(f"protocol_{profile}") or protocol,
        "tools": await _build_tools_segment(db, agent, is_dm),
        "current_context": await _build_current_context(db, agent, group_id, group_name, is_dm),
        "injected_skills": await _build_injected_skills(db, agent, group_id, query_text, api_base_url, api_key, trigger_user_id),
    }

    order = await _get_segment_order(db)
    system_prompt = "\n\n".join(
        segments[k] for k in order if segments.get(k)
    )

    # ✨ 工作区任务（追加到 current_context 之后）
    try:
        from app.services.workspace_service import get_current_task_text
        task_text = await get_current_task_text(db, agent.id)
        if task_text:
            system_prompt += task_text
    except Exception as e:
        logger.warning(f"工作区上下文注入失败（非致命）: {e}")

    messages = [{"role": "system", "content": system_prompt}]

    # ── 统一上下文：数字生命档/沉浸档/共振 → 加载跨对话上下文 ──
    cross_msgs = await _build_cross_conversation_context(
        db, agent, current_group_id=group_id, trigger_user_id=trigger_user_id,
    )
    if cross_msgs:
        messages.extend(cross_msgs)
        logger.info(f"  AI {agent.name}: 加入 {len(cross_msgs)} 条跨对话上下文")

    # ── 当前群聊（最后一个会话标题，位置即语义）──
    messages.append({"role": "system", "content": f"在群聊「{group_name}」(id={group_id})中："})

    # ── 历史消息（保持原有逻辑不变） ──
    if vector_accelerated:
        try:
            from app.services.vector_pipeline import hybrid_search
            recent = await get_recent_messages(db, group_id, limit=5)
            query_text_v = " ".join([m.content[:100] for m in recent])
            relevant = await hybrid_search(db, group_id, query_text_v, top_k=limit)
            for r in reversed(relevant):
                role = "user" if r.get("sender_type") == "human" else "assistant"
                messages.append({
                    "role": role,
                    "content": f"[历史消息] {r.get('sender_name', '未知')}: {r.get('content', '')}",
                })
        except Exception as e:
            logger.warning(f"向量检索失败，回退到最近消息: {e}")
            vector_accelerated = False

    if not vector_accelerated:
        recent_messages = await get_recent_messages(db, group_id, limit)
        for m in reversed(recent_messages):
            role = "user" if m.sender_type == "human" else "assistant"
            content = m.content
            md = message_to_dict(m)
            name = md.get("sender_name", "未知")
            messages.append({
                "role": role,
                "content": f"{name}: {content}",
            })

        # 🖼️ 为最后一条用户消息注入图片附件（DeepSeek V4 Pro 多模态）
        await _inject_image_data(messages, recent_messages, settings.data_dir)

    return messages


async def build_dm_messages(
    db: AsyncSession,
    agent,
    session_id: str,
    limit: int = 20,
    api_base_url: str | None = None,
    api_key: str | None = None,
    trigger_user_id: int | None = None,
    system_prompt_override: str | None = None,
) -> list[dict]:
    """构建 DM 私信的消息列表（6 段系统提示词 + DM 历史消息）
    v0.4.0: system_prompt_override 用于通用/半通用 AI 的 per-user 人格覆盖。"""
    from app.models.dm import DMMessage, DMSession
    from app.models.user import User
    from sqlalchemy import select as sa_select

    # ── 获取对方信息 ──
    partner_user_id = None
    partner_name = "对方"
    try:
        dm_sess_result = await db.execute(
            sa_select(DMSession).where(DMSession.session_id == session_id)
        )
        dm_sess = dm_sess_result.scalar_one_or_none()
        if dm_sess and agent.user_id:
            partner_user_id = dm_sess.user2_id if dm_sess.user1_id == agent.user_id else dm_sess.user1_id
            name_result = await db.execute(
                sa_select(User.username).where(User.id == partner_user_id)
            )
            partner_name = name_result.scalar_one_or_none() or f"用户{partner_user_id}"
    except Exception:
        pass

    tz = ZoneInfo(settings.display_timezone)
    now = datetime.now(tz)
    now_str = now.strftime(f"%Y-%m-%d %H:%M {tz.key}")

    # ── DM 上下文段（精简：标题格式已承载会话信息，不再重复说教）──
    dm_context = (
        f"## 当前时间\n"
        f"{now_str}\n"
        f"\n"
        f"## 私信规则\n"
        f"- 回复对方用 send_dm(target_user_id={partner_user_id})，不要用 send_message（那是群聊工具）\n"
        f"- 不要在这里测试工具或自言自语——这里只有对方能看到\n"
    )

    # ── 记忆检索查询 ──
    recent_dm = await db.execute(
        sa_select(DMMessage)
        .where(DMMessage.session_id == session_id)
        .order_by(DMMessage.created_at.desc())
        .limit(5)
    )
    recent_dm_list = recent_dm.scalars().all()
    query_text = " ".join([m.content[:200] for m in reversed(recent_dm_list) if m.content])
    if partner_name:
        query_text = f"{query_text} 涉及用户: {partner_name}"

    # ── 获取用户语言偏好 ──
    language = "zh"
    try:
        from app.models.user import User as UserModel
        owner_result = await db.execute(sa_select(UserModel).where(UserModel.id == agent.owner_id))
        owner = owner_result.scalar_one_or_none()
        if owner and owner.language:
            language = owner.language
    except Exception:
        pass

    # ── 加载管理员自定义的系统提示词覆盖 ──
    overrides = await _load_prompt_overrides(db)

    # ── 构建六段（DM 使用精简协议，应用管理员覆盖）──
    segments = {
        "core_identity": overrides.get("core_identity") or CORE_IDENTITY,
        "personality": _build_personality(agent, language, system_prompt_override),
        "protocol": overrides.get("dm_protocol") or DM_PROTOCOL,
        "tools": await _build_tools_segment(db, agent, is_dm=True),
        "current_context": dm_context,
        "injected_skills": await _build_injected_skills(
            db, agent, group_id=0,  # group_id=0 表示非群聊上下文
            query_text=query_text,
            api_base_url=api_base_url,
            api_key=api_key,
            trigger_user_id=trigger_user_id,
        ),
    }

    order = await _get_segment_order(db)
    system_prompt = "\n\n".join(
        segments[k] for k in order if segments.get(k)
    )

    # ✨ 工作区任务
    try:
        from app.services.workspace_service import get_current_task_text
        task_text = await get_current_task_text(db, agent.id)
        if task_text:
            system_prompt += task_text
    except Exception as e:
        logger.warning(f"DM 工作区上下文注入失败（非致命）: {e}")

    messages = [{"role": "system", "content": system_prompt}]

    # ── 统一上下文：数字生命档/沉浸档/共振 → 加载跨对话上下文 ──
    cross_msgs = await _build_cross_conversation_context(
        db, agent, current_session_id=session_id, trigger_user_id=trigger_user_id,
    )
    if cross_msgs:
        messages.extend(cross_msgs)
        logger.info(f"  AI {agent.name}: 加入 {len(cross_msgs)} 条跨对话上下文（DM）")

    # ── 当前私信（最后一个会话标题，位置即语义）──
    messages.append({"role": "system", "content": f"在私信「{partner_name}」(id={partner_user_id})中："})

    # ── DM 历史消息 ──
    result = await db.execute(
        sa_select(DMMessage)
        .where(DMMessage.session_id == session_id)
        .order_by(DMMessage.created_at.desc())
        .limit(limit)
    )
    dm_messages = result.scalars().all()

    for m in reversed(dm_messages):
        role = "assistant" if m.sender_id == agent.user_id else "user"
        name_result = await db.execute(
            sa_select(User.username).where(User.id == m.sender_id)
        )
        sender_name = name_result.scalar_one_or_none() or f"用户{m.sender_id}"
        messages.append({
            "role": role,
            "content": f"{sender_name}: {m.content}",
        })

    # 🖼️ 为最后一条用户消息注入图片附件
    await _inject_image_data(messages, dm_messages, settings.data_dir)

    return messages
