"""
上下文压缩服务

当 _tool_call_loop 中的消息列表增长到接近模型上下文窗口时，
自动压缩中间消息为摘要，保留 system prompt（维持 prompt cache 命中）
和最近 N 条消息。

压缩策略：
- 保留 messages[0]（system prompt）—— 不变动以最大化 prompt cache 命中
- 保留 messages[-K:]（最近 K 条消息，默认 5）
- 中间部分 → 调用 LLM 生成摘要（使用工作模型，max_tokens=800）
- 摘要以 system 角色注入到 system prompt 之后

同时提供 compress_context 工具让 AI 主动触发压缩。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 默认上下文窗口（DeepSeek V4 为 128K）
DEFAULT_CONTEXT_WINDOW = 128_000
# 压缩阈值：v1.0.1 大幅降低——常态压缩以稳定 prompt cache 前缀
# 旧值 0.8（~102K tokens）基本不触发；新值 ~8K tokens 即触发
COMPRESSION_THRESHOLD = 0.06
# 压缩后至少保留的最近消息数
DEFAULT_KEEP_LAST_N = 5
# 压缩用摘要的最大 token 数
SUMMARY_MAX_TOKENS = 800
# messages 总数低于此值不压缩
MIN_MESSAGES_FOR_COMPRESSION = 8


def estimate_tokens(messages: list[dict]) -> int:
    """
    简单 token 估算：字符数 / 4。
    对中英文混合场景足够准确（英文 ~4 char/token，中文 ~1.5 char/token，
    取 4 作为保守估计，确保不会低估）。

    只计算 role 和 content 字段的字符数，跳过 metadata（如 tool_calls 结构）
    后续可替换为 tiktoken 精确计数。
    """
    total_chars = 0
    for m in messages:
        for key in ("role", "content"):
            val = m.get(key, "")
            if isinstance(val, str):
                total_chars += len(val)
    return total_chars // 4


def should_compress(
    messages: list[dict],
    context_window: int = DEFAULT_CONTEXT_WINDOW,
    threshold: float = COMPRESSION_THRESHOLD,
    min_messages: int = MIN_MESSAGES_FOR_COMPRESSION,
) -> bool:
    """判断是否需要压缩上下文"""
    if len(messages) < min_messages:
        return False
    estimated = estimate_tokens(messages)
    return estimated >= int(context_window * threshold)


def build_compression_prompt(messages_to_compress: list[dict]) -> str:
    """
    构建压缩提示词。要求 LLM 将中间消息总结为简洁的对话摘要。
    """
    # 将待压缩消息格式化为可读文本
    conversation_text_parts = []
    for m in messages_to_compress:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if isinstance(content, str) and content.strip():
            # 截断过长内容
            truncated = content[:2000] + "…" if len(content) > 2000 else content
            label = {"user": "用户", "assistant": "AI", "tool": "工具结果", "system": "系统"}.get(role, role)
            conversation_text_parts.append(f"[{label}] {truncated}")
        elif m.get("tool_calls"):
            tc_names = [tc.get("function", {}).get("name", "?") for tc in m.get("tool_calls", [])]
            conversation_text_parts.append(f"[AI 调用工具] {', '.join(tc_names)}")

    conversation_text = "\n".join(conversation_text_parts)

    return (
        "请将以下对话历史压缩为一份简洁的摘要。摘要应包含：\n"
        "1. 讨论了哪些话题\n"
        "2. AI 执行了哪些关键操作（工具调用及其结果）\n"
        "3. 做出了哪些决定\n"
        "4. 当前未完成的事项（如有）\n\n"
        "要求：使用中文，简洁但信息完整，不超过 500 字。\n\n"
        "=== 对话历史 ===\n"
        f"{conversation_text}\n"
        "=== 结束 ===\n\n"
        "请输出摘要："
    )


async def compress_messages(
    messages: list[dict],
    api_base_url: str,
    api_key: str,
    model: str,
    keep_system: bool = True,
    keep_last_n: int = DEFAULT_KEEP_LAST_N,
    user_id: str | None = None,
) -> tuple[list[dict], dict]:
    """
    压缩消息列表。

    参数:
        messages: 当前消息列表
        api_base_url: LLM API 地址
        api_key: API 密钥
        model: 压缩用的模型（建议用工作模型）
        keep_system: 是否保留第一条 system 消息
        keep_last_n: 保留最近 N 条消息
        user_id: DeepSeek API user_id（用于 prompt cache 命名空间）

    返回:
        (new_messages, stats) — 压缩后的消息列表和统计信息
    """
    from app.services.llm_service import chat_completion

    original_count = len(messages)
    original_tokens = estimate_tokens(messages)

    # 确定保留范围
    start_idx = 1 if (keep_system and messages and messages[0].get("role") == "system") else 0
    end_idx = max(start_idx, original_count - keep_last_n)

    if end_idx <= start_idx:
        # 没有可压缩的内容
        logger.info(f"上下文压缩跳过：无可压缩消息（total={original_count}, keep_last={keep_last_n}）")
        return messages, {
            "compressed": False,
            "reason": "无可压缩消息",
            "before_tokens": original_tokens,
            "after_tokens": original_tokens,
        }

    # 中间部分需要压缩
    messages_to_compress = messages[start_idx:end_idx]
    logger.info(
        f"上下文压缩：总消息 {original_count} 条，"
        f"压缩中间 {len(messages_to_compress)} 条，"
        f"保留后 {keep_last_n} 条，"
        f"估算 token: {original_tokens}"
    )

    # 构建压缩请求
    compression_prompt = build_compression_prompt(messages_to_compress)
    compression_messages = [
        {"role": "user", "content": compression_prompt},
    ]

    try:
        response = await chat_completion(
            messages=compression_messages,
            model=model,
            api_base_url=api_base_url,
            api_key=api_key,
            temperature=0.3,       # 低温度，保持准确
            max_tokens=SUMMARY_MAX_TOKENS,
            user_id=user_id,
            stream=False,
        )
        summary = (response.get("content") or "").strip()
        if not summary:
            raise ValueError("LLM 返回空摘要")
    except Exception as e:
        logger.error(f"上下文压缩失败（LLM 摘要调用出错）: {e}")
        # 压缩失败不阻塞主流程，返回原消息列表
        return messages, {
            "compressed": False,
            "reason": f"摘要生成失败: {e}",
            "before_tokens": original_tokens,
            "after_tokens": original_tokens,
        }

    # 组装新消息列表
    new_messages = []
    if keep_system and messages and messages[0].get("role") == "system":
        new_messages.append(messages[0])  # system prompt 不变，保持 cache 命中

    # 注入摘要消息（system 角色，放在 system prompt 之后）
    summary_msg = {
        "role": "system",
        "content": f"[上下文摘要 — 以下是之前对话的压缩版本]\n{summary}",
    }
    new_messages.append(summary_msg)

    # 保留最近 N 条
    new_messages.extend(messages[end_idx:])

    new_tokens = estimate_tokens(new_messages)
    compression_ratio = round((1 - new_tokens / max(original_tokens, 1)) * 100)

    stats = {
        "compressed": True,
        "before_count": original_count,
        "after_count": len(new_messages),
        "compressed_count": len(messages_to_compress),
        "before_tokens": original_tokens,
        "after_tokens": new_tokens,
        "compression_ratio_pct": compression_ratio,
        "summary_length": len(summary),
    }

    logger.info(
        f"上下文压缩完成：{original_count} → {len(new_messages)} 条消息，"
        f"token 估算 {original_tokens} → {new_tokens}（压缩 {compression_ratio}%），"
        f"摘要长度 {len(summary)} 字符"
    )

    return new_messages, stats
