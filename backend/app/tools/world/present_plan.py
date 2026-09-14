"""present_plan — 提交计划

计划模式下：先探索、再出计划，用户弹窗通过后本轮按自动模式执行。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class PresentPlanTool(WorldToolPlugin):
    name = 'present_plan'
    label = '提交计划'
    segment = 'approval'

    description = (
        '把完整计划提交给用户过目（弹窗确认）。计划模式下这是动手前的必经一步：'
        '计划通过后，本轮的改动/下载/删除按自动模式直接执行；不通过则按用户的意见调整后重新提交。\n'
        'plan 要写清楚：要做哪几件事、改哪些文件、下载什么、删什么、大概顺序。别写空话。'
    )

    parameters = {
        'plan': {'type': 'string', 'description': '完整计划（markdown 文本，分条列出要做什么、动哪些文件）'},
    }

    required = ['plan']

    async def execute(self, ctx: WorldToolContext) -> dict:
        plan = str(ctx.args.get("plan") or "").strip()
        if not plan:
            return {"success": False, "error": "缺少 plan 参数"}
        from app.services.world.world_ai_mode import request_approval
        turn_id = (ctx.turn_state or {}).get("turn_id", "")
        approved, note = await request_approval(
            ctx.world.id, turn_id, kind="plan", title="AI 计划待确认", detail=plan,
        )
        if approved and ctx.turn_state is not None:
            ctx.turn_state["plan_approved"] = True     # 本轮后续操作按自动模式放行
        return {"success": True, "approved": approved, "note": note}

    def summary(self, result: dict) -> str:
        if not result.get("success"):
            return f"提交计划失败：{result.get('error', '未知错误')}"
        return "计划已通过，本轮按自动模式执行" if result.get("approved") else f"计划未通过（{result.get('note', '')}）"
