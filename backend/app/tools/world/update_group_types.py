"""update_group_types — 改群类型

设置本世界的群类型配置（有多少种类型的群、每种的上限和规则、群助手模板）。传完整的 types 数组（先 get_group_types 看现状再改，只改要改的字段）。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class UpdateGroupTypesTool(WorldToolPlugin):
    name = 'update_group_types'
    label = '改群类型'
    segment = 'group'

    description = (
        '设置本世界的群类型配置（有多少种类型的群、每种的上限和规则、群助手模板）。传完整的 types 数组（先 get_group_types 看现状再改，只改要改的字段）。\n每个类型字段：name=类型名（如 '
        '冒险团/商会，也可以是剧本角色名/职位名如 族长/骑士团长）、rules=世界规则（群主可见，群助手行为继承）、bind_limit=可绑定群数上限（-1 = 无限）、assistant_spec={count: '
        '每群助手数量, need_api: 是否需API, default_name: 助手默认名}。\n例：把冒险团上限改成 5 → types 里该类型 bind_limit=5；改成无限 → bind_limit=-1。'
    )

    parameters = {'types': {'type': 'array', 'items': {'type': 'object'}, 'description': '完整群类型列表（全量替换，保留不想改的）'}}

    required = ['types']

    async def execute(self, ctx: WorldToolContext) -> dict:
        args = ctx.args
        try:
            from app.services.world.group_type_service import save_group_types_config
            types = await save_group_types_config(
                ctx.world_repo, ctx.world.id, ctx.world.owner_id, args.get("types") or [],
            )
            return {"success": True, "types": types}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            return f"群类型配置已更新（{len(result.get('types') or [])} 个类型）"
        return f"更新群类型失败：{result.get('error', '未知错误')}"
