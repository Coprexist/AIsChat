"""send_group_message — 发群消息

以世界创建者身份在群聊发一条消息。用户要求你（或世界）在群里说话时调用。默认发到本世界绑定的群。
"""
import logging

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.chat.gm import send_gm_message as _send_gm_message


logger = logging.getLogger(__name__)


class SendGroupMessageTool(WorldToolPlugin):
    name = 'send_group_message'
    label = '发群消息'
    segment = 'group'

    description = '以世界创建者身份在群聊发一条消息。用户要求你（或世界）在群里说话时调用。默认发到本世界绑定的群。'

    parameters = {'group_id': {'type': 'integer', 'description': '可选：指定群聊 id（默认本世界绑定的群）'},
     'content': {'type': 'string', 'description': '消息内容'}}

    required = ['content']

    async def execute(self, ctx: WorldToolContext) -> dict:
        args = ctx.args
        try:
            gids = await resolve_group_ids(ctx, args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            content = str(args.get("content") or "").strip()
            if not content:
                return {"success": False, "error": "消息内容不能为空"}
            msg = await send_gm_message(ctx.world_repo.session, gid, "human", ctx.world.owner_id, content, source="world", allow_non_member=True)
            try:
                from app.routers.ws import manager
                await manager.broadcast_to_group(gid, {"type": "message", "data": {"id": msg.id, "content": content}})
            except Exception as e:
                # 消息已入库，但实时推送失败 → 群成员当下看不到（刷新才有）。必须留痕
                logger.warning(f"🌐 世界 #{ctx.world.id} 群消息实时推送失败（group={gid}, msg_id={msg.id}）: {e}")
            return {"success": True, "message_id": msg.id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        return f"已发送群消息（#{result.get('message_id')}）" if ok else f"发送失败：{result.get('error', '未知错误')}"
