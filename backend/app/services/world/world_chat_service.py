"""
世界 AI 对话服务（从 world_service 拆分）
- world_context_block：世界档案注入
- get_chat_history / _resolve_world_credentials / stream_world_chat：SSE 流式对话 + 工具多轮循环 + compact

跨模块依赖一律函数内懒导入（避免循环导入）。
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 实际请求日志（排查问题用）：每世界最近 10 条，落盘 data/world_llm_requests/{world_id}.jsonl
LLM_REQUEST_LOG_DIR = Path("data/world_llm_requests")
LLM_REQUEST_KEEP = 10


def _friendly_llm_error(err) -> str:
    """把 LLM 错误转成友好提示（余额不足/鉴权/限流/服务端）"""
    text = str(err)
    low = text.lower()
    if "402" in text or "insufficient balance" in low or "余额" in text:
        return "💰 世界 AI 余额不足（402）：请为 API 账号充值或更换有效 Key。已记录未完成的工作流，充值后说「继续」即可接着做。"
    if "401" in text or "authentication" in low or "invalid api key" in low or "403" in text:
        return "🔑 世界 AI 的 API Key 无效（401/403）：请在 API 配置中检查更新。"
    if "429" in text or "rate limit" in low:
        return "⏳ 请求太频繁（429 限流）：稍等片刻再试。"
    if "500" in text or "503" in text or "server error" in low or "busy" in low:
        return "🔧 DeepSeek 服务繁忙（5xx）：稍后再试。"
    return text[:200]


def _now_local() -> datetime:
    """本模块的时间戳（避免跨模块依赖 _now）"""
    from datetime import datetime as _dt, timezone as _tz
    return _dt.now(_tz.utc).replace(tzinfo=None)


def _is_json_line(line: str) -> bool:
    """行是否为完整可解析的 JSON（裁剪时跳过损坏行）"""
    try:
        json.loads(line)
        return True
    except Exception:
        return False


def _log_llm_request(world_id: int, turn_id: str, round_no: int, model: str, thinking: bool, messages: list) -> None:
    """保存一次实际 LLM 请求（消息全量），保留最近 10 条/世界

    append 模式（O_APPEND 行缓冲）：不再整文件重写，多轮/并发调用不会互相
    覆盖截断；超过 2 倍保留数时裁剪重写一次（顺带清掉损坏行）。
    """
    try:
        d = LLM_REQUEST_LOG_DIR
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{world_id}.jsonl"
        entry = {
            "ts": _now_local().isoformat(),
            "turn_id": turn_id,
            "round": round_no,
            "model": model,
            "thinking": thinking,
            "messages": messages,
        }
        line = json.dumps(entry, ensure_ascii=False)
        with open(path, "a", encoding="utf-8", buffering=1) as f:
            f.write(line + "\n")
        # 定期裁剪：超过 2x 保留数 → 只留最近 N 条（跳过损坏行）
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            good = [ln for ln in lines if ln.strip() and _is_json_line(ln)]
            if len(good) > LLM_REQUEST_KEEP * 2:
                path.write_text("\n".join(good[-LLM_REQUEST_KEEP:]) + "\n", encoding="utf-8")
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 请求日志保存失败: {e}")


async def _record_usage(db, world_id: int, turn_id: str, round_no, model: str, usage: dict | None, messages: list | None = None) -> None:
    """LLM 用量落库：
    - world_llm_usage：每世界缓存命中统计（2.7）
    - conversation_log：归入用户「群视界 agent」（个人 API 用量页可见）
    """
    if not usage:
        return
    try:
        from app.models.world import WorldLLMUsage
        db.add(WorldLLMUsage(
            world_id=world_id,
            turn_id=turn_id,
            round_no=str(round_no),
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            reasoning_tokens=int(usage.get("reasoning_tokens") or 0),
            cached_tokens=int(usage.get("cached_tokens") or 0),
        ))
        await db.flush()
        # 个人 API 用量：记账人 = 世界 AI 表单的世界主人（user_id 直记，查询时虚拟聚合「群视界 agent」）
        if messages:
            from app.services.content.conversation_log_service import save_conversation_log
            from app.models.world import World
            world = await db.get(World, world_id)
            if world is not None:
                await save_conversation_log(
                    db, None, messages, conversation_type="world",
                    token_usage=usage, model=model, thinking_enabled=False,
                    user_id=world.owner_id,
                )
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 用量记录失败: {e}")


def world_context_block(world) -> str:
    """世界档案：注入给世界 AI 的自身信息（名字/简介/状态/时间）"""
    return (
        "【你的世界档案】\n"
        f"- 世界名：{world.name}\n"
        f"- 简介：{world.description or '（无）'}\n"
        f"- 状态：{world.status}\n"
        f"- 时间流速：{world.time_flow_rate}x\n"
        f"- 世界时间：{world.world_time.isoformat() if world.world_time else '未开始'}\n"
        f"- 你的身份：world-{world.id}\n"
        "你可以用 update_world_info 工具修改世界名/简介。"
    )


# 世界 AI 对话上下文（与主对话压缩机制一致：128K 窗口 60% 触发提示，AI 调 compact 压缩）
WORLD_CHAT_KEEP_LAST = 10          # 压缩后保留的最近消息数
WORLD_CONTEXT_MIN_MESSAGES = 6     # 少于 N 条不触发压缩提示
DEFAULT_MAX_TOOL_ROUNDS = 50       # 工具循环默认上限（可在设计页配置 max_tool_rounds 覆盖）


CHAT_HISTORY_LIMIT = 30  # 每次对话携带的最近消息数

# "你可以问"默认预设问题（首次进入编辑页 / clear 后无对话历史时展示）
# 优先级：管理员后台 system_settings.world_preset_suggestions（统一维护）> 此处默认
async def get_chat_history(db: AsyncSession, world_id: int, limit: int = 30, before_id: int | None = None) -> list[dict]:
    """世界 AI 对话历史（最近 limit 条；before_id 传最旧 id 可翻更早）"""
    from app.models.world import WorldChatMessage

    query = select(WorldChatMessage).where(WorldChatMessage.world_id == world_id)
    if before_id is not None:
        query = query.where(WorldChatMessage.id < before_id)
    query = query.order_by(WorldChatMessage.id.desc()).limit(limit)
    result = await db.execute(query)
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "reasoning": m.reasoning if m.role in ("ai", "note") else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in reversed(result.scalars().all())
    ]


async def _save_ai_reply(db: AsyncSession, world, content: str, reasoning: str) -> None:
    """落库 AI 回复（含思考过程）；内容为空则跳过"""
    from app.services.world.world_service import _now
    from app.models.world import WorldChatMessage
    if not content:
        return
    db.add(WorldChatMessage(
        world_id=world.id, user_id=None, role="ai",
        content=content, reasoning=reasoning or None,
    ))
    world.last_active_at = _now()
    await db.commit()


async def _resolve_world_credentials(db: AsyncSession, world) -> tuple[str | None, str]:
    """世界 AI 计费/凭证：账单人 = 世界主人（主人 Key → 池 Key → 全局默认 base）"""
    from app.config import settings
    from app.models.user import User

    api_key, api_base = None, settings.deepseek_base_url
    owner = await db.get(User, world.owner_id) if world.owner_id else None
    if owner is not None:
        try:
            from app.utils.crypto import decrypt_api_key
            if owner.api_key_encrypted:
                api_key = decrypt_api_key(owner.api_key_encrypted)
                api_base = owner.api_base_url or settings.deepseek_base_url
            else:
                from app.services.infrastructure.quota_service import find_best_pool_key
                pool_key = await find_best_pool_key(db, owner.id)
                if pool_key:
                    api_key = decrypt_api_key(pool_key.api_key_encrypted)
                    api_base = pool_key.api_base_url or settings.deepseek_base_url
        except Exception as e:
            # 密钥解密失败等：降级到无 Key（走全局默认 base），让 LLM 层报清晰错误
            logger.warning(f"🌐 世界 #{world.id} 凭证解析降级: {e}")
            api_key, api_base = None, settings.deepseek_base_url
    return api_key, api_base


async def stream_world_chat(
    db: AsyncSession,
    world_id: int,
    user_id: int,
    message: str | list[str],
    turn_id: str = "",
):
    """世界 AI 对话（SSE 流式，参考大同差异分析流式实现）。

    事件格式（text/event-stream）：
      data: <内容增量>          — 正文逐 token
      data: [REASONING]<增量>   — 思考内容逐 token（开启 thinking 时）
      data: [ERROR]<信息>       — 错误
      data: [DONE]              — 结束
    内容里的换行用 {NL} 占位（SSE 行内不能有裸换行），前端还原。
    用户消息先落库；AI 回复流结束后落库（客户端中断也尽量保存已生成部分）。
    """
    import json

    import httpx
    from app.config import settings
    from app.models.world import World, WorldChatMessage

    world = await db.get(World, world_id)
    if world is None:
        yield "data: [ERROR]世界不存在\n\n"
        yield "data: [DONE]\n\n"
        return

    # 对话 = 活跃信号：唤醒 + 离线时间补偿（让 AI 看到的世界时间准确）
    from app.services.world.world_service import apply_time_compensation
    apply_time_compensation(world)
    await db.commit()

    from app.services.world.world_service import ensure_world_ai, take_pending_notices, CREATOR_DEFAULT_CONFIG
    wai = await ensure_world_ai(db, world_id)
    cfg = {
        "name": wai.name, "system_prompt": wai.system_prompt, "model": wai.model,
        "temperature": wai.temperature, "top_p": wai.top_p, "thinking": wai.thinking,
        "max_tool_rounds": wai.max_tool_rounds,
    }

    # ── 组装消息：静态 system 前缀保持稳定（prompt cache 友好）──
    # 位置1：世界档案 + 用户配置的系统提示词 + 工具约定（都是静态的）
    system_prompt = world_context_block(world) + "\n\n" + (
        cfg.get("system_prompt") or CREATOR_DEFAULT_CONFIG["system_prompt"]
    )
    system_prompt += "\n【工具约定】你的工具与平台 AI 同名同义（文件类：file_read/file_write/file_edit/file_list/file_delete，作用于世界文件夹）；另有 update_world_info / web_download / compact_context / list_world_blocks / view_world_block / apply_world_block / view_api_doc / store_memory / recall_memory / web_search / web_fetch。调用工具时不要把工具调用的原始内容写进回复文本，直接说你要做什么/做了什么；创建文件后告知用户文件路径。遇到不清楚的需求、含糊的指令或可能理解错的地方，主动提问确认，不要瞎猜。你也可以给用户下一步建议（问题/要求/选项都行）。⚠️ 如果你调用 suggest_questions 生成建议，要在回复正文里阐述这些建议或说明生成逻辑（可逐一展开，也可概括说明每个建议是什么/点了会发生什么），不要只丢一个列表让用户猜。收尾时最后一句要写实质内容（结论要点、建议选项的描述或你的思考脉络），不要用「我已经给出结论和下一步选项了，等你定方向」这类空话元话术。"
    system_prompt += "\n【能力边界】平台里有两类 AI，能力不同，被问起时准确回答，不要凭猜测：\n- 你（世界 AI / 群视界机器人）= 造物主：平台工具 + 设计侧技能库（data/world_ai_skills/，全局共享），在世界之外设计世界，不用也不会拿到世界侧技能\n- 群里的 AI 成员（居民，平台 agent，如绑定了本世界的群 AI）= 绑定本世界后拥有：① 世界侧技能（data/worlds/{id}/skills/ 下颁布的 manifest+code.py，像调普通工具一样 function calling 直接调用）② world_command 文本命令工具（把命令发到群里，由世界程序 main.py handle() 解析执行，与用户共用同一套语法）——所以群 AI 不是「只会说话没有工具」，它有工具，能力取决于这个世界颁布了什么技能\n- 世界侧技能由你（或世界配置）颁布：在世界的 skills/ 目录放 manifest.json + code.py，绑定本世界的群 AI 就能直接工具调用；你没颁布技能时它们就没有世界侧工具（只剩 world_command 和平台默认工具）\n- 用户/群成员直接在群里发命令文本（如「收诗：xxx」「我去 2,3」）→ 群消息钩子 → 世界程序 main.py 解析执行——这是「人直接与世界交互」，与群 AI 调工具是两条并存的路径，别混为一谈"
    system_prompt += "\n【接口文档】平台接口文档按区分区（01 世界编号变量 / 02 WorldUI 桥 / 03 文件操作 / 04 积木体系 / 05 群聊 API / 06 页面与资源 / 07 懒通知与世界时间 / 08 错误与安全）。需要接口细节时用 view_api_doc 打开对应分区（工具描述里有各区介绍，先看介绍再决定开哪个，不要一次全读）。"
    system_prompt += "\n【记忆约定】你的长期记忆（按世界隔离）一律用 manage_records 结构化存储（「目录/子目录/字段」三级，精确读写、不依赖向量）：\n- 记忆内容：项目进度、页面/功能清单、设定档案、知识库条目、关键决策、用户偏好、进行到一半的事\n- 写：action='set'（如 category='project', sub_key='图鉴页面', field='进度', value='已完成收录，待优化筛选'）；读：action='get' 或 action='summary'（快照）；列目录：action='categories'；删：action='delete'\n- 每次执行完文件改动、配置修改、发布状态等实际改动后，用 manage_records 更新对应记录（没有就 set 新建）\n- 每次写完计划/方案后也 manage_records 存一份（category='project', sub_key='当前计划'）\n- ⚠️ 不要用 store_memory/recall_memory 来记忆（本环境向量检索不可靠）：那是保留的旧工具，结构化记忆请走 manage_records\n- 被 clear_context 清空上下文或新会话开始时：先 manage_records categories + 相关 get 检索再继续工作，别从零开始\n- 记忆是这个世界的资产，跨世界不共享"
    system_prompt += "\n【UI 约定】若你的页面实现了自己的侧边栏/菜单/导航，请调用 WorldUI.hideFloatingIcon() 隐藏平台悬浮图标（见接口文档），避免重复；未实现时不要调用。"
    system_prompt += "\n【侧边栏约定】世界侧边栏/菜单必须保留平台基础菜单（首页/聊天/世界列表/设置四个目的地，可折叠成可展开的「平台」项但绝不能缺失，否则用户无法回到主应用）；平台项跳主应用（window.parent），世界自定义项跳世界内页面。组名/项名/样式可自行调整，推荐直接应用 platform-sidebar 积木。"
    system_prompt += "\n【路径约定】页面内资源（css/js/图片）一律用相对路径引用（支持跨文件夹 ../），不要用 / 开头的绝对路径（会 404）；数据请求用 /world/${WORLD_ID}/ 变量路径。"
    system_prompt += "\n【编号约定】不要硬编码任何编号（世界号/群号/用户 id）——世界编号 window.WORLD_ID、入口群聊编号 window.GROUP_ID 由平台注入变量，代码里一律用变量；群聊类工具默认作用于本世界绑定的群，直接说目的即可，无需也不应指定群号；成员 id 一律以 list_group_members 的返回为准。"
    system_prompt += "\n【世界运行规范】\n- 沙箱环境：世界代码（main.py / 沙箱脚本）的工作目录 = 世界文件夹本体，可直接读写世界文件夹里的文件（含 JSON 数据文件）；环境变量注入 WORLD_ID / WORLD_API_TOKEN / WORLD_API_BASE / WORLD_DIR（token 只用于受控 API，绝不外泄/打印/写进页面）\n- 数据规范（代码/数据分离）：\n  1) 结构化/操作数据（状态、计数、记录）→ 用受控 API 的世界数据库：GET/PUT/DELETE /data/{key}（key 用命名空间如 player.lihua / poems / quest.1，value 任意 JSON）——世界代码与页面三方共用同一份数据\n  2) 静态文字类（设定、文档、素材文本）→ 放世界文件夹 content/ 子目录（可自由建层级；content/ 是世界产物区，发布世界不打包，下载数据可选包含）\n  3) 代码（网页/脚本）放世界文件夹根目录或自有目录\n- 页面读数据：经世界代码发布状态（POST /state → 页面 SSE）或世界代码生成页面时内嵌；页面不要直连数据库\n【结构约定】注意维护和优化世界的项目结构：文件按职责组织（页面/样式/脚本/数据分开），定期清理无用文件，代码保持整洁可维护——世界会长期演进，结构混乱会让后续修改越来越难。"

    notices = await take_pending_notices(db, world_id)
    notice_lines = "\n".join(
        f"- {n['file']}（{n.get('location', '')}）: {n.get('summary', '')}"
        for n in notices
    ) if notices else ""

    # ── 上下文：有压缩摘要则 摘要+最近 N 条，否则最近 30 条；接近上限时提示 AI 调 compact（与主对话一致）──
    summary = (world.config or {}).get("chat_summary") or ""
    # 未完成工作流记忆：上次对话中断（无最终回复）→ 本次继续，不重做
    wm = (world.config or {}).get("workflow_memory")
    if wm and wm.get("tools_done"):
        done = "、".join(wm["tools_done"][-8:])
        system_prompt += (
            "\n\n【未完成工作流】上次对话在 " + str(wm.get("interrupted_at", ""))[:19] +
            " 中断，已执行：" + done + "。请继续完成剩余工作并给出总结，不要重复已完成的步骤。"
        )
    history = await get_chat_history(db, world_id, WORLD_CHAT_KEEP_LAST if summary else CHAT_HISTORY_LIMIT)
    hist_llm = [
        {"role": "assistant" if m["role"] == "ai" else m["role"], "content": m["content"]}
        for m in history if m["role"] not in ("tool", "note")
    ]
    # 用户消息列表（单条/批量统一；批量 = 排队消息一起发，逐条气泡）
    msg_list = message if isinstance(message, list) else [message]
    msg_list = [str(m).strip() for m in msg_list if str(m).strip()]
    from app.services.memory.context_compression_service import should_compress
    needs_compress = should_compress(
        [{"role": "system", "content": system_prompt}, *hist_llm,
         *[{"role": "user", "content": m} for m in msg_list]],
        min_messages=WORLD_CONTEXT_MIN_MESSAGES,
    )

    # 前缀稳定：位置2摘要（静态）+ 历史 + 用户消息（批量 = 逐条注入，AI 一次看到全部）
    messages = [{"role": "system", "content": system_prompt}]
    if summary:
        messages.append({"role": "system", "content": summary})
    messages += hist_llm
    for m in msg_list:
        messages.append({"role": "user", "content": m})

    # 动态信息全部放末尾（每次变化，不影响前缀 cache）——与主对话同规则
    if notice_lines:
        messages.append({"role": "system", "content": "【用户手动改动的懒通知，回复中应体现你看到了】\n" + notice_lines})
    if needs_compress:
        messages.append({"role": "system", "content": "⚠️ 上下文已接近上限，请调用 compact_context 工具压缩对话历史后再继续。"})
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(settings.display_timezone)
    messages.append({"role": "system", "content": f"## 当前时间\n{datetime.now(tz).strftime(f'%Y-%m-%d %H:%M {tz.key}')}\n"})

    # 世界内访客（身份系统 identity_index 快照）→ AI 知道谁在玩这个世界
    try:
        from app.services.world.world_service import get_world_data
        idx_row = await get_world_data(db, world_id, "identity_index")
        idx = (idx_row or {}).get("value")
        if isinstance(idx, dict) and idx:
            parts = []
            for v in idx.values():
                if isinstance(v, dict):
                    parts.append(f"{v.get('name', '?')}" + (f"（{v.get('role', '未绑定角色')}）" if v.get('role') else ""))
            if parts:
                messages.append({"role": "system", "content": "## 世界内访客\n" + "、".join(parts[:20])})
    except Exception:
        pass

    # 能力变更通知（世界源懒加载：增量 changelog 追加尾部，known 更新与注入同轮）
    try:
        from app.services.capability_versioning import build_change_notice
        notice = await build_change_notice(db, world.config, ["ai-skills"])
        if notice:
            messages.append({"role": "system", "content": notice})
            await db.commit()
    except Exception:
        pass

    # ── 落库：用户消息（批量 = 排队消息一起发，逐条气泡；先提交，即使流失败也不丢）──
    for m in msg_list:
        db.add(WorldChatMessage(world_id=world_id, user_id=user_id, role="user", content=m))
    try:
        await db.commit()
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 用户消息落库失败: {e}")

    # ── 用户斜杠命令（不走 LLM，仅单条）：/clear 清空上下文（保留记忆） /compact 压缩上下文 ──
    cmd_text = msg_list[0] if len(msg_list) == 1 else ""
    if cmd_text.startswith("/") and cmd_text in ("/clear", "/compact"):
        try:
            from app.services.world.world_chat_commands import run_slash_command
            note = await run_slash_command(db, world, cmd_text)
            db.add(WorldChatMessage(world_id=world_id, user_id=None, role="tool", content=note))
            await db.commit()
            yield f"data: [TOOL]{json.dumps({'name': cmd_text, 'success': True, 'summary': note}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.warning(f"🌐 世界 #{world_id} 命令执行失败: {e}")
            yield f"data: [ERROR]命令执行失败: {e}\n\n"
        yield "data: [DONE]\n\n"
        return

    from app.services.world.world_tools import WORLD_TOOLS
    from app.services.world.world_skill_runtime import build_ai_tools
    from app.services.capability_versioning import ensure_source_version, get_effective_definitions

    # 世界 AI（造物主）工具 = 平台内置 + 设计侧 skills（world_ai_skills/ 全局库；世界侧居民能力不注入）
    # 版本源 ai-skills（全局共享）：设计侧变更 → 版本化懒加载（通知 + compact 生效）
    skill_tools = build_ai_tools()
    if skill_tools:
        await ensure_source_version(db, "ai-skills", skill_tools, "设计侧能力")
    effective_skill_tools = await get_effective_definitions(db, world.config, "ai-skills", skill_tools)
    tools_for_world = [*WORLD_TOOLS, *effective_skill_tools]

    # ── 请求 DeepSeek（stream=true，透传 SSE）──
    api_key, api_base = await _resolve_world_credentials(db, world)
    model = cfg.get("model") or settings.default_chat_model
    thinking = bool(cfg.get("thinking", False))

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": cfg.get("temperature", 0.8),
        "top_p": cfg.get("top_p", 0.9),
        "max_tokens": 64000,
        "stream": True,
        "tools": tools_for_world,
        "stream_options": {"include_usage": True},
    }
    # v4 思考默认开启（正常行为）；显式开启时走 thinking 参数
    if thinking:
        payload["thinking"] = {"type": "enabled"}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # 本轮对话状态（温和去重 + 工作流记忆收集）
    turn_state: dict = {"executed": {}, "tools_done": []}

    # LLM 调用统一入口（工具轮/收尾共用）：与主系统一致走流式，规避非流式+tools+thinking 挂起
    async def _llm(messages: list, tools, round_no):
        from app.ai.llm import chat_completion
        _log_llm_request(world_id, turn_id, round_no, model, thinking, messages)
        return await chat_completion(
            messages=messages,
            model=model,
            api_base_url=api_base,
            api_key=api_key,
            temperature=cfg.get("temperature", 0.8),
            top_p=cfg.get("top_p", 0.9),
            thinking_enabled=thinking,
            stream=True,
            tools=tools,
        )

    full_content, full_reasoning = "", ""
    first_usage: dict | None = None  # 2.7：首轮 usage（流结束块捕获）
    tool_call_acc: dict[int, dict] = {}  # index → {id, name, arguments}
    try:
        _log_llm_request(world_id, turn_id, 0, model, thinking, messages)
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", f"{api_base}/v1/chat/completions", json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    err = (await resp.aread()).decode(errors="replace")[:300]
                    yield f"data: [ERROR]{_friendly_llm_error(f'{resp.status_code}: {err}')}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                buffer = ""
                done = False
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    buffer += chunk.decode("utf-8", errors="replace")
                    # 逐行处理 buffer（UTF-8 多字节被拆到两个 chunk 时，JSON 解析失败就把行放回）
                    while "\n" in buffer:
                        pos = buffer.find("\n")
                        line = buffer[:pos]
                        buffer = buffer[pos + 1:]
                        if not line.strip() or not line.startswith("data: "):
                            continue
                        p = line[6:]
                        if p == "[DONE]":
                            done = True
                            break
                        try:
                            j = json.loads(p)
                            choices = j.get("choices") or []
                            if not choices:
                                # 流结束的 usage 块（stream_options.include_usage）
                                if j.get("usage"):
                                    u = dict(j["usage"])
                                    pd = u.pop("prompt_tokens_details", None) or {}
                                    cd = u.pop("completion_tokens_details", None) or {}
                                    u["cached_tokens"] = pd.get("cached_tokens", 0)
                                    u["reasoning_tokens"] = cd.get("reasoning_tokens", 0)
                                    first_usage = u
                                continue
                            delta = choices[0].get("delta") or {}
                            t = delta.get("content")
                            # 出现工具调用后正文不再透传（模型可能把工具调用写成文本；最终以工具执行后的第二轮为准）
                            if t and not tool_call_acc:
                                full_content += t
                                yield f"data: {t.replace(chr(10), '{NL}')}\n\n"
                            rt = delta.get("reasoning_content")
                            if rt:
                                full_reasoning += rt
                                yield f"data: [REASONING]{rt.replace(chr(10), '{NL}')}\n\n"
                            # 工具调用（function calling 分片到达，按 index 累加）
                            tcs = delta.get("tool_calls")
                            if tcs:
                                for item in tcs:
                                    idx = item.get("index", 0)
                                    acc = tool_call_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                                    if item.get("id"):
                                        acc["id"] = item["id"]
                                    fn = item.get("function") or {}
                                    if fn.get("name"):
                                        acc["name"] = fn["name"]
                                    if fn.get("arguments"):
                                        acc["arguments"] += fn["arguments"]
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            buffer = line + "\n" + buffer
                            break
                    if done:
                        break
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 流式对话异常: {e}")
        yield f"data: [ERROR]{str(e)[:200]}\n\n"

    # 2.7：首轮用量落库（缓存命中统计）
    await _record_usage(db, world_id, turn_id, "0", model, first_usage, messages)

    # ── 工具调用：多轮循环（list → write → …，最多 5 轮防死循环）──
    # 每轮：执行工具 → [TOOL] 事件显示 + 注入 AI → 继续带 tools 调 LLM，直到模型不再调工具
    # 收尾保障：工具场景的 AI 回复落库放 finally——客户端中断（流 aclose）也强制收尾，保证历史闭环
    had_error = False
    turn_error = None
    if tool_call_acc:
        try:
            try:
                from app.ai.llm import chat_completion
                from app.services.world.world_tools import _execute_world_tool, _tool_result_summary
                # 第一轮过渡叙述 + 对应思考过程：给用户看（role=note，不进 AI 上下文）
                if full_content or full_reasoning:
                    db.add(WorldChatMessage(
                        world_id=world_id, user_id=None, role="note",
                        content=full_content or "（…）", reasoning=full_reasoning or None,
                    ))
                    await db.commit()
                # 第一轮正文重置（最终以收尾轮为准）
                full_content = ""
                # 首轮思考保留：后续轮有思考会覆盖；但工具轮 DeepSeek 常不输出 reasoning_content，
                # 若清空则落库无思考（刷新后「思考过程」丢失）——保留首轮思考作兜底
                # full_reasoning = ""
                # 第一轮流式里收集到的 tool_calls（重构为 API 格式；content 用空串而非 None，避免部分接口/思考模式异常）
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": acc["id"] or f"call_{idx}",
                            "type": "function",
                            "function": {"name": acc["name"], "arguments": acc["arguments"] or "{}"},
                        }
                        for idx, acc in sorted(tool_call_acc.items())
                    ],
                })
                # 工具循环上限：creator_config.max_tool_rounds（默认 50，设计页可改）
                max_rounds = int(cfg.get("max_tool_rounds") or DEFAULT_MAX_TOOL_ROUNDS)
                max_rounds = max(1, min(max_rounds, 200))
                final = ""
                for _r in range(max_rounds):
                    # 执行本轮所有工具调用
                    for idx, acc in sorted(tool_call_acc.items()):
                        result = await _execute_world_tool(db, world, acc["name"], acc["arguments"], turn_state)
                        summary = _tool_result_summary(acc["name"], result)
                        turn_state["tools_done"].append(summary)
                        messages.append({
                            "role": "tool",
                        "tool_call_id": acc["id"] or f"call_{idx}",
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                    db.add(WorldChatMessage(world_id=world_id, user_id=None, role="tool", content=summary))
                    yield f"data: [TOOL]{json.dumps({'name': acc['name'], 'success': bool(result.get('success')), 'summary': summary}, ensure_ascii=False)}\n\n"
                    await db.commit()

                    # 下一轮：继续带 tools，直到模型不再调用（同时捕获思考内容）
                    # 最后 3 轮：提醒尽快收尾总结
                    remaining = max_rounds - _r
                    if remaining <= 3:
                        messages.append({"role": "system", "content": f"⚠️ 你还有最后 {remaining} 轮工具调用机会，请尽快结束当前工作并给出总结！"})
                    resp = await _llm(messages, tools_for_world, _r + 1)
                    await _record_usage(db, world_id, turn_id, str(_r + 1), model, (resp or {}).get("usage"), messages)
                    content = (resp or {}).get("content") or ""
                    reasoning = (resp or {}).get("reasoning_content") or ""
                    tcs = (resp or {}).get("tool_calls")
                    if reasoning:
                        full_reasoning = reasoning
                        # 工具轮思考也流式显示给用户（刷新后仍可从历史看到）
                        yield f"data: [REASONING]{reasoning.replace(chr(10), '{NL}')}\n\n"
                    if not tcs:
                        # 收尾轮：正文作为最终回复（finally 落库 ai），不进 note
                        final = content
                        break
                    # 中间轮（还要继续调工具）：正文也流式展示 + 落库 note（历史可见、不进 AI 上下文）——
                    # 此前只覆盖 full_content 变量被吞掉，用户只能看到首轮和收尾轮两句话
                    if content or reasoning:
                        # 中间轮思考也要落库（对齐首轮 note：reasoning 字段），否则刷新后「工具调用的思考」丢失；
                        # 只有思考没正文时也用「（…）」占位，避免历史里空气泡
                        if content:
                            full_content = content
                        db.add(WorldChatMessage(
                            world_id=world_id, user_id=None, role="note",
                            content=(content or "（…）")[:4000],
                            reasoning=reasoning or None,
                        ))
                        await db.commit()
                        if content:
                            yield f"data: {content.replace(chr(10), '{NL}')}\n\n"
                    # 模型还要继续调工具：记录真实 tool_calls，进入下一轮
                    messages.append({"role": "assistant", "content": content or "", "tool_calls": tcs})
                    tool_call_acc = {
                        i: {"id": tc.get("id", ""), "name": tc["function"]["name"], "arguments": tc["function"].get("arguments") or ""}
                        for i, tc in enumerate(tcs)
                    }
                else:
                    final = ""  # 达到轮次上限：走强制收尾轮

                # 强制收尾轮：不带 tools，保证必有最终回复（含思考捕获）
                if not final:
                    _log_llm_request(world_id, turn_id, "final", model, thinking, messages)
                    resp_final = await _llm(messages, None, "final")
                    await _record_usage(db, world_id, turn_id, "final", model, (resp_final or {}).get("usage"), messages)
                    final = (resp_final or {}).get("content") or "（工具执行完成）"
                    fr = (resp_final or {}).get("reasoning_content") or ""
                    if fr:
                        full_reasoning = fr
                    full_content = final
                yield f"data: {final.replace(chr(10), '{NL}')}\n\n"
            except Exception as e:
                had_error = True
                turn_error = e
                logger.warning(f"🌐 世界 #{world_id} 工具执行/后续轮失败: {e}")
                yield f"data: [ERROR]{_friendly_llm_error(e)}\n\n"
        finally:
            # ── 落库 AI 回复（finally + shield：页面关闭/刷新导致任务取消，收尾照跑）──
            async def _closing():
                nonlocal full_content, full_reasoning  # 闭包内赋值：必须声明 nonlocal，否则 UnboundLocalError → 回复永不落库
                # 中断兜底：工具场景没生成最终回复 → 强制收尾轮；出错则落个闭环说明
                if tool_call_acc and not full_content:
                    if not had_error:
                        try:
                            from app.ai.llm import chat_completion
                            resp = await _llm(messages, None, "finalize")
                            full_content = (resp or {}).get("content") or "（工具执行完成）"
                            fr = (resp or {}).get("reasoning_content") or ""
                            if fr:
                                full_reasoning = fr
                        except Exception as e:
                            logger.warning(f"🌐 世界 #{world_id} 中断收尾失败: {e}")
                            full_content = full_content or "（工具执行中断）"
                    else:
                        full_content = _friendly_llm_error(turn_error) if turn_error else "（对话中断：工具执行出错，请重试或换个说法）"
                await _save_ai_reply(db, world, full_content, full_reasoning)
                # 工作流记忆：完整结束（有最终回复）→ 清除；中断 → 记录已做步骤，下次对话继续
                try:
                    cfg_all = dict(world.config or {})
                    if full_content and not full_content.startswith("（"):
                        cfg_all.pop("workflow_memory", None)
                    elif tool_call_acc:
                        cfg_all["workflow_memory"] = {
                            "interrupted_at": _now_local().isoformat(),
                            "tools_done": list(turn_state.get("tools_done", []))[-10:],
                        }
                    world.config = cfg_all
                    await db.commit()
                except Exception as e:
                    logger.warning(f"🌐 世界 #{world_id} 工作流记忆保存失败: {e}")

            try:
                # shield：即使任务被取消（页面刷新/关闭），收尾与落库也跑完
                await asyncio.shield(_closing())
            except Exception as e:
                logger.warning(f"🌐 世界 #{world_id} 回复落库失败: {e}")
    else:
        # ── 非工具场景：落库 AI 回复（完整内容 + 思考过程）──
        try:
            await _save_ai_reply(db, world, full_content, full_reasoning)
        except Exception as e:
            logger.warning(f"🌐 世界 #{world_id} 回复落库失败: {e}")

    # ── "你可以"建议：AI 调过 suggest_questions → 用它；否则轻量 LLM 兜底（用世界 key）；再不行预设 ──
    try:
        suggestions = list(turn_state.get("suggestions") or []) if turn_state else []
        if not suggestions:
            from app.services.world.world_suggestions import suggest_fallback
            suggestions = await suggest_fallback(db, world)
        if suggestions:
            try:
                from app.services.world.world_service import set_world_data
                await set_world_data(db, world_id, "ui.suggestions", suggestions[:5])
            except Exception:
                pass
            yield f"data: [SUGGEST]{json.dumps(suggestions[:5], ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 建议问题生成失败: {e}")

    yield "data: [DONE]\n\n"


# ═══════════════════════════════════════════════════════════════
# 序列化
# ═══════════════════════════════════════════════════════════════