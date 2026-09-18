"""file_write — 写文件

创建或写入世界文件（HTML/CSS/JS/图片等，自动建目录，类型白名单限制）。创建网页/改代码用它。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import arg_error


class FileWriteTool(WorldToolPlugin):
    name = 'file_write'
    label = '写文件'
    segment = 'file'

    description = '创建或写入世界文件（HTML/CSS/JS/图片等，自动建目录，类型白名单限制）。创建网页/改代码用它。'

    parameters = {'path': {'type': 'string', 'description': '相对路径，如 index.html 或 css/style.css'},
     'content': {'type': 'string', 'description': '文件内容'}}

    required = ['path', 'content']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            path = str(args.get("path", "")).strip()
            content = str(args.get("content", ""))
            if not path:
                return arg_error("缺少 path 参数", args)
            from app.services.world.world_file_service import read_file, write_file
            # 内容相同检测：打断模型的重复写入循环（温和提示，非硬拦截）
            try:
                existing = read_file(ctx.world.id, path)
                if not existing.get("binary") and existing.get("content") == content:
                    return {"success": True, "path": path, "unchanged": True, "note": "文件内容与现有完全一致，未做更改（无需重复写入）"}
            except (ValueError, FileNotFoundError):
                pass  # 文件不存在 → 正常创建
            write_file(ctx.world.id, path, content)
            return {"success": True, "path": path}
        except (ValueError, FileNotFoundError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            if result.get("skipped"):
                return f"⏭ 已跳过（该操作本次对话已执行过）：{result.get('path')}"
            return f"成功创建文件 {result.get('path')}"
        return f"创建文件失败：{result.get('error', '未知错误')}"
