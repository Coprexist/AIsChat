"""
execute_command 工具 — AI 通过 OpenCLI 执行命令
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry, ToolErrorCode

logger = logging.getLogger(__name__)


class ExecuteCommand(ToolPlugin):
    name = "execute_command"
    description = ("通过 OpenCLI 执行命令。\n"
                   "**文件操作（始终可用，安全沙箱隔离）：** file_read（读取文本文件）、file_write（创建/覆盖文件）、file_list（列出目录）、file_delete（删除文件）、file_info（查看文件信息）、create_dir（创建目录）——所有文件操作自动限制在你的个人工作空间内，不会影响系统。\n"
                   "**高级命令（需管理员开启白名单）：** browser（上网查资料）、gh（GitHub CLI）、docker、obsidian 等。\n"
                   "⚠️ browser 命令依赖 Chromium 浏览器服务，部分环境可能不可用（如 NAS Docker 部署）。\n"
                   "如果 browser 报错，请改用 web_search（搜索关键词）和 web_fetch（获取指定 URL）工具，它们不依赖浏览器，更稳定。\n"
                   "不在白名单中的命令会被拒绝。browser 等命令的详细用法请用 tool_help 查询。")
    segment = "file_operations"
    parameters = {
        "command": {"type": "string", "description": "命令名称。文件操作：file_read/file_write/file_list/file_delete/file_info/create_dir。高级操作：browser open/gh repo/docker ps 等（需白名单）"},
        "args": {"type": "array", "items": {"type": "string"}, "description": "命令参数列表", "nullable": True},
    }
    required = ["command"]
    states = ["active", "dnd"]
    admin_description = "执行 OpenCLI 命令。需管理员配置白名单，AI 可通过它操作文件系统、运行脚本、管理数据。"
    trigger_condition = "AI 需要系统级操作时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.opencli_service import execute_opencli
        from app.utils.error_handler import build_tool_error

        command = arguments["command"]
        args = arguments.get("args") or []

        try:
            result = await execute_opencli(db, agent_id=agent_id, command=command, args=args)
            return {
                "success": True,
                "command": result["command"],
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "duration_ms": result["duration_ms"],
            }
        except PermissionError as e:
            return build_tool_error(ToolErrorCode.OPENCLI_PERMISSION_DENIED, str(e))
        except TimeoutError as e:
            return build_tool_error(ToolErrorCode.OPENCLI_TIMEOUT, str(e))
        except Exception as e:
            logger.error(f"execute_command 执行失败 (command={command}, args={args}): {e}", exc_info=True)
            return build_tool_error(ToolErrorCode.OPENCLI_EXEC_FAILED, f"命令执行失败: {str(e)}")


ToolRegistry.register(ExecuteCommand)
