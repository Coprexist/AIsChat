"""ask_user — 询问用户（弹窗）

AI 主动发起的是/否询问；与平台门禁共用同一条审批通道（world_ai_mode.request_approval）。
"""

from app.services.world.world_ai_mode import USER_NOTE_KEY
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import arg_error

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
        '**用用户听得懂的话问**：一句话说清"要他定什么"，别用内部术语、别堆文件名与参数——'
        '用户看到的就是弹窗标题，看不懂只能瞎点。detail 里放用户真正要看的内容（方案差异、将改动什么）。\n'
        '弹窗里还有个输入框：用户可能不点按钮而是写下理由或补充要求，会随答复一起给你（结果里的 '
        f'{USER_NOTE_KEY}）——**以用户的话为准**，别只读"同意/不同意"两个字。'
    )

    parameters = {
        'kind': {'type': 'string', 'enum': list(KINDS), 'description': '事件类型关键词（必填）'},
        'question': {'type': 'string', 'description': '要问用户的问题（简短明确，一句话）'},
        'detail': {'type': 'string', 'description': '补充说明（可选；给用户看的具体内容）'},
    }

    required = ['kind', 'question']

    async def execute(self, ctx: WorldToolContext) -> dict:
        args = ctx.args
        kind = str(args.get("kind") or "").strip()
        question = str(args.get("question") or "").strip()
        detail = str(args.get("detail") or "").strip()
        if kind not in KINDS:
            return arg_error(f"kind 必填且必须是 {'/'.join(KINDS)} 之一（收到 {kind!r}）", args)
        if not question:
            return arg_error("缺少 question 参数", args)
        from app.services.world.world_ai_mode import request_approval, unattended_policy
        # 没人应答怎么办由模式决定：自动档等 10 分钟然后自行继续（对齐 DSH），
        # 审阅/计划档一律不放行——不能因为"等超时了"就把敏感操作默认批了
        on_timeout, timeout = unattended_policy(ctx.world)
        turn_id = (ctx.turn_state or {}).get("turn_id", "")
        approval = await request_approval(
            # title = 要用户拍板的那句话；detail = AI 写的补充内容，按 markdown 渲染
            ctx.world.id, turn_id, kind=kind, title=question,
            body=detail, body_format="markdown",
            timeout=timeout, on_timeout=on_timeout,
        )
        # attended = 真有人点了按钮（超时/没前端为 False）；别再抠"未回复"这类字样判断
        return {
            "success": True, "approved": approval.approved, "answered": approval.attended,
            "answer": ("同意" if approval.approved else "不同意") if approval.attended else "未回复",
            USER_NOTE_KEY: approval.note,       # 用户自己写的理由/补充要求，原样交给 AI
            "summary": approval.reason,         # 一句话结论（含无人应答的说明）
        }

    def summary(self, result: dict) -> str:
        if not result.get("success"):
            return f"询问失败：{result.get('error', '未知错误')}"
        text = f"用户{result.get('answer', '未答复')}"
        note = result.get(USER_NOTE_KEY) or ""
        return f"{text}（{note}）" if note else text
