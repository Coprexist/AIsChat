"""rename_session — 给当前对话命名

群视界 AI 给「当前这场对话」起名或改名：会话列表里显示名字，比 w12:m:3f9a… 好认。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class RenameSessionTool(WorldToolPlugin):
    name = 'rename_session'
    label = '命名对话'
    segment = 'self'

    description = (
        '给**当前这场对话**起名或改名（用户在会话列表里看到的就是这个名字）。\n'
        '什么时候用：一个话题聊出眉目时、或换了新话题时，顺手起个 6~20 字的短名字'
        '（如「造卡牌对战界面」「修地缝掉落」）；用户说"这个对话叫 xxx"就照改。\n'
        '名字是给用户做导航用的，不是日志——别写时间戳、别把整句需求抄进去。'
        '传空字符串 = 清除命名（回落显示编号）。'
    )

    parameters = {'title': {'type': 'string', 'description': '对话名（6~20 字，短而具体；空字符串 = 清除）'}}

    required = ['title']

    async def execute(self, ctx: WorldToolContext) -> dict:
        from app.services.world.world_chat_service import set_session_title
        title = set_session_title(ctx.world, str(ctx.args.get("title") or ""))
        try:
            await ctx.world_repo.commit()
        except Exception as e:
            return {"success": False, "error": f"保存失败：{e}"}
        return {"success": True, "title": title}

    def summary(self, result: dict) -> str:
        if not result.get("success"):
            return f"命名失败：{result.get('error', '未知错误')}"
        return f"本对话已命名为「{result['title']}」" if result.get("title") else "已清除本对话的命名"
