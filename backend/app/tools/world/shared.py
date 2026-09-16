"""世界工具共用件。

被多个工具复用的东西放这里（参数解析、群 id 解析、下载落点与审核），
工具文件只 import 自己用得上的那几个。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from sqlalchemy import select

from app.models.world import WorldBinding

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"                      # 下载固定落点（产品 2026-09-15 定）


def parse_args(arguments: str) -> dict:
    try:
        return json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}


async def bound_group_ids(ctx) -> list[int]:
    """世界绑定的群 id 列表"""
    rows = (await ctx.world_repo.execute(
        select(WorldBinding).where(
            WorldBinding.world_id == ctx.world.id,
            WorldBinding.entity_type == "group",
        )
    )).scalars().all()
    return [r.entity_id for r in rows]


async def resolve_group_ids(ctx, args: dict) -> list[int]:
    """群 id 解析：显式 group_id 优先；否则世界绑定的群（AI 无需知道编号，符合变量注入哲学）"""
    explicit = args.get("group_id")
    if explicit not in (None, "", 0):
        try:
            return [int(explicit)]
        except (TypeError, ValueError):
            pass
    return await bound_group_ids(ctx)


def normalize_code_url(url: str) -> str:
    """代码站链接归一：GitHub blob / gist 页 → raw 直链。

    AI 常直接贴浏览器地址（github.com/…/blob/… 是 HTML 页不是文件），转成可下载的 raw；
    只做能确定的形态转换，其余原样返回（不猜站点）。
    """
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/(.+)", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    m = re.match(r"https?://gist\.github\.com/[^/]+/[^/]+/?$", url)
    if m:
        return url.rstrip("/") + "/raw"
    return url


def download_target(path: str) -> str:
    """下载固定落点：一律落在 downloads/ 下，AI 给的相对路径当 downloads/ 内的子路径。"""
    rel = (path or "").strip().lstrip("/")
    if rel.startswith(DOWNLOAD_DIR + "/"):
        rel = rel[len(DOWNLOAD_DIR) + 1:]
    if ".." in rel.split("/"):
        raise ValueError("非法路径: 不允许 .. 越界")
    return f"{DOWNLOAD_DIR}/{rel}" if rel else DOWNLOAD_DIR


def auto_download_path(url: str, content_type: str) -> str:
    """自动命名：优先 URL 文件名，其次按 content-type 映射扩展名（落在 downloads/）。"""
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    if name and "." in name and not name.startswith("."):
        return f"{DOWNLOAD_DIR}/{name}"
    ext = ".html"
    if "image/png" in content_type:
        ext = ".png"
    elif "image/jpeg" in content_type:
        ext = ".jpg"
    elif "image/svg" in content_type:
        ext = ".svg"
    elif "image/webp" in content_type:
        ext = ".webp"
    elif "text/css" in content_type:
        ext = ".css"
    elif "javascript" in content_type:
        ext = ".js"
    elif "application/json" in content_type:
        ext = ".json"
    return f"{DOWNLOAD_DIR}/download-{uuid.uuid4().hex[:8]}{ext}"


async def web_download(world, arguments: str, approved: bool = False) -> dict:
    """下载网络文件到固定目录 downloads/（审核 + 后缀守卫 + 大小限制）。

    审批归平台门禁（world_ai_mode.gate_tool_call）统一负责，工具自己不再问：
    - approved=True（自动模式，或用户已在弹窗里同意）→ 直接下载；
    - approved=False（决策技能 / 定时 / 斜杠命令等没走门禁的旁路）→ 下载完成后弹窗问是否保留，
      没人应答按「不保留」删除（产品 2026-09-15 定）。
    """
    import httpx
    from app.tools.file_operations.web_fetch import _is_private_url
    from app.services.world.world_ai_mode import get_mode, request_approval, with_user_note
    from app.services.world.world_moderation import audit, inspect
    from app.services.world.world_file_service import MAX_FILE_SIZE, delete_file, write_file_bytes

    args = parse_args(arguments)
    url = normalize_code_url(str(args.get("url") or "").strip())   # GitHub 页面链接 → raw 直链
    if not url.startswith(("http://", "https://")):
        return {"success": False, "error": "URL 必须以 http/https 开头"}
    block = await asyncio.to_thread(_is_private_url, url)
    if block:
        return {"success": False, "error": f"禁止访问内网/本机地址：{block}"}

    wid = world.id
    want_path = str(args.get("path") or "").strip()
    try:
        planned = download_target(want_path)          # 固定落点：downloads/…
    except ValueError as e:
        return {"success": False, "error": str(e)}
    reason = inspect(url, planned)                    # 下载前先审（URL + 目标文件名）
    if reason:
        audit(wid, url, planned, reason)
        return {"success": False, "error": reason}

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (AIsChat world downloader)"})
        if r.status_code != 200:
            return {"success": False, "error": f"下载失败：HTTP {r.status_code}"}
        content = r.content
        path = planned if want_path else auto_download_path(url, r.headers.get("content-type", ""))
        reason = inspect(url, path, content)          # 下载后复审（文本正文，命中即不落盘）
        if reason:
            audit(wid, url, path, reason)
            return {"success": False, "error": reason}
        if len(content) > MAX_FILE_SIZE:
            return {"success": False, "error": f"文件过大（{len(content) // 1024}KB > {MAX_FILE_SIZE // 1024 // 1024}MB）"}
        write_file_bytes(wid, path, content)
    except ValueError as e:
        return {"success": False, "error": f"保存失败：{str(e)[:160]}"}
    except httpx.HTTPError as e:
        return {"success": False, "error": f"下载失败：{str(e)[:120]}"}
    logger.info(f"🌐 世界 #{wid} 已下载 {url[:60]} → {path}（{len(content)}B）")

    if approved or get_mode(world) == "auto":
        return {"success": True, "path": path, "size": len(content), "url": url}

    # 旁路下载：没经过平台门禁 → 按产品要求，下载完成后再问用户是否保留
    # 事后确认同样不默认保留：没人应答就删掉（on_timeout=False，安全默认）
    keep = await request_approval(
        wid, "", kind="download",
        title=f"是否保留刚下载的文件？{path}",
        detail=f"{url}\n{len(content) // 1024}KB → {path}",
        on_timeout=False,
    )
    if keep.approved:
        # 用户可能顺便写了要求（"留着，但改名叫 x.png"）——不能让这句话烂在弹窗里
        return with_user_note({"success": True, "path": path, "size": len(content), "url": url},
                              keep.instruction)
    try:
        delete_file(wid, path)
    except (ValueError, FileNotFoundError) as e:
        logger.warning(f"🌐 世界 #{wid} 未保留文件删除失败: {e}")
    return {"success": False, "path": path, "error": f"用户选择不保留，已删除刚下载的文件（{keep.reason}）"}
