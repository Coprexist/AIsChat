"""file_edit — 编辑文件

增量编辑世界文件（查找替换/行后插入/删除行），比全量重写省 token。编辑前建议先 file_read 确认内容。多次插入时从最大行号开始往小插。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class FileEditTool(WorldToolPlugin):
    name = 'file_edit'
    label = '编辑文件'
    segment = 'file'

    description = '增量编辑世界文件（查找替换/行后插入/删除行），比全量重写省 token。编辑前建议先 file_read 确认内容。多次插入时从最大行号开始往小插。'

    parameters = {'path': {'type': 'string', 'description': '相对路径'},
     'operation': {'type': 'string',
                   'enum': ['str_replace', 'insert', 'delete_lines'],
                   'description': 'str_replace=精确替换（old_string 必须唯一）；insert=在 line '
                                  '行之后插入；delete_lines=删除 start_line..end_line（含两端）'},
     'old_string': {'type': 'string', 'description': 'str_replace 必填：被替换的精确原文'},
     'new_string': {'type': 'string', 'description': '替换后的新内容 / 要插入的内容'},
     'line': {'type': 'integer', 'description': 'insert 必填：在此行号之后插入（1 开头，0=文件开头）'},
     'start_line': {'type': 'integer', 'description': 'delete_lines 必填：起始行（1 开头）'},
     'end_line': {'type': 'integer', 'description': 'delete_lines 必填：结束行（含）'}}

    required = ['path', 'operation']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            path = str(args.get("path", "")).strip()
            operation = str(args.get("operation", "")).strip()
            if not path or operation not in ("str_replace", "insert", "delete_lines"):
                return {"success": False, "error": "缺少 path 或 operation 非法"}
            from app.services.world.world_file_service import read_file, write_file
            from app.utils.pure.file_edit import apply_file_edit  # 与主站共用同一份编辑核心
            existing = read_file(ctx.world.id, path)
            if existing.get("binary"):
                return {"success": False, "error": "二进制文件不可编辑"}
            new_content, err = apply_file_edit(existing.get("content") or "", operation, args)
            if err:
                return {"success": False, "error": err}
            write_file(ctx.world.id, path, new_content)
            return {"success": True, "path": path, "operation": operation}
        except (ValueError, FileNotFoundError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            op = {"str_replace": "替换", "insert": "插入", "delete_lines": "删除行"}.get(result.get("operation", ""), "编辑")
            return f"已{op} {result.get('path')}"
        return f"编辑失败：{result.get('error', '未知错误')}"
