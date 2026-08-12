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

logger = logging.getLogger(__name__)

# 文档随代码走（git 跟踪；__file__ 相对，不依赖 cwd）
DOCS_ROOT = Path(__file__).resolve().parent / "api_docs"
SECTIONS_DIR = DOCS_ROOT / "sections"


def _discover_sections() -> list[dict]:
    """动态发现分区：扫描 sections/ 目录（NN-*.md），标题/介绍从文件头解析。
    新增分区=放一个 md 文件；改名=改 md 第一行；删除=删文件——均无需改代码/重启。
    约定：第一行 `# NN 标题`，第二行 `> 区介绍：xxx`。"""
    sections = []
    if not SECTIONS_DIR.is_dir():
        return sections
    for p in sorted(SECTIONS_DIR.glob("[0-9][0-9]-*.md")):
        sid = p.stem[:2]
        title = p.stem[3:]
        intro = ""
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:500]
            m = re.search(r"^#\s*[0-9]{2}\s*(.+)$", head, re.M)
            if m:
                title = m.group(1).strip()
            m2 = re.search(r"^>\s*区介绍：(.+)$", head, re.M)
            if m2:
                intro = m2.group(1).strip()
        except Exception:
            pass
        sections.append({"id": sid, "title": title, "file": p.name, "intro": intro})
    return sections


# 分区注册表（id → 标题/文件名/区介绍）——工具 description 与 view_section 共用同一份；
# 动态从 sections/ 目录发现（见 _discover_sections），增删改分区无需重启
SECTIONS: list[dict] = _discover_sections()


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
