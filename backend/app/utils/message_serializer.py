"""
通用消息序列化器
将 Message（群聊）和 DMMessage（私信）ORM 对象统一转为 dict，
消除 dm_service 和 group_service 中的重复序列化逻辑。
"""
import json


def make_preview(content: str | None, attachments: list | None = None, max_len: int = 50) -> str:
    """生成消息预览文本。

    纯附件无文字 → 显示 [文件]（超出 1 个则 [N个文件]）；
    有文字 → 截取前 max_len 个字符。
    """
    if content:
        preview = content[:max_len]
        if len(content) > max_len:
            preview += "..."
        return preview
    if attachments:
        count = len(attachments)
        return "[文件]" if count == 1 else f"[{count}个文件]"
    return ""


def serialize_message(message, *,
                      sender_name=None,
                      sender_type=None,
                      sender_avatar_url=None,
                      conversation_key='group_id',
                      include_read_at=False) -> dict:
    """将消息 ORM 对象序列化为字典。

    兼容 Message (群聊) 和 DMMessage (私信) 两种模型，
    通过 getattr 鸭子类型访问字段，用参数处理模型差异。

    Args:
        message: Message 或 DMMessage ORM 实例
        sender_name: 发送者名称（ORM 字段为 None 时使用）
        sender_type: 发送者类型（ORM 字段为 None 时使用）
        sender_avatar_url: 发送者头像 URL（ORM 字段为 None 时使用）
        conversation_key: 会话 ID 键名，群聊用 'group_id'，私信用 'session_id'
        include_read_at: 是否包含 read_at 字段（私信有，群聊无）
    """
    # sender_name: 参数优先于 ORM 字段（联邦消息通过 ORM 字段存储）
    effective_name = sender_name or getattr(message, 'sender_name', None)

    # sender_type: 参数优先于 ORM 字段（DMMessage 无此字段，靠调用方传入）
    effective_type = sender_type or getattr(message, 'sender_type', None)

    # sender_avatar_url: ORM 优先于参数（Message 模型 ORM 存储联邦权威值），空值统一归一到 None
    # 注意：与 sender_name/type 的参数优先策略不同——avatar 在联邦场景下由 _download_remote_avatar
    # 后台下载后写入 DB，DB 值比消息中的临时 URL 更权威。
    effective_avatar = getattr(message, 'sender_avatar_url', None) or sender_avatar_url or None

    # attachments: JSONB 自动反序列化，Text 列需手动 json.loads
    attachments = getattr(message, 'attachments', None)
    if isinstance(attachments, str):
        try:
            attachments = json.loads(attachments)
        except (json.JSONDecodeError, TypeError):
            attachments = None

    conversation_value = getattr(message, conversation_key, None)

    result = {
        "id": message.id,
        conversation_key: conversation_value,
        "sender_type": effective_type,
        "sender_id": message.sender_id,
        "sender_name": effective_name,
        "sender_avatar_url": effective_avatar,
        "content": message.content,
        "reply_to": getattr(message, 'reply_to', None),
        "source_public_id": getattr(message, 'source_public_id', None),
        "attachments": attachments,
        "created_at": str(message.created_at) if message.created_at else None,
    }

    # message_type（DMMessage 有，Message 没有，默认 'normal'）
    mt = getattr(message, 'message_type', None)
    if mt:
        result["message_type"] = mt

    if include_read_at:
        m_read_at = getattr(message, 'read_at', None)
        result["read_at"] = str(m_read_at) if m_read_at else None

    return result
