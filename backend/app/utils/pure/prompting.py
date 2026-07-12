"""
提示词构建纯函数——无 IO，无副作用。

所有函数只做字符串/数据结构变换，不访问 DB、网络、文件系统。
"""

from datetime import datetime, timedelta, timezone


# ═══════════════════════════════════════════════════════════════
# 模型解析
# ═══════════════════════════════════════════════════════════════

def resolve_model(agent, default_model: str = "deepseek-v4-flash") -> str:
    """
    解析 AI 代理实际使用的模型（纯函数）。
    优先使用 agent 自定义模型，否则使用传入的默认值。
    """
    if hasattr(agent, "chat_model") and agent.chat_model:
        return agent.chat_model
    return default_model


# ═══════════════════════════════════════════════════════════════
# 个性段
# ═══════════════════════════════════════════════════════════════

def build_personality_segment(
    agent,
    language: str = "zh",
    system_prompt_override: str | None = None,
) -> str:
    """
    personality 段：AI 当前人格（纯函数）。

    hide_ai_identity=True 时，不出现"AI 群聊参与者"字样。
    language='en' 时使用英文 fallback。
    system_prompt_override 为 per-user 配置覆盖（通用/半通用 AI）。
    """
    effective_prompt = system_prompt_override or getattr(agent, 'current_system_prompt', None)
    name = getattr(agent, 'name', 'AI')
    hide = getattr(agent, 'hide_ai_identity', False)

    if effective_prompt:
        # 即使有自定义提示词，也要确保 AI 知道自己的名字，
        # 避免 core_identity 中的示例名造成身份混淆
        if language == "en":
            name_line = f"Your name is {name}."
        else:
            name_line = f"你的名字是 {name}。"
        # 如果提示词已以「你是/你叫/Your name is/You are」开头，不再重复
        starts_with_name = any(
            effective_prompt.lstrip().startswith(p)
            for p in ("你是", "你叫", "Your name is", "You are", "You're")
        )
        if starts_with_name:
            return effective_prompt
        return f"{name_line}\n\n{effective_prompt}"

    if hide:
        if language == "en":
            return (
                f"You are {name}. Engage naturally in the conversation. "
                "Use tools to send messages, store memories, switch states, etc."
            )
        return (
            f"你是 {name}。请自然地参与对话，"
            "可以调用工具来发送消息、存储记忆、切换状态等。"
        )

    if language == "en":
        return (
            f"You are {name}, an AI group chat participant. "
            "Engage naturally in the conversation. Use tools to send messages, "
            "store memories, switch states, etc."
        )
    return (
        f"你是 {name}，一个 AI 群聊参与者。请自然地参与对话，"
        "可以调用工具来发送消息、存储记忆、切换状态等。"
    )


# ═══════════════════════════════════════════════════════════════
# 时间格式化
# ═══════════════════════════════════════════════════════════════

def format_time_shanghai(dt: datetime) -> str:
    """UTC → 上海时间 (UTC+8)，标注时区让 AI 理解每个用户的时间（纯函数）。"""
    shanghai = timezone(timedelta(hours=8))
    local = dt.replace(tzinfo=timezone.utc).astimezone(shanghai)
    return f"Shanghai {local.strftime('%m-%d %H:%M')}"


# ═══════════════════════════════════════════════════════════════
# 消息格式化
# ═══════════════════════════════════════════════════════════════

def format_message(msg: dict, agent_name: str = "", max_content_len: int = 200) -> str:
    """
    纯函数：统一格式化单条消息。多会话上下文、当前对话、向量检索全部走这里。
    结构化输入 → 一行文本输出。

    msg 结构: {time, speaker_name, speaker_id?, is_self?, content, prefix?}
    """
    parts: list[str] = []
    if msg.get("time"):
        parts.append(f"[{msg['time']}]")
    if msg.get("prefix"):
        parts.append(msg["prefix"])

    if msg.get("is_self"):
        speaker = f"你（{agent_name}）"
    elif msg.get("speaker_id") is not None:
        speaker = f"{msg['speaker_name']}（id={msg['speaker_id']}）"
    else:
        speaker = msg.get("speaker_name", "未知")

    content = msg.get('content', '')
    if max_content_len > 0:
        content = content[:max_content_len]
    parts.append(f"{speaker}: {content}")
    return " ".join(parts)


def format_context_for_ai(conversations: list[dict], agent_name: str) -> list[dict]:
    """
    纯函数：将结构化跨对话数据转为 AI 可读的 system 消息列表。
    内部调用 format_message() 统一格式化。

    v2.0.3: 添加强禁令 + 消息截断，防止 LLM 把历史存档当活跃对话回复。
    """
    messages: list[dict] = []
    if conversations:
        messages.append({
            "role": "system",
            "content": (
                "⚠️ 以下是你在**其他群/私信**中的**历史消息存档**。"
                "这些消息来自不同对话，**绝对不是当前群的消息**。"
                "你**禁止**回复这些存档中的任何内容——它们不在当前对话中。"
                "你**禁止**在当前群用 send_gm 回复存档中的人。"
                "把存档当作新闻摘要，看完即可，不要互动。"
            ),
        })
    for conv in conversations:
        if conv["type"] == "group":
            header = f"在群聊「{conv['name']}」(id={conv['id']})中："
        else:
            header = f"在私信「{conv['name']}」(id={conv['id']})中："
        messages.append({"role": "system", "content": header})
        for m in conv["messages"]:
            # 跨对话消息截断到 30 字符，只保留话题线索
            truncated = dict(m)
            truncated["content"] = m["content"][:30]
            messages.append({
                "role": "system",
                "content": format_message(truncated, agent_name),
            })
    return messages


# ═══════════════════════════════════════════════════════════════
# 提示词组装
# ═══════════════════════════════════════════════════════════════

def assemble_system_prompt(segments: dict[str, str], order: list[str]) -> str:
    """
    纯函数：按指定顺序拼接各段为完整系统提示词。
    双换行分隔各段。
    """
    parts = []
    for key in order:
        if key in segments and segments[key]:
            parts.append(segments[key])
    return "\n\n".join(parts)
