"""web_search — 网页搜索

搜索引擎：通过 Bing 搜索网络上的最新信息，返回标题、链接和摘要。使用场景：搜索新闻、查找资料、获取实时信息、验证事实。与 web_fetch 配合使用：先用 web_search 找链接，再用 web_fetch 
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class WebSearchTool(WorldToolPlugin):
    name = 'web_search'
    label = '网页搜索'
    segment = 'net'

    description = (
        '搜索引擎：通过 Bing 搜索网络上的最新信息，返回标题、链接和摘要。使用场景：搜索新闻、查找资料、获取实时信息、验证事实。与 web_fetch 配合使用：先用 web_search 找链接，'
        '再用 web_fetch 看具体内容。'
    )

    parameters = {'query': {'type': 'string', 'description': '搜索关键词，支持中文'},
     'count': {'type': 'integer', 'description': '返回结果数量（1-10，默认 5）'}}

    required = ['query']

    async def execute(self, ctx: WorldToolContext) -> dict:
        # 复用主系统同一份实现（同一份代码，无 opencli 依赖）
        try:
            args = ctx.args
            from app.tools.file_operations.web_search import WebSearch
            return await WebSearch().execute(ctx.world_repo.session, 0, None, args, {})
        except (ValueError, TypeError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            return f"搜索结果 {result.get('count', 0)} 条：" + "、".join(r.get('title', '')[:20] for r in (result.get('results') or [])[:5])
        return f"搜索失败：{result.get('error', '未知错误')}"
