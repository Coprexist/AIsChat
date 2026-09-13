"""get_group_messages — 读群消息

读取群聊的最近消息（含发送者名字），了解群里最近聊了什么。默认操作本世界绑定的群，不需要传群 id。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import resolve_group_ids
from app.chat.gm import get_gm_messages
from sqlalchemy import select


class GetGroupMessagesTool(WorldToolPlugin):
    name = 'get_group_messages'
    label = '读群消息'
    segment = 'group'

    description = '读取群聊的最近消息（含发送者名字），了解群里最近聊了什么。默认操作本世界绑定的群，不需要传群 id。'

    parameters = {'group_id': {'type': 'integer', 'description': '可选：指定群聊 id（默认本世界绑定的群）'},
     'limit': {'type': 'integer', 'description': '条数，默认 20，最大 50'}}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        args = ctx.args
        try:
            gids = await resolve_group_ids(ctx, args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            limit = max(1, min(int(args.get("limit") or 20), 50))
            msgs = await get_gm_messages(ctx.world_repo.session, gid, limit)
            from app.models.user import User
            from app.models.agent import Agent
            all_ids = {m.sender_id for m in msgs}
            name_map = {}
            if all_ids:
                u_res = await ctx.world_repo.execute(select(User.id, User.username, User.type).where(User.id.in_(all_ids)))
                for uid, uname, utype in u_res.all():
                    name_map[uid] = uname
                    if utype == "ai":
                        a = (await ctx.world_repo.execute(select(Agent.name).where(Agent.user_id == uid))).first()
                        if a:
                            name_map[uid] = a[0]
            out = [{
                "id": m.id,
                "sender": name_map.get(m.sender_id, f"#{m.sender_id}"),
                "content": m.content,
                "created_at": str(m.created_at) if m.created_at else None,
            } for m in msgs]
            return {"success": True, "messages": out}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            msgs = result.get("messages") or []
            if not msgs:
                return "群聊暂无消息"
            return f"群聊最近 {len(msgs)} 条消息（{msgs[0]['sender']}…{msgs[-1]['sender']}）"
        return f"读消息失败：{result.get('error', '未知错误')}"
