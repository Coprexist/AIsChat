"""
send_file 工具 — AI 将已有文件作为附件引用发送（不复制存储）
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class SendFile(ToolPlugin):
    name = "send_file"
    description = (
        "将你文件空间中已有的文件作为附件发送到群聊或私信。"
        "文件必须先通过 file_write 创建（会自动注册到文件系统）。"
        "群聊用 group_id，私信用 target_user_id（二选一）。"
        "可选附带文字说明 content。"
    )
    segment = "chat_social"
    parameters = {
        "file_path": {"type": "string", "description": "文件路径（你在 file_write/file_read 中使用的相对路径，如 workspace/report.md）"},
        "group_id": {"type": "integer", "nullable": True, "description": "目标群聊 ID（群聊时填写）"},
        "target_user_id": {"type": "integer", "nullable": True, "description": "目标用户 ID（私信时填写）"},
        "content": {"type": "string", "nullable": True, "description": "附带的文字说明（可选）"},
    }
    required = ["file_path"]
    states = ["active"]
    admin_description = "在群聊中发送文件。AI 分享工作成果、资料或图片时调用，支持引用已有文件。"
    trigger_condition = "AI 需要分享文件到群聊时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.models.file import FileMetadata
        from app.services.group_service import create_message as create_group_message, message_to_dict
        from app.services.dm_service import send_dm_message, get_or_create_dm_session
        from app.models.agent import Agent as AgentModel

        file_path = arguments["file_path"]
        target_group = arguments.get("group_id", group_id)
        target_user = arguments.get("target_user_id")
        caption = (arguments.get("content") or "").strip()

        # ── 校验：group_id 和 target_user_id 二选一 ──
        if target_group is not None and target_user is not None:
            return {"error": True, "message": "不能同时指定 group_id 和 target_user_id，请二选一"}
        if target_group is None and target_user is None and group_id is None:
            return {"error": True, "message": "请指定 group_id（群聊）或 target_user_id（私信）"}
        if target_group is None:
            target_group = group_id

        # ── 查找文件元数据（AI 自己的文件，零拷贝引用） ──
        result = await db.execute(
            select(FileMetadata).where(
                FileMetadata.path == file_path,
                FileMetadata.owner_type == "ai",
                FileMetadata.owner_id == agent_id,
            )
        )
        metadata = result.scalar_one_or_none()

        if not metadata:
            return {
                "error": True,
                "message": (
                    f"文件不存在: {file_path}。"
                    "请先用 file_write 写入文件（会自动注册），再用 send_file 发送。"
                ),
            }

        attachment_info = {
            "file_id": metadata.id,
            "name": file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
            "path": metadata.path,
            "size": metadata.size,
            "mime_type": metadata.mime_type or "application/octet-stream",
        }

        # ── AI 名称和头像 ──
        agent_name = context.get("agent_name", f"AI:{agent_id}")
        sender_avatar = None
        agent_user_id = None
        try:
            a_result = await db.execute(select(AgentModel).where(AgentModel.id == agent_id))
            a_obj = a_result.scalar_one_or_none()
            if a_obj:
                sender_avatar = a_obj.avatar_url
                agent_user_id = a_obj.user_id
        except Exception:
            pass

        if agent_user_id is None and target_user is not None:
            return {"error": True, "message": "AI 尚未初始化统一用户 ID"}

        manager = context.get("manager")

        if target_user is not None:
            # ── DM 私信（sender_id 用 users 表 ID） ──
            session = await get_or_create_dm_session(db, current_user_id=agent_user_id, target_user_id=target_user)
            if session is None:
                return {"error": True, "message": "无法创建 DM 会话"}
            try:
                msg = await send_dm_message(
                    db, session["session_id"], sender_id=agent_user_id,
                    content=caption if caption else " ",
                    attachments=[attachment_info],
                )
                await db.commit()
            except ValueError as e:
                await db.rollback()
                return {"error": True, "message": str(e)}
            except Exception as e:
                await db.rollback()
                logger.error(f"send_file DM 失败: {e}", exc_info=True)
                return {"error": True, "message": f"发送失败: {str(e)}"}

            # WebSocket 推送（对齐 send_dm.py 模式）
            if manager:
                await manager.broadcast_to_dm(
                    session["session_id"],
                    {"type": "message", "conversation_type": "dm", "data": {**msg, "sender_name": agent_name}},
                )

            return {
                "success": True,
                "message": f"文件 {attachment_info['name']} 已通过私信发送",
                "attachment": attachment_info,
            }

        else:
            # ── 群聊 ──
            try:
                message = await create_group_message(
                    db, group_id=target_group,
                    sender_type="ai", sender_id=agent_user_id,
                    content=caption if caption else "",
                    attachments=[attachment_info],
                )
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error(f"send_file 群聊失败: {e}", exc_info=True)
                return {"error": True, "message": f"发送失败: {str(e)}"}

            # 广播
            msg_data = message_to_dict(message, sender_name=agent_name, sender_avatar_url=sender_avatar)
            if manager:
                await manager.broadcast_to_group(target_group, {"type": "message", "data": msg_data})

            # 触发其他 AI
            from app.services.ai_response_worker import message_queue
            import asyncio
            next_depth = context.get("chain_depth", 0) + 1
            try:
                message_queue.put_nowait({
                    "group_id": target_group,
                    "message_id": message.id,
                    "content": caption,
                    "sender_type": "ai",
                    "sender_id": agent_user_id,
                    "chain_depth": next_depth,
                })
            except asyncio.QueueFull:
                pass

            return {
                "success": True,
                "message": f"文件 {attachment_info['name']} 已发送到群聊",
                "attachment": attachment_info,
            }


ToolRegistry.register(SendFile)
