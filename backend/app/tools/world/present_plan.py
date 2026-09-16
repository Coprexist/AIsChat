"""present_plan — 提交计划

计划模式下：先探索、再出计划，用户弹窗通过后本轮按自动模式执行。
"""

from app.services.world.world_ai_mode import USER_NOTE_KEY
from app.tools.world.base import WorldToolPlugin, WorldToolContext


class PresentPlanTool(WorldToolPlugin):
    name = 'present_plan'
    label = '提交计划'
    segment = 'approval'

    description = (
        '把完整计划提交给用户过目（弹窗确认）。计划模式下这是动手前的必经一步：'
        '计划通过后，本轮的改动/下载/删除按自动模式直接执行；不通过则按用户的意见调整后重新提交。\n'
        'plan 要写清楚：要做哪几件事、改哪些文件、下载什么、删什么、大概顺序。别写空话。\n'
        '用户在弹窗里除了点通过/不通过，还可能写下修改意见（结果里的 '
        f'{USER_NOTE_KEY}）：**按用户的话调整**后重新提交，别当作没看见。'
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
        # 计划必须真有人点头：无人应答一律不通过（on_timeout=False），
        # 否则"计划模式"会退化成"等 5 分钟自动开工"
        approval = await request_approval(
            ctx.world.id, turn_id, kind="plan", title="AI 提交了一份计划",
            detail="通过后，本轮剩下的操作按自动模式直接执行",
            body=plan, body_format="markdown",
            on_timeout=False,
        )
        if approval.approved and ctx.turn_state is not None:
            ctx.turn_state["plan_approved"] = True     # 本轮后续操作按自动模式放行
        return {
            "success": True, "approved": approval.approved,
            # 用户可能只通过一部分、或写下修改意见——原样交给 AI，让它调整后重新提交
            USER_NOTE_KEY: approval.note, "summary": approval.reason,
        }

    def summary(self, result: dict) -> str:
        if not result.get("success"):
            return f"提交计划失败：{result.get('error', '未知错误')}"
        note = result.get(USER_NOTE_KEY) or ""
        if not result.get("approved"):
            return f"计划未通过（{note or '用户未说明理由'}）"
        return f"计划已通过（用户补充：{note}）" if note else "计划已通过，本轮按自动模式执行"
