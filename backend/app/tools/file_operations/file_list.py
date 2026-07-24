"""
file_list 工具 — AI 列出自己的文件
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class FileList(ToolPlugin):
    name = "file_list"
    description = "列出你文件空间中的文件和子目录。"
    segment = "file_operations"
    parameters = {
        "path": {"type": "string", "description": "要列出的目录路径（相对于根目录），默认为根目录 '/'"},
    }
    required = []
    states = ["active", "dnd"]
    admin_description = "列出自己工作文件夹的内容。AI 浏览文件目录结构、查看有哪些文件可用。"
    trigger_condition = "AI 需要浏览文件目录时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.content.file_service import ai_list_files

        path = arguments.get("path", "/")
        try:
            files = await ai_list_files(db, agent_id, path)
            return {"success": True, "path": path, "files": files, "count": len(files)}
        except ValueError as e:
            return {"error": True, "message": str(e)}
        except Exception as e:
            logger.error(f"file_list 失败: {e}", exc_info=True)
            return {"error": True, "message": f"列出失败：{e}"}


ToolRegistry.register(FileList)
