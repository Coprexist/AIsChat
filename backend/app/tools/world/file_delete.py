"""file_delete — 删文件

删除世界文件。
"""
import json

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.services.world.world_file_service import delete_file


class FileDeleteTool(WorldToolPlugin):
    name = 'file_delete'
    label = '删文件'
    segment = 'file'

    description = '删除世界文件。'

    parameters = {'path': {'type': 'string', 'description': '相对路径'}}

    required = ['path']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            path = str(args.get("path", "")).strip()
            if not path:
                return {"success": False, "error": "缺少 path 参数"}
            delete_file(ctx.world.id, path)
            return {"success": True, "path": path}
        except (ValueError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        return f"已删除文件 {result.get('path')}" if ok else f"删除失败：{result.get('error', '未知错误')}"
