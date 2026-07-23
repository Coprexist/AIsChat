"""
file_read 工具 — AI 读取自己的文件
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class FileRead(ToolPlugin):
    name = "file_read"
    description = "读取你自己文件空间中的一个文本文件。只能访问 /app/data/agents/{your_id}/ 下的文件。"
    segment = "file_operations"
    parameters = {
        "path": {"type": "string", "description": "要读取的文件路径（相对于你的文件空间根目录）"},
    }
    required = ["path"]
    states = ["active", "dnd"]
    admin_description = "读取自己的文件内容。AI 查看工作笔记、代码、数据或其他持久化资料时调用。"
    trigger_condition = "AI 需要读取文件内容时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.content.file_service import ai_read_file

        path = arguments.get("path", "")
        try:
            content = await ai_read_file(db, agent_id, path)
            return {"success": True, "path": path, "content": content}
        except ValueError as e:
            return {"error": True, "message": str(e)}
        except Exception as e:
            logger.error(f"file_read 失败: {e}", exc_info=True)
            return {"error": True, "message": f"读取文件失败: {str(e)}"}


ToolRegistry.register(FileRead)
