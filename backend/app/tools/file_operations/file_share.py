"""
file_share 工具 — AI 分享文件给其他 AI
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class FileShare(ToolPlugin):
    name = "file_share"
    description = "将你的一个文件分享给其他 AI。分享后对方可以读取该文件，你也可以设置对方的权限为 viewer(只读) 或 collaborator(可编辑)。"
    segment = "file_operations"
    parameters = {
        "path": {"type": "string", "description": "要分享的文件路径（相对于你的文件空间根目录）"},
        "target_ai_id": {"type": "integer", "description": "目标 AI 的 ID"},
        "role": {
            "type": "string", "enum": ["collaborator", "viewer"],
            "description": "对方的角色：collaborator=可读写, viewer=只读。默认 collaborator。",
        },
    }
    required = ["path", "target_ai_id"]
    states = ["active", "dnd"]
    admin_description = "将工作区文件分享到群聊。让群成员可以查看或下载 AI 的文件。"
    trigger_condition = "AI 需要将文件分享给群成员时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.content.file_service import ai_share_file

        path = arguments["path"]
        target_ai_id = arguments["target_ai_id"]
        role = arguments.get("role", "collaborator")
        try:
            result = await ai_share_file(db, agent_id, path, "ai", target_ai_id, role)
            return {"success": True, **result}
        except ValueError as e:
            return {"error": True, "message": str(e)}
        except Exception as e:
            logger.error(f"file_share 失败: {e}", exc_info=True)
            return {"error": True, "message": f"分享文件失败: {str(e)}"}


ToolRegistry.register(FileShare)
