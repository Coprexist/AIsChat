"""get_bound_groups — 查绑定群

查本世界绑定了哪些群聊（返回群名/成员数/是否暂停）。用于了解本世界的群聊入口。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import bound_group_ids
from app.chat.gm import get_group as _get_group
from sqlalchemy import func as _func
from sqlalchemy import select


class GetBoundGroupsTool(WorldToolPlugin):
    name = 'get_bound_groups'
    label = '查绑定群'
    segment = 'group'

    description = '查本世界绑定了哪些群聊（返回群名/成员数/是否暂停）。用于了解本世界的群聊入口。'

    parameters = {}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            gids = await bound_group_ids(ctx)
            from app.models.group import GroupMember
            out = []
            for gid in gids:
                g = await _get_group(ctx.world_repo.session, gid)
                if g is None:
                    continue
                cnt = (await ctx.world_repo.execute(
                    select(_func.count()).select_from(GroupMember).where(GroupMember.group_id == gid)
                )).scalar()
                out.append({
                    "group_id": gid,
                    "name": g.name,
                    "is_paused": g.is_paused,
                    "member_count": cnt,
                    "created_at": str(g.created_at) if g.created_at else None,
                })
            return {"success": True, "groups": out}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            groups = result.get("groups") or []
            if not groups:
                return "本世界未绑定任何群聊"
            return "绑定群聊：" + "、".join(f"{g['name']}(#{g['group_id']}，{g['member_count']}人)" for g in groups)
        return f"查绑定群失败：{result.get('error', '未知错误')}"
