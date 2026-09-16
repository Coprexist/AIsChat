"""web_fetch — 抓网页

上网查资料：获取指定 URL 的网页内容（纯文本）。比 browser 命令更轻量快速，适合获取网页正文、API 响应、文档等。不支持需要 JavaScript 渲染的页面（如 SPA 应用）。页面加载慢/内容延迟出现时
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class WebFetchTool(WorldToolPlugin):
    name = 'web_fetch'
    label = '抓网页'
    segment = 'net'

    description = (
        '上网查资料：获取指定 URL 的网页内容（纯文本）。比 browser 命令更轻量快速，适合获取网页正文、API 响应、文档等。不支持需要 JavaScript 渲染的页面（如 SPA 应用）'
        '。页面加载慢/内容延迟出现时，可设置 delay_ms 先等待再抓取。'
    )

    parameters = {'url': {'type': 'string', 'description': '要访问的完整 URL（含 https://）'},
     'selector': {'type': 'string',
                  'description': "可选：只提取指定标签的内容（如 'article'、'div'、'p'）。注意：只支持 HTML 标签名，不支持 CSS "
                                 '类/ID 选择器'},
     'delay_ms': {'type': 'integer',
                  'description': '可选：发起请求前先等待的毫秒数（0-30000，默认 0）。目标网页加载慢/内容延迟出现时设置，给服务器和页面数据生成留出时间'}}

    required = ['url']

    async def execute(self, ctx: WorldToolContext) -> dict:
        # 复用主系统同一份实现（含 delay_ms 延迟抓取）
        try:
            from app.tools.file_operations.web_fetch import WebFetch
            from app.tools.world.shared import from_site_result
            result = await WebFetch().execute(ctx.world_repo.session, 0, None, ctx.args, {})
            return from_site_result(result)          # 主站错误形状 → 世界约定（唯一适配点）
        except (ValueError, TypeError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            via = f"（经镜像 {result['via']}）" if result.get("via") else ""
            return f"已获取 {result.get('url', '')[:60]}{via}"
        return f"抓取失败：{result.get('error', '未知错误')}"
