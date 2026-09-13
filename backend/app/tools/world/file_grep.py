"""file_grep — 搜文件内容

按关键词/正则搜索世界文件内容，返回命中行+行号（轻量定位，不用整文件全读）。找到位置后配合 file_read(offset,limit) 读对应段落。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class FileGrepTool(WorldToolPlugin):
    name = 'file_grep'
    label = '搜文件内容'
    segment = 'file'

    description = '按关键词/正则搜索世界文件内容，返回命中行+行号（轻量定位，不用整文件全读）。找到位置后配合 file_read(offset,limit) 读对应段落。'

    parameters = {'path': {'type': 'string', 'description': '相对路径'},
     'pattern': {'type': 'string', 'description': '关键词或正则表达式（正则非法时按普通子串匹配）'},
     'max_hits': {'type': 'integer', 'description': '最多返回几条命中（默认 30）'}}

    required = ['path', 'pattern']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            path = str(args.get("path", "")).strip()
            pattern = str(args.get("pattern", "")).strip()
            if not path or not pattern:
                return {"success": False, "error": "缺少 path 或 pattern 参数"}
            max_hits = args.get("max_hits")
            try:
                max_hits = int(max_hits) if max_hits is not None else 30
            except (TypeError, ValueError):
                max_hits = 30
            from app.services.world.world_file_service import grep_file
            result = grep_file(ctx.world.id, path, pattern, max_hits=max_hits)
            if result.get("binary"):
                return {"success": True, "path": path, "binary": True, "note": "二进制文件，无法搜索"}
            hits = result.get("hits") or []
            if not hits:
                return {"success": True, "path": path, "pattern": pattern, "hits": [], "total_hits": 0, "note": f"未找到匹配「{pattern}」"}
            return {"success": True, "path": path, "pattern": pattern, "hits": hits, "total_hits": len(hits)}
        except (ValueError, FileNotFoundError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            hits = result.get("hits") or []
            if result.get("binary"):
                return f"{result.get('path')}（二进制文件，无法搜索）"
            if not hits:
                return f"在 {result.get('path')} 未找到「{result.get('pattern')}」"
            first = f"{hits[0]['line']}:{hits[0]['content'][:40]}" if hits else ""
            return f"在 {result.get('path')} 找到 {result.get('total_hits')} 处「{result.get('pattern')}」：{first}…"
        return f"搜索失败：{result.get('error', '未知错误')}"
