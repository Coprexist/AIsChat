"""
世界 API 文档注册表 — 平台为世界 AI 提供的分区接口文档

文档结构（data/world_api_docs/）：
  index.md                 总览（区名 + 区介绍 + 使用指引）
  sections/01-*.md …       各区详细 API

设计：AI 侧只暴露「区名 + 区介绍」（view_api_doc 工具的 description 里），
需要细节时由 AI 自己选择打开哪个区，避免全量文档塞进上下文。
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DOCS_ROOT = Path("data/world_api_docs")
SECTIONS_DIR = DOCS_ROOT / "sections"

# 分区注册表（id → 标题/文件名/区介绍）——工具 description 与 view_section 共用同一份
SECTIONS: list[dict] = [
    {"id": "01", "title": "世界编号变量", "file": "01-variables.md",
     "intro": "window 注入的 WORLD_ID/GROUP_ID/USER_ID 等变量与打包原则，写页面代码前必读"},
    {"id": "02", "title": "世界UI桥 WorldUI", "file": "02-worldui.md",
     "intro": "控制宿主外壳：侧边栏/悬浮图标显隐"},
    {"id": "03", "title": "文件操作", "file": "03-files.md",
     "intro": "file_list/write/read/edit/delete 全部参数、类型白名单与越界防护"},
    {"id": "04", "title": "积木体系", "file": "04-blocks.md",
     "intro": "list/view/apply_world_block 用法、现有积木（侧边栏/群聊对话窗）与侧边栏约定"},
    {"id": "05", "title": "群聊 API", "file": "05-group-chat.md",
     "intro": "读消息/发消息/成员列表/角色管理工具、身份与权限约定"},
    {"id": "06", "title": "页面与资源", "file": "06-pages-assets.md",
     "intro": "沉浸界面入口、静态资源路由与相对路径规则"},
    {"id": "07", "title": "懒通知与世界时间", "file": "07-notices-time.md",
     "intro": "用户改代码的通知机制、世界时间与运行模式"},
    {"id": "08", "title": "错误与安全", "file": "08-errors-security.md",
     "intro": "错误体格式、状态码、认证与安全约定"},
]


def section_intro_text() -> str:
    """给 view_api_doc 工具 description 用的「区名 + 区介绍」文本"""
    return "\n".join(f"{s['id']} {s['title']}：{s['intro']}" for s in SECTIONS)


def view_section(section_id: str) -> dict:
    """按区号读取分区文档内容（防路径穿越：只允许注册表内 id）"""
    sec = next((s for s in SECTIONS if s["id"] == section_id), None)
    if sec is None:
        raise ValueError(f"未知分区: {section_id}（可选：{' / '.join(s['id'] for s in SECTIONS)}）")
    path = SECTIONS_DIR / sec["file"]
    if not path.exists():
        raise FileNotFoundError(f"分区文档缺失: {sec['file']}")
    return {
        "section": sec["id"],
        "title": sec["title"],
        "content": path.read_text(encoding="utf-8"),
    }
