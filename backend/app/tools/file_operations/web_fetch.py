"""
web_fetch 工具 — AI 通过 HTTP 请求获取网页内容（轻量，不依赖 Chromium）
"""
import asyncio
import re
import logging
import socket
import httpx
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry, ToolErrorCode
from app.utils.pure.url_guard import classify_address

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 出站取数（SSRF 防护的唯一入口）
# ═══════════════════════════════════════════════════════════════
# 一个域名可能解析出多个地址，其中只有一个是坏的。实例（2026-09-16 用户反馈
# "禁止访问内网地址: lite.duckduckgo.com (2001::1f0d:5e0a)"）：本机 DNS 给这个域名塞了个
# 2001::1f0d:5e0a——它在 2001::/32（Teredo）里，本机根本没有隧道，拨过去只会
# "Network is unreachable"；而它旁边那个公网 IPv4 是好的。
# 原先的判定「任一地址命中 is_private 就整单拒绝」有两个毛病：
#   ① 把这种特殊用途地址说成"内网地址"，误导用户；
#   ② 连带着把能用的公网地址一起毙掉。
#
# 现在的做法：**地址由我们自己挑、自己拨**（把选中的 IP 钉进连接，Host 头与 SNI 仍是原域名，
# 证书校验不受影响），并且**每一跳重定向都重新复检**——这比"只看第一次解析"更严，不是更松：
# 唯一的放松是"不再因为一个不可拨的地址否决整次请求"，而真正指向内网的地址照旧一律拒绝。
# "哪些地址算内网"只在 app/utils/pure/url_guard.py 定义一处（出站守卫共用同一份判定）。
REDIRECT_LIMIT = 5
# 超时类异常的默认文案（它们常常自带空字符串消息）
_TIMEOUT_LABELS = {httpx.ConnectTimeout: "连接超时", httpx.ReadTimeout: "读取超时", httpx.WriteTimeout: "写入超时"}


class BlockedFetch(Exception):
    """被 SSRF 防护拦下 / 地址不可用（msg 是给用户看的一句话）"""




def resolve_candidates(url: str) -> tuple[list[str], str | None]:
    """解析域名 → 可拨地址列表（IPv4 优先）。返回 (地址, 错误文案)，错误时地址为空。

    只要出现**任一**内网地址就整单拒绝（DNS rebinding 的经典打法：一半公网一半内网），
    这条比"挑个公网的就走"更保守；而不可拨的特殊用途地址只是被跳过。
    """
    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except ValueError:
        return [], "URL 解析失败"
    if not host:
        return [], "URL 缺少主机名"
    if host in ("localhost", "localhost.localdomain") or host.endswith(".local"):
        return [], f"禁止访问本机/内网地址: {host}"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return [], f"域名解析失败：{host}"
    internal: list[str] = []
    usable: list[str] = []
    unusable: list[str] = []
    for info in infos:
        ip = str(info[4][0]).split("%")[0]
        kind = classify_address(ip)
        bucket = internal if kind == "internal" else usable if kind == "ok" else unusable
        if ip not in bucket:
            bucket.append(ip)
    if internal:
        return [], f"禁止访问内网地址: {host} ({internal[0]})"
    if not usable:
        extra = f"，只解析到 {unusable[0]}（不可路由的特殊用途地址）" if unusable else ""
        return [], f"没有可用地址：{host}{extra}"
    # IPv4 优先：本机没有 IPv6 出口时，先拨 v6 只会 Network is unreachable（用户机器实测）
    usable.sort(key=lambda ip: ":" in ip)
    return usable, None


def pin_url(url: str, ip: str) -> str:
    """把 URL 的主机名换成已复检通过的 IP（Host 头与 SNI 保持原域名，证书照常校验）"""
    host = f"[{ip}]" if ":" in ip else ip
    return str(httpx.URL(url).copy_with(host=host))


async def safe_get(client: httpx.AsyncClient, url: str, *, headers: dict | None = None,
                   max_redirects: int = REDIRECT_LIMIT) -> httpx.Response:
    """SSRF 安全的 GET（对外唯一入口）：自己挑地址、钉住连接、逐跳复检重定向。

    调用方建 client 时**不要**开 follow_redirects（每一跳都要过一遍内网判定）。
    """
    request_headers = dict(headers or {})
    for _ in range(max_redirects + 1):
        candidates, block = await asyncio.to_thread(resolve_candidates, url)
        if block:
            raise BlockedFetch(block)
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Host 头照抄原 netloc（含端口、去掉 userinfo）：服务端看到的还是它自己的域名
        netloc = parsed.netloc.rsplit("@", 1)[-1]
        resp: httpx.Response | None = None
        last_error: Exception | None = None
        for ip in candidates:
            try:
                resp = await client.get(
                    pin_url(url, ip),
                    headers={**request_headers, "Host": netloc},
                    extensions={"sni_hostname": host} if parsed.scheme == "https" else None,
                )
                break
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                last_error = e            # 这个地址不通就换下一个：多地址域名不该被一个坏地址拖死
        if resp is None:
            # ConnectTimeout 这类异常自带空消息，别给用户看「（）」
            assert last_error is not None
            why = _TIMEOUT_LABELS.get(type(last_error)) or str(last_error) or type(last_error).__name__
            raise BlockedFetch(f"连接失败：{host}（{why}）")
        location = resp.headers.get("location")
        if resp.is_redirect and location:
            url = str(resp.url.join(location))
            continue
        return resp
    raise BlockedFetch(f"重定向次数过多（>{max_redirects}）")


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
        "页面加载慢/内容延迟出现时，可设置 delay_ms 先等待再抓取。"
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
        "delay_ms": {
            "type": "integer",
            "description": "可选：发起请求前先等待的毫秒数（0-30000，默认 0）。目标网页加载慢/内容延迟出现时设置，给服务器和页面数据生成留出时间",
            "nullable": True,
        },
    }
    required = ["url"]
    states = ["active", "dnd"]
    admin_description = "AI 通过 HTTP 获取网页内容，无需 Chromium 浏览器。无法渲染 JavaScript 页面。支持 delay_ms 等待后再抓取。"
    trigger_condition = "AI 需要查阅网络资料时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.utils.error_handler import build_tool_error

        url = arguments["url"].strip()
        selector = arguments.get("selector", "").strip() or None
        # AI 可设定延迟：等待指定毫秒后再发起请求（慢速/动态加载页面用）
        try:
            delay_ms = min(max(int(arguments.get("delay_ms") or 0), 0), 30000)
        except (TypeError, ValueError):
            delay_ms = 0
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

        # 基本 URL 校验
        if not url.startswith(("http://", "https://")):
            return build_tool_error(ToolErrorCode.TOOL_EXEC_FAILED, "URL 必须以 http:// 或 https:// 开头")

        # SSRF 防护：挑地址 + 钉住连接 + 逐跳复检，全在 safe_get 一处（不要再自己解析一遍）
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await safe_get(client, url, headers={"User-Agent": UA})

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

        except BlockedFetch as e:
            return build_tool_error(ToolErrorCode.TOOL_EXEC_FAILED, str(e))
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
