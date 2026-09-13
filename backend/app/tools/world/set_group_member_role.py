"""set_group_member_role — 改成员角色

修改群成员角色（admin/member）。仅群主可操作。默认操作本世界绑定的群。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import resolve_group_ids
from app.chat.gm import change_member_role as _change_member_role


class SetGroupMemberRoleTool(WorldToolPlugin):
    name = 'set_group_member_role'
    label = '改成员角色'
    segment = 'group'

    description = '修改群成员角色（admin/member）。仅群主可操作。默认操作本世界绑定的群。'

    parameters = {'group_id': {'type': 'integer', 'description': '可选：指定群聊 id（默认本世界绑定的群）'},
     'member_type': {'type': 'string', 'enum': ['human', 'ai'], 'description': '成员类型'},
     'member_id': {'type': 'integer', 'description': '成员 id（来自 list_group_members）'},
     'role': {'type': 'string', 'enum': ['admin', 'member'], 'description': '新角色'}}

    required = ['member_type', 'member_id', 'role']

    async def execute(self, ctx: WorldToolContext) -> dict:
        args = ctx.args
        try:
            gids = await resolve_group_ids(ctx, args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            mtype = str(args.get("member_type") or "")
            mid = int(args.get("member_id") or 0)
            role = str(args.get("role") or "")
            await _change_member_role(ctx.world_repo.session, gid, ctx.world.owner_id, mtype, mid, role)
            return {"success": True, "member_id": mid, "role": role}
        except (ValueError, TypeError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        return f"已把成员 {result.get('member_id')} 的角色设为 {result.get('role')}" if ok else f"改角色失败：{result.get('error', '未知错误')}"
