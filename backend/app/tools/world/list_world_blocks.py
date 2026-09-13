"""list_world_blocks — 查积木

查积木：列出平台提供的预制世界块（可复用 UI 组件，如侧边栏）。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.services.world.world_blocks import list_blocks


class ListWorldBlocksTool(WorldToolPlugin):
    name = 'list_world_blocks'
    label = '查积木'
    segment = 'world'

    description = '查积木：列出平台提供的预制世界块（可复用 UI 组件，如侧边栏）。'

    parameters = {}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            blocks = list_blocks()
            return {"success": True, "blocks": [
                {"id": b["id"], "name": b["name"], "description": b["description"]}
                for b in blocks
            ]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            blocks = result.get("blocks") or []
            names = "、".join(f"{b['name']}({b['id']})" for b in blocks[:8])
            return f"平台积木（{len(blocks)} 个）：{names}" + ("…" if len(blocks) > 8 else "")
        return f"查积木失败：{result.get('error', '未知错误')}"
