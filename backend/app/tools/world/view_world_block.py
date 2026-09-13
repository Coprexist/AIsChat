"""view_world_block — 看积木

查看积木详情和完整代码（应用前先看，确认是否适合本世界）。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.services.world.world_blocks import view_block


class ViewWorldBlockTool(WorldToolPlugin):
    name = 'view_world_block'
    label = '看积木'
    segment = 'world'

    description = '查看积木详情和完整代码（应用前先看，确认是否适合本世界）。'

    parameters = {'block_id': {'type': 'string', 'description': '积木 id'}}

    required = ['block_id']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            block_id = str(args.get("block_id", "")).strip()
            if not block_id:
                return {"success": False, "error": "缺少 block_id 参数"}
            return {"success": True, **view_block(block_id)}
        except ValueError as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            files = list((result.get("files_content") or {}).keys())
            return f"积木「{result.get('name')}」：{(result.get('description') or '')[:40]}｜文件：{'、'.join(files)}"
        return f"看积木失败：{result.get('error', '未知错误')}"
