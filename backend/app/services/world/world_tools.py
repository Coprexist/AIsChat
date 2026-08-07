"""
世界 AI 工具集 — 工具定义 + 执行（从 world_service 拆分）
- WORLD_TOOLS：暴露给 LLM 的 function calling 定义
- _execute_world_tool：执行工具（以世界主人身份；文件走隔离目录+白名单）
- _tool_result_summary：工具结果展示文案

跨模块依赖一律函数内懒导入（避免循环导入）。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.world.world_api_docs import section_intro_text

logger = logging.getLogger(__name__)


WORLD_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_world_info",
            "description": "更新这个世界（你自己所在的世界）的名称或简介。用户要求改名/改设定时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "新的世界名"},
                    "description": {"type": "string", "description": "新的世界观简介"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "列出世界文件夹里的文件（网页代码等）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "创建或写入世界文件（HTML/CSS/JS/图片等，自动建目录，类型白名单限制）。创建网页/改代码用它。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 index.html 或 css/style.css"},
                    "content": {"type": "string", "description": "文件内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_delete",
            "description": "删除世界文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compact_context",
            "description": "压缩对话上下文：把之前的对话总结为摘要，释放上下文空间。当系统提示上下文接近上限时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_questions",
            "description": "向用户展示接下来的建议（3-4 个，每个 ≤20 字）：可以是问题（如「卡牌对战怎么玩？」）、陈述性要求（如「把背景改成星空」）或下一步选项（如「查看世界文件」）——具体、好玩、引导探索。完成回复觉得用户需要引导时调用——用户点一下就执行。注意：这些建议会显示在你这条回复的下方（对话流里，紧跟你的消息），不是页面顶部——向用户说明时就说「回复下方/消息下面」的建议。⚠️ 调用后在回复正文里阐述这些建议或说明生成逻辑：让用户明白每个建议是什么/点了会发生什么（可逐一展开，也可概括说明），不要只丢一个列表让用户猜。",
            "parameters": {
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "3-4 个建议（问题/要求/下一步选项，用户可直接点击发送）",
                    },
                },
                "required": ["questions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "读取世界文件内容（编辑前确认内容用；长文件截断显示）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "相对路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_edit",
            "description": "增量编辑世界文件（查找替换/行后插入/删除行），比全量重写省 token。编辑前建议先 file_read 确认内容。多次插入时从最大行号开始往小插。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径"},
                    "operation": {"type": "string", "enum": ["str_replace", "insert", "delete_lines"], "description": "str_replace=精确替换（old_string 必须唯一）；insert=在 line 行之后插入；delete_lines=删除 start_line..end_line（含两端）"},
                    "old_string": {"type": "string", "description": "str_replace 必填：被替换的精确原文"},
                    "new_string": {"type": "string", "description": "替换后的新内容 / 要插入的内容"},
                    "line": {"type": "integer", "description": "insert 必填：在此行号之后插入（1 开头，0=文件开头）"},
                    "start_line": {"type": "integer", "description": "delete_lines 必填：起始行（1 开头）"},
                    "end_line": {"type": "integer", "description": "delete_lines 必填：结束行（含）"},
                },
                "required": ["path", "operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_world_blocks",
            "description": "查积木：列出平台提供的预制世界块（可复用 UI 组件，如侧边栏）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_world_block",
            "description": "查看积木详情和完整代码（应用前先看，确认是否适合本世界）。",
            "parameters": {
                "type": "object",
                "properties": {"block_id": {"type": "string", "description": "积木 id"}},
                "required": ["block_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_world_block",
            "description": "应用积木：把积木文件直接部署进世界文件夹（blocks/{block_id}/），按返回的 usage 在页面中引入。",
            "parameters": {
                "type": "object",
                "properties": {"block_id": {"type": "string", "description": "积木 id"}},
                "required": ["block_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_api_doc",
            "description": "查看「群视界 API 文档」指定分区的详细接口内容（文档按区分区，此处只列区名与区介绍，需要细节时按需打开对应分区）：\n" + section_intro_text(),
            "parameters": {
                "type": "object",
                "properties": {"section": {"type": "string", "description": "分区号（01~08）"}},
                "required": ["section"],
            },
        },
    },
    # ── 世界代码执行（2.1 沙箱 + 2.2 触发文件）──
    {
        "type": "function",
        "function": {
            "name": "run_world_code",
            "description": "在沙箱中运行本世界的 Python 代码（测试用）：可直接跑一段脚本（code），或触发入口 main.py 的 handle(event)（给 event 即触发模式）。世界代码运行在隔离沙箱（内存/CPU/超时受限，无网络）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "可选：直接执行的 Python 脚本"},
                    "entry": {"type": "string", "description": "可选：世界文件夹内入口文件（默认 main.py，触发模式用）"},
                    "event": {"type": "object", "description": "可选：触发事件 dict；给了就执行入口的 handle(event) 并返回结果"},
                },
                "required": [],
            },
        },
    },
    # ── 上网（复用主系统同一份实现：web_search/web_fetch，无 opencli 依赖）──
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索引擎：通过 Bing 搜索网络上的最新信息，返回标题、链接和摘要。使用场景：搜索新闻、查找资料、获取实时信息、验证事实。与 web_fetch 配合使用：先用 web_search 找链接，再用 web_fetch 看具体内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，支持中文"},
                    "count": {"type": "integer", "description": "返回结果数量（1-10，默认 5）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "上网查资料：获取指定 URL 的网页内容（纯文本）。比 browser 命令更轻量快速，适合获取网页正文、API 响应、文档等。不支持需要 JavaScript 渲染的页面（如 SPA 应用）。页面加载慢/内容延迟出现时，可设置 delay_ms 先等待再抓取。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要访问的完整 URL（含 https://）"},
                    "selector": {"type": "string", "description": "可选：只提取指定标签的内容（如 'article'、'div'、'p'）。注意：只支持 HTML 标签名，不支持 CSS 类/ID 选择器"},
                    "delay_ms": {"type": "integer", "description": "可选：发起请求前先等待的毫秒数（0-30000，默认 0）。目标网页加载慢/内容延迟出现时设置，给服务器和页面数据生成留出时间"},
                },
                "required": ["url"],
            },
        },
    },
    # ── 记忆（世界专属表 world_ai_memories，工具名与主站统一）──
    {
        "type": "function",
        "function": {
            "name": "store_memory",
            "description": "存储一条长期记忆（这个世界的重要信息，以后可以检索回忆）。世界的重要设定、用户偏好、关键事件值得存。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "记忆标题（简短概括）"},
                    "content": {"type": "string", "description": "记忆详细内容"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "检索本世界的长期记忆（语义搜索）。用户提到以前的事、或需要历史上下文时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询（描述你想找什么）"},
                    "top_k": {"type": "integer", "description": "返回条数（1-20，默认 5）"},
                },
                "required": ["query"],
            },
        },
    },
    # ── 群聊 API（以世界创建者身份执行；群 id 默认取本世界绑定的群，AI 无需知道编号）──
    {
        "type": "function",
        "function": {
            "name": "get_bound_groups",
            "description": "查本世界绑定了哪些群聊（返回群名/成员数/是否暂停）。用于了解本世界的群聊入口。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_group_messages",
            "description": "读取群聊的最近消息（含发送者名字），了解群里最近聊了什么。默认操作本世界绑定的群，不需要传群 id。",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "可选：指定群聊 id（默认本世界绑定的群）"},
                    "limit": {"type": "integer", "description": "条数，默认 20，最大 50"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_group_members",
            "description": "列出群聊成员（谁是谁 + 角色：owner/admin/member + 在线状态）。默认操作本世界绑定的群。",
            "parameters": {
                "type": "object",
                "properties": {"group_id": {"type": "integer", "description": "可选：指定群聊 id（默认本世界绑定的群）"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_group_message",
            "description": "以世界创建者身份在群聊发一条消息。用户要求你（或世界）在群里说话时调用。默认发到本世界绑定的群。",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "可选：指定群聊 id（默认本世界绑定的群）"},
                    "content": {"type": "string", "description": "消息内容"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_group_member_role",
            "description": "修改群成员角色（admin/member）。仅群主可操作。默认操作本世界绑定的群。",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "可选：指定群聊 id（默认本世界绑定的群）"},
                    "member_type": {"type": "string", "enum": ["human", "ai"], "description": "成员类型"},
                    "member_id": {"type": "integer", "description": "成员 id（来自 list_group_members）"},
                    "role": {"type": "string", "enum": ["admin", "member"], "description": "新角色"},
                },
                "required": ["member_type", "member_id", "role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kick_group_member",
            "description": "把某成员移出群聊。仅群主/管理员可操作。默认操作本世界绑定的群。",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "可选：指定群聊 id（默认本世界绑定的群）"},
                    "member_type": {"type": "string", "enum": ["human", "ai"], "description": "成员类型"},
                    "member_id": {"type": "integer", "description": "成员 id"},
                },
                "required": ["member_type", "member_id"],
            },
        },
    },
]


def _tool_result_summary(name: str, result: dict) -> str:
    """工具执行结果的展示文案（前端 [TOOL] 事件 + 落库 role=tool）"""
    ok = bool(result.get("success"))
    if name == "update_world_info":
        if ok:
            parts = []
            if result.get("name"):
                parts.append(f"名称→{result['name']}")
            if result.get("description"):
                parts.append("简介已更新")
            return "已更新世界信息" + (f"（{'，'.join(parts)}）" if parts else "")
        return f"更新世界信息失败：{result.get('error', '未知错误')}"
    if name == "file_list":
        files = result.get("files") or []
        if not files:
            return "世界文件夹是空的"
        shown = "、".join(files[:10]) + (f" 等{len(files)}个" if len(files) > 10 else "")
        return f"世界文件（{len(files)} 个）：{shown}"
    if name == "file_write":
        if ok:
            if result.get("skipped"):
                return f"⏭ 已跳过（该操作本次对话已执行过）：{result.get('path')}"
            return f"成功创建文件 {result.get('path')}"
        return f"创建文件失败：{result.get('error', '未知错误')}"
    if name == "file_delete":
        return f"已删除文件 {result.get('path')}" if ok else f"删除失败：{result.get('error', '未知错误')}"
    if name == "file_edit":
        if ok:
            op = {"str_replace": "替换", "insert": "插入", "delete_lines": "删除行"}.get(result.get("operation", ""), "编辑")
            return f"已{op} {result.get('path')}"
        return f"编辑失败：{result.get('error', '未知错误')}"
    if name == "file_read":
        if ok:
            if result.get("binary"):
                return f"{result.get('path')}（二进制文件）"
            c = result.get("content") or ""
            return f"已读取 {result.get('path')}（{len(c)} 字符）"
        return f"读取失败：{result.get('error', '未知错误')}"
    if name == "compact_context":
        if ok:
            return (
                f"上下文已压缩（{result.get('before_tokens')}→{result.get('after_tokens')} tokens，"
                f"压缩 {result.get('compression_ratio_pct')}%）"
            )
        return f"上下文压缩失败：{result.get('error', '未知错误')}"
    if name == "list_world_blocks":
        if ok:
            blocks = result.get("blocks") or []
            names = "、".join(f"{b['name']}({b['id']})" for b in blocks[:8])
            return f"平台积木（{len(blocks)} 个）：{names}" + ("…" if len(blocks) > 8 else "")
        return f"查积木失败：{result.get('error', '未知错误')}"
    if name == "view_world_block":
        if ok:
            files = list((result.get("files_content") or {}).keys())
            return f"积木「{result.get('name')}」：{(result.get('description') or '')[:40]}｜文件：{'、'.join(files)}"
        return f"看积木失败：{result.get('error', '未知错误')}"
    if name == "apply_world_block":
        if ok:
            return (
                f"已应用积木「{result.get('name')}」→ {'、'.join(result.get('applied_files', []))}。"
                f"用法：{result.get('usage', '')[:60]}"
            )
        return f"应用积木失败：{result.get('error', '未知错误')}"
    if name == "view_api_doc":
        if ok:
            return f"接口文档「{result.get('title') or result.get('section', '')}」已读取"
        return f"接口文档读取失败：{result.get('error', '未知错误')}"
    if name == "store_memory":
        return f"已记住「{result.get('title', '')}」" + ("（无向量）" if ok and not result.get("embedded") else "") if ok else f"记忆失败：{result.get('error', '未知错误')}"
    if name == "recall_memory":
        if ok:
            mems = result.get("memories") or []
            if not mems:
                return "没找到相关记忆"
            return f"检索到 {len(mems)} 条记忆：" + "、".join(m.get('title', '') for m in mems[:5])
        return f"记忆检索失败：{result.get('error', '未知错误')}"
    if name == "web_search":
        if ok:
            return f"搜索结果 {result.get('count', 0)} 条：" + "、".join(r.get('title', '')[:20] for r in (result.get('results') or [])[:5])
        return f"搜索失败：{result.get('error', '未知错误')}"
    if name == "web_fetch":
        if ok:
            return f"已获取 {result.get('url', '')[:60]}"
        return f"抓取失败：{result.get('error', '未知错误')}"
    if name == "run_world_code":
        if ok:
            if "result" in result:
                return f"世界代码触发成功：{str(result.get('result'))[:120]}"
            out = (result.get('stdout') or '').strip().splitlines()
            return f"世界代码运行成功（{result.get('duration_ms', 0)}ms）：" + (out[-1][:120] if out else "无输出")
        return f"世界代码执行失败：{result.get('error', '未知错误')}"
    if name == "get_bound_groups":
        if ok:
            groups = result.get("groups") or []
            if not groups:
                return "本世界未绑定任何群聊"
            return "绑定群聊：" + "、".join(f"{g['name']}(#{g['group_id']}，{g['member_count']}人)" for g in groups)
        return f"查绑定群失败：{result.get('error', '未知错误')}"
    if name == "get_group_messages":
        if ok:
            msgs = result.get("messages") or []
            if not msgs:
                return "群聊暂无消息"
            return f"群聊最近 {len(msgs)} 条消息（{msgs[0]['sender']}…{msgs[-1]['sender']}）"
        return f"读消息失败：{result.get('error', '未知错误')}"
    if name == "list_group_members":
        if ok:
            members = result.get("members") or []
            return f"群成员（{len(members)} 人）：" + "、".join(f"{m['name']}({m['role']})" for m in members[:8])
        return f"查成员失败：{result.get('error', '未知错误')}"
    if name == "send_group_message":
        return f"已发送群消息（#{result.get('message_id')}）" if ok else f"发送失败：{result.get('error', '未知错误')}"
    if name == "set_group_member_role":
        return f"已把成员 {result.get('member_id')} 的角色设为 {result.get('role')}" if ok else f"改角色失败：{result.get('error', '未知错误')}"
    if name == "kick_group_member":
        return f"已把成员 {result.get('member_id')} 移出群聊" if ok else f"移出失败：{result.get('error', '未知错误')}"
    if result.get("skipped"):
        return "⏭ 已跳过（该操作本次对话已执行过），请直接总结或执行新操作"
    return f"工具执行{'成功' if ok else '失败'}"


async def _do_execute(db: AsyncSession, world, name: str, arguments: str, turn_state: dict | None = None) -> dict:
    """实际执行世界 AI 的工具调用（以世界主人身份写操作；文件走隔离目录+白名单）"""
    import json

    if name == "update_world_info":
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {"success": False, "error": "参数解析失败"}
        patch = {
            k: v.strip() for k, v in args.items()
            if k in ("name", "description") and isinstance(v, str) and v.strip()
        }
        if not patch:
            return {"success": False, "error": "没有有效的 name/description 参数"}
        try:
            from app.services.world.world_service import update_world
            updated = await update_world(db, world.id, world.owner_id, **patch)
            return {"success": True, "name": updated["name"], "description": updated["description"]}
        except ValueError as e:
            return {"success": False, "error": str(e)}

    from app.services.world.world_file_service import delete_file, list_files, write_file

    # ── 群聊 API 工具（以世界创建者身份执行，权限按群聊角色体系：owner/admin/member）──
    from app.chat.message import (
        get_group as _get_group,
        get_group_members as _get_group_members,
        get_recent_messages as _get_recent_messages,
        create_message as _create_message,
        change_member_role as _change_member_role,
        remove_member as _remove_member,
    )
    from app.models.world import WorldBinding
    from sqlalchemy import func as _func

    def _parse_args():
        try:
            return json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {}

    async def _bound_group_ids() -> list[int]:
        rows = (await db.execute(
            select(WorldBinding).where(
                WorldBinding.world_id == world.id,
                WorldBinding.entity_type == "group",
            )
        )).scalars().all()
        return [r.entity_id for r in rows]

    async def _resolve_group_ids(args: dict) -> list[int]:
        """群 id 解析：显式 group_id 优先；否则世界绑定的群（AI 无需知道编号，符合变量注入哲学）"""
        explicit = args.get("group_id")
        if explicit not in (None, "", 0):
            try:
                return [int(explicit)]
            except (TypeError, ValueError):
                pass
        return await _bound_group_ids()

    if name == "get_bound_groups":
        try:
            gids = await _bound_group_ids()
            from app.models.group import GroupMember
            out = []
            for gid in gids:
                g = await _get_group(db, gid)
                if g is None:
                    continue
                cnt = (await db.execute(
                    select(_func.count()).select_from(GroupMember).where(GroupMember.group_id == gid)
                )).scalar()
                out.append({
                    "group_id": gid,
                    "name": g.name,
                    "is_paused": g.is_paused,
                    "member_count": cnt,
                    "created_at": str(g.created_at) if g.created_at else None,
                })
            return {"success": True, "groups": out}
        except Exception as e:
            return {"success": False, "error": str(e)}

    if name == "get_group_messages":
        args = _parse_args()
        try:
            gids = await _resolve_group_ids(args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            limit = max(1, min(int(args.get("limit") or 20), 50))
            msgs = await _get_recent_messages(db, gid, limit)
            from app.models.user import User
            from app.models.agent import Agent
            all_ids = {m.sender_id for m in msgs}
            name_map = {}
            if all_ids:
                u_res = await db.execute(select(User.id, User.username, User.type).where(User.id.in_(all_ids)))
                for uid, uname, utype in u_res.all():
                    name_map[uid] = uname
                    if utype == "ai":
                        a = (await db.execute(select(Agent.name).where(Agent.user_id == uid))).first()
                        if a:
                            name_map[uid] = a[0]
            out = [{
                "id": m.id,
                "sender": name_map.get(m.sender_id, f"#{m.sender_id}"),
                "content": m.content,
                "created_at": str(m.created_at) if m.created_at else None,
            } for m in msgs]
            return {"success": True, "messages": out}
        except Exception as e:
            return {"success": False, "error": str(e)}

    if name == "list_group_members":
        args = _parse_args()
        try:
            gids = await _resolve_group_ids(args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            members = await _get_group_members(db, gid)
            from app.models.user import User
            from app.models.agent import Agent
            out = []
            for m in members:
                nm = None
                if m.member_type == "human":
                    u = await db.get(User, m.member_id)
                    if u:
                        nm = u.username
                else:
                    a = (await db.execute(select(Agent.name).where(Agent.user_id == m.member_id))).first()
                    if a:
                        nm = a[0]
                out.append({
                    "type": m.member_type,
                    "id": m.member_id,
                    "name": nm or f"{m.member_type}:{m.member_id}",
                    "role": m.role,
                })
            return {"success": True, "members": out}
        except Exception as e:
            return {"success": False, "error": str(e)}

    if name == "send_group_message":
        args = _parse_args()
        try:
            gids = await _resolve_group_ids(args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            content = str(args.get("content") or "").strip()
            if not content:
                return {"success": False, "error": "消息内容不能为空"}
            msg = await _create_message(db, gid, "human", world.owner_id, content, source="world", allow_non_member=True)
            try:
                from app.routers.ws import manager
                await manager.broadcast_to_group(gid, {"type": "message", "data": {"id": msg.id, "content": content}})
            except Exception:
                pass
            return {"success": True, "message_id": msg.id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    if name == "set_group_member_role":
        args = _parse_args()
        try:
            gids = await _resolve_group_ids(args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            mtype = str(args.get("member_type") or "")
            mid = int(args.get("member_id") or 0)
            role = str(args.get("role") or "")
            await _change_member_role(db, gid, world.owner_id, mtype, mid, role)
            return {"success": True, "member_id": mid, "role": role}
        except (ValueError, TypeError) as e:
            return {"success": False, "error": str(e)}

    if name == "kick_group_member":
        args = _parse_args()
        try:
            gids = await _resolve_group_ids(args)
            if not gids:
                return {"success": False, "error": "本世界未绑定任何群聊"}
            gid = gids[0]
            mtype = str(args.get("member_type") or "")
            mid = int(args.get("member_id") or 0)
            await _remove_member(db, gid, world.owner_id, mtype, mid)
            return {"success": True, "member_id": mid}
        except ValueError as e:
            return {"success": False, "error": str(e)}

    if name == "file_list":
        try:
            files = list_files(world.id)
            return {"success": True, "files": [f["path"] for f in files]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    if name == "file_write":
        try:
            args = json.loads(arguments or "{}")
            path = str(args.get("path", "")).strip()
            content = str(args.get("content", ""))
            if not path:
                return {"success": False, "error": "缺少 path 参数"}
            from app.services.world.world_file_service import read_file, write_file
            # 内容相同检测：打断模型的重复写入循环（温和提示，非硬拦截）
            try:
                existing = read_file(world.id, path)
                if not existing.get("binary") and existing.get("content") == content:
                    return {"success": True, "path": path, "unchanged": True, "note": "文件内容与现有完全一致，未做更改（无需重复写入）"}
            except (ValueError, FileNotFoundError):
                pass  # 文件不存在 → 正常创建
            write_file(world.id, path, content)
            return {"success": True, "path": path}
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}
    if name == "file_delete":
        try:
            args = json.loads(arguments or "{}")
            path = str(args.get("path", "")).strip()
            if not path:
                return {"success": False, "error": "缺少 path 参数"}
            delete_file(world.id, path)
            return {"success": True, "path": path}
        except (ValueError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}
    from app.services.world.world_blocks import apply_block, list_blocks, view_block
    if name == "list_world_blocks":
        try:
            blocks = list_blocks()
            return {"success": True, "blocks": [
                {"id": b["id"], "name": b["name"], "description": b["description"]}
                for b in blocks
            ]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    if name == "view_world_block":
        try:
            args = json.loads(arguments or "{}")
            block_id = str(args.get("block_id", "")).strip()
            if not block_id:
                return {"success": False, "error": "缺少 block_id 参数"}
            return {"success": True, **view_block(block_id)}
        except ValueError as e:
            return {"success": False, "error": str(e)}
    if name == "apply_world_block":
        try:
            args = json.loads(arguments or "{}")
            block_id = str(args.get("block_id", "")).strip()
            if not block_id:
                return {"success": False, "error": "缺少 block_id 参数"}
            return apply_block(world.id, block_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

    if name == "view_api_doc":
        try:
            args = json.loads(arguments or "{}")
            section = str(args.get("section", "")).strip()
            if not section:
                from app.services.world.world_api_docs import SECTIONS
                ids = " / ".join(s["id"] for s in SECTIONS)
                return {"success": False, "error": f"缺少 section 参数（可选：{ids}）"}
            from app.services.world.world_api_docs import view_section
            return {"success": True, **view_section(section)}
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    if name == "store_memory":
        try:
            args = json.loads(arguments or "{}")
            title = str(args.get("title", "")).strip()
            content = str(args.get("content", "")).strip()
            if not title or not content:
                return {"success": False, "error": "title 和 content 不能为空"}
            from app.models.world import WorldAIMemory
            from app.utils.embedding import get_embedding
            from app.services.world.world_chat_service import _resolve_world_credentials
            api_key, api_base = await _resolve_world_credentials(db, world)
            embedding = None
            try:
                embedding = await get_embedding(title + "\n" + content, api_base_url=api_base, api_key=api_key)
            except Exception as e:
                logger.warning(f"🌐 世界 #{world.id} 记忆向量化失败（将无向量存储）: {e}")
            # 同名 title 覆盖更新（记忆更新语义：执行改动/计划后用固定 title 刷新）
            from sqlalchemy import select as sa_select
            existing = (await db.execute(
                sa_select(WorldAIMemory).where(
                    WorldAIMemory.world_id == world.id, WorldAIMemory.title == title
                )
            )).scalars().first()
            if existing is not None:
                existing.content = content
                existing.embedding = embedding
            else:
                db.add(WorldAIMemory(world_id=world.id, title=title, content=content, embedding=embedding))
            await db.flush()
            return {"success": True, "title": title, "embedded": embedding is not None, "updated": existing is not None}
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    if name == "recall_memory":
        try:
            args = json.loads(arguments or "{}")
            query = str(args.get("query", "")).strip()
            top_k = max(1, min(int(args.get("top_k") or 5), 20))
            if not query:
                return {"success": False, "error": "query 不能为空"}
            from app.models.world import WorldAIMemory
            from app.utils.embedding import get_embedding
            from app.services.world.world_chat_service import _resolve_world_credentials
            api_key, api_base = await _resolve_world_credentials(db, world)
            memories = []
            # 第一轮：向量语义检索（与主站 recall 同款：embedding <=> 余弦距离）
            try:
                vec = await get_embedding(query, api_base_url=api_base, api_key=api_key)
                emb_str = "[" + ",".join(str(x) for x in vec) + "]"
                rows = (await db.execute(
                    select(WorldAIMemory)
                    .where(WorldAIMemory.world_id == world.id, WorldAIMemory.embedding != None)
                    .order_by(WorldAIMemory.embedding.op("<=>")(emb_str))
                    .limit(top_k)
                )).scalars().all()
                memories = [
                    {"title": m.title, "content": m.content, "created_at": str(m.created_at) if m.created_at else None}
                    for m in rows
                ]
            except Exception as e:
                logger.warning(f"🌐 世界 #{world.id} 向量检索失败（走文本回退）: {e}")
            # 回退：文本包含匹配（向量不可用或无结果时）
            if not memories:
                rows = (await db.execute(
                    select(WorldAIMemory)
                    .where(WorldAIMemory.world_id == world.id)
                    .order_by(WorldAIMemory.created_at.desc())
                    .limit(200)
                )).scalars().all()
                q = query.lower()
                memories = [
                    {"title": m.title, "content": m.content, "created_at": str(m.created_at) if m.created_at else None}
                    for m in rows if q in (m.title or "").lower() or q in (m.content or "").lower()
                ][:top_k]
            return {"success": True, "query": query, "memories": memories}
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    if name == "web_search":
        # 复用主系统同一份实现（同一份代码，无 opencli 依赖）
        try:
            args = json.loads(arguments or "{}")
            from app.tools.file_operations.web_search import WebSearch
            return await WebSearch().execute(db, 0, None, args, {})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    if name == "run_world_code":
        # 2.1/2.2：沙箱执行世界代码（code 脚本）或触发入口 handle(event)
        try:
            args = json.loads(arguments or "{}")
            # 确保沙箱 env 注入 WORLD_API_TOKEN / WORLD_API_BASE（懒生成，worlds.config.api_token）
            from app.routers.world_proxy import ensure_world_api_token
            await ensure_world_api_token(db, world)
            await db.commit()
            from app.services.world.world_sandbox import run_world_code as _run_code, run_world_trigger as _run_trigger
            if args.get("event") is not None:
                entry = str(args.get("entry") or "main.py").strip()
                return await _run_trigger(world, event=args.get("event"), entry=entry)
            code = args.get("code")
            entry = str(args.get("entry") or "").strip() or None
            return await _run_code(world, code=code if isinstance(code, str) else None, entry=entry)
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    if name == "web_fetch":
        # 复用主系统同一份实现（含 delay_ms 延迟抓取）
        try:
            args = json.loads(arguments or "{}")
            from app.tools.file_operations.web_fetch import WebFetch
            return await WebFetch().execute(db, 0, None, args, {})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    if name == "file_edit":
        try:
            args = json.loads(arguments or "{}")
            path = str(args.get("path", "")).strip()
            operation = str(args.get("operation", "")).strip()
            if not path or operation not in ("str_replace", "insert", "delete_lines"):
                return {"success": False, "error": "缺少 path 或 operation 非法"}
            from app.services.world.world_file_service import read_file, write_file
            from app.utils.pure.file_edit import apply_file_edit  # 与主站共用同一份编辑核心
            existing = read_file(world.id, path)
            if existing.get("binary"):
                return {"success": False, "error": "二进制文件不可编辑"}
            new_content, err = apply_file_edit(existing.get("content") or "", operation, args)
            if err:
                return {"success": False, "error": err}
            write_file(world.id, path, new_content)
            return {"success": True, "path": path, "operation": operation}
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}
    if name == "file_read":
        try:
            args = json.loads(arguments or "{}")
            path = str(args.get("path", "")).strip()
            if not path:
                return {"success": False, "error": "缺少 path 参数"}
            from app.services.world.world_file_service import read_file
            existing = read_file(world.id, path)
            if existing.get("binary"):
                return {"success": True, "path": path, "binary": True, "note": "二进制文件，内容不返回"}
            content = existing.get("content") or ""
            if len(content) > 6000:
                content = content[:6000] + "\n…（内容较长已截断，如需修改请用 edit_world_file 定位）"
            return {"success": True, "path": path, "content": content}
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}
    if name == "compact_context":
        # 复用主对话的压缩服务：总结中间消息 → 存 worlds.config.chat_summary → 下次只发摘要+最近 N 条
        try:
            from app.config import settings
            from app.services.memory.context_compression_service import compress_messages
            from app.services.world.world_chat_service import _resolve_world_credentials
            api_key, api_base = await _resolve_world_credentials(db, world)
            from app.models.world import WorldAI
            wai = (await db.execute(select(WorldAI).where(WorldAI.world_id == world.id))).scalar_one_or_none()
            model = (wai.model if wai else None) or settings.default_chat_model
            from app.services.world.world_chat_service import get_chat_history
            history = await get_chat_history(db, world.id, 200)
            from app.services.world.world_chat_service import WORLD_CHAT_KEEP_LAST, WORLD_CONTEXT_MIN_MESSAGES
            if len(history) < WORLD_CONTEXT_MIN_MESSAGES:
                return {"success": False, "error": f"对话太短（{len(history)} 条），无需压缩"}
            msgs = [{"role": "system", "content": "世界 AI 对话"}]  # keep_system 保留
            msgs += [
                {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
                for m in history if m["role"] not in ("tool", "note")
            ]
            new_messages, stats = await compress_messages(
                messages=msgs,
                api_base_url=api_base,
                api_key=api_key,
                model=model,
                keep_system=True,
                keep_last_n=WORLD_CHAT_KEEP_LAST,
            )
            if not stats.get("compressed"):
                return {"success": False, "error": stats.get("reason", "压缩未执行")}
            summary = next(
                (m["content"] for m in new_messages if m.get("role") == "system" and "上下文摘要" in str(m.get("content", ""))),
                "",
            )
            if not summary:
                return {"success": False, "error": "摘要提取失败"}
            world.config = {**(world.config or {}), "chat_summary": summary}
            # 能力懒加载：压缩后 effective 对齐最新（世界 skill 工具定义直接用最新的）
            try:
                from app.services.capability_versioning import mark_effective_latest
                await mark_effective_latest(db, world.config, ["ai-skills"])
            except Exception:
                pass
            await db.flush()
            return {
                "success": True,
                "before_tokens": stats.get("before_tokens", 0),
                "after_tokens": stats.get("after_tokens", 0),
                "compression_ratio_pct": stats.get("compression_ratio_pct", 0),
            }
        except Exception as e:
            logger.warning(f"🌐 世界 #{world.id} 压缩失败: {e}")
            return {"success": False, "error": str(e)}

    if name == "clear_context":
        # 清空对话上下文（历史消息 + 工作流记忆），长期记忆（world_ai_memories）保留——
        # 清空后 AI 从 store_memory 的记忆恢复工作状态
        try:
            from app.models.world import WorldChatMessage
            from sqlalchemy import delete as sa_delete
            await db.execute(sa_delete(WorldChatMessage).where(WorldChatMessage.world_id == world.id))
            world.config = {
                **(world.config or {}),
                "chat_summary": None,
                "workflow_memory": None,
            }
            await db.commit()
            return {"success": True, "note": "对话上下文已清空（历史消息+摘要+工作流记忆）；长期记忆保留，请从记忆恢复工作状态。"}
        except Exception as e:
            logger.warning(f"🌐 世界 #{world.id} 清空上下文失败: {e}")
            return {"success": False, "error": str(e)}

    if name == "suggest_questions":
        # "你可以问"建议：AI 自己生成问题 → 存 turn_state，流收尾时 [SUGGEST] 发给前端
        try:
            args = json.loads(arguments or "{}")
            questions = [str(q).strip()[:40] for q in (args.get("questions") or []) if str(q).strip()]
            if not questions:
                return {"success": False, "error": "questions 不能为空"}
            if turn_state is not None:
                turn_state["suggestions"] = questions[:5]
            return {"success": True, "count": len(questions), "note": "已生成建议问题，回复末尾会展示给用户"}
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    # ── 文件式 skill（世界 AI 只用设计侧造物主工具；世界侧居民能力归群 AI）──
    from app.services.world.world_skill_runtime import execute_skill
    skill_result = await execute_skill(db, world, name, arguments, scope='ai')
    if skill_result is not None:
        return skill_result

    return {"success": False, "error": f"未知工具: {name}"}


async def _execute_world_tool(
    db: AsyncSession, world, name: str, arguments: str, turn_state: dict | None = None,
) -> dict:
    """温和去重包装：5 分钟内重复调用且结果与上次完全一致才提示跳过。

    list_world_files 可能是 AI 在验证写入结果——结果变了不算重复；
    超过 5 分钟（如用户手动改了文件）允许重跑。
    """
    import time as _time
    result = await _do_execute(db, world, name, arguments, turn_state)
    if turn_state is not None:
        executed = turn_state.setdefault("executed", {})
        key = f"{name}|{arguments}"
        now = _time.monotonic()
        prev = executed.get(key)
        if prev is not None and (now - prev["ts"]) <= 300 and prev["result"] == result:
            return {
                **result,
                "skipped": True,
                "note": "该操作本次对话已执行过（5 分钟内且结果相同），请直接总结或执行新操作，不要重复。",
            }
        executed[key] = {"result": result, "ts": now}
    return result


# ═══════════════════════════════════════════════════════════════
# 世界 CRUD
# ═══════════════════════════════════════════════════════════════