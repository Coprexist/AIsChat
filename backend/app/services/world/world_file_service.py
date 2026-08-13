"""
世界文件服务 — 世界文件读写（隔离目录）

文件存储：data/worlds/{world_id}/（代码）+ data/worlds/{world_id}/data/（数据）
路径安全：拒绝 ../ 越界，所有操作限定在世界目录内。
"""
import logging
import os
import re
import shutil
import json
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


def read_file(world_id: int, rel_path: str, offset: int | None = None, limit: int | None = None) -> dict:
    """读文件（文本按 utf-8，二进制返回大小）。

    offset/limit：按行分页读（1-based 行号）——大文件不用全读，
    先 file_grep 定位行号再读对应段落（2026-08-13 产品定，对齐 OpenClaw read 工具）。
    """
    target = _safe_path(world_id, rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"文件不存在: {rel_path}")
    data = target.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"path": rel_path, "binary": True, "size": len(data), "content": None}
    if offset is not None or limit is not None:
        lines = text.split("\n")
        total = len(lines)
        start = max(1, offset or 1)
        end = total if limit is None else min(total, start + limit - 1)
        start = min(start, total + 1)  # offset 超界 → 空段
        slice_lines = lines[start - 1:end]
        content = "\n".join(slice_lines)
        return {
            "path": rel_path, "content": content, "binary": False, "size": len(data),
            "total_lines": total, "start_line": start, "end_line": end,
            "truncated": end < total,
        }
    return {"path": rel_path, "content": text, "binary": False, "size": len(data), "total_lines": len(text.split("\n"))}


def grep_file(world_id: int, rel_path: str, pattern: str, max_hits: int = 30) -> dict:
    """按关键词/正则搜文件内容，返回命中行 + 行号（轻量定位，2026-08-13 新增）。

    对齐 OpenClaw 的 grep 用法：先定位再按需读，不用整文件全读。
    """
    import re as _re
    target = _safe_path(world_id, rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"文件不存在: {rel_path}")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"path": rel_path, "binary": True, "hits": [], "total_hits": 0}
    try:
        rx = _re.compile(pattern)
    except _re.error:
        # 非正则 → 当普通子串（大小写不敏感）
        rx = _re.compile(_re.escape(pattern), _re.IGNORECASE)
    hits = []
    for i, line in enumerate(text.split("\n"), start=1):
        if rx.search(line):
            hits.append({"line": i, "content": line[:300]})
            if len(hits) >= max_hits:
                break
    return {"path": rel_path, "hits": hits, "total_hits": len(hits), "max_hits": max_hits}


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

def import_zip(world_id: int, zip_bytes: bytes, exclude_content: bool = True) -> dict:
    """解压 zip 到世界目录（过滤越界与危险文件）。
    exclude_content=True（默认）：跳过 content/ 数据文件——数据是运行产物，导入包不该覆盖；
    商城导入（新世界）不受影响（新世界无 content）。"""
    import io
    import zipfile

    base = _world_dir(world_id)
    count = 0
    skipped_content = 0
    meta: dict | None = None
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                # 安全：拒绝绝对路径与 ..
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    continue
                if info.is_dir():
                    continue
                # 虚拟元数据条目：读回不落盘（随包配置载体）
                if name == "world_meta.json":
                    try:
                        meta = json.loads(zf.read(info).decode("utf-8"))
                    except Exception:
                        meta = None
                    continue
                if exclude_content and name.startswith("content/"):
                    skipped_content += 1
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
    logger.info(f"🌐 世界 #{world_id} zip 导入 {count} 个文件（跳过数据文件 {skipped_content}，meta={'y' if meta else 'n'}）")
    return {"imported": count, "skipped_content": skipped_content, "meta": meta}


def export_zip(world_id: int, include_content: bool = True, meta: dict | None = None) -> bytes:
    """打包世界文件为 zip。代码/数据分离：
    include_content=True（默认）包含 content/ 产物区（静态文字数据，世界自己的产物）；
    False 只打包代码区（世界根目录 + skills 等），供世界发布用。
    meta 非空时以虚拟条目 world_meta.json 写入 zip（不落盘，世界目录零污染），
    用于携带运行配置（如 group_trigger_mode）随包分发——导入端读回合并。"""
    import io
    import json
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
        if meta:
            zf.writestr("world_meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    logger.info(f"🌐 世界 #{world_id} 打包导出 {len(buf.getvalue())}B (include_content={include_content}, meta={'y' if meta else 'n'})")
    return buf.getvalue()
