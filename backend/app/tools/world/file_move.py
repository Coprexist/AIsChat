"""file_move — 移动文件

移动/重命名世界文件（同目录改名、跨目录搬移都行；目录可整体搬移）。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import arg_error


class FileMoveTool(WorldToolPlugin):
    name = 'file_move'
    label = '移动文件'
    segment = 'file'

    description = (
        '移动或重命名世界文件（同目录改名、跨目录搬移都行；目录可整体搬移）。'
        '源与目标都要写完整文件名（相对世界根，如 css/old.css → assets/new.css），不要把目标写成目录。'
    )

    parameters = {
        'from': {'type': 'string', 'description': '源路径（相对世界根，如 css/old.css）'},
        'to': {'type': 'string', 'description': '目标路径（相对世界根，含文件名，如 assets/new.css）'},
    }

    required = ['from', 'to']

    async def execute(self, ctx: WorldToolContext) -> dict:
        args = ctx.args
        src = str(args.get("from", "")).strip()
        dst = str(args.get("to", "")).strip()
        if not src or not dst:
            missing = " / ".join(k for k, v in (("from", src), ("to", dst)) if not v)
            return arg_error(f"缺少 {missing} 参数", args)
        try:
            from app.services.world.world_file_service import move_file
            result = move_file(ctx.world.id, src, dst)
            if result.get("banned_removed"):
                result["warning"] = f"⚠️ 顺带强删了禁用后缀文件：{'、'.join(result['banned_removed'])}"
            return {"success": True, **result}
        except (ValueError, FileNotFoundError, OSError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        if result.get("success"):
            note = f"已移动 {result.get('from')} → {result.get('path')}"
            return f"{note}；{result['warning']}" if result.get("warning") else note
        return f"移动失败：{result.get('error', '未知错误')}"
