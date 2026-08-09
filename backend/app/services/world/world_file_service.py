"""
世界文件服务 — 世界文件读写（隔离目录）

文件存储：data/worlds/{world_id}/（代码）+ data/worlds/{world_id}/data/（数据）
路径安全：拒绝 ../ 越界，所有操作限定在世界目录内。
"""
import logging
import os
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

WORLDS_ROOT = Path("data/worlds")

# 允许的文件扩展名（世界代码）
ALLOWED_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".json", ".md", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".woff", ".woff2", ".ttf", ".mp3", ".wav", ".ogg", ".mp4", ".webm",
    # py 文件只允许写入（阶段 2 才执行，先允许存储）
    ".py",
}
MAX_FILE_SIZE = 32 * 1024 * 1024  # 单文件 32MB（网页资源/下载文件用）


def _world_dir(world_id: int) -> Path:
    """世界代码目录（自动创建）"""
    d = WORLDS_ROOT / str(world_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_path(world_id: int, rel_path: str) -> Path:
    """解析相对路径，防越界（../ 与绝对路径一律拒绝）"""
    rel_path = (rel_path or "").strip().lstrip("/")
    if not rel_path:
        raise ValueError("路径不能为空")
    if ".." in rel_path.split("/"):
        raise ValueError("非法路径: 不允许 .. 越界")
    base = _world_dir(world_id).resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("非法路径: 越出世界目录")
    return target


def _check_ext(path: Path) -> None:
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不允许的文件类型: {path.suffix}，可选: {sorted(ALLOWED_EXTENSIONS)[:8]}...")


# ═══════════════════════════════════════════════════════════════
# 文件操作
# ═══════════════════════════════════════════════════════════════

def list_files(world_id: int, prefix: str = "") -> list[dict]:
    """文件树"""
    base = _world_dir(world_id)
    result = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(base))
            if prefix and not rel.startswith(prefix):
                continue
            result.append({
                "path": rel,
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            })
    return result


def read_file(world_id: int, rel_path: str) -> dict:
    """读文件（文本按 utf-8，二进制返回大小）"""
    target = _safe_path(world_id, rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"文件不存在: {rel_path}")
    data = target.read_bytes()
    try:
        text = data.decode("utf-8")
        return {"path": rel_path, "content": text, "binary": False, "size": len(data)}
    except UnicodeDecodeError:
        return {"path": rel_path, "binary": True, "size": len(data), "content": None}


def write_file(world_id: int, rel_path: str, content: str) -> dict:
    """写文件（自动建目录）"""
    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        raise ValueError(f"文件超过 {MAX_FILE_SIZE // 1024 // 1024}MB 限制")
    target = _safe_path(world_id, rel_path)
    _check_ext(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info(f"🌐 世界 #{world_id} 写入文件: {rel_path} ({len(content)}B)")
    return {"path": rel_path, "size": len(content.encode("utf-8"))}


def write_file_bytes(world_id: int, rel_path: str, data: bytes) -> dict:
    """写二进制文件（图片/音频等上传用；校验与 write_file 同一套：白名单/越界/大小）"""
    if len(data) > MAX_FILE_SIZE:
        raise ValueError(f"文件超过 {MAX_FILE_SIZE // 1024 // 1024}MB 限制")
    target = _safe_path(world_id, rel_path)
    _check_ext(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    logger.info(f"🌐 世界 #{world_id} 写入二进制文件: {rel_path} ({len(data)}B)")
    return {"path": rel_path, "size": len(data)}


def delete_file(world_id: int, rel_path: str) -> None:
    """删除文件"""
    target = _safe_path(world_id, rel_path)
    if target.is_file():
        target.unlink()
        logger.info(f"🗑️ 世界 #{world_id} 删除文件: {rel_path}")
    elif target.is_dir():
        shutil.rmtree(target)
        logger.info(f"🗑️ 世界 #{world_id} 删除目录: {rel_path}")
    else:
        raise FileNotFoundError(f"不存在: {rel_path}")


# ═══════════════════════════════════════════════════════════════
# 文件夹导入（zip 或批量文件）
# ═══════════════════════════════════════════════════════════════

def import_zip(world_id: int, zip_bytes: bytes) -> dict:
    """解压 zip 到世界目录（过滤越界与危险文件）"""
    import io
    import zipfile

    base = _world_dir(world_id)
    count = 0
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                # 安全：拒绝绝对路径与 ..
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    continue
                if info.is_dir():
                    continue
                target = (base / name).resolve()
                if not str(target).startswith(str(base.resolve())):
                    continue
                try:
                    _check_ext(target)
                except ValueError:
                    continue
                if info.file_size > MAX_FILE_SIZE:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
                count += 1
    except zipfile.BadZipFile:
        raise ValueError("无效的 zip 文件")
    logger.info(f"🌐 世界 #{world_id} zip 导入 {count} 个文件")
    return {"imported": count}


def export_zip(world_id: int, include_content: bool = True) -> bytes:
    """打包世界文件为 zip。代码/数据分离：
    include_content=True（默认）包含 content/ 产物区（静态文字数据，世界自己的产物）；
    False 只打包代码区（世界根目录 + skills 等），供世界发布用。"""
    import io
    import zipfile

    base = _world_dir(world_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in base.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(base))
                if not include_content and rel.startswith("content/"):
                    continue
                zf.write(p, rel)
    logger.info(f"🌐 世界 #{world_id} 打包导出 {len(buf.getvalue())}B (include_content={include_content})")
    return buf.getvalue()
