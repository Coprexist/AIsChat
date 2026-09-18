"""
世界 AI 建议问题生成（"你可以"按钮）——从 world_chat_service 拆分

两条路，各管一段（2026-09-18 简化）：
1. AI 自己生成：suggest_questions 工具 → turn_state["suggestions"] → 流收尾 [SUGGEST] + 持久化
2. 预设：只在**没有对话历史**时用（首次进入 / clear 后），由 GET /worlds/{id}/chat/suggest 给

原来的"轻量 LLM 兜底"已删除：实测它几乎总是解析失败退化成随机预设，而 AI 正文里往往已经
写了自己的那几条建议，两套并排显示必然对不上（用户 2026-09-18 反馈"提示的选项不是他说的那 4 个"）。
"""
from __future__ import annotations

import random

from app.repositories.world_repo import WorldRepository


# "你可以"默认预设（首次进入编辑页 / clear 后无对话历史时展示）
# 优先级：管理员后台 system_settings.world_preset_suggestions（统一维护）> 此处默认
DEFAULT_PRESET_SUGGESTIONS = [
    "帮我做一个卡牌对战的世界",
    "帮我做一个聊天室",
    "我想让世界变为2D冒险世界",
    "做一个剧本杀界面",
    "将世界做成狼人杀平台",
    "你能帮我做什么？",
    "这是干什么的？",
]


async def load_preset_suggestions(world_repo: WorldRepository) -> list[str]:
    """统一读取预设并随机挑 4 个：后台 system_settings.world_preset_suggestions（无则默认）——每次不同，引导探索"""
    try:
        from app.services.infrastructure.system_settings_service import get_settings
        s = await get_settings(world_repo)
        presets = s.get("world_preset_suggestions")
        if isinstance(presets, list) and presets:
            pool = [str(q).strip()[:40] for q in presets if str(q).strip()]
        else:
            pool = list(DEFAULT_PRESET_SUGGESTIONS)
    except Exception:
        pool = list(DEFAULT_PRESET_SUGGESTIONS)
    random.shuffle(pool)
    return pool[:4]
