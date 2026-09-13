"""kick_group_member — 移出成员

把某成员移出群聊。仅群主/管理员可操作。默认操作本世界绑定的群。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import resolve_group_ids
from app.chat.gm import remove_member as _remove_member


class KickGroupMemberTool(WorldToolPlugin):
    name = 'kick_group_member'
    label = '移出成员'
    segment = 'group'

    description = '把某成员移出群聊。仅群主/管理员可操作。默认操作本世界绑定的群。'

    parameters = {'group_id': {'type': 'integer', 'description': '可选：指定群聊 id（默认本世界绑定的群）'},
     'member_type': {'type': 'string', 'enum': ['human', 'ai'], 'description': '成员类型'},
     'member_id': {'type': 'integer', 'description': '成员 id'}}

    required = ['member_type', 'member_id']

    async def execute(self, ctx: WorldToolContext) -> dict:
        args = ctx.args
        try:
            gids = await resolve_group_ids(ctx, args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            mtype = str(args.get("member_type") or "")
            mid = int(args.get("member_id") or 0)
            await _remove_member(ctx.world_repo.session, gid, ctx.world.owner_id, mtype, mid)
            return {"success": True, "member_id": mid}
        except ValueError as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        return f"已把成员 {result.get('member_id')} 移出群聊" if ok else f"移出失败：{result.get('error', '未知错误')}"
