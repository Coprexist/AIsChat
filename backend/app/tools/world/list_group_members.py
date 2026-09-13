"""list_group_members — 查群成员

列出群聊成员（谁是谁 + 角色：owner/admin/member + 在线状态）。默认操作本世界绑定的群。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import resolve_group_ids
from app.chat.gm import get_group_members as _get_group_members
from sqlalchemy import select


class ListGroupMembersTool(WorldToolPlugin):
    name = 'list_group_members'
    label = '查群成员'
    segment = 'group'

    description = '列出群聊成员（谁是谁 + 角色：owner/admin/member + 在线状态）。默认操作本世界绑定的群。'

    parameters = {'group_id': {'type': 'integer', 'description': '可选：指定群聊 id（默认本世界绑定的群）'}}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        args = ctx.args
        try:
            gids = await resolve_group_ids(ctx, args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            members = await _get_group_members(ctx.world_repo.session, gid)
            from app.models.user import User
            from app.models.agent import Agent
            out = []
            for m in members:
                nm = None
                if m.member_type == "human":
                    u = await ctx.world_repo.get(User, m.member_id)
                    if u:
                        nm = u.username
                else:
                    a = (await ctx.world_repo.execute(select(Agent.name).where(Agent.user_id == m.member_id))).first()
                    if a:
                        nm = a[0]
                out.append({
                    "type": m.member_type,
                    "id": m.member_id,
                    "name": nm or f"{m.member_type}:{m.member_id}",
                    "role": m.role,
                })
            return {"success": True, "members": out}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            members = result.get("members") or []
            return f"群成员（{len(members)} 人）：" + "、".join(f"{m['name']}({m['role']})" for m in members[:8])
        return f"查成员失败：{result.get('error', '未知错误')}"
