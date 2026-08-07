"""
世界商城 API — 世界包发布 / 浏览 / 一键导入（2026-08-07 MVP）

- 发布：世界代码区（不含 content/）导出 zip → 存 data/market/ → 商品元数据入库
- 浏览：列表 + 搜索（标题/描述）+ 标签过滤
- 导入：下载 zip → 创建新世界 → import_zip（安全过滤）→ 一键复制
- 分级：MVP 只做 world（完整世界包）；block（积木组件）后置
"""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["世界商城"])

DATA_DIR = Path("data")
MARKET_DIR = DATA_DIR / "market"
MAX_PACKAGE_BYTES = 20 * 1024 * 1024  # 世界包上限 20MB


# ═══════════════════════════════════════════════════════════════
# 模型
# ═══════════════════════════════════════════════════════════════

class PublishRequest(BaseModel):
    world_id: int
    title: str = ""
    description: str = ""
    tags: list[str] = []


class UpdateItemRequest(BaseModel):
    """编辑商品（字段可选，只更新提供的）"""
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None


# ═══════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════

def _item_dict(item) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "title": item.title,
        "description": item.description,
        "tags": item.tags or [],
        "author_id": item.author_id,
        "author_name": item.author_name,
        "source_world_id": item.source_world_id,
        "package_size": item.package_size,
        "downloads": item.downloads,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


async def _require_owner(db: AsyncSession, world_id: int, user_id: int):
    from app.models.world import World
    world = (await db.execute(select(World).where(World.id == world_id))).scalar_one_or_none()
    if world is None:
        raise HTTPException(status_code=404, detail="世界不存在")
    if world.owner_id != user_id:
        raise HTTPException(status_code=403, detail="只有世界创建者可以发布")
    return world


# ═══════════════════════════════════════════════════════════════
# 发布 / 列表 / 详情 / 下架 / 导入 / 下载
# ═══════════════════════════════════════════════════════════════

@router.post("/items")
async def publish_item(
    req: PublishRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发布当前世界到商城（世界代码区打包，不含 content/）"""
    world = await _require_owner(db, req.world_id, current_user["user_id"])
    from app.services.world.world_file_service import export_zip
    data = export_zip(world.id, include_content=False)
    if not data:
        raise HTTPException(status_code=400, detail="世界没有可发布的文件")
    if len(data) > MAX_PACKAGE_BYTES:
        raise HTTPException(status_code=400, detail=f"世界包过大（{len(data)//1024}KB > {MAX_PACKAGE_BYTES//1024//1024}MB）")

    from app.models.world import WorldMarketItem
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex[:16]}.zip"
    (MARKET_DIR / fname).write_bytes(data)

    title = (req.title or world.name).strip()[:100]
    item = WorldMarketItem(
        kind="world",
        title=title,
        description=(req.description or world.description or "").strip(),
        tags=[str(t).strip()[:30] for t in (req.tags or []) if str(t).strip()][:10],
        author_id=current_user["user_id"],
        author_name=current_user.get("username") or "",
        source_world_id=world.id,
        package_path=f"market/{fname}",
        package_size=len(data),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info(f"🏪 世界 #{world.id}「{title}」发布到商城（item {item.id}，{len(data)}B）")
    return _item_dict(item)


@router.get("/items")
async def list_items(
    q: str = Query("", description="搜索标题/描述"),
    tag: str = Query("", description="按标签过滤"),
    kind: str = Query("world", description="world | block"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """商城列表（在架商品；q 模糊搜索，tag 精确匹配）"""
    from app.models.world import WorldMarketItem
    stmt = select(WorldMarketItem).where(WorldMarketItem.status == "on", WorldMarketItem.kind == kind)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(WorldMarketItem.title.ilike(like), WorldMarketItem.description.ilike(like)))
    if tag.strip():
        from sqlalchemy.dialects.postgresql import JSONB
        stmt = stmt.where(WorldMarketItem.tags.contains([tag.strip()]))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(
        stmt.order_by(WorldMarketItem.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()
    return {"total": total, "items": [_item_dict(r) for r in rows]}


@router.get("/items/{item_id}")
async def get_item(
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.world import WorldMarketItem
    item = (await db.execute(select(WorldMarketItem).where(WorldMarketItem.id == item_id))).scalar_one_or_none()
    if item is None or item.status != "on":
        raise HTTPException(status_code=404, detail="商品不存在")
    return _item_dict(item)


@router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    req: UpdateItemRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑商品（标题/描述/标签；仅发布者或管理员）"""
    from app.models.world import WorldMarketItem
    item = (await db.execute(select(WorldMarketItem).where(WorldMarketItem.id == item_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    if item.author_id != current_user["user_id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="只有发布者或管理员可以编辑")
    if req.title is not None and str(req.title).strip():
        item.title = str(req.title).strip()[:100]
    if req.description is not None:
        item.description = str(req.description).strip()
    if req.tags is not None:
        item.tags = [str(t).strip()[:30] for t in req.tags if str(t).strip()][:10]
    await db.commit()
    await db.refresh(item)
    return _item_dict(item)


@router.delete("/items/{item_id}")
async def unpublish_item(
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下架（发布者本人或管理员）"""
    from app.models.world import WorldMarketItem
    item = (await db.execute(select(WorldMarketItem).where(WorldMarketItem.id == item_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    if item.author_id != current_user["user_id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="只有发布者或管理员可以下架")
    item.status = "off"
    await db.commit()
    return {"success": True}


@router.post("/items/{item_id}/import")
async def import_item(
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """一键导入：下载商城包 → 创建新世界 → 导入文件（安全过滤）"""
    from app.models.world import WorldMarketItem
    item = (await db.execute(select(WorldMarketItem).where(WorldMarketItem.id == item_id))).scalar_one_or_none()
    if item is None or item.status != "on":
        raise HTTPException(status_code=404, detail="商品不存在")
    pkg = DATA_DIR / item.package_path
    if not pkg.is_file():
        raise HTTPException(status_code=404, detail="商品包缺失")

    from app.services.world.world_service import create_world
    from app.services.world.world_file_service import import_zip
    created = await create_world(db, current_user["user_id"], item.title, item.description or "", 1.0, None)
    world_id = int(created["id"])
    try:
        result = import_zip(world_id, pkg.read_bytes())
        if result.get("imported", 0) == 0:
            raise HTTPException(status_code=400, detail="商品包没有可导入的文件")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    item.downloads = (item.downloads or 0) + 1
    await db.commit()
    logger.info(f"🏪 用户 {current_user['user_id']} 导入商城商品 {item_id} → 新世界 #{world_id}（{result.get('imported')} 文件）")
    return {"world_id": world_id, "name": created.get("name") or item.title, "imported": result.get("imported", 0)}


@router.get("/items/{item_id}/download")
async def download_item(
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下载商品 zip（手动导入用）"""
    from app.models.world import WorldMarketItem
    item = (await db.execute(select(WorldMarketItem).where(WorldMarketItem.id == item_id))).scalar_one_or_none()
    if item is None or item.status != "on":
        raise HTTPException(status_code=404, detail="商品不存在")
    pkg = DATA_DIR / item.package_path
    if not pkg.is_file():
        raise HTTPException(status_code=404, detail="商品包缺失")
    from fastapi.responses import Response
    return Response(
        content=pkg.read_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=market_{item_id}.zip"},
    )
