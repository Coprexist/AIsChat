"""get_group_types — 查群类型

查看本世界的群类型配置（每个类型的规则/绑定上限/群助手模板），以及各类型已绑定的群数。用户问群类型/群助手相关时先调用它。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext


class GetGroupTypesTool(WorldToolPlugin):
    name = 'get_group_types'
    label = '查群类型'
    segment = 'group'

    description = '查看本世界的群类型配置（每个类型的规则/绑定上限/群助手模板），以及各类型已绑定的群数。用户问群类型/群助手相关时先调用它。'

    parameters = {}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            from app.services.world.group_type_service import list_group_types
            types = await list_group_types(ctx.world_repo, ctx.world.id)
            return {"success": True, "types": types}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        types = result.get("types") or []
        if not types:
            return "本世界还没有群类型配置"
        lines = [f"{t['name']}（上限{'无限' if t['bind_limit'] == -1 else t['bind_limit']}，已绑{t['bound_count']}群，助手{t['assistant_spec'].get('count', 1)}个"
                 + ("，无需API" if t['assistant_spec'].get('need_api') is False else "") + "）" for t in types]
        return "群类型：" + "；".join(lines)
