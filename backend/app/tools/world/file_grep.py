"""file_grep — 搜文件内容

按关键词/正则搜索世界文件内容，返回命中行+行号（轻量定位，不用整文件全读）。
path 可传单个文件、目录（递归搜索）或字符串数组；找「哪些文件用了某段代码」直接传目录或 "."（整个世界），
不用自己写沙箱脚本扫目录。找到位置后配合 file_read(offset,limit) 读对应段落。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import arg_error

# 命中上限：返回的内容要进上下文，宁可让 AI 缩小 path 或改用更精确的 pattern
DEFAULT_MAX_HITS = 30
MAX_HITS_LIMIT = 100


def _path_list(value) -> list[str]:
    """path 归一：单个字符串（可含换行分隔）或字符串数组 → 去空白去重、保持顺序。"""
    raw = value if isinstance(value, (list, tuple)) else str(value or "").splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        for piece in str(item).splitlines():
            rel = piece.strip()
            if rel and rel not in seen:
                seen.add(rel)
                out.append(rel)
    return out


def _single_result(path: str, pattern: str, result: dict) -> dict:
    """单文件：返回形状与旧版一致（命中只有 line/content，不带文件路径）"""
    if result.get("binary"):
        return {"success": True, "path": path, "binary": True, "note": "二进制文件，无法搜索"}
    hits = [{"line": h["line"], "content": h["content"]} for h in result.get("hits") or []]
    if not hits:
        return {"success": True, "path": path, "pattern": pattern, "hits": [], "total_hits": 0,
                "note": f"未找到匹配「{pattern}」"}
    return {"success": True, "path": path, "pattern": pattern, "hits": hits, "total_hits": len(hits)}


def _multi_result(paths: list[str], pattern: str, max_hits: int, result: dict) -> dict:
    """多文件/目录：每条命中带 path，附扫描量与截断提示"""
    hits = result.get("hits") or []
    scope = "、".join(paths)
    if len(scope) > 80:
        scope = scope[:80] + "…"
    out = {
        "success": True,
        "paths": paths,
        "pattern": pattern,
        "hits": hits,
        "total_hits": len(hits),
        "files_scanned": result.get("files_scanned", 0),
        "truncated": bool(result.get("truncated")),
    }
    notes = []
    if not hits:
        notes.append(f"在 {scope} 未找到匹配「{pattern}」")
    if result.get("truncated"):
        notes.append(f"命中已达上限 {max_hits} 条，可能还有更多（缩小 path 或改用更精确的 pattern）")
    if result.get("scan_truncated"):
        notes.append("文件数过多，只扫描了部分文件")
    if result.get("skipped_large"):
        notes.append(f"跳过 {result['skipped_large']} 个超过 2MB 的大文件")
    if notes:
        out["note"] = "；".join(notes)
    return out


class FileGrepTool(WorldToolPlugin):
    name = 'file_grep'
    label = '搜文件内容'
    segment = 'file'

    description = (
        '按关键词/正则搜索世界文件内容，返回命中行+行号（轻量定位，不用整文件全读）。'
        'path 可传文件、目录（递归搜索，跳过 __pycache__/dist 等产物）或数组（多文件/多目录混合），'
        '传 "." 搜整个世界——找「哪些文件用了某段代码」就这样搜，别自己写沙箱脚本扫目录。'
        '命中带文件路径与行号，找到后配合 file_read(offset,limit) 读对应段落。'
    )

    parameters = {'path': {'type': ['string', 'array'], 'items': {'type': 'string'},
                           'description': '相对路径：文件、目录（递归搜索）或 "."（整个世界）；多个用数组（也接受换行分隔的字符串）'},
                  'pattern': {'type': 'string', 'description': '关键词或正则表达式（正则非法时按普通子串匹配）'},
                  'max_hits': {'type': 'integer',
                               'description': f'最多返回几条命中（默认 {DEFAULT_MAX_HITS}，上限 {MAX_HITS_LIMIT}）'}}

    required = ['path', 'pattern']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            paths = _path_list(args.get("path"))
            pattern = str(args.get("pattern", "")).strip()
            if not paths:
                return arg_error("缺少 path 参数", args)
            if not pattern:
                return arg_error("缺少 pattern 参数", args)
            max_hits = args.get("max_hits")
            try:
                max_hits = int(max_hits) if max_hits is not None else DEFAULT_MAX_HITS
            except (TypeError, ValueError):
                max_hits = DEFAULT_MAX_HITS
            max_hits = max(1, min(max_hits, MAX_HITS_LIMIT))
            from app.services.world.world_file_service import grep_paths
            result = grep_paths(ctx.world.id, paths, pattern, max_hits=max_hits)
            if result.get("single_file"):
                return _single_result(paths[0], pattern, result)
            return _multi_result(paths, pattern, max_hits, result)
        except (ValueError, FileNotFoundError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        if not result.get("success"):
            return f"搜索失败：{result.get('error', '未知错误')}"
        hits = result.get("hits") or []
        if result.get("binary"):
            return f"{result.get('path')}（二进制文件，无法搜索）"
        scope = result.get("path") or "、".join(result.get("paths") or []) or "整个世界"
        if not hits:
            return f"在 {scope} 未找到「{result.get('pattern')}」"
        first = hits[0]
        where = f"{first['path']}:" if first.get("path") else ""
        head = f"{where}{first.get('line')}:{(first.get('content') or '')[:40]}"
        return (f"在 {scope} 找到 {result.get('total_hits')} 处「{result.get('pattern')}」：{head}"
                + ("…" if result.get("truncated") else ""))
