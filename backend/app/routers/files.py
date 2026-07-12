"""
文件系统路由
上传、下载、删除、列表、协作模式管理、消息附件
"""
import os
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.file import FileMetadata, FileReference, FileCollaborator
from app.utils.auth import get_current_user
from app.config import settings
from app.services.file_service import (
    upload_file, list_files, get_file, get_file_physical_path,
    delete_file, check_file_access, track_file_reference,
    set_collaboration_mode, add_file_collaborator, remove_file_collaborator,
    get_file_collaborators, get_file_referrers,
    _check_path_safe, _get_physical_path,
    _remove_forward_reference,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fs", tags=["文件"])


# ============================================================
# 目录列表
# ============================================================

@router.get("/list")
async def list_directory(
    path: str = Query("/", description="目录路径"),
    include_forwarded: bool = Query(False, description="是否包含转发来的文件"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出目录内容（自动过滤无权条目），可选包含转发来的文件"""
    if not _check_path_safe(path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径不合法")

    files = await list_files(db, path, "human", current_user["user_id"])

    # 追加用户 AI 的文件（与 /user/storage 对齐）
    from sqlalchemy import select
    from app.models.agent import Agent
    from app.models.file import FileMetadata as FM
    agent_ids_r = await db.execute(
        select(Agent.id).where(Agent.owner_id == current_user["user_id"])
    )
    agent_ids = [row[0] for row in agent_ids_r.all()]
    seen_paths = {f["path"] for f in files}
    for aid in agent_ids:
        ai_files = await list_files(db, path, "ai", aid)
        for f in ai_files:
            if f["path"] not in seen_paths:
                files.append(f)
                seen_paths.add(f["path"])

    # 追加用户 AI 的文件（与 /user/storage 对齐）
    from sqlalchemy import select
    from app.models.agent import Agent
    from app.models.file import FileMetadata as FM
    agent_result = await db.execute(
        select(Agent.id).where(Agent.owner_id == current_user["user_id"])
    )
    agent_ids = [row[0] for row in agent_result.all()]
    if agent_ids:
        ai_files = await list_files(db, path, "ai", agent_ids)  # ai_list_files 接受 list
        # 去重（防止 AI 文件重复）
        seen_paths = {f["path"] for f in files}
        for f in ai_files:
            if f["path"] not in seen_paths:
                files.append(f)
                seen_paths.add(f["path"])

    # 合并转发来的文件
    if include_forwarded:
        from app.services.file_service import get_user_forwarded_file_ids
        forwarded_ids = await get_user_forwarded_file_ids(db, current_user["user_id"])
        if forwarded_ids:
            from sqlalchemy import select
            from app.models.file import FileMetadata as FM
            fwd_result = await db.execute(select(FM).where(FM.id.in_(forwarded_ids)))
            for fm in fwd_result.scalars():
                files.append({
                    "id": fm.id,
                    "path": fm.path,
                    "owner_type": fm.owner_type,
                    "owner_id": fm.owner_id,
                    "size": fm.size,
                    "mime_type": fm.mime_type,
                    "collaboration_mode": fm.collaboration_mode,
                    "created_at": str(fm.created_at) if fm.created_at else None,
                    "updated_at": str(fm.updated_at) if fm.updated_at else None,
                    "is_forwarded": True,
                })

    return files


# ============================================================
# 文件上传
# ============================================================

@router.post("/upload")
async def upload_file_endpoint(
    path: str = Query("/"),
    collaboration_mode: str = Query("solo", pattern="^(solo|shared|open)$"),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传文件"""
    if not _check_path_safe(path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径不合法")

    content = await file.read()
    from app.config import get_effective_upload_max_size_mb
    max_mb = get_effective_upload_max_size_mb()
    max_bytes = max_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(400, f"文件大小不能超过 {max_mb}MB")
    metadata = await upload_file(
        db, path, file.filename or f"unnamed_{uuid.uuid4().hex[:8]}",
        content, file.content_type, "human", current_user["user_id"],
        collaboration_mode=collaboration_mode,
    )

    return {
        "id": metadata.id,
        "path": metadata.path,
        "size": metadata.size,
        "mime_type": metadata.mime_type,
        "collaboration_mode": metadata.collaboration_mode,
        "created_at": str(metadata.created_at) if metadata.created_at else None,
    }


# ============================================================
# 消息附件上传（独立端点，上传后返回 file_id 供消息引用）
# ============================================================

@router.post("/upload-attachment")
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传消息附件（存入 attachments/ 子目录）"""
    content = await file.read()

    # 限制附件大小
    from app.config import get_effective_upload_max_size_mb
    max_mb = get_effective_upload_max_size_mb()
    max_size = max_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                          detail=f"附件大小不能超过 {max_mb}MB")

    try:
        metadata = await upload_file(
            db, "attachments/", file.filename or f"att_{uuid.uuid4().hex[:8]}",
            content, file.content_type, "human", current_user["user_id"],
            collaboration_mode="solo",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"附件上传失败: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"上传失败: {e}")

    return {
        "file_id": metadata.id,
        "name": os.path.basename(metadata.path),
        "path": metadata.path,
        "size": metadata.size,
        "mime_type": metadata.mime_type,
    }


# ============================================================
# 文件下载
# ============================================================

@router.get("/download-avatar/{filename}")
async def serve_avatar(filename: str):
    """直接返回头像文件（无需鉴权，仅限 avatars 目录）"""
    import os
    from fastapi.responses import FileResponse
    filepath = os.path.join("/app/uploads/avatars", filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="头像不存在")
    return FileResponse(filepath)


@router.get("/download/{file_id}")
async def download_file(
    file_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下载文件（含权限检查）"""
    try:
        metadata = await get_file(db, file_id)
    except Exception as e:
        logger.error(f"下载文件 {file_id} 查询元数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="查询文件失败")

    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    # 权限检查
    try:
        can_access = await check_file_access(db, file_id, "human", current_user["user_id"], "read")
    except Exception as e:
        logger.error(f"下载文件 {file_id} 权限检查异常: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"权限检查失败: {e}")

    if not can_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问此文件")

    physical_path = _get_physical_path(metadata.path)
    if not os.path.exists(physical_path):
        logger.error(f"下载文件 {file_id}: 物理文件不存在 path={physical_path} metadata.path={metadata.path}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"物理文件不存在")

    # 追踪引用
    await track_file_reference(db, file_id, "human", current_user["user_id"], "read")

    return FileResponse(
        physical_path,
        media_type=metadata.mime_type or "application/octet-stream",
        filename=os.path.basename(metadata.path),
    )


@router.get("/public/{file_id}")
async def download_public_file(file_id: int, db: AsyncSession = Depends(get_db)):
    """公开下载（无需登录，供维护弹窗等场景）"""
    metadata = await get_file(db, file_id)
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    physical_path = _get_physical_path(metadata.path)
    if not os.path.exists(physical_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="物理文件不存在")
    return FileResponse(physical_path, media_type=metadata.mime_type or "application/octet-stream")


# ============================================================
# 文件删除
# ============================================================

@router.delete("/delete/{file_id}")
async def delete_file_endpoint(
    file_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除文件（owner 删除时会自动过户给转发者或标记孤儿）"""
    try:
        result = await delete_file(db, file_id, "human", current_user["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    action = result.get("action", "deleted")
    messages = {
        "deleted": "文件已删除",
        "released": "已释放文件引用",
        "transferred": f"文件已由他人接管",
        "orphaned": "文件无人持有，将在宽限期后清理",
    }
    return {"message": messages.get(action, "操作成功"), **result}


@router.delete("/release/{file_id}")
async def release_file_reference(
    file_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """释放转发文件的引用（非 owner 从存储中移除）"""
    try:
        result = await delete_file(db, file_id, "human", current_user["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"message": "已释放文件引用", **result}


# ============================================================
# 协作模式管理
# ============================================================

@router.put("/{file_id}/collaboration-mode")
async def update_collaboration_mode(
    file_id: int,
    mode: str = Query(..., pattern="^(solo|shared|open)$"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改文件协作模式（仅 owner）"""
    try:
        metadata = await set_collaboration_mode(db, file_id, mode, "human", current_user["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "file_id": metadata.id,
        "path": metadata.path,
        "collaboration_mode": metadata.collaboration_mode,
    }


@router.post("/{file_id}/collaborators")
async def add_collaborator(
    file_id: int,
    collaborator_type: str = Query(..., pattern="^(ai|user)$"),
    collaborator_id: int = Query(...),
    role: str = Query("collaborator", pattern="^(collaborator|viewer)$"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """添加文件协作者（仅 owner）"""
    try:
        collab = await add_file_collaborator(
            db, file_id, collaborator_type, collaborator_id, role,
            requester_type="human", requester_id=current_user["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "id": collab.id,
        "file_id": collab.file_id,
        "collaborator_type": collab.collaborator_type,
        "collaborator_id": collab.collaborator_id,
        "role": collab.role,
    }


@router.delete("/{file_id}/collaborators/{collaborator_type}/{collaborator_id}")
async def remove_collaborator(
    file_id: int,
    collaborator_type: str,
    collaborator_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """移除文件协作者"""
    try:
        await remove_file_collaborator(db, file_id, collaborator_type, collaborator_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"message": "协作者已移除"}


@router.get("/{file_id}/collaborators")
async def list_collaborators(
    file_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出文件的协作者"""
    metadata = await get_file(db, file_id)
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    collaborators = await get_file_collaborators(db, file_id)
    referrers = await get_file_referrers(db, file_id)

    return {
        "file_id": file_id,
        "path": metadata.path,
        "collaboration_mode": metadata.collaboration_mode,
        "collaborators": collaborators,
        "referrers": referrers,
    }


@router.get("/{file_id}/references-detail")
async def get_file_references_detail(
    file_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取文件的详细引用信息（含群名、AI 名等可读名称），用于删除确认"""
    from app.models.file import FileReference as FR
    from app.models.agent import Agent
    from app.models.user import User
    from app.models.group import Group as GroupModel
    from app.models.message import Message as MessageModel
    from sqlalchemy import select

    metadata = await get_file(db, file_id)
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    # 查询所有引用
    ref_result = await db.execute(
        select(FR).where(FR.file_id == file_id)
    )
    refs = ref_result.scalars().all()

    references = []
    for r in refs:
        ref_info = {
            "referrer_type": r.referrer_type,
            "referrer_id": r.referrer_id,
            "ref_type": r.ref_type,
            "display": f"{r.referrer_type}:{r.referrer_id}",
        }

        # 解析为可读名称
        if r.referrer_type == "ai":
            agent_result = await db.execute(select(Agent.name).where(Agent.id == r.referrer_id))
            name = agent_result.scalar_one_or_none()
            ref_info["display"] = f"AI「{name or r.referrer_id}」"

        elif r.referrer_type == "human":
            user_result = await db.execute(select(User.username).where(User.id == r.referrer_id))
            name = user_result.scalar_one_or_none()
            ref_info["display"] = f"用户「{name or r.referrer_id}」"

        elif r.referrer_type == "group":
            group_result = await db.execute(select(GroupModel.name).where(GroupModel.id == r.referrer_id))
            name = group_result.scalar_one_or_none()
            ref_info["display"] = f"群聊「{name or r.referrer_id}」"

        elif r.referrer_type == "message":
            # 消息引用：查出消息所在的群聊或 DM
            msg_result = await db.execute(
                select(MessageModel.group_id).where(MessageModel.id == r.referrer_id)
            )
            gid = msg_result.scalar_one_or_none()
            if gid is not None:
                # 群聊消息
                gname_result = await db.execute(select(GroupModel.name).where(GroupModel.id == gid))
                gname = gname_result.scalar_one_or_none()
                ref_info["display"] = f"群聊「{gname or gid}」的消息 #{r.referrer_id}"
            else:
                ref_info["display"] = f"私信消息 #{r.referrer_id}"

        references.append(ref_info)

    return {
        "file_id": file_id,
        "path": metadata.path,
        "name": metadata.path.rsplit("/", 1)[-1] if "/" in metadata.path else metadata.path,
        "size": metadata.size,
        "reference_count": len(references),
        "references": references,
    }


# ============================================================
# 创建目录
# ============================================================

@router.post("/mkdir")
async def create_directory(
    path: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """创建目录"""
    if not _check_path_safe(path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径不合法")

    physical_path = os.path.join(settings.data_dir, path)
    os.makedirs(physical_path, exist_ok=True)

    return {"message": "目录已创建", "path": path}
