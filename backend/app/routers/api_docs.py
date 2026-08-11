"""
世界 API 接口文档（程序员查看/下载用）——独立前缀，避免与 /worlds/{world_id} 冲突

与 view_api_doc 工具同源（data/world_api_docs/sections/*.md），AI 看到的文档这里都能看。

导出：md 直接下载；docx 走 pandoc（可选能力——容器装了 pandoc 才可用）。
"""
import logging
import shutil
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session as _async_session
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-docs", tags=["接口文档"])

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# pandoc 在线安装状态（内存态；重启后 pandoc 已装则 docx_available 直接为 True）
_INSTALL_STATE: dict = {"running": False, "ok": False, "error": "", "started_at": ""}


def docx_available() -> bool:
    """pandoc 是否可用（可选依赖：容器装了/在线装完才有 docx 导出）"""
    return shutil.which("pandoc") is not None


async def _install_pandoc_background() -> None:
    """后台安装 pandoc（apt-get；管理员触发，进度靠轮询 status）"""
    from datetime import datetime, timezone
    _INSTALL_STATE["running"] = True
    _INSTALL_STATE["error"] = ""
    _INSTALL_STATE["started_at"] = datetime.now(timezone.utc).isoformat()
    try:
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            "apt-get", "update", "-qq",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        proc = await asyncio.create_subprocess_exec(
            "apt-get", "install", "-y", "-qq", "--no-install-recommends", "pandoc",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        _INSTALL_STATE["ok"] = proc.returncode == 0
        _INSTALL_STATE["error"] = "" if proc.returncode == 0 else f"apt 安装失败（code {proc.returncode}）"
    except Exception as e:
        _INSTALL_STATE["ok"] = False
        _INSTALL_STATE["error"] = str(e)
    finally:
        _INSTALL_STATE["running"] = False


@router.get("")
async def list_api_docs(current_user: dict = Depends(get_current_user)):
    """分区列表（id / 标题 / 区介绍）"""
    from app.services.world.world_api_docs import SECTIONS
    return {"sections": SECTIONS}


@router.get("/status")
async def export_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(_async_session),
):
    """导出能力状态：docx 是否可用 + 当前用户是否管理员（未装时管理员看安装提示，普通用户不显示）"""
    from app.models.user import User
    u = await db.get(User, current_user["user_id"])
    is_admin = bool(u and u.role == "admin")
    return {
        "docx_available": docx_available(),
        "is_admin": is_admin,
        "installing": _INSTALL_STATE["running"],
        "install_error": _INSTALL_STATE["error"] or None,
    }


@router.post("/install")
async def install_pandoc(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(_async_session),
):
    """管理员在线安装 pandoc（apt-get，后台执行；轮询 export/status 看 installing/ok）"""
    from app.models.user import User
    u = await db.get(User, current_user["user_id"])
    if not (u and u.role == "admin"):
        raise HTTPException(status_code=403, detail="仅管理员可安装")
    if docx_available():
        return {"docx_available": True, "installing": False}
    if _INSTALL_STATE["running"]:
        return {"docx_available": False, "installing": True}
    import asyncio
    asyncio.create_task(_install_pandoc_background())
    return {"docx_available": False, "installing": True}


class DocxExportRequest(BaseModel):
    """md 内容 → docx（前端组织好内容（单分区/全部合并），后端只管转换）"""
    md: str
    filename: str = "api-doc.docx"


@router.post("/convert")
async def export_docx(
    req: DocxExportRequest,
    current_user: dict = Depends(get_current_user),
):
    """pandoc 把 md 转 docx 下载（未装 pandoc 返回 400，前端据此隐藏 docx 选项）"""
    if not docx_available():
        raise HTTPException(status_code=400, detail="docx 导出未安装（需要 pandoc）")
    try:
        result = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "docx", "--toc", "--toc-depth=2"],
            input=req.md, capture_output=True, timeout=30,
        )
    except Exception as e:
        logger.error(f"pandoc 转换失败: {e}")
        raise HTTPException(status_code=500, detail=f"docx 转换失败: {e}")
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"pandoc 错误: {result.stderr.decode(errors='replace')[:200]}")
    filename = req.filename if req.filename.endswith(".docx") else req.filename + ".docx"
    return Response(
        result.stdout,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{section_id}")
async def get_api_doc(section_id: str, current_user: dict = Depends(get_current_user)):
    """读取某个分区的接口文档内容（防路径穿越：仅注册表内 id）"""
    from app.services.world.world_api_docs import view_section
    try:
        return view_section(section_id)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
