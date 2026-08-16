"""
统一插件 API — 目录即插件，两级开关

- GET    /plugins                 插件列表（含管理员全局开关 + 当前用户偏好 + 生效状态 + 皮肤变量）
- POST   /plugins/{id}/toggle     管理员全局开放/关闭
- POST   /plugins/{id}/pref       用户个人启用/停用
- POST   /plugins/rescan          管理员手动重扫磁盘（新增/卸载立即生效）

生效规则：effective = plugins.enabled AND user_plugin_prefs.enabled（偏好默认开）
皮肤规则：用户同一时刻只启用一个 skin 类插件（启用 A 自动停用其余 skin）
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.auth import get_current_user, require_admin
from app.services.plugin import catalog
from app.services.plugin.skill_bridge import apply_skill_plugins

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins", tags=["统一插件"])


class PrefRequest(BaseModel):
    enabled: bool = True


def _to_view(row, manifest: dict, user_pref: bool, is_admin: bool) -> dict:
    """DB 行 + 磁盘 manifest → API 视图"""
    skin_vars = catalog.get_skin_vars(manifest) if manifest.get("category") == "skin" else {}
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "category": row.category,
        "version": row.version,
        "author": row.author,
        "icon": row.icon,
        "builtin": row.builtin,
        "global_enabled": row.enabled,
        "user_enabled": user_pref,
        "effective": bool(row.enabled and user_pref),
        "is_admin": is_admin,
        "skin_vars": skin_vars,
    }


@router.get("")
async def list_plugins(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """插件列表（登录即可；管理员看到全局开关，普通用户看到自己的开关）"""
    from app.models.plugin import Plugin, UserPluginPref
    from app.models.user import User as UserModel

    await catalog.sync_plugins_to_db(db)  # 懒同步：目录变化即时可见（装好即可用）
    await apply_skill_plugins(db)

    user_id = current_user["user_id"]
    # 角色从 DB 重读（JWT role 可能是提权前的旧值），与 require_admin 同源
    urow = await db.get(UserModel, user_id)
    is_admin = bool(urow and urow.role == "admin")

    result = await db.execute(select(Plugin))
    rows = {p.id: p for p in result.scalars().all()}

    # 所有用户（含 admin）都查个人偏好：admin 也是普通用户，皮肤开关同样走 pref
    pref_result = await db.execute(
        select(UserPluginPref).where(UserPluginPref.user_id == user_id)
    )
    prefs = {p.plugin_id: p.enabled for p in pref_result.scalars().all()}

    disk = catalog.scan_disk()
    plugins = []
    for pid in sorted(rows.keys()):
        row = rows[pid]
        manifest = disk.get(pid, {})
        user_pref = prefs.get(pid, True)
        plugins.append(_to_view(row, manifest, user_pref, is_admin))
    return {"plugins": plugins}


@router.post("/rescan")
async def rescan_plugins(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员手动重扫磁盘插件目录（新增/卸载立即生效）"""
    changed = await catalog.sync_plugins_to_db(db)
    await apply_skill_plugins(db)
    return {"message": f"重扫完成，{changed} 项变更"}


@router.post("/{plugin_id}/toggle")
async def toggle_plugin(
    plugin_id: str,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员全局开放/关闭插件"""
    from app.models.plugin import Plugin

    row = await db.get(Plugin, plugin_id)
    if row is None:
        raise HTTPException(404, f"未知插件: {plugin_id}")
    row.enabled = not row.enabled
    await db.commit()
    await apply_skill_plugins(db)
    state = "开放" if row.enabled else "关闭"
    logger.info(f"管理员{state}插件 {plugin_id}")
    return {"message": f"「{row.name}」已{state}", "global_enabled": row.enabled}


@router.post("/{plugin_id}/pref")
async def set_plugin_pref(
    plugin_id: str,
    req: PrefRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户个人启用/停用插件；skin 类互斥（启用一个自动停用其余）"""
    from app.models.plugin import Plugin, UserPluginPref

    row = await db.get(Plugin, plugin_id)
    if row is None:
        raise HTTPException(404, f"未知插件: {plugin_id}")
    if not row.enabled:
        raise HTTPException(403, f"「{row.name}」已被管理员关闭，无法启用")

    user_id = current_user["user_id"]

    if req.enabled and row.category == "skin":
        # 互斥：显式把其他所有皮肤的用户偏好置为停用（无记录也要落 False 记录，
        # 否则列表默认 user_enabled=True 会让多个皮肤同时 effective）
        other_skins = await db.execute(
            select(Plugin).where(Plugin.category == "skin", Plugin.id != plugin_id)
        )
        for other_row in other_skins.scalars().all():
            other_pref = (
                await db.execute(
                    select(UserPluginPref).where(
                        UserPluginPref.user_id == user_id,
                        UserPluginPref.plugin_id == other_row.id,
                    )
                )
            ).scalar_one_or_none()
            if other_pref is None:
                db.add(UserPluginPref(user_id=user_id, plugin_id=other_row.id, enabled=False))
            else:
                other_pref.enabled = False

    pref = (
        await db.execute(
            select(UserPluginPref).where(
                UserPluginPref.user_id == user_id,
                UserPluginPref.plugin_id == plugin_id,
            )
        )
    ).scalar_one_or_none()

    if pref is None:
        pref = UserPluginPref(user_id=user_id, plugin_id=plugin_id, enabled=req.enabled)
        db.add(pref)
    else:
        pref.enabled = req.enabled
    await db.commit()

    return {
        "message": f"「{row.name}」已{'启用' if req.enabled else '停用'}",
        "user_enabled": req.enabled,
        "effective": bool(row.enabled and req.enabled),
    }
