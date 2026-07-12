"""
file_edit 工具 — AI 增量编辑文件（查找替换 / 行后插入）
不需要重写整个文件，节省 token，适合大文件小幅修改。
"""
import logging
import os
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class FileEdit(ToolPlugin):
    name = "file_edit"
    description = (
        "增量编辑文件（查找替换或行后插入），比 file_write 更省 token。"
        "大文件只需传要改的部分，不用重写全文。"
    )
    segment = "file_operations"
    parameters = {
        "path": {
            "type": "string",
            "description": "文件路径（相对于你的文件空间根目录）",
        },
        "operation": {
            "type": "string",
            "enum": ["str_replace", "insert"],
            "description": (
                "操作类型：\n"
                "- str_replace：精确字符串替换。先读取文件确认原文存在且唯一，再执行替换。\n"
                "- insert：在指定行号之后插入新内容。"
            ),
        },
        "old_string": {
            "type": "string",
            "description": "（str_replace 必填）要被替换的精确原文。必须完全匹配文件中某一段且唯一，否则拒绝执行。",
        },
        "new_string": {
            "type": "string",
            "description": "替换后的新内容（str_replace）或要插入的新内容（insert）。",
        },
        "insert_line": {
            "type": "integer",
            "description": "（insert 必填）在此行号之后插入。行号从 1 开始。0 = 插入到文件开头。",
        },
    }
    required = ["path", "operation"]
    states = ["active", "dnd"]
    admin_description = "增量编辑自己的文件（查找替换或行后插入），避免大文件全量重写的 token 开销。"
    trigger_condition = "AI 需要修改已有文件的局部内容时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.file_service import ai_read_file, ai_write_file

        path = arguments["path"]
        operation = arguments["operation"]
        new_string = arguments.get("new_string", "")

        try:
            # 1. 读取当前文件内容
            old_content = await ai_read_file(db, agent_id, path)
        except ValueError as e:
            return {"error": True, "message": str(e)}
        except Exception as e:
            logger.error(f"file_edit 读取失败: {e}", exc_info=True)
            return {"error": True, "message": f"读取文件失败: {str(e)}"}

        lines = old_content.split("\n")

        if operation == "str_replace":
            old_string = arguments.get("old_string", "")
            if not old_string:
                return {"error": True, "message": "str_replace 操作需要提供 old_string 参数"}

            count = old_content.count(old_string)
            if count == 0:
                return {
                    "error": True,
                    "message": f"未在文件中找到匹配的原文。请检查 old_string 是否完全一致（含缩进和换行）。",
                }
            if count > 1:
                return {
                    "error": True,
                    "message": f"在文件中找到 {count} 处匹配，无法确定替换哪一处。请提供更长的上下文确保唯一。",
                }

            new_content = old_content.replace(old_string, new_string, 1)

        elif operation == "insert":
            insert_line = arguments.get("insert_line", 0)
            if insert_line < 0:
                return {"error": True, "message": "insert_line 不能小于 0"}
            if insert_line > len(lines):
                return {
                    "error": True,
                    "message": f"行号 {insert_line} 超出文件范围（共 {len(lines)} 行）",
                }

            new_lines = lines.copy()
            new_lines.insert(insert_line, new_string)  # insert into list, after specified line
            # 注意：list.insert(index, item) 会插入到 index 位置之前
            # 如果 insert_line=0，插入到第 1 行前 = 文件开头
            # 如果 insert_line=1，插入到第 1 行后 = 第 2 行
            # 所以我们直接使用 insert_line 作为索引
            new_content = "\n".join(new_lines)

        else:
            return {"error": True, "message": f"不支持的操作: {operation}"}

        # 3. 写回文件
        try:
            metadata = await ai_write_file(db, agent_id, path, new_content, "solo")
            return {
                "success": True,
                "path": metadata.path,
                "size": metadata.size,
                "operation": operation,
            }
        except ValueError as e:
            return {"error": True, "message": str(e)}
        except Exception as e:
            logger.error(f"file_edit 写入失败: {e}", exc_info=True)
            return {"error": True, "message": f"写入文件失败: {str(e)}"}


ToolRegistry.register(FileEdit)
