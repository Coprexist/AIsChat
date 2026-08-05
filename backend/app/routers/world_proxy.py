"""
世界入口路由代理 — 世界标识规范（设计文档 7.3）

  GET /world/{world_id}/files/*   静态资源（路由到世界文件目录）
  GET /world/{world_id}/preview   沉浸界面入口（注入 WORLD_ID）

世界编号由前端注入为变量（window.WORLD_ID），AI/人类代码只管写变量名。
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/world", tags=["群视界入口"])

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def _resolve_world_file(world_id: int, rel_path: str):
    """解析世界文件（防越界），返回 (Path, mime) 或抛 404"""
    from pathlib import Path
    from app.services.world.world_file_service import WORLDS_ROOT

    base = (WORLDS_ROOT / str(world_id)).resolve()
    rel_path = (rel_path or "").strip().lstrip("/")
    if not rel_path or ".." in rel_path.split("/"):
        raise HTTPException(status_code=404, detail="文件不存在")
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    mime = MIME_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return target, mime


async def _get_creator_name(db: AsyncSession, world_id: int) -> str:
    """群视界 AI 名字（worlds.creator_config.name，默认群视界机器人）"""
    from app.models.world import World
    world = await db.get(World, world_id)
    if world is None:
        return "群视界机器人"
    cfg = world.creator_config or {}
    return cfg.get("name") or "群视界机器人"


def _inject_world_vars(html: str, world_id: int, creator_name: str, group_id: int | None) -> str:
    """向世界 HTML 注入环境变量（世界代码零硬编码，打包/换实例即插即用）。

    变量（world code 直接读 window.*）：
      WORLD_ID     世界编号
      WORLD_AI_ID  群视界 AI 身份（world-{id}）
      WORLD_AI_NAME 群视界 AI 名字
      GROUP_ID     入口群聊编号（无 = null）
      USER_ID      当前用户编号（无登录态 = null，客户端可补）
    """
    script = (
        "<script>\n"
        f"window.WORLD_ID = {world_id};\n"
        f"window.WORLD_AI_ID = 'world-{world_id}';\n"
        f"window.WORLD_AI_NAME = {json.dumps(creator_name, ensure_ascii=False)};\n"
        f"window.GROUP_ID = {group_id if group_id is not None else 'null'};\n"
        "window.USER_ID = null; // 由宿主环境注入\n"
        "</script>\n"
        "<script>\n"
        "// 平台 UI 桥：世界代码可控制宿主侧边栏/悬浮图标（详见接口文档）\n"
        "window.WorldUI = {\n"
        "  toggleSidebar: function(){ _worldUi('toggle_sidebar') },\n"
        "  showSidebar: function(){ _worldUi('show_sidebar') },\n"
        "  hideSidebar: function(){ _worldUi('hide_sidebar') },\n"
        "  hideFloatingIcon: function(){ _worldUi('hide_floating_icon') },\n"
        "  showFloatingIcon: function(){ _worldUi('show_floating_icon') }\n"
        "};\n"
        "function _worldUi(action){ try{ window.parent.postMessage({type:'world_ui', action:action}, '*') }catch(e){} }\n"
        "</script>\n"
    )
    if "</head>" in html:
        return html.replace("</head>", script + "</head>", 1)
    if "<head" in html:
        # 有 <head> 但无闭合标签（不标准但常见），插在 head 标签后
        import re
        m = re.search(r"<head[^>]*>", html)
        return html[:m.end()] + script + html[m.end():]
    return script + html


@router.get("/{world_id}/files/{path:path}")
async def serve_world_file(
    world_id: int,
    path: str,
    group_id: int | None = Query(default=None, description="入口群聊编号"),
    db: AsyncSession = Depends(get_db),
):
    """静态资源路由：/world/{WORLD_ID}/files/<相对路径>（HTML 自动注入世界变量）"""
    target, mime = _resolve_world_file(world_id, path)
    if mime.startswith("text/html"):
        creator_name = await _get_creator_name(db, world_id)
        # 变量注入：URL 没带 group_id 时，自动补世界绑定的第一个群（保持「编号一律变量」哲学）
        if group_id is None:
            try:
                from app.models.world import WorldBinding
                row = (await db.execute(
                    select(WorldBinding).where(
                        WorldBinding.world_id == world_id,
                        WorldBinding.entity_type == "group",
                    ).order_by(WorldBinding.id).limit(1)
                )).scalar_one_or_none()
                if row is not None:
                    group_id = row.entity_id
            except Exception:
                pass
        html = target.read_text(encoding="utf-8", errors="replace")
        return HTMLResponse(_inject_world_vars(html, world_id, creator_name, group_id))
    return FileResponse(target, media_type=mime)


@router.get("/{world_id}/preview")
async def world_preview(
    world_id: int,
    group_id: int | None = Query(default=None, description="入口群聊编号"),
    db: AsyncSession = Depends(get_db),
):
    """沉浸界面入口：重定向到规范挂载点 /world/{id}/files/index.html

    页面内部一律用相对路径（打包即插即用）；/preview 与 /files/ 层级不同，
    相对路径在 /preview 下会解析错（style.css → /world/{id}/style.css 404），
    所以统一重定向到 files 挂载点，由 serve_world_file 注入世界变量。
    """
    try:
        _resolve_world_file(world_id, "index.html")
    except HTTPException:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;display:flex;align-items:center;"
            "justify-content:center;height:100vh;color:#888'>"
            "<div>这个世界还没有 index.html，让群视界机器人创建一个吧</div></body></html>"
        )
    # 打开过 = 活跃信号（调度器据此唤醒/延迟休眠）
    try:
        from app.models.world import World
        world = await db.get(World, world_id)
        if world is not None:
            world.last_active_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
    except Exception:
        pass
    url = f"/world/{world_id}/files/index.html"
    if group_id is not None:
        url += f"?group_id={group_id}"
    return RedirectResponse(url, status_code=307)
