"""file_copy — 复制文件

世界内复制文件/目录（不跨世界——各自目录隔离）。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import arg_error


class FileCopyTool(WorldToolPlugin):
    name = 'file_copy'
    label = '复制文件'
    segment = 'file'

    description = (
        '在世界内复制文件或目录（原文件保留）。目标要写完整文件名（相对世界根，如 assets/a.css），'
        '不要把目标写成目录；不能跨世界复制。从网上取代码用 web_download，改内容用 file_write/file_edit。'
    )

    parameters = {
        'from': {'type': 'string', 'description': '源路径（相对世界根，如 index.html）'},
        'to': {'type': 'string', 'description': '目标路径（相对世界根，含文件名，如 backup/index.bak.html）'},
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
            from app.services.world.world_file_service import copy_file
            result = copy_file(ctx.world.id, src, dst)
            if result.get("banned_removed"):
                result["warning"] = f"⚠️ 顺带强删了禁用后缀文件：{'、'.join(result['banned_removed'])}"
            return {"success": True, **result}
        except (ValueError, FileNotFoundError, OSError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        if result.get("success"):
            note = f"已复制 {result.get('from')} → {result.get('path')}（{result.get('size', 0)}B）"
            return f"{note}；{result['warning']}" if result.get("warning") else note
        return f"复制失败：{result.get('error', '未知错误')}"
