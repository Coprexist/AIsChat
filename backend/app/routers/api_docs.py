"""
世界 API 接口文档（程序员查看/下载用）——独立前缀，避免与 /worlds/{world_id} 冲突

与 view_api_doc 工具同源（data/world_api_docs/sections/*.md），AI 看到的文档这里都能看。
"""
from fastapi import APIRouter, Depends, HTTPException
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api-docs", tags=["接口文档"])


@router.get("")
async def list_api_docs(current_user: dict = Depends(get_current_user)):
    """分区列表（id / 标题 / 区介绍）"""
    from app.services.world.world_api_docs import SECTIONS
    return {"sections": SECTIONS}


@router.get("/{section_id}")
async def get_api_doc(section_id: str, current_user: dict = Depends(get_current_user)):
    """读取某个分区的接口文档内容（防路径穿越：仅注册表内 id）"""
    from app.services.world.world_api_docs import view_section
    try:
        return view_section(section_id)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
