"""ask_user — 询问用户（弹窗）

AI 主动发起的是/否询问；与平台门禁共用同一条审批通道（world_ai_mode.request_approval）。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext

# 事件类型关键词（必填）：用户看到的弹窗按这个分类，也决定审批的归属
KINDS = ("download", "delete", "modify", "other")


class AskUserTool(WorldToolPlugin):
    name = 'ask_user'
    label = '询问用户'
    segment = 'approval'

    description = (
        '弹窗询问用户是否同意（用户在弹窗里点同意/不同意，你的执行会等这个答复）。\n'
        'kind 必填——事件类型关键词，只能选：download（要下载东西）/ delete（要删东西）/ '
        'modify（要改世界机制——用户没说或与先前说法有出入的改动）/ other（其他需要用户拍板的事，如选方案）。\n'
        '审阅模式下下载/删除/改动机制本来就由平台弹窗把关，你不需要用本工具替代它；'
        '本工具用于其余需要用户当场选择、确认的场合（方案取舍、理解是否一致、要不要继续）。\n'
        '问题要一句话说清，detail 里放用户真正要看的内容（方案差异、将改动什么）。'
    )

    parameters = {
        'kind': {'type': 'string', 'enum': list(KINDS), 'description': '事件类型关键词（必填）'},
        'question': {'type': 'string', 'description': '要问用户的问题（简短明确，一句话）'},
        'detail': {'type': 'string', 'description': '补充说明（可选；给用户看的具体内容）'},
    }

    required = ['kind', 'question']

    async def execute(self, ctx: WorldToolContext) -> dict:
        kind = str(ctx.args.get("kind") or "").strip()
        question = str(ctx.args.get("question") or "").strip()
        detail = str(ctx.args.get("detail") or "").strip()
        if kind not in KINDS:
            return {"success": False, "error": f"kind 必填且必须是 {'/'.join(KINDS)} 之一"}
        if not question:
            return {"success": False, "error": "缺少 question 参数"}
        from app.services.world.world_ai_mode import request_approval
        turn_id = (ctx.turn_state or {}).get("turn_id", "")
        approved, note = await request_approval(
            ctx.world.id, turn_id, kind=kind, title=question, detail=detail,
        )
        return {
            "success": True, "approved": approved,
            "answer": "同意" if approved else "不同意", "note": note,
        }

    def summary(self, result: dict) -> str:
        if not result.get("success"):
            return f"询问失败：{result.get('error', '未知错误')}"
        return f"用户{result.get('answer', '未答复')}（{result.get('note', '')}）"
