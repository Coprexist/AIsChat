"""
世界积木（预制世界块）注册表 — 平台提供可复用的 UI 组件包，世界 AI 可查/看/应用

积木包结构（data/world_blocks/{block_id}/）：
  manifest.json   {id, name, description, version, files[], entry, usage}
  文件            自包含的 css/js/html 片段

应用 = 把积木文件复制进世界文件夹（blocks/{block_id}/），世界代码按 usage 引入。
"""
import json
import logging
from pathlib import Path

from app.repositories.world_repo import WorldRepository, SQLAlchemyWorldRepository
from sqlalchemy.ext.asyncio import AsyncSession
logger = logging.getLogger(__name__)

def _ensure_repo(db_or_repo):
    """兼容旧调用：传入 AsyncSession 时包装为 SQLAlchemyWorldRepository。"""
    if isinstance(db_or_repo, AsyncSession):
        return SQLAlchemyWorldRepository(db_or_repo)
    return db_or_repo


BLOCKS_ROOT = Path("data/world_blocks")


def _block_dir(block_id: str) -> Path:
    # 防路径穿越：只允许 [a-z0-9-]
    if not block_id or not all(c.isalnum() or c in "-_" for c in block_id):
        raise ValueError(f"非法积木 id: {block_id}")
    return (BLOCKS_ROOT / block_id).resolve()


def _load_manifest(block_dir: Path) -> dict | None:
    mf = block_dir / "manifest.json"
    if not mf.exists():
        return None
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"积木 manifest 解析失败 {block_dir}: {e}")
        return None


def list_blocks() -> list[dict]:
    """所有可用积木的摘要列表"""
    if not BLOCKS_ROOT.exists():
        return []
    out = []
    for d in sorted(BLOCKS_ROOT.iterdir()):
        if not d.is_dir():
            continue
        mf = _load_manifest(d)
        if mf:
            out.append({
                "id": mf.get("id", d.name),
                "name": mf.get("name", d.name),
                "description": mf.get("description", ""),
                "version": mf.get("version", ""),
                "files": mf.get("files", []),
                "entry": mf.get("entry", ""),
            })
    return out


def view_block(block_id: str) -> dict:
    """积木详情 + 全部文件内容（AI 阅读/定制用）"""
    bdir = _block_dir(block_id)
    if not bdir.is_dir():
        raise ValueError(f"积木不存在: {block_id}")
    mf = _load_manifest(bdir)
    if mf is None:
        raise ValueError(f"积木 manifest 缺失: {block_id}")
    files = {}
    for fname in mf.get("files", []):
        p = bdir / fname
        if p.is_file() and p.suffix in (".css", ".js", ".html", ".json", ".md", ".txt"):
            files[fname] = p.read_text(encoding="utf-8", errors="replace")
    return {**mf, "files_content": files}


DIY_TEMPLATE_CSS = """/* ═══════════ DIY 定制区（用户管，平台更新积木不会覆盖本文件）═══════════
   在这里覆盖积木样式（加载顺序在基础样式之后，优先级更高）。示例：
   .sidebar-block { background: #1e1a30; }
   .sb-brand { color: #a78bfa; }
*/
"""

DIY_TEMPLATE_JS = """// ═══════════ DIY 定制区（用户管，平台更新积木不会覆盖本文件）═══════════
// 在这里写自定义逻辑（加载顺序在积木主文件之后，可访问积木暴露的全局对象）。
"""


def apply_block(world_id: int, block_id: str, prefix: str = "blocks") -> dict:
    """把积木文件复制进世界文件夹 blocks/{block_id}/。

    分块约定：
    - 主文件（manifest.files）平台管，可覆盖更新；
    - diy/（custom.css/custom.js）用户管，**更新时跳过不覆盖**（DIY 保护）；
    - 更新时旧主文件备份到 blocks/{block_id}/.bak/（DIY 依赖旧版时可手动回滚）。
    返回含 is_update / previous_version / version（供更新通知）。
    """
    from app.services.world.world_file_service import _world_dir, write_file

    bdir = _block_dir(block_id)
    if not bdir.is_dir():
        raise ValueError(f"积木不存在: {block_id}")
    mf = _load_manifest(bdir)
    if mf is None:
        raise ValueError(f"积木 manifest 缺失: {block_id}")

    world_dir = _world_dir(world_id)
    block_dir_in_world = world_dir / prefix / block_id
    is_update = block_dir_in_world.is_dir()

    # 读旧版本（世界内 manifest）
    prev_version = None
    if is_update:
        old_mf = block_dir_in_world / "manifest.json"
        if old_mf.exists():
            try:
                prev_version = (json.loads(old_mf.read_text(encoding="utf-8", errors="replace")) or {}).get("version")
            except Exception:
                pass

    # 更新时：旧主文件备份到 .bak/（DIY 依赖旧版可回滚）
    if is_update:
        for fname in mf.get("files", []):
            old = block_dir_in_world / fname
            if old.is_file():
                try:
                    write_file(world_id, f"{prefix}/{block_id}/.bak/{fname}", old.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    pass

    # 写主文件（平台管）
    applied = []
    for fname in mf.get("files", []):
        p = bdir / fname
        if not p.is_file():
            continue
        target = f"{prefix}/{block_id}/{fname}"
        write_file(world_id, target, p.read_text(encoding="utf-8", errors="replace"))
        applied.append(target)

    # DIY 区（用户管）：首次应用写模板，更新时跳过不覆盖
    diy_css = block_dir_in_world / "diy" / "custom.css"
    if not diy_css.exists():
        write_file(world_id, f"{prefix}/{block_id}/diy/custom.css", DIY_TEMPLATE_CSS)
    diy_js = block_dir_in_world / "diy" / "custom.js"
    if not diy_js.exists():
        write_file(world_id, f"{prefix}/{block_id}/diy/custom.js", DIY_TEMPLATE_JS)

    return {
        "success": True,
        "block_id": block_id,
        "name": mf.get("name", block_id),
        "applied_files": applied,
        "usage": mf.get("usage", ""),
        "version": mf.get("version"),
        "previous_version": prev_version,
        "is_update": is_update,
    }


async def update_block_for_all_worlds(db, block_id: str) -> dict:
    """平台侧批量更新积木：所有已应用该积木的世界重新 apply（跳过 diy/），
    并给每个世界写懒通知（下次对话注入世界 AI 上下文）。返回更新统计。"""
    db = _ensure_repo(db)
    from sqlalchemy import select
    from app.models.world import World
    from app.services.world.world_service import add_pending_notice

    rows = (await db.execute(select(World.id))).scalars().all()
    updated = []
    for wid in rows:
        try:
            result = apply_block(wid, block_id)
        except ValueError:
            continue  # 积木不存在等
        if not result.get("is_update"):
            continue  # 该世界没应用过此积木
        updated.append(wid)
        # 懒通知：积木更新注入世界 AI 上下文
        try:
            await add_pending_notice(
                db, wid, f"blocks/{block_id}/", "平台积木更新",
                f"积木「{result.get('name', block_id)}」已更新"
                + (f" v{result['previous_version']} → v{result['version']}" if result.get("version") and result.get("previous_version") and result["version"] != result["previous_version"] else "")
                + f"；你的 DIY（blocks/{block_id}/diy/）已保留，主文件旧版备份在 .bak/ 可回滚。",
            )
        except Exception:
            pass
    return {"block_id": block_id, "updated_worlds": updated, "count": len(updated)}
