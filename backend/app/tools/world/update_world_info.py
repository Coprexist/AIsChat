"""update_world_info — 改世界信息

更新这个世界（你自己所在的世界）的名称或简介。用户要求改名/改设定时调用。
"""
import json

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class UpdateWorldInfoTool(WorldToolPlugin):
    name = 'update_world_info'
    label = '改世界信息'
    segment = 'world'

    description = '更新这个世界（你自己所在的世界）的名称或简介。用户要求改名/改设定时调用。'

    parameters = {'name': {'type': 'string', 'description': '新的世界名'},
     'description': {'type': 'string', 'description': '新的世界观简介'}}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
        except json.JSONDecodeError:
            return {"success": False, "error": "参数解析失败"}
        patch = {
            k: v.strip() for k, v in args.items()
            if k in ("name", "description") and isinstance(v, str) and v.strip()
        }
        if not patch:
            return {"success": False, "error": "没有有效的 name/description 参数"}
        try:
            from app.services.world.world_service import update_world
            updated = await update_world(ctx.world_repo, ctx.world.id, ctx.world.owner_id, **patch)
            return {"success": True, "name": updated["name"], "description": updated["description"]}
        except ValueError as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            parts = []
            if result.get("name"):
                parts.append(f"名称→{result['name']}")
            if result.get("description"):
                parts.append("简介已更新")
            return "已更新世界信息" + (f"（{'，'.join(parts)}）" if parts else "")
        return f"更新世界信息失败：{result.get('error', '未知错误')}"
