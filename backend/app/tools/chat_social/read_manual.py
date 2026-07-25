"""
read_manual 工具 — AI 查看用户手册，了解平台功能和消息格式
"""
import logging
from pathlib import Path
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)

MANUAL_PATH = Path("/aischat/docs/guides/用户手册.md")


class ReadManual(ToolPlugin):
    name = "read_manual"
    description = (
        "查看用户手册，了解平台支持的消息格式、功能规范。"
        "当用户询问如何发彩色文字、用什么格式、有哪些功能时，应主动调用此工具查询手册获取准确信息。"
        "可搜索关键词（彩色文字、Markdown、文件转发、闹钟、联邦等），不传关键词返回目录概览。"
    )
    segment = "chat_social"
    parameters = {
        "keyword": {
            "type": "string",
            "description": "搜索关键词（可选）。如「彩色文字」「文件转发」「闹钟」「联邦」。不传则返回手册目录结构。",
        },
    }
    required = []
    states = ["active", "dnd"]
    admin_description = "AI 查看用户手册，了解平台功能。支持关键词搜索。"

    async def execute(self, db, agent_id, group_id, arguments, context):
        if not MANUAL_PATH.exists():
            return {"ok": False, "error": "手册文件不存在"}

        content = MANUAL_PATH.read_text(encoding="utf-8")
        keyword = arguments.get("keyword", "").strip()

        if not keyword:
            toc_lines = []
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("# ") or stripped.startswith("## ") or stripped.startswith("### "):
                    toc_lines.append(stripped)
            text = "\n".join(toc_lines[:40])
            if len(text) > 2000:
                text = text[:2000] + "\n\n…（省略）"
            return {"ok": True, "keyword": None, "result": text}

        lines = content.split("\n")
        results = []
        current_section = ""

        for i, line in enumerate(lines):
            if line.startswith("## ") or line.startswith("### "):
                current_section = line.strip()
            if keyword.lower() in line.lower():
                start = max(0, i - 2)
                end = min(len(lines), i + 6)
                snippet = "\n".join(lines[start:end])
                results.append(f"【{current_section}】\n{snippet}")

        if not results:
            return {"ok": True, "keyword": keyword, "result": f"未找到与「{keyword}」相关的条目。可尝试其他关键词。"}

        merged = "\n\n---\n\n".join(results[:8])
        if len(merged) > 4000:
            merged = merged[:4000] + "\n\n…（更多结果被截断）"

        return {"ok": True, "keyword": keyword, "result": merged}


ToolRegistry.register(ReadManual)
