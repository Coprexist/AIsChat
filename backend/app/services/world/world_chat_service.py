"""
世界 AI 对话服务（从 world_service 拆分）
- world_context_block：世界档案注入
- get_chat_history / _resolve_world_credentials / stream_world_chat：SSE 流式对话 + 工具多轮循环 + compact

跨模块依赖一律函数内懒导入（避免循环导入）。
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 实际请求日志（排查问题用）：每世界最近 10 条，落盘 data/world_llm_requests/{world_id}.jsonl
LLM_REQUEST_LOG_DIR = Path("data/world_llm_requests")
LLM_REQUEST_KEEP = 10


# ═══════════════════════════════════════════════════════════════
# 强注入提示词段（系统级不可改，随每次对话追加到用户可改的 system_prompt 之后）
# ═══════════════════════════════════════════════════════════════
# 2026-08-12 产品定：重要的（平台约定/能力边界/运行规范）从用户可改中提出来，
# 作为默认配置提示词的一部分——用户改的是角色人设，这些是平台强约束。
# 前端设置页只读展示（深灰），不提供编辑入口。

FORCED_PROMPT_SEGMENTS = [
    # 能力边界
    "\n【能力边界】平台里有两类 AI，能力不同，被问起时准确回答，不要凭猜测：\n- 你（世界 AI / 群视界机器人）= 造物主：平台工具 + 设计侧技能库（data/world_ai_skills/，全局共享），在世界之外设计世界，不用也不会拿到世界侧技能\n- 群里的 AI 成员（居民，平台 agent，如绑定了本世界的群 AI）= 绑定本世界后拥有：① 世界侧技能（data/worlds/{id}/skills/ 下颁布的 manifest+code.py，像调普通工具一样 function calling 直接调用）② world_command 文本命令工具（把命令发到群里，由世界程序 main.py handle() 解析执行，与用户共用同一套语法）——所以群 AI 不是「只会说话没有工具」，它有工具，能力取决于这个世界颁布了什么技能\n- 世界侧技能由你（或世界配置）颁布：在世界的 skills/ 目录放 manifest.json + code.py，绑定本世界的群 AI 就能直接工具调用；你没颁布技能时它们就没有世界侧工具（只剩 world_command 和平台默认工具）\n- 用户/群成员直接在群里发命令文本（如「收诗：xxx」「我去 2,3」）→ 群消息钩子 → 世界程序 main.py 解析执行——这是「人直接与世界交互」，与群 AI 调工具是两条并存的路径，别混为一谈",
    # 注意事项（通用行为准则，浓缩版）
    "\n【注意事项】遇到含糊指令主动提问确认，不瞎猜；调用工具后不要在回复里重复工具原始输出，直接说做了什么；创建文件后告知路径；给建议时简要阐述每个建议是什么（别只丢列表）；收尾最后一句写实质内容，不用「等你定方向」这类空话。",
    # 接口文档
    "\n【接口文档】平台接口文档按区分区（01 世界编号变量 / 02 WorldUI 桥 / 03 文件操作 / 04 积木体系 / 05 群聊 API / 06 页面与资源 / 07 懒通知与世界时间 / 08 错误与安全）。需要接口细节时用 view_api_doc 打开对应分区（工具描述里有各区介绍，先看介绍再决定开哪个，不要一次全读）。",
    # 记忆约定（精简：只保留结构化记忆一句，细节走文档）
    "\n【记忆约定】你的长期记忆（按世界隔离）一律用 manage_records 结构化存储（目录/子目录/字段三级），不用 store_memory/recall_memory（向量不可靠）；新会话开始时先 categories + 相关 get 检索再继续。",
    # UI 约定
    "\n【UI 约定】若你的页面实现了自己的侧边栏/菜单/导航，请调用 WorldUI.hideFloatingIcon() 隐藏平台悬浮图标（见接口文档），避免重复；未实现时不要调用。",
    # 群类型约定
    "\n【群类型约定】群类型 = slug（稳定 id）+ name（显示名）：绑定群/AI 存的是 slug，改名字只改 name、绝不能改 slug，否则已绑定的群/AI 会脱绑。世界未配置类型文件时系统自动提供「默认类型」（slug=default）兜底，群/AI 都可绑定。\n⚠️ 设计世界时必须写清楚：① 世界类型（群聊以什么类型进入）② AI 加入的类型（AI 以什么身份入驻）——关键剧本的角色可以直接创建以角色名或职位命名的类型（如 族长/骑士团长/商人），不只泛类型（冒险团/商会）。类型用 update_group_types 配置（slug 用英文小写稳定 id，上限可用 -1 = 无限，默认类型群/AI 都无限）。",
    # AI 侧 skill（按类型分层注入）
    "\n【AI 侧 skill】设计世界时不仅要写世界页面，还要考虑为 AI 居民写 skill：\n- skill 按类型分层注入——给不同类型的 AI 发不同的 skill（如 铁匠类型 → forge_weapon，商人类型 → trade）；skill 声明 types 字段（省略或 [*] = 所有类型通用，指定列表 = 仅这些类型可用）\n- 通过群聊进入世界的实体默认落到该群绑定的 AI 类型；AI 直接绑定世界 → 落到自己绑定的类型\n- skill 放 data/worlds/{id}/skills/ 下（manifest.json + code.py），居民像调普通工具一样 function calling 直接调用；你（造物主）是 skill 的颁布者，别忘了为每个类型设计配套能力\n- ⚠️ skill 设计准则（站在使用方角度）：可操作性（参数清晰、报错可读）、简便性（一次调用完成一件事）、效果最大化（一个完整意图做进一次调用）——AI 用最少次调用完成用户意图 = 好 skill；发布前模拟一遍 AI 调用路径，要调好几步才能办成事就合并",
    # 不同场景进入世界的 index 响应
    "\n【入口场景响应】依据进入场景，为同一个世界做不同的 index 响应：从群聊进入 / 从私信进入 / AI 直接进入，前端首页可以不同（如从私信进入 = 直接打开世界中与 AI 的对话的前端响应，而不是完整世界主页）。入口场景由平台注入变量（WORLD_ID / GROUP_ID / 入口类型），世界代码据此分发。",
    # 侧边栏约定
    "\n【侧边栏约定】世界侧边栏/菜单必须保留平台基础菜单（首页/聊天/世界列表/设置四个目的地，可折叠成可展开的「平台」项但绝不能缺失，否则用户无法回到主应用）；平台项跳主应用（window.parent），世界自定义项跳世界内页面。组名/项名/样式可自行调整，推荐直接应用 platform-sidebar 积木。⚠️ 手机版适配：自定义侧边栏必须适配手机屏幕——窄屏（<768px）默认收拢/隐藏，提供展开入口（如悬浮按钮/顶部按钮），绝不能默认展开占满屏幕；至少要实现可收拢功能，移动端优先。",
    # 路径约定
    "\n【路径约定】页面内资源（css/js/图片）一律用相对路径引用（支持跨文件夹 ../），不要用 / 开头的绝对路径（会 404）；数据请求用 /world/${WORLD_ID}/ 变量路径。",
    # 文件查询（2026-08-13 新增：对齐 OpenClaw read 工具设计——先定位再分段读，不整文件全读）
    "\n【文件查询】看文件不要整文件全读浪费上下文：先 file_grep 按关键词/正则定位（返回命中行+行号），再用 file_read 的 offset/limit 按行分页读对应段落（返回 total_lines/start_line/end_line/truncated）。改文件用 file_edit 精确替换，编辑前只读目标区域即可。",
    # 编号约定
    "\n【编号约定】不要硬编码任何编号（世界号/群号/用户 id）——世界编号 window.WORLD_ID、入口群聊编号 window.GROUP_ID 由平台注入变量，代码里一律用变量；群聊类工具默认作用于本世界绑定的群，直接说目的即可，无需也不应指定群号；成员 id 一律以 list_group_members 的返回为准。",
    # 设计美学（占一部分即可，控制 token）
    "\n【设计美学】世界是给人看的可视化界面，注重观感：配色协调有主色调、层级清晰（标题/正文/按钮主次分明）、留白适当不拥挤；移动端适配（窄屏可用）；动效克制、有加载/空状态；第一次进页面知道怎么玩（引导/提示）。丑的界面用户不玩。",
    # 世界运行规范
    "\n【世界运行规范】\n- 沙箱环境：世界代码（main.py / 沙箱脚本）的工作目录 = 世界文件夹本体，可直接读写世界文件夹里的文件（含 JSON 数据文件）；环境变量注入 WORLD_ID / WORLD_API_TOKEN / WORLD_API_BASE / WORLD_DIR（token 只用于受控 API，绝不外泄/打印/写进页面）\n- 数据规范（代码/数据分离）：\n  1) 结构化/操作数据（状态、计数、记录）→ 用受控 API 的世界数据库：GET/PUT/DELETE /data/{key}（key 用命名空间如 player.lihua / poems / quest.1，value 任意 JSON）——世界代码与页面三方共用同一份数据\n  2) 静态文字类（设定、文档、素材文本）→ 放世界文件夹 content/ 子目录（可自由建层级；content/ 是世界产物区，发布世界不打包，下载数据可选包含）\n  3) 代码（网页/脚本）放世界文件夹根目录或自有目录\n- 页面读数据：经世界代码发布状态（POST /state → 页面 SSE）或世界代码生成页面时内嵌；页面不要直连数据库\n【内容提炼与动态加载】（产品 2026-08-12 定）剧情/按钮列表/大量设定等**内容不准写死在渲染中**：能提炼为文档/列表/数据文件的提炼掉，页面动态加载（fetch/import）；不固定数目；图片/音频等资源同理；同构多实例（NPC/卡牌/角色）**每个实例一个文件**（如 npcs/lihua.json）。改内容/新增实例都不碰渲染代码。\n【结构约定】注意维护和优化世界的项目结构：文件按职责组织（页面/样式/脚本/数据分开），定期清理无用文件，代码保持整洁可维护——世界会长期演进，结构混乱会让后续修改越来越难。⚠️ **适时拆分文件**：文件一旦变大（或你觉得对维护不利）就拆分——拆成职责单一的小文件/模块，别让单个文件越来越臃肿；拆分的判断标准：这个文件继续变大会不会让后续修改变难？会就拆。",
]


def build_forced_prompt() -> str:
    """强注入提示词全文（只读展示用，与对话组装完全一致）"""
    return "".join(FORCED_PROMPT_SEGMENTS)


def _mark(value: str) -> str:
    """重要记忆标记（软锚定）：value 以 ⭐/❗ 开头 → 名字加对应前缀。

    产品定：重要度覆盖整个级的记忆可直接写在该级（value 前缀标记），
    地图生成时把标记提到名字上，产生 Attention 特征峰值。
    """
    v = (value or "").strip()
    if v.startswith("❗"):
        return "❗"
    if v.startswith("⭐"):
        return "⭐"
    return ""


async def build_memory_map(db: AsyncSession, world_id: int) -> str | None:
    """记忆地图（缩进树）：clear/new/compact 后注入，让 AI 知道有什么记忆存档。

    格式（省 token + 软锚定）：
    【本世界记忆】\nproject/\n  图鉴页面/\n    进度\n  ⭐当前计划\nuser/\n  ⭐偏好\n详细内容用 manage_records get 按需取。

    规则：只注入有内容的路径（空目录不出现）；重要记忆 ⭐ 前缀（软锚定，注意力倾斜）；
    硬约束 ❗ 前缀；详细 value 不注入（第 4 级按需 get）。
    """
    from app.models.world import WorldStructuredRecord
    from sqlalchemy import select as _sel

    rows = (await db.execute(
        _sel(WorldStructuredRecord).where(
            WorldStructuredRecord.world_id == world_id
        ).order_by(WorldStructuredRecord.category, WorldStructuredRecord.sub_key, WorldStructuredRecord.field)
    )).scalars().all()
    if not rows:
        return None

    # 分组：category → {sub_key: {field: value}}，sub_key 为空串时挂 category 下
    cats: dict[str, dict[str, dict[str, str]]] = {}
    for r in rows:
        cats.setdefault(r.category, {}).setdefault(r.sub_key, {})[r.field] = r.value
    lines = ["【本世界记忆】"]
    for cat in sorted(cats):
        subs = cats[cat]
        if not subs or (len(subs) == 1 and "" in subs):
            # 只有无 sub_key 的记录：直接列出 field（带重要标记的加前缀）
            fields = subs.get("", {})
            if fields:
                lines.append(f"{cat}/")
                for f in sorted(fields):
                    lines.append(f"  {_mark(fields[f])}{f}")
            continue
        lines.append(f"{cat}/")
        for sk in sorted(subs):
            if sk == "":
                continue
            fields = {f: v for f, v in subs[sk].items() if f}
            if fields:
                lines.append(f"  {sk}/")
                for f in sorted(fields):
                    lines.append(f"    {_mark(fields[f])}{f}")
            else:
                lines.append(f"  {sk}")
    lines.append("⭐=重要记忆 ❗=硬约束（详细内容用 manage_records get 按需取）")
    return "\n".join(lines)




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


def session_key(world) -> str:
    """当前会话 key（world.config.current_session；无 = 默认会话 'default'）"""
    return (world.config or {}).get("current_session") or "default"


def session_id_for_db(world) -> str | None:
    """落库用的 session_id：默认会话存 NULL（兼容旧数据），/new 会话存 uuid"""
    return (world.config or {}).get("current_session") or None

def session_settings(world, global_defaults: dict | None = None) -> dict:
    """会话生命周期配置：世界配置（设计页可改）> 全局默认（管理员 system_settings）> 代码默认
    auto_new_enabled / auto_new_time("04:00") / compact_idle_hours(18, 0=关) / retention_days(90, 0=关)"""
    g = global_defaults or {}
    cfg = (world.config or {}).get("session_settings") or {}
    return {
        "auto_new_enabled": bool(cfg.get("auto_new_enabled", g.get("auto_new_enabled", True))),
        "auto_new_time": str(cfg.get("auto_new_time") or g.get("auto_new_time") or "04:00"),
        "compact_idle_hours": int(cfg.get("compact_idle_hours") or g.get("compact_idle_hours") or 18),
        "retention_days": int(cfg.get("retention_days") or g.get("retention_days") or 90),
    }

def new_session_id(world) -> str:
    """生成会话 id：w{wid}:{type}:{uuid12}；与已存在会话碰撞则重试（uuid 防碰撞）"""
    import uuid as _uuid
    sessions = ((world.config or {}).get("sessions") or {})
    typ = "m"  # 分类：m=设计页主对话（预留 g{群id}=群入口）
    while True:
        sid = f"w{world.id}:{typ}:{_uuid.uuid4().hex[:12]}"
        if sid not in sessions:
            return sid


def touch_session(world) -> None:
    """更新当前会话元信息（last_active_at）"""
    from datetime import datetime, timezone
    cfg = dict(world.config or {})
    sessions = dict(cfg.get("sessions") or {})
    key = (cfg.get("current_session") or "default")
    meta = dict(sessions.get(key) or {})
    meta["last_active_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    sessions[key] = meta
    cfg["sessions"] = sessions
    world.config = cfg


async def ensure_session_lifecycle(db, world) -> dict:
    """懒加载会话生命周期检查（GET/POST /chat 入口调用，无定时器）：

    - auto_new：跨过每日 auto_new_time（默认 04:00）→ 自动开新会话（已 new 过不重复）

    - retention：未收藏会话超过保留天数 → 删除（id+消息+列表）

    - idle_compact 不在此处（放 stream_world_chat 开头，需 LLM 压缩）

    返回 {auto_newed: bool, cleaned: int}"""
    from datetime import datetime, timezone, timedelta
    from zoneinfo import ZoneInfo
    from app.models.world import WorldChatMessage
    from sqlalchemy import delete as sa_delete

    # auto_new 按用户时区（display_timezone）算；retention 用 UTC（时长比较与基准无关）
    from app.config import settings as _settings
    tz = ZoneInfo(_settings.display_timezone)
    local_now = datetime.now(tz)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cfg = dict(world.config or {})
    st = session_settings(world)
    result = {"auto_newed": False, "cleaned": 0}

    # ── auto_new：跨过配置时间点（用户时区）→ 开新会话 ──
    if st["auto_new_enabled"]:
        try:
            hh, mm = str(st["auto_new_time"]).split(":")[:2]
            today_cutoff = local_now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except Exception:
            today_cutoff = local_now.replace(hour=4, minute=0, second=0, microsecond=0)
        # 最近一次应 new 的时间点：现在未到今天的配置点（凌晨）→ 取昨天的；否则取今天的
        # ⚠️ 若直接取「今天」的配置点，凌晨时它在未来 → last 永远 < cutoff → 每次访问都开新会话（会话爆炸）
        cutoff = today_cutoff - timedelta(days=1) if local_now < today_cutoff else today_cutoff
        last = cfg.get("last_auto_new_at")
        if last is None or last < cutoff.isoformat():
            # 跨过时间点且还没 new 过 → 开新会话（旧会话保存，可切回）
            cfg["current_session"] = new_session_id(world)
            sessions = dict(cfg.get("sessions") or {})
            sessions[cfg["current_session"]] = {
                "created_at": local_now.isoformat(),
                "last_active_at": local_now.isoformat(),
            }
            cfg["sessions"] = sessions
            cfg["last_auto_new_at"] = local_now.isoformat()
            world.config = cfg
            await db.commit()
            result["auto_newed"] = True

    # ── retention：清理过期未收藏会话 ──
    days = st["retention_days"]
    if days > 0:
        sessions = dict(cfg.get("sessions") or {})
        expired = []
        for sid, meta in sessions.items():
            if sid == (cfg.get("current_session") or "default"):
                continue  # 当前会话不清理
            if (meta or {}).get("pinned_by"):
                continue  # 收藏的会话不清理
            la = (meta or {}).get("last_active_at")
            if not la:
                continue
            try:
                la_dt = datetime.fromisoformat(la)
            except Exception:
                continue
            if now_utc - la_dt > timedelta(days=days):
                expired.append(sid)
        if expired:
            for sid in expired:
                q = sa_delete(WorldChatMessage).where(
                    WorldChatMessage.world_id == world.id,
                    WorldChatMessage.session_id == sid,
                )
                await db.execute(q)
                sessions.pop(sid, None)
            cfg["sessions"] = sessions
            world.config = cfg
            await db.commit()
            result["cleaned"] = len(expired)
    return result


async def get_chat_history(db: AsyncSession, world_id: int, limit: int = 30, before_id: int | None = None, session_id: str | None = None) -> list[dict]:
    """世界 AI 对话历史（最近 limit 条；before_id 传最旧 id 可翻更早；session_id 过滤会话）"""
    from app.models.world import WorldChatMessage

    query = select(WorldChatMessage).where(WorldChatMessage.world_id == world_id)
    if session_id is None:
        query = query.where(WorldChatMessage.session_id.is_(None))
    else:
        query = query.where(WorldChatMessage.session_id == session_id)
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


async def _save_ai_reply(db: AsyncSession, world, content: str, reasoning: str, session_id: str | None = None) -> None:
    """落库 AI 回复（含思考过程）；内容为空则跳过"""
    from app.services.world.world_service import _now
    from app.models.world import WorldChatMessage
    if not content:
        return
    db.add(WorldChatMessage(
        world_id=world.id, user_id=None, role="ai",
        content=content, reasoning=reasoning or None,
        session_id=session_id,
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


async def _stream_llm_once(
    world_id: int, turn_id: str, round_no: int,
    model: str, thinking: bool, api_base: str, api_key: str | None,
    messages: list, tools, cfg: dict,
    out: dict | None = None,
):
    """单次 LLM 流式调用：逐 chunk yield SSE 事件（正文/思考），并收集完整结果。

    2026-08-13 修复：工具轮（round 2+）之前复用 chat_completion（聚合式）——
    正文/思考要等整次调用结束才一次性出现，没有流式效果。
    提取首轮的手写流式解析为公共生成器，工具轮也走它。

    用法：
        out = {}
        async for event in _stream_llm_once(..., out=out):
            yield event          # 外层再转发（或丢弃）
        # 之后 out 里是完整 content/reasoning_content/tool_calls/usage
    """
    import httpx
    _log_llm_request(world_id, turn_id, round_no, model, thinking, messages)
    # 构造 payload（与首轮一致：stream + include_usage）
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": cfg.get("temperature", 0.8),
        "top_p": cfg.get("top_p", 0.9),
    }
    if thinking:
        payload["thinking"] = {"type": "enabled"}
    if tools:
        payload["tools"] = tools
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}

    result: dict = {"content": "", "reasoning_content": "", "tool_calls": None, "usage": None}
    if out is not None:
        out.clear()
        out.update(result)
    tool_call_acc: dict = {}
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", f"{api_base}/v1/chat/completions", json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    err = (await resp.aread()).decode(errors="replace")[:300]
                    yield f"data: [ERROR]{_friendly_llm_error(f'{resp.status_code}: {err}')}\n\n"
                    return
                buffer = ""
                done = False
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    buffer += chunk.decode("utf-8", errors="replace")
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
                                if j.get("usage"):
                                    result["usage"] = j["usage"]
                                continue
                            delta = choices[0].get("delta") or {}
                            t = delta.get("content")
                            if t:
                                result["content"] += t
                                yield f"data: {t.replace(chr(10), '{NL}')}\n\n"
                            rt = delta.get("reasoning_content")
                            if rt:
                                result["reasoning_content"] += rt
                                yield f"data: [REASONING]{rt.replace(chr(10), '{NL}')}\n\n"
                            tcs = delta.get("tool_calls")
                            if tcs:
                                for item in tcs:
                                    cid = item.get("id") or ""
                                    key = cid if cid else f"idx_{item.get('index', 0)}"
                                    acc = tool_call_acc.setdefault(key, {"id": "", "name": "", "arguments": "", "index": item.get("index", 0)})
                                    if cid:
                                        acc["id"] = cid
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
        return
    if tool_call_acc:
        result["tool_calls"] = [
            {
                "id": acc["id"] or f"call_{key}",
                "type": "function",
                "function": {"name": acc["name"], "arguments": acc["arguments"] or "{}"},
            }
            for key, acc in sorted(tool_call_acc.items())
        ]
    if out is not None:
        out.clear()
        out.update(result)
    yield f"data: [DONE]\n\n"


async def _inject_pending_user_messages(
    db: AsyncSession, world_id: int, messages: list, sid_db: str | None,
):
    """把排队中的普通消息注入当前工具轮（每轮 LLM 调用前调用）。

    产品定（2026-08-13）：AI 工具轮进行中用户发的普通消息不打断循环，
    在下一轮 LLM 调用前自然注入（drain → 落库 → 发事件 → 拼进上下文）。
    协议：先 [INSERTED]{count} 信号（清前端排队弹窗，不计入历史），
    再逐条 [INSERT]{msg_id, content}（已落库、记入历史，前端画真实气泡）。
    无排队消息时生成器直接结束（零开销）。
    """
    from app.models.world import WorldChatMessage
    from app.services.world.world_turn import get_world_worker
    insert_items = await get_world_worker(world_id).drain_inserts()
    if not insert_items:
        return
    # 信号先行：前端按 FIFO 从排队弹窗移除 count 条
    total = sum(len(_it["messages"]) for _it in insert_items)
    yield f"data: [INSERTED]{json.dumps({'count': total}, ensure_ascii=False)}\n\n"
    # 逐条落库 + 发事件 + 拼进上下文（AI 下一轮思考可见）
    for _it in insert_items:
        for _m in _it["messages"]:
            _m_text = str(_m).strip()
            if not _m_text:
                continue
            _wm = WorldChatMessage(
                world_id=world_id, user_id=_it["user_id"],
                role="user", content=_m_text, session_id=sid_db,
            )
            db.add(_wm)
            await db.flush()
            yield f"data: [INSERT]{json.dumps({'msg_id': _wm.id, 'content': _m_text}, ensure_ascii=False)}\n\n"
            messages.append({"role": "user", "content": _m_text})
    await db.commit()


async def _execute_tool_round(
    db: AsyncSession, world, world_id: int, tool_call_acc: dict,
    messages: list, turn_state: dict, sid_db: str | None,
):
    """执行本轮所有工具调用：执行 → 摘要 → 注入上下文 → 落库 → 状态事件。

    工具轮循环内的单轮执行单元（2026-08-13 拆分；同日升级为多状态事件）：
    - 执行前 yield [TOOL_UPDATE]{tool_id, status:running}（前端显示"正在执行 XX"）
    - 工具内部可 yield 进度（on_progress → status:update，如 运行代码/编译/执行中）
    - 执行后 yield 同 id [TOOL_UPDATE]{status:done}（前端按 id 原地更新气泡）
    - 落库：同 tool_id 更新最后一条（历史只留最终态）
    """
    import json
    import uuid
    from app.models.world import WorldChatMessage
    from app.services.world.world_tools import _execute_world_tool, _tool_result_summary
    for idx, acc in sorted(tool_call_acc.items()):
        tool_id = f"t_{uuid.uuid4().hex[:8]}"
        args_summary = _args_summary(acc.get("arguments") or "")
        # ① 执行前：running 状态（前端创建/更新气泡：正在执行 XX）
        yield f"data: [TOOL_UPDATE]{json.dumps({'tool_id': tool_id, 'status': 'running', 'name': acc['name'], 'args_summary': args_summary}, ensure_ascii=False)}\n\n"
        # ② 工具内部进度事件（耗时工具如 run_world_code 分阶段 yield update）
        progress_events: list[str] = []
        async def _on_progress(note: str) -> None:
            progress_events.append(note)
        try:
            result = await _execute_world_tool(
                db, world, acc["name"], acc["arguments"], turn_state,
                on_progress=_on_progress,
            )
        except TypeError:
            # 兼容：工具签名未支持 on_progress
            result = await _execute_world_tool(db, world, acc["name"], acc["arguments"], turn_state)
        summary = _tool_result_summary(acc["name"], result)
        turn_state["tools_done"].append(summary)
        messages.append({
            "role": "tool",
            "tool_call_id": acc["id"] or f"call_{idx}",
            "content": json.dumps(result, ensure_ascii=False),
        })
        # ③ 进度事件转发（同 tool_id，status=update）
        for note in progress_events:
            yield f"data: [TOOL_UPDATE]{json.dumps({'tool_id': tool_id, 'status': 'update', 'name': acc['name'], 'summary': note}, ensure_ascii=False)}\n\n"
        # ④ 执行后：done（同 tool_id，前端原地更新）
        yield f"data: [TOOL_UPDATE]{json.dumps({'tool_id': tool_id, 'status': 'done', 'name': acc['name'], 'success': bool(result.get('success')), 'summary': summary}, ensure_ascii=False)}\n\n"
        # ⑤ 落库：同 tool_id 更新最后一条（历史只留最终态）；无 tool_id 旧字段则新增
        existing = (await db.execute(
            select(WorldChatMessage).where(
                WorldChatMessage.world_id == world_id,
                WorldChatMessage.tool_id == tool_id,
            ).order_by(WorldChatMessage.id.desc()).limit(1)
        )).scalar_one_or_none()
        if existing is not None:
            existing.content = summary
        else:
            db.add(WorldChatMessage(
                world_id=world_id, user_id=None, role="tool",
                content=summary, session_id=sid_db, tool_id=tool_id,
            ))
        await db.commit()


def _args_summary(arguments: str) -> str:
    """工具参数摘要（展示用）：取 path/code/event 等关键字段，避免全量刷屏"""
    import json
    try:
        args = json.loads(arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(args, dict):
        return ""
    for key in ("path", "code", "event", "name", "query"):
        v = args.get(key)
        if v:
            s = str(v).strip()
            return s[:80] + ("…" if len(s) > 80 else "")
    return ""


async def _prepare_world_chat(
    db: AsyncSession, world_id: int, user_id: int, message: str | list[str],
) -> dict | None:
    """世界 AI 对话的准备阶段：世界加载/凭证/前缀/历史/消息列表/命令识别。

    返回上下文 dict（供 stream_world_chat 编排）；世界不存在返回 None。
    斜杠命令不在这里执行（需 yield SSE），只识别 cmd_text 供主编排处理。
    """
    import httpx  # noqa: F401（_stream_llm_once 用，保留模块级导入习惯）
    from app.config import settings
    from app.models.world import World

    world = await db.get(World, world_id)
    if world is None:
        return None

    # 对话 = 活跃信号：唤醒 + 离线时间补偿（让 AI 看到的世界时间准确）
    from app.services.world.world_service import apply_time_compensation
    apply_time_compensation(world)
    await db.commit()

    # ── 会话空闲自动 compact（懒加载：发消息时检查；空闲超时先压缩再继续，趁缓存最大化利用）──
    try:
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        st = session_settings(world)
        hours = st["compact_idle_hours"]
        if hours > 0:
            _cfg = world.config or {}
            _key = _cfg.get("current_session") or "default"
            _meta = (_cfg.get("sessions") or {}).get(_key) or {}
            _la = _meta.get("last_active_at")
            if _la:
                _la_dt = _dt.fromisoformat(_la)
                _now = _dt.now(_tz.utc).replace(tzinfo=None)
                if _now - _la_dt > _td(hours=hours):
                    from app.services.world.world_tools import _do_execute
                    await _do_execute(db, world, "compact_context", "{}")
                    touch_session(world)
                    await db.commit()
                    logger.info(f"🌐 世界 #{world_id} 会话 {_key} 空闲 {hours}h 已自动压缩")
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 空闲自动压缩失败: {e}")

    from app.services.world.world_service import ensure_world_ai, take_pending_notices, CREATOR_DEFAULT_CONFIG
    wai = await ensure_world_ai(db, world_id)
    cfg = {
        "name": wai.name, "system_prompt": wai.system_prompt, "model": wai.model,
        "temperature": wai.temperature, "top_p": wai.top_p, "thinking": wai.thinking,
        "max_tool_rounds": wai.max_tool_rounds,
    }

    # ── 前缀文本版本化（2026-08-12 产品定：所有进前缀的内容必须保证缓存命中）──
    # 三个文本源：用户可改提示词（每世界）/ 强注入段（全局）/ 昵称（每世界）
    # 变更 → 写新版本 + 尾部 changelog 告知，不碰前缀；compact / clear 解锁后生效
    from app.services.capability_versioning import (
        ensure_text_source_version, get_effective_text,
    )
    user_prompt = cfg.get("system_prompt") or CREATOR_DEFAULT_CONFIG["system_prompt"]
    forced_prompt = build_forced_prompt()
    creator_name = cfg.get("name") or "群视界机器人"
    await ensure_text_source_version(db, f"world-prompt-{world_id}", user_prompt, "世界AI提示词")
    await ensure_text_source_version(db, "forced-prompt", forced_prompt, "强注入段")
    await ensure_text_source_version(db, f"world-name-{world_id}", creator_name, "世界AI昵称")
    eff_user_prompt = await get_effective_text(db, world.config, f"world-prompt-{world_id}", user_prompt)
    eff_forced_prompt = await get_effective_text(db, world.config, "forced-prompt", forced_prompt)
    eff_name = await get_effective_text(db, world.config, f"world-name-{world_id}", creator_name)

    # ── 组装消息：静态 system 前缀保持稳定（prompt cache 友好）──
    system_prompt = world_context_block(world) + "\n\n" + eff_user_prompt
    system_prompt += eff_forced_prompt  # 强注入段：平台强约束，用户不可改
    system_prompt += f"\n【名字】你的名字是「{eff_name}」，对外标识 world-{world_id}。"

    notices = await take_pending_notices(db, world_id)
    notice_lines = "\n".join(
        f"- {n['file']}（{n.get('location', '')}）: {n.get('summary', '')}"
        for n in notices
    ) if notices else ""

    # ── 上下文：有压缩摘要则 摘要+最近 N 条，否则最近 30 条；接近上限时提示 AI 调 compact ──
    sid_db = session_id_for_db(world)  # 落库用 session_id（默认会话 None）
    summaries = (world.config or {}).get("chat_summaries") or {}
    summary = summaries.get(session_key(world)) or ""
    # 未完成工作流记忆：上次对话中断（无最终回复）→ 本次继续，不重做
    wm = (world.config or {}).get("workflow_memory")
    if wm and wm.get("tools_done"):
        done = "、".join(wm["tools_done"][-8:])
        system_prompt += (
            "\n\n【未完成工作流】上次对话在 " + str(wm.get("interrupted_at", ""))[:19] +
            " 中断，已执行：" + done + "。请继续完成剩余工作并给出总结，不要重复已完成的步骤。"
        )
    history = await get_chat_history(db, world_id, WORLD_CHAT_KEEP_LAST if summary else CHAT_HISTORY_LIMIT, session_id=sid_db)
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
    # 记忆地图：只在上下文起点（无摘要 = 新会话/clear 后）注入
    if not summary:
        try:
            memory_map = await build_memory_map(db, world_id)
            if memory_map:
                messages.append({"role": "system", "content": memory_map})
        except Exception:
            pass
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

    # 能力变更通知（懒加载：增量 changelog 追加尾部，known 更新与注入同轮）
    try:
        from app.services.capability_versioning import build_change_notice
        notice = await build_change_notice(db, world.config, [
            "ai-skills",
            f"world-prompt-{world_id}",
            "forced-prompt",
            f"world-name-{world_id}",
        ])
        if notice:
            messages.append({"role": "system", "content": notice})
            await db.commit()
    except Exception:
        pass

    # 落库用户消息（批量 = 排队消息一起发，逐条气泡；先提交，即使流失败也不丢）
    from app.models.world import WorldChatMessage
    for m in msg_list:
        db.add(WorldChatMessage(world_id=world_id, user_id=user_id, role="user", content=m, session_id=sid_db))
    try:
        await db.commit()
    except Exception as e:
        logger.warning(f"🌐 世界 #{world_id} 用户消息落库失败: {e}")

    # 世界 AI（造物主）工具 = 平台内置 + 设计侧 skills（world_ai_skills/ 全局库；世界侧居民能力不注入）
    from app.services.world.world_tools import WORLD_TOOLS
    from app.services.world.world_skill_runtime import build_ai_tools
    from app.services.capability_versioning import ensure_source_version, get_effective_definitions
    skill_tools = build_ai_tools()
    if skill_tools:
        await ensure_source_version(db, "ai-skills", skill_tools, "设计侧能力")
    effective_skill_tools = await get_effective_definitions(db, world.config, "ai-skills", skill_tools)
    tools_for_world = [*WORLD_TOOLS, *effective_skill_tools]

    # 凭证 + 模型
    api_key, api_base = await _resolve_world_credentials(db, world)
    model = cfg.get("model") or settings.default_chat_model
    thinking = bool(cfg.get("thinking", False))

    cmd_text = msg_list[0] if len(msg_list) == 1 else ""
    return {
        "world": world, "wai": wai, "cfg": cfg,
        "api_key": api_key, "api_base": api_base, "model": model, "thinking": thinking,
        "tools_for_world": tools_for_world, "messages": messages, "msg_list": msg_list,
        "sid_db": sid_db, "cmd_text": cmd_text,
    }


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

    编排：准备（_prepare_world_chat）→ 命令/首轮流式 → 工具轮（_run_tool_loop）→ 建议。
    """
    import json

    import httpx  # 首轮流式（client.stream）用
    from app.models.world import WorldChatMessage

    ctx = await _prepare_world_chat(db, world_id, user_id, message)
    if ctx is None:
        yield "data: [ERROR]世界不存在\n\n"
        yield "data: [DONE]\n\n"
        return
    world = ctx["world"]
    cfg = ctx["cfg"]
    api_key, api_base = ctx["api_key"], ctx["api_base"]
    model, thinking = ctx["model"], ctx["thinking"]
    tools_for_world = ctx["tools_for_world"]
    messages = ctx["messages"]
    msg_list = ctx["msg_list"]
    sid_db = ctx["sid_db"]
    cmd_text = ctx["cmd_text"]

    # ── 用户斜杠命令（不走 LLM，仅单条）    # ── 用户斜杠命令（不走 LLM，仅单条）：命令注册表在 world_chat_commands（/clear /compact /new /sessions /use /pin /unpin）──
    cmd_text = msg_list[0] if len(msg_list) == 1 else ""
    if cmd_text.startswith("/"):
        try:
            from app.services.world.world_chat_commands import run_slash_command
            note = await run_slash_command(db, world, cmd_text, user_id=user_id)
        except Exception as e:
            logger.warning(f"🌐 世界 #{world_id} 命令执行失败: {e}")
            yield f"data: [ERROR]命令执行失败: {e}\n\n"
            yield "data: [DONE]\n\n"
            return
        if note is not None:
            db.add(WorldChatMessage(world_id=world_id, user_id=None, role="tool", content=note, session_id=sid_db))
            await db.commit()
            yield f"data: [TOOL_UPDATE]{json.dumps({'tool_id': f't_{uuid.uuid4().hex[:8]}', 'status': 'done', 'name': cmd_text.lstrip('/'), 'success': True, 'summary': note}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        # note 为 None = 非注册命令：继续走 LLM（未知斜杠当普通消息处理）

    # ── 请求 DeepSeek（stream=true，透传 SSE）──
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
                            # 工具调用（function calling 分片到达）
                            # ⚠️ 并行调用修复（2026-08-13）：DeepSeek 并行 tool_calls 的 index 可能重复（都=0），
                            # 按 index 累加会把两个调用的 arguments 拼串 → JSON 损坏/字段丢失。
                            # 优先用 id（call_00/call_01 唯一）区分，id 缺失才退回 index。
                            tcs = delta.get("tool_calls")
                            if tcs:
                                for item in tcs:
                                    cid = item.get("id") or ""
                                    key = cid if cid else f"idx_{item.get('index', 0)}"
                                    acc = tool_call_acc.setdefault(key, {"id": "", "name": "", "arguments": "", "index": item.get("index", 0)})
                                    if cid:
                                        acc["id"] = cid
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
                # 2026-08-13：正文/思考独立展示——无正文存空串（不占位），思考独立渲染
                if full_content or full_reasoning:
                    db.add(WorldChatMessage(
                        world_id=world_id, user_id=None, role="note",
                        content=full_content or "", reasoning=full_reasoning or None,
                        session_id=sid_db,
                    ))
                    await db.commit()
                # 第一轮正文重置（最终以收尾轮为准）
                full_content = ""
                # 首轮思考保留：后续轮有思考会覆盖；但工具轮 DeepSeek 常不输出 reasoning_content，
                # 若清空则落库无思考（刷新后「思考过程」丢失）——保留首轮思考作兜底
                # full_reasoning = ""
                # 第一轮流式里收集到的 tool_calls（重构为 API 格式；content 用空串而非 None，避免部分接口/思考模式异常）
                # ⚠️ DeepSeek thinking 模式：首轮 assistant 也要回传 reasoning_content（2026-08-13 修复）
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
                    **({"reasoning_content": full_reasoning} if full_reasoning else {}),
                })
                # 工具循环上限：creator_config.max_tool_rounds（默认 50，设计页可改）
                max_rounds = int(cfg.get("max_tool_rounds") or DEFAULT_MAX_TOOL_ROUNDS)
                max_rounds = max(1, min(max_rounds, 200))
                final = ""
                for _r in range(max_rounds):
                    # 排队消息注入（无则零开销）：AI 工具轮进行中用户发的普通消息在下一轮自然拼进上下文
                    try:
                        async for event in _inject_pending_user_messages(db, world_id, messages, sid_db):
                            yield event
                    except Exception as e:
                        logger.warning(f"🌐 世界 #{world_id} 排队消息注入失败（非致命）: {e}")
                    # 执行本轮所有工具调用（执行→注入→落库→[TOOL] 事件）
                    async for event in _execute_tool_round(db, world, world_id, tool_call_acc, messages, turn_state, sid_db):
                        yield event

                    # 下一轮：继续带 tools，直到模型不再调用（同时捕获思考内容）
                    # 最后 3 轮：提醒尽快收尾总结
                    remaining = max_rounds - _r
                    if remaining <= 3:
                        messages.append({"role": "system", "content": f"⚠️ 你还有最后 {remaining} 轮工具调用机会，请尽快结束当前工作并给出总结！"})
                    # 2026-08-13：工具轮流式化——逐 chunk 转发正文/思考（之前等整次调用结束一次性出）
                    out: dict = {}
                    async for event in _stream_llm_once(
                        world_id, turn_id, _r + 1, model, thinking, api_base, api_key,
                        messages, tools_for_world, cfg, out=out,
                    ):
                        yield event
                    resp = out
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
                    # 2026-08-13：正文/思考独立展示——无正文存空串（不占位），思考独立渲染
                    if content or reasoning:
                        # 中间轮思考也要落库（对齐首轮 note：reasoning 字段），否则刷新后「工具调用的思考」丢失
                        if content:
                            full_content = content
                        db.add(WorldChatMessage(
                            world_id=world_id, user_id=None, role="note",
                            content=(content or "")[:4000],
                            reasoning=reasoning or None,
                            session_id=sid_db,
                        ))
                        await db.commit()
                        if content:
                            yield f"data: {content.replace(chr(10), '{NL}')}\n\n"
                    # 模型还要继续调工具：记录真实 tool_calls，进入下一轮
                    # ⚠️ DeepSeek thinking 模式硬性要求：assistant 消息必须回传 reasoning_content，
                    # 否则 400 invalid_request_error（2026-08-13 修复）
                    messages.append({
                        "role": "assistant", "content": content or "",
                        "tool_calls": tcs,
                        **({"reasoning_content": reasoning} if reasoning else {}),
                    })
                    tool_call_acc = {
                        i: {"id": tc.get("id", ""), "name": tc["function"]["name"], "arguments": tc["function"].get("arguments") or ""}
                        for i, tc in enumerate(tcs)
                    }
                else:
                    final = ""  # 达到轮次上限：走强制收尾轮

                # 强制收尾轮：不带 tools，保证必有最终回复（含思考捕获）
                if not final:
                    _log_llm_request(world_id, turn_id, "final", model, thinking, messages)
                    # 2026-08-13：收尾轮流式化（之前等整次结束一次性出）
                    out_f: dict = {}
                    async for event in _stream_llm_once(
                        world_id, turn_id, "final", model, thinking, api_base, api_key,
                        messages, None, cfg, out=out_f,
                    ):
                        yield event
                    resp_final = out_f
                    await _record_usage(db, world_id, turn_id, "final", model, (resp_final or {}).get("usage"), messages)
                    final = (resp_final or {}).get("content") or "（工具执行完成）"
                    fr = (resp_final or {}).get("reasoning_content") or ""
                    if fr:
                        full_reasoning = fr
                    full_content = final
                else:
                    # ⚠️ 正常收尾轮（模型不再调工具 → final=content 已 break）：收尾总结也必须进 full_content，
                    # 否则流式显示正常但落库的是中间轮最后一段叙述 → 刷新后总结消失
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
                await _save_ai_reply(db, world, full_content, full_reasoning, session_id=sid_db)
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
            await _save_ai_reply(db, world, full_content, full_reasoning, session_id=sid_db)
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