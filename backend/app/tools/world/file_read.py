"""file_read — 读文件

读取世界文件内容（编辑前确认内容用）。大文件支持按行分页：offset=起始行号（1-based，默认1），limit=读多少行（不填读到底）；返回 total_lines/start_line/end_line/tru
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import arg_error


class FileReadTool(WorldToolPlugin):
    name = 'file_read'
    label = '读文件'
    segment = 'file'

    description = (
        '读取世界文件内容（编辑前确认内容用）。大文件支持按行分页：offset=起始行号（1-based，默认1），limit=读多少行（不填读到底）；返回 total_lines/start_line/end_line/truncated。'
        '建议：先 file_grep 定位行号，再分段读对应区间，不要整文件全读浪费上下文。'
    )

    parameters = {'path': {'type': 'string', 'description': '相对路径'},
     'offset': {'type': 'integer', 'description': '起始行号（1-based，默认 1）'},
     'limit': {'type': 'integer', 'description': '读取行数（不填读到底）'}}

    required = ['path']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            path = str(args.get("path", "")).strip()
            if not path:
                return arg_error("缺少 path 参数", args)
            from app.services.world.world_file_service import read_file
            # 2026-08-13：支持按行分页（offset/limit）——大文件先 grep 定位再分段读
            offset = args.get("offset")
            limit = args.get("limit")
            try:
                offset = int(offset) if offset is not None else None
                limit = int(limit) if limit is not None else None
            except (TypeError, ValueError):
                return {"success": False, "error": "offset/limit 必须是整数"}
            existing = read_file(ctx.world.id, path, offset=offset, limit=limit)
            if existing.get("binary"):
                return {"success": True, "path": path, "binary": True, "note": "二进制文件，内容不返回"}
            content = existing.get("content") or ""
            if len(content) > 6000:
                content = content[:6000] + "\n…（内容较长已截断，可用 file_read offset/limit 分段读）"
            meta = {k: existing[k] for k in ("total_lines", "start_line", "end_line", "truncated") if k in existing}
            return {"success": True, "path": path, "content": content, **meta}
        except (ValueError, FileNotFoundError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            if result.get("binary"):
                return f"{result.get('path')}（二进制文件）"
            c = result.get("content") or ""
            if result.get("start_line"):
                return f"已读取 {result.get('path')} 第{result.get('start_line')}-{result.get('end_line')}行（共{result.get('total_lines')}行，{len(c)}字符）" + ("，已截断" if result.get("truncated") else "")
            return f"已读取 {result.get('path')}（{len(c)} 字符）"
        return f"读取失败：{result.get('error', '未知错误')}"
