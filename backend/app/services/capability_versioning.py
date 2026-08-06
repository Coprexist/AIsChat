"""
能力懒加载：skills/tools 版本化 + 增量变更注入（2026-08-06 珑哥方案）

能力源：platform（内置工具）/ world-{id}（世界 skills 转出的工具定义）。
每个 AI 两个进度（agents.cap_known_versions / cap_effective_versions，JSONB {source: version}）：
- known（告知进度）：已注入变更通知的版本 —— 落后则注入"增量 changelog"（只有新变化），注入后更新
- effective（生效进度）：请求实际使用的定义版本 —— compact 时切到最新

不变式：
- 请求 payload 的 tools = effective 版本的定义快照（compact 前不动 → 前缀缓存稳定）
- 变更告知 = 动态尾部 system 消息（不影响前缀）
- 旧版本定义永远保留在 capability_versions（平台发布后旧对话继续用旧定义请求）
"""
from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SOURCE_PLATFORM = "platform"


def defs_hash(definitions: list) -> str:
    """工具定义列表 → 内容哈希（检测变更）"""
    return hashlib.sha256(
        json.dumps(definitions, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _def_by_name(definitions: list, name: str) -> dict | None:
    for d in definitions or []:
        fn = (d or {}).get("function") or {}
        if fn.get("name") == name:
            return d
    return None


def _diff_changelog(old_defs: list | None, new_defs: list) -> str:
    """自动 diff 两版定义 → 变更摘要（新增/移除/更新工具名）"""
    old_names = {((d or {}).get("function") or {}).get("name") for d in (old_defs or [])}
    new_names = {((d or {}).get("function") or {}).get("name") for d in (new_defs or [])}
    added = new_names - old_names
    removed = old_names - new_names
    changed = {
        n for n in (new_names & old_names)
        if _def_by_name(new_defs, n) != _def_by_name(old_defs, n)
    }
    lines = []
    for n in sorted(added):
        lines.append(f"新增能力 {n}")
    for n in sorted(removed):
        lines.append(f"移除能力 {n}")
    for n in sorted(changed):
        lines.append(f"更新能力 {n}")
    return "\n".join(lines) or "能力定义更新（无名称变化）"


# ── 版本写入（启动/变更检测时调用） ──

async def ensure_source_version(
    db: AsyncSession, source: str, definitions: list, label: str,
) -> int:
    """对比该源最新版本：内容变了 → 写新版本（diff 生成 changelog）；没变 → 返回当前版本号"""
    from app.models.agent import CapabilityVersion

    h = defs_hash(definitions)
    latest = (await db.execute(
        select(CapabilityVersion)
        .where(CapabilityVersion.source == source)
        .order_by(CapabilityVersion.version.desc())
        .limit(1)
    )).scalar_one_or_none()

    if latest is not None and latest.content_hash == h:
        return latest.version

    new_version = (latest.version if latest else 0) + 1
    changelog = f"[{label} v{new_version}] " + _diff_changelog(
        latest.definitions if latest else None, definitions
    )
    db.add(CapabilityVersion(
        source=source, version=new_version, content_hash=h,
        changelog=changelog, definitions=definitions,
    ))
    await db.commit()
    logger.info(f"🧬 能力源 {source} 新版本 v{new_version}: {changelog[:120]}")
    return new_version


async def ensure_platform_version(db: AsyncSession) -> int:
    """平台内置工具版本化（启动时调用）"""
    from app.tools.base import ToolRegistry
    return await ensure_source_version(
        db, SOURCE_PLATFORM, ToolRegistry.get_all_definitions(), "平台工具"
    )


async def ensure_world_version(db: AsyncSession, world_id: int, skill_tools: list) -> int:
    """世界 skills 工具版本化（世界 AI 对话时调用）"""
    source = f"world-{world_id}"
    return await ensure_source_version(db, source, skill_tools, f"世界{world_id}")


# ── 查询 ──

async def get_version(db: AsyncSession, source: str, version: int):
    from app.models.agent import CapabilityVersion
    return (await db.execute(
        select(CapabilityVersion).where(
            CapabilityVersion.source == source,
            CapabilityVersion.version == version,
        )
    )).scalar_one_or_none()


async def get_latest_version(db: AsyncSession, source: str):
    from app.models.agent import CapabilityVersion
    return (await db.execute(
        select(CapabilityVersion)
        .where(CapabilityVersion.source == source)
        .order_by(CapabilityVersion.version.desc())
        .limit(1)
    )).scalar_one_or_none()


# ── AI 进度读写 ──

def _holder_map(holder, key: str) -> dict:
    """holder 可以是 agent（有属性）或 dict（如 worlds.config）"""
    if isinstance(holder, dict):
        return dict(holder.get(key) or {})
    return dict(getattr(holder, key, None) or {})


def _set_holder_map(holder, key: str, m: dict) -> None:
    if isinstance(holder, dict):
        holder[key] = m
    else:
        setattr(holder, key, m)


async def get_effective_definitions(
    db: AsyncSession, holder, source: str, fallback_definitions: list,
) -> list:
    """请求用的工具定义：按 effective 版本取快照；无记录（新 AI/新源）→ 用当前定义并同步 effective"""
    ver = _holder_map(holder, "cap_effective_versions").get(source)
    if ver is not None:
        row = await get_version(db, source, ver)
        if row is not None and row.definitions is not None:
            return row.definitions
    # 新 AI：直接用当前（latest）定义，并把 effective 对齐最新版本
    latest = await get_latest_version(db, source)
    if latest is not None:
        e = _holder_map(holder, "cap_effective_versions")
        e[source] = latest.version
        _set_holder_map(holder, "cap_effective_versions", e)
        if latest.definitions is not None:
            return latest.definitions
    return fallback_definitions


async def build_change_notice(db: AsyncSession, agent, sources: list[str]) -> str | None:
    """增量变更通知：对比 known vs latest，落后则拼 changelog（只含新变化），并更新 known。

    返回通知文本（追加进 system 尾部）；无变化返回 None。
    注意：调用方需把通知真正放进 messages 后再提交（known 更新与注入同事务）。
    """
    from app.models.agent import CapabilityVersion

    lines: list[str] = []
    changed = False
    for source in sources:
        latest = (await db.execute(
            select(CapabilityVersion)
            .where(CapabilityVersion.source == source)
            .order_by(CapabilityVersion.version.desc())
            .limit(1)
        )).scalar_one_or_none()
        if latest is None:
            continue
        known = _holder_map(agent, "cap_known_versions").get(source, 0)
        if known >= latest.version:
            continue
        # 取 known+1 .. latest 的 changelog（增量：只注入新变化）
        rows = (await db.execute(
            select(CapabilityVersion)
            .where(
                CapabilityVersion.source == source,
                CapabilityVersion.version > known,
                CapabilityVersion.version <= latest.version,
            )
            .order_by(CapabilityVersion.version.asc())
        )).scalars().all()
        parts = [f"[{r.changelog}]" for r in rows if r.changelog]
        if parts:
            lines.append(f"【能力变更通知 {source} v{known}→v{latest.version}】\n" + "\n".join(parts))
            k = _holder_map(agent, "cap_known_versions")
            k[source] = latest.version
            _set_holder_map(agent, "cap_known_versions", k)
            changed = True
    if not changed:
        return None
    return "\n\n".join(lines)


async def mark_effective_latest(db: AsyncSession, agent, sources: list[str]) -> None:
    """compact 后调用：effective 全部对齐最新（工具定义直接用最新的）"""
    from app.models.agent import CapabilityVersion

    for source in sources:
        latest = (await db.execute(
            select(CapabilityVersion)
            .where(CapabilityVersion.source == source)
            .order_by(CapabilityVersion.version.desc())
            .limit(1)
        )).scalar_one_or_none()
        if latest is not None:
            e = _holder_map(agent, "cap_effective_versions")
            e[source] = latest.version
            _set_holder_map(agent, "cap_effective_versions", e)
