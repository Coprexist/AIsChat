"""
世界商城 × GitHub 同步服务
==========================
职责边界（单一职责，路由层只做参数校验与鉴权，业务都在这里）：
- 配置读写         get_market_config / save_market_config
- GitHub HTTP     _gh_get / _gh_put / _gh_download（Contents API 封装）
- 索引快照         load_snapshot / save_snapshot（本地文件缓存，GitHub 板块的数据源）
- 同步             sync_item_to_github（本地 → GitHub：meta + zip + index）
- 刷新             refresh_from_github（GitHub → 快照）
- 导入             import_from_github（快照条目 → 下载 zip → 建世界）
- 状态计算         compute_sync_state（已同步 / 同步过 / 未同步）

设计要点：
- GitHub 板块不实时请求远端：refresh 把 index.json 落成快照文件，板块读快照；
  管理员可手动刷新（auto_sync 开启时启动自动拉取）。
- 目录名 = 作者命名（清洗后的标题），GitHub 支持中文路径；空标题兜底 world-{id}。
- 云端 downloads = 同步时本地下载数的快照（GitHub 无文件下载统计 API，字段预留扩展）。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
INDEX_PATH = "worlds/index.json"
SNAPSHOT_PATH = "data/market/github_index_cache.json"

# ─────────────────────────── 配置 ───────────────────────────


async def get_market_config(db) -> dict:
    """读商城配置（含 GitHub 设置）——直接查 DB（get_settings 的返回 dict 不含此字段）"""
    from sqlalchemy import text
    row = (await db.execute(text("SELECT market_config FROM system_settings WHERE id=1"))).first()
    raw = row[0] if row else None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    cfg = dict(raw or {})
    return {
        "github_repo": str(cfg.get("github_repo") or "").strip(),
        "github_token": str(cfg.get("github_token") or "").strip(),
        "auto_sync_enabled": bool(cfg.get("auto_sync_enabled", False)),
    }


async def save_market_config(db, *, github_repo: str | None = None,
                             github_token: str | None = None,
                             auto_sync_enabled: bool | None = None) -> dict:
    """更新商城配置（仅更新传入的字段，其余保留）"""
    from sqlalchemy import text
    row = (await db.execute(text("SELECT market_config FROM system_settings WHERE id=1"))).first()
    raw = row[0] if row else None
    cfg = dict(raw or {}) if isinstance(raw, dict) else {}
    if github_repo is not None:
        cfg["github_repo"] = github_repo.strip()
    if github_token is not None:
        cfg["github_token"] = github_token.strip()
    if auto_sync_enabled is not None:
        cfg["auto_sync_enabled"] = bool(auto_sync_enabled)
    await db.execute(
        text("UPDATE system_settings SET market_config = :cfg WHERE id = 1"),
        {"cfg": json.dumps(cfg, ensure_ascii=False)},
    )
    await db.commit()
    return cfg


def _repo_parts(repo: str) -> tuple[str, str] | None:
    """'owner/name' → (owner, name)"""
    m = re.match(r"^([\w.-]+)/([\w.-]+)$", repo.strip())
    return (m.group(1), m.group(2)) if m else None


# ─────────────────────────── GitHub HTTP ───────────────────────────


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _gh_get(owner: str, repo: str, path: str, token: str) -> dict | None:
    """GET Contents API；404 返回 None，其他非 200 抛错"""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", headers=_headers(token))
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise RuntimeError(f"GitHub 读取失败 {path}: {r.status_code} {r.text[:200]}")
    return r.json()


async def _gh_put(owner: str, repo: str, path: str, content_b64: str, token: str,
                  sha: str | None = None, message: str = "sync") -> dict:
    """PUT Contents API（创建/更新，更新需带 sha）"""
    body = {"message": message, "content": content_b64}
    if sha:
        body["sha"] = sha
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.put(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                             json=body, headers=_headers(token))
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub 写入失败 {path}: {r.status_code} {r.text[:300]}")
    return r.json()


async def _gh_download(owner: str, repo: str, path: str, token: str) -> bytes:
    """下载仓库文件内容（Contents API base64 解码）"""
    data = await _gh_get(owner, repo, path, token)
    if data is None:
        raise ValueError(f"GitHub 文件不存在: {path}")
    return base64.b64decode(data["content"])


async def verify_github_token(token: str) -> str:
    """验证 GitHub token 有效性，返回 GitHub 用户名（失败抛 RuntimeError）"""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{GITHUB_API}/user", headers=_headers(token))
    if r.status_code != 200:
        raise RuntimeError(f"GitHub token 无效（{r.status_code}），请检查后重试")
    username = r.json().get("login") or ""
    if not username:
        raise RuntimeError("GitHub 响应异常，未获取到用户名")
    return username


# ─────────────────────────── 索引快照 ───────────────────────────


def _snapshot_file() -> Path:
    # 支持环境变量覆盖（可测试性；生产默认 data/market/github_index_cache.json）
    return Path(os.environ.get("GITHUB_SNAPSHOT_PATH", SNAPSHOT_PATH))


def load_snapshot() -> dict:
    """读 GitHub 索引快照；缺失/损坏返回空结构（不抛错）"""
    try:
        data = json.loads(_snapshot_file().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("worlds"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"synced_at": None, "worlds": []}


def save_snapshot(worlds: list[dict], synced_at: str | None = None) -> None:
    """写 GitHub 索引快照（原子写：先临时文件再 rename）。
    快照只是缓存，写失败仅告警、不阻塞主流程。"""
    data = {"synced_at": synced_at or datetime.now(timezone.utc).isoformat(), "worlds": worlds}
    path = _snapshot_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        logger.warning(f"快照写入失败（不影响主流程）: {e}")


def snapshot_map() -> dict[int, dict]:
    """快照条目按 id 建索引，供本地商品状态计算/标注使用"""
    return {int(w.get("id") or 0): w for w in load_snapshot().get("worlds", [])}


# ─────────────────────────── 目录名（作者命名） ───────────────────────────


def _clean_slug(title: str | None) -> str:
    """标题 → 安全目录名：去路径分隔符/保留字/控制字符；保留中文；截断 60 字符"""
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", title or "").strip().strip(" .")
    return s[:60]


def _slug(item) -> str:
    """同步目录名：优先作者命名（清洗后的标题），空则兜底 world-{id}"""
    return _clean_slug(item.title) or f"world-{item.id}"


def _item_dir(item) -> str:
    return f"worlds/{_slug(item)}"


# ─────────────────────────── 同步状态 ───────────────────────────


def compute_sync_state(item, gh_entry: dict | None) -> str:
    """本地商品的同步状态：
    - unsynced  从未同步（无 github_path）
    - synced    同步后无改动（本地 updated_at ≤ 快照里的 updated_at）
    - stale     同步后又改过（本地 updated_at > 快照里的 updated_at，需重新同步）
    """
    if not getattr(item, "github_path", None):
        return "unsynced"
    gh_updated = (gh_entry or {}).get("updated_at")
    if not gh_updated or item.updated_at is None:
        return "stale"  # 快照缺失/异常 → 保守提示重新同步
    try:
        gh_ts = datetime.fromisoformat(gh_updated)
        local_ts = item.updated_at
        if local_ts.tzinfo is None:
            local_ts = local_ts.replace(tzinfo=timezone.utc)
        if gh_ts.tzinfo is None:
            gh_ts = gh_ts.replace(tzinfo=timezone.utc)
        return "synced" if local_ts <= gh_ts else "stale"
    except (ValueError, TypeError):
        return "stale"


# ─────────────────────────── 同步（本地 → GitHub） ───────────────────────────


async def sync_item_to_github(db, item, token_override: str | None = None) -> dict:
    """把本地商品推送到 GitHub：meta.json + world.zip + 更新 index.json + 刷新快照。
    token_override：用户绑定的 token（以用户身份推送）；None 时用管理员配置 token。"""
    cfg = await get_market_config(db)
    parts = _repo_parts(cfg["github_repo"])
    if not parts:
        raise ValueError("后台未配置 GitHub 仓库（market_config.github_repo）")
    owner, repo = parts
    token = token_override or cfg["github_token"]
    if not token:
        raise ValueError("未配置 GitHub Token（请绑定自己的 GitHub 账户，或由管理员配置）")

    pkg = Path("data") / item.package_path
    if not pkg.is_file():
        raise ValueError("商品包文件缺失，无法同步")

    slug = _slug(item)
    d = _item_dir(item)
    meta = {
        "id": item.id,
        "kind": item.kind,
        "title": item.title,
        "description": item.description or "",
        "tags": item.tags or [],
        "author_name": item.author_name or f"user-{item.author_id}",
        "source_world_id": item.source_world_id,
        "package_size": item.package_size,
        "downloads": item.downloads or 0,          # 云端下载数 = 同步时本地快照
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "download_url": f"{d}/world.zip",
    }

    # 重名检查：index.json 里已有同名目录（其他商品）→ 拒绝
    idx = await _gh_get(owner, repo, INDEX_PATH, token)
    worlds = _index_worlds(idx)
    dup = next((w for w in worlds if w.get("slug") == slug and int(w.get("id") or 0) != item.id), None)
    if dup:
        raise ValueError(f"GitHub 上已存在同名世界「{dup.get('title')}」（{slug}），请修改标题后重试")

    # 逐文件推送（meta 与 zip 均带旧 sha 以支持覆盖更新）
    old_meta = await _gh_get(owner, repo, f"{d}/meta.json", token)
    await _gh_put(owner, repo, f"{d}/meta.json",
                  base64.b64encode(json.dumps(meta, ensure_ascii=False).encode()).decode(),
                  token, sha=old_meta.get("sha") if old_meta else None,
                  message=f"sync {slug} meta")
    old_zip = await _gh_get(owner, repo, f"{d}/world.zip", token)
    await _gh_put(owner, repo, f"{d}/world.zip",
                  base64.b64encode(pkg.read_bytes()).decode(),
                  token, sha=old_zip.get("sha") if old_zip else None,
                  message=f"sync {slug} package")

    # 更新 index.json（同 id 条目替换）
    entry = {
        "id": item.id,
        "slug": slug,
        "title": meta["title"],
        "description": meta["description"],
        "tags": meta["tags"],
        "author_name": meta["author_name"],
        "downloads": meta["downloads"],
        "updated_at": meta["updated_at"],
        "zip": f"{d}/world.zip",
        "meta": f"{d}/meta.json",
    }
    worlds = [w for w in worlds if int(w.get("id") or 0) != item.id]
    worlds.append(entry)
    await _gh_put(owner, repo, INDEX_PATH,
                  base64.b64encode(json.dumps({"worlds": worlds}, ensure_ascii=False, indent=2).encode()).decode(),
                  token, sha=idx.get("sha") if idx else None,
                  message=f"update index ({slug})")
    save_snapshot(worlds)

    # 记录 github_path
    from sqlalchemy import text
    await db.execute(text("UPDATE world_market_items SET github_path = :p WHERE id = :id"),
                     {"p": d, "id": item.id})
    await db.commit()
    logger.info(f"🏪 商品 #{item.id}「{item.title}」已同步到 GitHub {cfg['github_repo']}/{d}")
    return {"success": True, "path": d}


def _index_worlds(idx: dict | None) -> list[dict]:
    """index.json 响应 → 世界条目列表（容错）"""
    if not idx:
        return []
    try:
        data = json.loads(base64.b64decode(idx["content"]).decode())
        return data.get("worlds", []) if isinstance(data, dict) else []
    except (KeyError, json.JSONDecodeError):
        return []


# ─────────────────────────── 刷新（GitHub → 快照） ───────────────────────────


async def refresh_from_github(db) -> dict:
    """管理员手动/自动刷新：拉 index.json → 更新快照。返回新增/更新/移除统计"""
    cfg = await get_market_config(db)
    parts = _repo_parts(cfg["github_repo"])
    if not parts:
        raise ValueError("后台未配置 GitHub 仓库（market_config.github_repo）")
    owner, repo = parts
    token = cfg["github_token"]
    if not token:
        raise ValueError("后台未配置 GitHub Token（market_config.github_token）")

    idx = await _gh_get(owner, repo, INDEX_PATH, token)
    if idx is None:
        # 仓库还没有 index.json → 初始化空索引，快照为空
        await _gh_put(owner, repo, INDEX_PATH,
                      base64.b64encode(json.dumps({"worlds": []}, ensure_ascii=False).encode()).decode(),
                      token, message="init market index")
        save_snapshot([])
        return {"added": 0, "updated": 0, "removed": 0}

    worlds = _index_worlds(idx)
    old = {int(w.get("id") or 0): w for w in load_snapshot().get("worlds", [])}
    added = sum(1 for w in worlds if int(w.get("id") or 0) not in old)
    updated = sum(1 for w in worlds
                  if int(w.get("id") or 0) in old
                  and old[int(w.get("id") or 0)].get("updated_at") != w.get("updated_at"))
    removed = sum(1 for wid in old if wid not in {int(w.get("id") or 0) for w in worlds})
    save_snapshot(worlds)
    logger.info(f"🏪 GitHub 商城刷新完成: +{added} 新增, {updated} 更新, -{removed} 移除")
    return {"added": added, "updated": updated, "removed": removed}


# ─────────────────────────── 导入（GitHub → 本地世界） ───────────────────────────


async def import_from_github(db, user_id: int, item_id: int) -> dict:
    """按快照条目导入：下载 world.zip → 创建新世界 → 导入文件（安全过滤）"""
    cfg = await get_market_config(db)
    parts = _repo_parts(cfg["github_repo"])
    if not parts:
        raise ValueError("后台未配置 GitHub 仓库")
    owner, repo = parts
    token = cfg["github_token"]

    entry = snapshot_map().get(item_id)
    if entry is None:
        raise ValueError("快照中不存在该资源（先刷新 GitHub 商城）")
    zip_path = entry.get("zip") or ""
    if not zip_path:
        raise ValueError("该资源缺少包文件路径")

    from app.services.world.world_service import create_world
    from app.services.world.world_file_service import import_zip
    zip_bytes = await _gh_download(owner, repo, zip_path, token)
    if not zip_bytes:
        raise ValueError("资源包为空")

    created = await create_world(db, user_id, str(entry.get("title") or f"World {item_id}")[:100],
                                 str(entry.get("description") or ""), 1.0, None)
    world_id = int(created["id"])
    try:
        result = import_zip(world_id, zip_bytes)
        if result.get("imported", 0) == 0:
            raise ValueError("资源包没有可导入的文件")
    except ValueError as e:
        raise ValueError(str(e))
    logger.info(f"🏪 用户 {user_id} 从 GitHub 导入资源 {item_id}「{entry.get('title')}」→ 新世界 #{world_id}")
    return {"world_id": world_id, "name": created.get("name") or entry.get("title"),
            "imported": result.get("imported", 0)}
