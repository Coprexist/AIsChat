"""file_list — 列文件

列出世界文件夹里的文件（网页代码等）。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.services.world.world_file_service import list_files


class FileListTool(WorldToolPlugin):
    name = 'file_list'
    label = '列文件'
    segment = 'file'

    description = '列出世界文件夹里的文件（网页代码等）。'

    parameters = {}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            files = list_files(ctx.world.id)
            return {"success": True, "files": [f["path"] for f in files]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        files = result.get("files") or []
        if not files:
            return "世界文件夹是空的"
        shown = "、".join(files[:10]) + (f" 等{len(files)}个" if len(files) > 10 else "")
        return f"世界文件（{len(files)} 个）：{shown}"
