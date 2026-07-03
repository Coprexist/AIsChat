"""
纯字符串/格式化函数——无 IO，无副作用。
"""
import json


def format_log_as_markdown(log: dict) -> str:
    """将对话日志 dict 格式化为 Markdown 字符串（纯函数）。"""
    lines = [
        f"# AI 对话日志 #{log.get('id')}",
        f"",
        f"- **AI ID**: {log.get('agent_id')}",
        f"- **类型**: {log.get('conversation_type')}",
        f"- **模型**: {log.get('model', 'N/A')}",
        f"- **深度推理**: {'开启' if log.get('thinking_enabled') else '关闭'}",
        f"- **消息数**: {log.get('message_count')}",
        f"- **有输出**: {'是' if log.get('has_output') else '否'}",
        f"- **时间**: {log.get('created_at', 'N/A')}",
        f"",
    ]
    token_usage = log.get('token_usage')
    if token_usage:
        lines.append(f"- **Token 用量**: {json.dumps(token_usage, ensure_ascii=False)}")
        lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    messages = log.get('messages', [])
    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                    elif part.get('type') == 'image_url':
                        parts.append('[图片]')
                    elif part.get('type') == 'tool_use':
                        parts.append(f"[工具调用: {part.get('name', '')}]")
                    elif part.get('type') == 'tool_result':
                        parts.append(f"[工具结果]")
                    else:
                        parts.append(json.dumps(part, ensure_ascii=False))
            content = '\n'.join(parts)

        tool_calls = msg.get('tool_calls')
        reasoning = msg.get('reasoning_content')

        if role == 'system':
            lines.append(f"### 📋 System")
        elif role == 'user':
            lines.append(f"### 👤 User")
        elif role == 'assistant':
            lines.append(f"### 🤖 Assistant")
        elif role == 'tool':
            lines.append(f"### 🔧 Tool")
        else:
            lines.append(f"### {role}")

        lines.append(f"")

        if reasoning:
            lines.append(f"> **推理过程**:")
            lines.append(f"> ")
            for rl in reasoning.split('\n'):
                lines.append(f"> {rl}")
            lines.append(f"")

        if content:
            lines.append(content)
            lines.append(f"")

        if tool_calls:
            lines.append(f"**工具调用**:")
            for tc in (tool_calls if isinstance(tool_calls, list) else [tool_calls]):
                fn = tc.get('function', {}) if isinstance(tc, dict) else {}
                lines.append(f"- `{fn.get('name', tc.get('name', 'unknown'))}`")
                args = fn.get('arguments', tc.get('arguments', ''))
                if args:
                    lines.append(f"  ```json")
                    lines.append(f"  {args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}")
                    lines.append(f"  ```")
            lines.append(f"")

        lines.append(f"---")
        lines.append(f"")

    return '\n'.join(lines)


def mask_api_key(encrypted: str) -> str:
    """脱敏显示 API Key——密文为空返回空，否则显示 ****...后4位。"""
    if not encrypted:
        return ""
    if len(encrypted) <= 4:
        return "****"
    return "****" + encrypted[-4:]
