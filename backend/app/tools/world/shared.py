"""世界工具共用件。

被多个工具复用的东西放这里（参数解析、群 id 解析、两阶段网络下载），
工具文件只 import 自己用得上的那几个。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from app.models.world import WorldBinding

logger = logging.getLogger(__name__)

# ── web_download：两阶段（先确认后下载）──
_DOWNLOAD_CONFIRM_TTL = 300                     # 确认有效期 5 分钟
_DOWNLOAD_EXT_WHITELIST = {
    ".html", ".htm", ".css", ".js", ".mjs", ".json", ".map",
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp",
    ".txt", ".md", ".xml", ".csv", ".yaml", ".yml", ".toml",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".zip", ".gz", ".tar", ".pdf",
}
# 世界 id → {confirm_id, url, path, ts}（进程内待确认，重启即失效——安全兜底）
_pending_downloads: dict[int, dict] = {}


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


def auto_download_path(url: str, content_type: str) -> str:
    """自动命名：优先 URL 文件名，其次按 content-type 映射扩展名。"""
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    if name and "." in name and not name.startswith("."):
        return f"assets/{name}"
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
    return f"assets/download-{uuid.uuid4().hex[:8]}{ext}"


async def web_download(world, arguments: str) -> dict:
    """两阶段下载：
    阶段 1（无 confirm_id）：SSRF 检查 + 登记待确认 → need_confirm + confirm_id
    阶段 2（confirmed=true + confirm_id）：校验匹配 → 下载 → 白名单/大小校验 → 写世界文件夹
    """
    import httpx
    from app.tools.file_operations.web_fetch import _is_private_url

    args = parse_args(arguments)
    url = str(args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"success": False, "error": "URL 必须以 http/https 开头"}
    block = await asyncio.to_thread(_is_private_url, url)
    if block:
        return {"success": False, "error": f"禁止访问内网/本机地址：{block}"}

    wid = world.id
    confirm_id = str(args.get("confirm_id") or "").strip()
    confirmed = bool(args.get("confirmed"))
    want_path = str(args.get("path") or "").strip()

    if not confirmed:
        # 阶段 1：登记待确认
        cid = uuid.uuid4().hex[:12]
        _pending_downloads[wid] = {"confirm_id": cid, "url": url, "path": want_path, "ts": time.time()}
        logger.info(f"🌐 世界 #{wid} 请求下载待确认: {url[:80]}")
        return {
            "status": "need_confirm",
            "confirm_id": cid,
            "url": url,
            "path": want_path or "（自动命名到 assets/）",
            "hint": "在回复里询问用户是否允许下载此文件，用户同意后再调用第二次（带 confirm_id + confirmed=true）",
        }

    # 阶段 2：校验确认
    pend = _pending_downloads.get(wid)
    if not pend or pend.get("confirm_id") != confirm_id or pend.get("url") != url:
        return {"success": False, "error": "确认信息无效，请重新发起下载"}
    if time.time() - pend.get("ts", 0) > _DOWNLOAD_CONFIRM_TTL:
        _pending_downloads.pop(wid, None)
        return {"success": False, "error": "确认已过期（5 分钟），请重新发起下载"}

    path = want_path or pend.get("path") or ""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (AIsChat world downloader)"})
        if r.status_code != 200:
            return {"success": False, "error": f"下载失败：HTTP {r.status_code}"}
        content = r.content
        ext = Path(path.split("?")[0]).suffix.lower()
        if ext and ext not in _DOWNLOAD_EXT_WHITELIST:
            return {"success": False, "error": f"不允许下载 {ext} 类型文件"}
        if not path:
            path = auto_download_path(url, r.headers.get("content-type", ""))
        from app.services.world.world_file_service import write_file_bytes, MAX_FILE_SIZE
        if len(content) > MAX_FILE_SIZE:
            return {"success": False, "error": f"文件过大（{len(content) // 1024}KB > {MAX_FILE_SIZE // 1024 // 1024}MB）"}
        write_file_bytes(world.id, path, content)
        _pending_downloads.pop(wid, None)
        logger.info(f"🌐 世界 #{wid} 已下载 {url[:60]} → {path}（{len(content)}B）")
        return {"success": True, "path": path, "size": len(content), "url": url}
    except ValueError as e:
        return {"success": False, "error": f"保存失败：{str(e)[:120]}"}
    except httpx.HTTPError as e:
        return {"success": False, "error": f"下载失败：{str(e)[:120]}"}
