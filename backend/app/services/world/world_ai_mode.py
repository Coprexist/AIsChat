"""世界 AI 运行模式与操作审批 — 自动 / 审阅 / 计划（产品 2026-09-15 定）

三种模式对三类敏感动作（下载文件 / 删除文件 / 改动机制）的处置：
- auto   自动：不打断，AI 自行执行下载、改动机制、删除文件
- review 审阅：平台弹窗征得同意后才执行（同类动作本轮同意一次即可）；未同意一律不执行
- plan   计划：敏感动作先全部挡住，AI 用 present_plan 出计划 → 用户弹窗通过 → 本轮按自动模式执行

单一机制：审批一律走 request_approval() 这一条通道（弹窗 + 等服务端事件），
AI 侧的 ask_user 工具与平台门禁共用它，不存在第二套确认逻辑。

存储：worlds.config["ai_mode"]。**只由用户/API 改**——AI 没有改模式的工具，
否则等于让它自己拆掉审阅（安全边界不能靠自觉）。

配套硬约束（见 shared.web_download）：没走平台门禁的路径（决策技能 / 定时 / 斜杠命令）
下载完文件后，平台再弹窗问是否保留；无人应答按「不保留」删除。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

logger = logging.getLogger(__name__)

MODES = ("auto", "review", "plan")
MODE_LABELS = {"auto": "自动模式", "review": "审阅模式", "plan": "计划模式"}
DEFAULT_MODE = "review"                 # 默认最安全的一档（老世界一并生效）

# 三类敏感动作 → 工具名单（按动作类批准：一次同意覆盖本轮同类操作，避免弹窗轰炸）
ACTION_TOOLS: dict[str, frozenset[str]] = {
    "download": frozenset({"web_download"}),
    "delete": frozenset({"file_delete"}),
    "modify": frozenset({
        "file_write", "file_edit", "file_move", "file_copy",
        "apply_world_block", "run_world_code",
        "update_group_types", "update_trigger_mode", "update_world_info",
        "set_group_member_role", "kick_group_member",
    }),
}
ACTION_LABELS = {"download": "下载文件", "delete": "删除文件", "modify": "改动世界机制"}

# 只读 / 无副作用工具：明列，其余未登记的一律按「改动机制」（保守默认，安全优先）
SAFE_TOOLS = frozenset({
    "view_api_doc", "view_world_block", "list_world_blocks",
    "file_list", "file_read", "file_grep",
    "get_bound_groups", "get_group_messages", "get_group_types",
    "list_group_members", "send_group_message", "suggest_questions",
    "manage_records", "store_memory", "recall_memory",
    "web_fetch", "web_search",
    "clear_context", "compact_context",
    "ask_user", "present_plan",
})

_APPROVAL_TIMEOUT = 300                 # 等用户点按钮的上限（秒）；超时 = 不通过（安全默认）
_WAIT_FOR_VIEWER = 20                   # 没人在看时先等一小会儿（页面最多 10s 一次空闲轮询会接上）


def get_mode(world) -> str:
    """世界当前运行模式（未设置/非法值 → DEFAULT_MODE）"""
    mode = str((world.config or {}).get("ai_mode") or DEFAULT_MODE)
    return mode if mode in MODES else DEFAULT_MODE


def action_of(tool_name: str) -> str | None:
    """工具 → 动作类；None = 无需审批。未登记的工具按「改动机制」处理（保守）。"""
    if tool_name in SAFE_TOOLS:
        return None
    for action, names in ACTION_TOOLS.items():
        if tool_name in names:
            return action
    return "modify"


def needs_gate(world, tool_name: str) -> bool:
    """该工具在当前模式下是否需要门禁介入（auto 永远不需要）"""
    return get_mode(world) != "auto" and action_of(tool_name) is not None


# ═══════════════════════════════════════════════════════════════
# 审批通道（唯一机制：弹窗 + 等答案）
# ═══════════════════════════════════════════════════════════════
# approval_id → {future, kind, title, detail, world_id, created_at}
_pending: dict[str, dict] = {}


def _broadcasters(world_id: int, turn_id: str) -> list:
    """审批弹窗的投递目标：指定轮次；没指定（旁路下载等）就发给该世界所有活跃轮次。

    仅保留有订阅者（前端确实连着）的通道——没有订阅者 = 没人在看，不值得空等。
    """
    from app.services.world.world_turn import active_broadcasts, get_turn_broadcast
    tbs = [get_turn_broadcast(world_id, turn_id)] if turn_id else active_broadcasts(world_id)
    return [tb for tb in tbs if tb is not None and tb.subscribers]


def _event(payload: dict) -> str:
    return "data: [APPROVAL]" + json.dumps(payload, ensure_ascii=False) + "\n\n"


async def request_approval(
    world_id: int, turn_id: str, *, kind: str, title: str,
    detail: str = "", timeout: int = _APPROVAL_TIMEOUT,
) -> tuple[bool, str]:
    """弹窗征询用户同意（唯一审批通道）。返回 (是否同意, 说明)。

    没有可交互前端（轮次不在 / 没有订阅者 / 非轮次上下文）→ 立即按「不通过」返回，
    不空等：审阅模式下没人在看时保守拒绝，是正确行为。
    """
    # 页面未必已经在看这个轮次（外部发起的轮次靠空闲轮询接上）——先等一小会儿再判定无人。
    tbs = _broadcasters(world_id, turn_id)
    deadline = time.monotonic() + _WAIT_FOR_VIEWER
    while not tbs and time.monotonic() < deadline:
        await asyncio.sleep(1)
        tbs = _broadcasters(world_id, turn_id)
    if not tbs:
        return False, "当前没有可交互的前端（弹窗无人应答），已按「不通过」处理"

    approval_id = uuid.uuid4().hex[:12]
    entry = {
        "id": approval_id, "world_id": world_id, "kind": kind,
        "title": title, "detail": (detail or "")[:4000],
        "created_at": time.time(),
        "future": asyncio.get_running_loop().create_future(),
    }
    _pending[approval_id] = entry
    pending_event = _event({
        "approval_id": approval_id, "status": "pending", "kind": kind,
        "title": title, "detail": entry["detail"],
    })
    try:
        for tb in tbs:
            await tb.broadcast(pending_event)
        logger.info(f"🔐 世界 #{world_id} 等待用户审批（{kind}）: {title[:60]}")
        approved = bool(await asyncio.wait_for(entry["future"], timeout=timeout))
        reason = entry.get("note") or ("用户已同意" if approved else "用户选择不同意")
    except asyncio.TimeoutError:
        approved, reason = False, f"等待用户确认超时（{timeout}s），已按「不通过」处理"
    except asyncio.CancelledError:
        approved, reason = False, "轮次被中断，审批未完成（按「不通过」处理）"
        raise
    finally:
        _pending.pop(approval_id, None)
        resolved_event = _event({
            "approval_id": approval_id, "status": "resolved",
            "kind": kind, "approved": approved,
        })
        for tb in tbs:                               # 弹窗关不掉不影响业务结果
            try:
                await tb.broadcast(resolved_event)
            except Exception as e:
                logger.warning(f"🔐 世界 #{world_id} 审批结果回执广播失败: {e}")
    logger.info(f"🔐 世界 #{world_id} 审批结果（{kind}）: {approved}｜{reason[:60]}")
    return approved, reason


def resolve_approval(approval_id: str, approved: bool, note: str = "") -> bool:
    """用户弹窗点击回执（HTTP 端点调用）。返回是否命中待审批项。"""
    entry = _pending.get(approval_id)
    if entry is None or entry["future"].done():
        return False
    entry["note"] = (note or "").strip()
    entry["future"].set_result(bool(approved))
    return True


def pending_approvals(world_id: int) -> list[dict]:
    """该世界待审批项（前端刷新后重画弹窗；不含 future）"""
    return [
        {"approval_id": e["id"], "kind": e["kind"], "title": e["title"],
         "detail": e["detail"], "created_at": e["created_at"]}
        for e in _pending.values() if e["world_id"] == world_id
    ]


# ═══════════════════════════════════════════════════════════════
# 工具门禁
# ═══════════════════════════════════════════════════════════════

async def gate_tool_call(world, world_id: int, tool_name: str, args: dict, turn_state: dict):
    """工具执行前的唯一门禁。返回 (allowed, approved_for_tool, reason)。

    - auto：直接放行（approved=True，工具知道平台已经兜过底了，不用再自己问）
    - plan：计划未通过 → 挡住并提示先出计划；通过后本轮全部放行
    - review：同类动作本轮同意过一次就放行，否则弹窗问
    """
    action = action_of(tool_name)
    if action is None:
        return True, False, ""
    mode = get_mode(world)
    if mode == "auto":
        return True, True, ""

    if mode == "plan" and not turn_state.get("plan_approved"):
        return False, False, (
            "计划模式：本轮计划还没通过。请先用 present_plan 提交完整计划（要改哪些文件、下载什么、删什么），"
            "用户在弹窗里通过后我才会执行——先出计划，不要直接动手。"
        )

    approved_classes = turn_state.setdefault("approved_classes", set())
    if turn_state.get("plan_approved") or action in approved_classes:
        return True, True, ""

    ok, note = await request_approval(
        world_id, turn_state.get("turn_id", ""),
        kind=action,
        title=f"{MODE_LABELS[mode]}：AI 请求{ACTION_LABELS[action]}",
        detail=describe_action(tool_name, args),
    )
    if not ok:
        return False, False, (
            f"用户没有同意本次{ACTION_LABELS[action]}（{note}），操作未执行。"
            "请先向用户说明原因，得到明确同意后再来一次；不要换个方式绕过。"
        )
    approved_classes.add(action)
    return True, True, ""


def describe_action(tool_name: str, args: dict) -> str:
    """弹窗里给人看的操作说明（做了什么、动到哪个文件）"""
    if tool_name == "web_download":
        return f"下载：{args.get('url', '')}\n保存到：{args.get('path') or 'downloads/（自动命名）'}"
    if tool_name == "file_delete":
        return f"删除：{args.get('path', '')}"
    if tool_name in ("file_move", "file_copy"):
        return f"{'移动' if tool_name == 'file_move' else '复制'}：{args.get('from', '')} → {args.get('to', '')}"
    if tool_name in ("file_write", "file_edit"):
        path = args.get("path", "")
        body = str(args.get("content") or args.get("new_string") or "")
        return f"{'改写' if tool_name == 'file_edit' else '写入'}：{path}\n\n{body[:1500]}"
    return f"{tool_name}\n\n{json.dumps(args, ensure_ascii=False)[:1500]}"


# ═══════════════════════════════════════════════════════════════
# 提示词（模式语义与门禁同一处定义，避免两处说法不一致）
# ═══════════════════════════════════════════════════════════════

def build_mode_prompt(mode: str) -> str:
    """强注入的模式说明段（非 auto 才需要讲规矩）"""
    if mode == "auto":
        return (
            "\n【运行模式：自动】本世界处于自动模式：下载文件、改动世界机制、删除文件都由你自行决定并执行，"
            "平台不会弹窗打断你。仍须遵守内容与文件类型的硬规则（不得下载色情/暴力/违法内容、"
            "不得下载可执行文件与脚本）。"
        )
    if mode == "review":
        return (
            "\n【运行模式：审阅】本世界处于审阅模式：**下载文件、改动世界机制、删除文件**三类操作平台会弹窗"
            "请用户确认，用户同意后才会执行（同类操作本轮同意一次即可，之后不再打断）。\n"
            "- 用户明确要求你做的改动，也只需照常调用工具（平台会弹一次确认），不用额外解释；\n"
            "- 你自己判断需要做的改动（用户没说、或与用户先前说法有出入），**先向用户说明为什么**，再调用工具；\n"
            "- 被拒绝时不要换路径、换工具、改参数重试——停下来问清楚用户的意图；\n"
            "- 需要用户在其他事情上拍板（选方案、确认理解）时用 ask_user 工具，事件类型关键词必填。"
        )
    return (
        "\n【运行模式：计划】本世界处于计划模式：**先探索、先规划**。\n"
        "- 收到任务先读相关文件/资料摸清现状，然后用 present_plan 提交计划（要改哪些文件、下载什么、删什么、"
        "分几步），用户在弹窗里通过后，本轮剩下的操作按自动模式执行——此时直接干，不要再逐步请示；\n"
        "- 计划未通过前，任何写入/下载/删除工具都会被平台挡下，这是正常的，不要反复试；\n"
        "- 用户在弹窗里可能只通过部分内容或提出修改：按用户的意见调整后重新 present_plan。"
    )
