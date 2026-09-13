"""update_trigger_mode — 改触发模式

设置本世界在绑定群里的 AI 触发模式（world_decision_skill.md §3）：mention_only=只有 @ 本世界 AI（或 @all/群公告）才唤醒 AI 本体，其余群消息不触发（默认，安静且省
"""
import json

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class UpdateTriggerModeTool(WorldToolPlugin):
    name = 'update_trigger_mode'
    label = '改触发模式'
    segment = 'world'

    description = (
        '设置本世界在绑定群里的 AI 触发模式（world_decision_skill.md §3）：mention_only=只有 @ 本世界 AI（或 @all/群公告）才唤醒 AI 本体，其余群消息不触发（默认，'
        '安静且省调用——日常事件由世界程序/决策逻辑处理）；all=所有群消息都进入 AI 判断（活跃互动世界用）。世界希望安静/省成本时调成 mention_only，需要频繁互动时调回 all。'
    )

    parameters = {'mode': {'type': 'string',
              'enum': ['mention_only', 'all'],
              'description': 'mention_only 或 all'}}

    required = ['mode']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
        except json.JSONDecodeError:
            return {"success": False, "error": "参数解析失败"}
        mode = str(args.get("mode") or "").strip()
        if mode not in ("mention_only", "all"):
            return {"success": False, "error": "mode 必须是 mention_only 或 all"}
        from app.services.world.world_service import update_world
        await update_world(ctx.world_repo, ctx.world.id, ctx.world.owner_id, config={"group_trigger_mode": mode})
        return {"success": True, "group_trigger_mode": mode}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            mode = result.get("group_trigger_mode")
            return "群触发模式已改为" + ("仅 @ 时响应" if mode == "mention_only" else "响应所有消息")
        return f"改群触发模式失败：{result.get('error', '未知错误')}"
