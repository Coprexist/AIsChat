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

logger = logging.getLogger(__name__)

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


def apply_block(world_id: int, block_id: str, prefix: str = "blocks") -> dict:
    """把积木文件复制进世界文件夹 blocks/{block_id}/，返回应用路径与用法"""
    from app.services.world.world_file_service import _world_dir, write_file

    bdir = _block_dir(block_id)
    if not bdir.is_dir():
        raise ValueError(f"积木不存在: {block_id}")
    mf = _load_manifest(bdir)
    if mf is None:
        raise ValueError(f"积木 manifest 缺失: {block_id}")

    applied = []
    for fname in mf.get("files", []):
        p = bdir / fname
        if not p.is_file():
            continue
        target = f"{prefix}/{block_id}/{fname}"
        write_file(world_id, target, p.read_text(encoding="utf-8", errors="replace"))
        applied.append(target)

    return {
        "success": True,
        "block_id": block_id,
        "name": mf.get("name", block_id),
        "applied_files": applied,
        "usage": mf.get("usage", ""),
    }
