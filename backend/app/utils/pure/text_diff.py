"""写入类工具的改动摘要（file_write / file_edit 共用）

世界 AI 改完文件后为了确认改对了，往往要回读一次（几千 token）。落盘时顺手回一个
「增减行数 + 首处改动及上下文」，多数情况就不用回读了。
"""

from __future__ import annotations

import difflib

__all__ = ["summarize_change"]

_MAX_LINES = 8
_EXCERPT_LIMIT = 240


def summarize_change(old: str, new: str) -> dict:
    """返回 {lines_added, lines_removed, first_change_line, excerpt}；无差异时只有前两项 0。

    first_change_line 是新文件的 1 起行号；excerpt 带行号与省略标记，超长截断。
    """
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added = removed = 0
    first_line: int | None = None
    excerpt_lines: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        added += j2 - j1
        removed += i2 - i1
        if first_line is not None:
            continue
        first_line = j1 + 1
        start = max(0, j1 - 1)                     # 带上文一行，便于定位
        end = min(len(new_lines), max(j2, j1 + 1) + 1)
        for k in range(start, min(end, start + _MAX_LINES)):
            excerpt_lines.append(f"{k + 1}|{new_lines[k]}")
    excerpt = "\n".join(excerpt_lines)
    if len(excerpt) > _EXCERPT_LIMIT:
        excerpt = excerpt[:_EXCERPT_LIMIT] + "…"
    out = {"lines_added": added, "lines_removed": removed}
    if first_line is not None:
        out["first_change_line"] = first_line
        out["excerpt"] = excerpt
    return out
