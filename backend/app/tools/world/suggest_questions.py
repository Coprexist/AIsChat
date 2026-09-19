"""suggest_questions — 生成建议问题

向用户展示接下来的建议（3-4 个，每个 ≤20 字）：可以是问题（如「卡牌对战怎么玩？」）、陈述性要求（如「把背景改成星空」）或下一步选项（如「查看世界文件」）——具体、好玩、引导探索。完成回复觉得用户需要引导时调用—
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class SuggestQuestionsTool(WorldToolPlugin):
    name = 'suggest_questions'
    label = '生成建议问题'
    segment = 'self'

    description = (
        '向用户展示接下来的建议（3-4 个，每个 ≤20 字）：可以是问题（如「卡牌对战怎么玩？」）、陈述性要求（如「把背景改成星空」）或下一步选项（如「查看世界文件」）——具体、好玩、引导探索。完成回复觉得用户需要引导时调用——用户点一下就执行。'
        '注意：这些建议会显示在你这条回复的下方（对话流里，紧跟你的消息），不是页面顶部——向用户说明时就说「回复下方/消息下面」的建议。⚠️ 调用后在回复正文里阐述这些建议或说明生成逻辑：让用户明白每个建议是什么/点了会发生什么（可逐一展开，'
        '也可概括说明），不要只丢一个列表让用户猜。'
        '⚠️ 只要你在回复正文里写了「下面还有几个建议/选项」，就必须调用本工具把它们交给平台——'
        '界面显示的就是这几条；不调用就会显示平台预设，与你写的内容对不上（用户会来问）。'
        '不需要建议时：⑧（纯技术问答、用户只是确认「对不对」等）要么**不调用**本工具（本次不显示任何建议），'
        '要么显式传空数组 questions=[] 明确抑制本次建议——空数组不会回落成平台预设。'
    )

    parameters = {'questions': {'type': 'array',
                   'items': {'type': 'string'},
                   'description': '3-4 个建议（问题/要求/下一步选项，用户可直接点击发送）'}}

    required = ['questions']

    async def execute(self, ctx: WorldToolContext) -> dict:
        # "你可以问"建议：AI 自己生成问题 → 存 turn_state，流收尾时 [SUGGEST] 发给前端
        try:
            args = ctx.args
            questions = [str(q).strip()[:40] for q in (args.get("questions") or []) if str(q).strip()]
            if not questions:
                # 空数组 = 显式抑制：本次不展示任何建议（不回落平台预设）
                if ctx.turn_state is not None:
                    ctx.turn_state["suggestions"] = []
                return {"success": True, "count": 0,
                        "note": "本次不展示建议（已显式抑制，不会回落平台预设）"}
            if ctx.turn_state is not None:
                ctx.turn_state["suggestions"] = questions[:5]
            return {"success": True, "count": len(questions), "note": "已生成建议问题，回复末尾会展示给用户"}
        except (ValueError, TypeError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            return f"已生成 {result.get('count', 0)} 条建议问题（回复末尾展示给用户）"
        return f"生成建议问题失败：{result.get('error', '未知错误')}"
