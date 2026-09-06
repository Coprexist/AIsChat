"""
世界 API 文档注册表 — 平台为世界 AI 提供的分区接口文档

文档结构（data/world_api_docs/）：
  index.md                 总览（区名 + 区介绍 + 使用指引）
  sections/01-*.md …       各区详细 API

设计：AI 侧只暴露「区名 + 区介绍」（view_api_doc 工具的 description 里），
需要细节时由 AI 自己选择打开哪个区，避免全量文档塞进上下文。
"""
import logging
import re
from pathlib import Path

from app.repositories.world_repo import WorldRepository, SQLAlchemyWorldRepository
from sqlalchemy.ext.asyncio import AsyncSession
logger = logging.getLogger(__name__)

def _ensure_repo(db_or_repo):
    """兼容旧调用：传入 AsyncSession 时包装为 SQLAlchemyWorldRepository。"""
    if isinstance(db_or_repo, AsyncSession):
        return SQLAlchemyWorldRepository(db_or_repo)
    return db_or_repo


# 文档随代码走（git 跟踪；__file__ 相对，不依赖 cwd）
DOCS_ROOT = Path(__file__).resolve().parent / "api_docs"
SECTIONS_DIR = DOCS_ROOT / "sections"


def _discover_sections() -> list[dict]:
    """动态发现分区：扫描 sections/ 目录（NN-*.md），按固定行号约定解析（语言无关）：
    行1 `# NN 标题` / 行2 `> 区介绍内容` / 行3+ 正文。
    新增分区=放一个 md 文件；改名=改 md 第一行；删除=删文件——均无需改代码/重启。"""
    sections = []
    if not SECTIONS_DIR.is_dir():
        return sections
    for p in sorted(SECTIONS_DIR.glob("[0-9][0-9]-*.md")):
        sid = p.stem[:2]
        title = p.stem[3:]
        intro = ""
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines:
                # 行1：`# NN 标题` → 标题（只剥 # 和编号，无语言依赖）
                m = re.match(r"^#\s*[0-9]{2}\s*(.+)$", lines[0].strip())
                if m:
                    title = m.group(1).strip()
            if len(lines) >= 2:
                # 行2：`> xxx` → 区介绍（只剥引用前缀，内容任意语言）
                intro = re.sub(r"^>\s*", "", lines[1].strip())
        except Exception:
            pass
        sections.append({"id": sid, "title": title, "file": p.name, "intro": intro})
    return sections


# 分区注册表（id → 标题/文件名/区介绍）——工具 description 与 view_section 共用同一份；
# 动态从 sections/ 目录发现（见 _discover_sections），增删改分区无需重启
SECTIONS: list[dict] = _discover_sections()


async def ensure_sections_seeded(db) -> None:
    """首次启动/访问：扫 md 源，把 DB 里没有的分区写入（md 种子，不覆盖已有值）。"""
    db = _ensure_repo(db)
    try:
        from sqlalchemy import select
        from app.models.api_doc_section import ApiDocSection
        existing = set((await db.execute(select(ApiDocSection.id))).scalars().all())
        for s in _discover_sections():
            if s["id"] in existing:
                continue
            db.add(ApiDocSection(id=s["id"], title=s["title"], intro=s["intro"], doc_file=s["file"]))
        await db.commit()
    except Exception as e:
        logger.warning(f"接口文档分区 seed 失败: {e}", exc_info=True)


async def get_sections(db) -> list[dict]:
    """分区列表（运行时权威 = DB 快照；确保已 seed）——快，无文件解析。"""
    db = _ensure_repo(db)
    from sqlalchemy import select
    from app.models.api_doc_section import ApiDocSection
    await ensure_sections_seeded(db)
    rows = (await db.execute(select(ApiDocSection).order_by(ApiDocSection.id))).scalars().all()
    return [{"id": r.id, "title": r.title, "intro": r.intro, "file": r.doc_file} for r in rows]


async def sync_sections_from_docs(db) -> dict:
    """「从文档中更新」：md → DB 全量同步（新增/更新/删除，以 md 为准）。"""
    db = _ensure_repo(db)
    from sqlalchemy import select
    from app.models.api_doc_section import ApiDocSection
    docs = _discover_sections()
    rows = (await db.execute(select(ApiDocSection))).scalars().all()
    by_id = {r.id: r for r in rows}
    created = updated = removed = 0
    for s in docs:
        row = by_id.pop(s["id"], None)
        if row is None:
            db.add(ApiDocSection(id=s["id"], title=s["title"], intro=s["intro"], doc_file=s["file"]))
            created += 1
        else:
            if row.title != s["title"] or row.intro != s["intro"]:
                row.title, row.intro, row.doc_file = s["title"], s["intro"], s["file"]
                updated += 1
    for leftover in by_id.values():
        await db.delete(leftover)
        removed += 1
    await db.commit()
    return {"created": created, "updated": updated, "removed": removed}


def _write_back_doc(section_id: str, title: str, intro: str) -> bool:
    """表单保存勾选「同步更新文档」：写回 md 行1/行2（行3+ 正文不动）。返回是否成功。"""
    try:
        p = None
        for cand in SECTIONS_DIR.glob(f"{section_id}-*.md"):
            p = cand
            break
        if p is None:
            return False
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            lines[0] = f"# {section_id} {title}"
        if len(lines) >= 2:
            lines[1] = f"> {intro}"
        p.write_text("\n".join(lines), encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"写回文档失败 {section_id}: {e}", exc_info=True)
        return False


async def save_sections(db, items: list[dict], write_back: bool = False) -> dict:
    """表单保存：items=[{id,title,intro}] 更新 DB；write_back=True 时同步写回 md。"""
    db = _ensure_repo(db)
    from sqlalchemy import select
    from app.models.api_doc_section import ApiDocSection
    saved = 0
    for it in items:
        sid = str(it.get("id", "")).strip()
        title = str(it.get("title", "")).strip()
        intro = str(it.get("intro", "")).strip()
        if not sid or not title:
            continue
        row = (await db.execute(select(ApiDocSection).where(ApiDocSection.id == sid))).scalar_one_or_none()
        if row is None:
            row = ApiDocSection(id=sid, title=title, intro=intro)
            db.add(row)
        else:
            row.title, row.intro = title, intro
        if write_back:
            _write_back_doc(sid, title, intro)
        saved += 1
    await db.commit()
    return {"saved": saved, "write_back": write_back}


def section_intro_text() -> str:
    """给 view_api_doc 工具 description 用的「区名 + 区介绍」文本（实时扫描，改文档即时生效）"""
    return "\n".join(f"{s['id']} {s['title']}：{s['intro']}" for s in _discover_sections())


def view_section(section_id: str) -> dict:
    """按区号读取分区文档内容（防路径穿越：只允许注册表内 id；分区表实时扫描）"""
    sec = next((s for s in _discover_sections() if s["id"] == section_id), None)
    if sec is None:
        raise ValueError(f"未知分区: {section_id}（可选：{' / '.join(s['id'] for s in _discover_sections())}）")
    path = SECTIONS_DIR / sec["file"]
    if not path.exists():
        raise FileNotFoundError(f"分区文档缺失: {sec['file']}")
    return {
        "section": sec["id"],
        "title": sec["title"],
        "content": path.read_text(encoding="utf-8"),
    }
