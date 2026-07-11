"""
web_search 工具 — AI 通过 Bing 搜索获取网页搜索结果（轻量，不依赖 API Key）
"""
import re
import logging
import httpx
from urllib.parse import quote_plus
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry, ToolErrorCode

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
TIMEOUT = 10.0
MAX_RESULTS = 10


class WebSearch(ToolPlugin):
    name = "web_search"
    description = (
        "搜索引擎：通过 Bing 搜索网络上的最新信息，返回标题、链接和摘要。"
        "使用场景：搜索新闻、查找资料、获取实时信息、验证事实。"
        "与 web_fetch 配合使用：先用 web_search 找链接，再用 web_fetch 看具体内容。"
    )
    segment = "file_operations"
    parameters = {
        "query": {
            "type": "string",
            "description": "搜索关键词，支持中文",
        },
        "count": {
            "type": "integer",
            "description": f"返回结果数量（1-{MAX_RESULTS}，默认 5）",
            "nullable": True,
        },
    }
    required = ["query"]
    states = ["active", "dnd"]
    admin_description = "AI 通过 Bing 搜索网络信息，无需 API Key。返回标题+链接+摘要。"
    trigger_condition = "AI 需要查询实时信息/新闻/资料时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.utils.error_handler import build_tool_error

        query = arguments["query"].strip()
        count = min(arguments.get("count", 5) or 5, MAX_RESULTS)

        if not query:
            return build_tool_error(ToolErrorCode.TOOL_EXEC_FAILED, "搜索关键词不能为空")

        try:
            results = await _search_bing(query, count)
            return {
                "success": True,
                "query": query,
                "count": len(results),
                "results": results,
                "tip": "如需查看具体内容，请使用 web_fetch 工具打开对应链接",
            }
        except Exception as e:
            logger.error(f"web_search 失败: {e}", exc_info=True)
            return build_tool_error(ToolErrorCode.TOOL_EXEC_FAILED, f"搜索失败: {str(e)}")


async def _search_bing(query: str, count: int) -> list[dict]:
    """通过 Bing 搜索，返回结构化结果列表"""
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={count}"

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, headers={
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    if resp.status_code >= 400:
        raise Exception(f"Bing 返回 HTTP {resp.status_code}")

    html = resp.text
    results = []

    # Bing 搜索结果格式：
    # <li class="b_algo"> 包含标题、链接、摘要
    # 按 <h2><a href="...">标题</a></h2> 提取

    # 分割成结果块
    blocks = re.split(r'<li[^>]*class="b_algo"[^>]*>', html)[1:]

    for block in blocks[:count]:
        try:
            # 标题 + 链接
            title_match = re.search(r'<h2[^>]*>.*?<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_match:
                continue
            link = title_match.group(1)
            title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()

            # 摘要
            snippet = ""
            snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
            if snippet_match:
                snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                # 清理 Bing 的省略号
                snippet = snippet.replace(' ...', '…').replace('&amp;', '&')

            if title and link:
                results.append({
                    "title": title,
                    "url": link,
                    "snippet": snippet or "",
                })
        except Exception:
            continue

    return results


ToolRegistry.register(WebSearch)
