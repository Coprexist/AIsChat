"""
web_fetch 工具 — AI 通过 HTTP 请求获取网页内容（轻量，不依赖 Chromium）
"""
import re
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry, ToolErrorCode

logger = logging.getLogger(__name__)

# 常用 User-Agent 伪装
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
# 最大响应字节（500KB）
MAX_RESPONSE_BYTES = 500 * 1024
# 超时
TIMEOUT = 15.0


class WebFetch(ToolPlugin):
    name = "web_fetch"
    description = (
        "上网查资料：获取指定 URL 的网页内容（纯文本）。"
        "比 browser 命令更轻量快速，适合获取网页正文、API 响应、文档等。"
        "不支持需要 JavaScript 渲染的页面（如 SPA 应用）。"
    )
    segment = "file_operations"
    parameters = {
        "url": {
            "type": "string",
            "description": "要访问的完整 URL（含 https://）",
        },
        "selector": {
            "type": "string",
            "description": "可选：只提取指定标签的内容（如 'article'、'div'、'p'）。注意：只支持 HTML 标签名，不支持 CSS 类/ID 选择器",
            "nullable": True,
        },
    }
    required = ["url"]
    states = ["active", "dnd"]
    admin_description = "AI 通过 HTTP 获取网页内容，无需 Chromium 浏览器。无法渲染 JavaScript 页面。"
    trigger_condition = "AI 需要查阅网络资料时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.utils.error_handler import build_tool_error

        url = arguments["url"].strip()
        selector = arguments.get("selector", "").strip() or None

        # 基本 URL 校验
        if not url.startswith(("http://", "https://")):
            return build_tool_error(ToolErrorCode.TOOL_EXEC_FAILED, "URL 必须以 http:// 或 https:// 开头")

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": UA})

            if resp.status_code >= 400:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}",
                    "url": url,
                }

            # 截断过大响应
            content = resp.text[:MAX_RESPONSE_BYTES]
            if len(resp.text) > MAX_RESPONSE_BYTES:
                content += "\n\n[内容已被截断，仅显示前 500KB]"

            # 简单 HTML 转文本（如果响应是 HTML）
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type.lower():
                content = _html_to_text(content, selector)

            return {
                "success": True,
                "url": url,
                "status": resp.status_code,
                "content": content[:10000],  # 给 AI 看的最终内容限制 10K 字符
                "content_type": content_type,
            }

        except httpx.TimeoutException:
            return build_tool_error(ToolErrorCode.TOOL_EXEC_FAILED, f"请求超时（{TIMEOUT}s）")
        except httpx.ConnectError:
            return build_tool_error(ToolErrorCode.TOOL_EXEC_FAILED, f"连接失败：无法访问 {url}")
        except Exception as e:
            logger.error(f"web_fetch 失败: {e}", exc_info=True)
            return build_tool_error(ToolErrorCode.TOOL_EXEC_FAILED, f"请求失败: {str(e)}")


def _html_to_text(html: str, selector: str | None = None) -> str:
    """简单 HTML → 纯文本（不依赖第三方解析库，适合常见场景）"""
    # 如果提供了 selector，尝试用正则提取对应标签内容（简化版）
    if selector:
        # 匹配 <tag> 或 <tag class="..."> 或 <tag id="...">
        pattern = rf'<{selector}[^>]*>(.*?)</{selector}>'
        matches = re.findall(pattern, html, re.DOTALL)
        if matches:
            html = "\n".join(matches)

    # 去掉 script/style
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)

    # 替换 br 为换行
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)

    # 去掉所有标签
    html = re.sub(r'<[^>]+>', '', html)

    # 解码 HTML 实体
    html = html.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    html = html.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')

    # 合并空白行
    lines = [line.strip() for line in html.split('\n')]
    lines = [line for line in lines if line]
    return '\n'.join(lines)


ToolRegistry.register(WebFetch)
