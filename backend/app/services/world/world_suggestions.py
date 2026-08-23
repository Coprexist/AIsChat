"""
世界 AI 建议问题生成（"你可以"按钮）——从 world_chat_service 拆分

三级策略（2026-08-06 产品定）：
1. AI 自己生成（suggest_questions 工具）→ turn_state["suggestions"]
2. 本模块兜底：轻量 LLM 生成（用世界 AI 自己的 key）
3. 预设：后台 system_settings.world_preset_suggestions（统一维护）随机挑 4 个
"""
from __future__ import annotations

import json
import logging
import random

from sqlalchemy import select
from app.repositories.world_repo import WorldRepository

logger = logging.getLogger(__name__)


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


async def suggest_fallback(world_repo: WorldRepository, world) -> list[str]:
    """轻量 LLM 兜底生成建议（用世界 AI 自己的 key）；无历史/失败 → 预设"""
    try:
        from app.models.world import WorldChatMessage, WorldAI
        rows = (await world_repo.execute(
            select(WorldChatMessage)
            .where(WorldChatMessage.world_id == world.id, WorldChatMessage.role.in_(["user", "ai"]))
            .order_by(WorldChatMessage.id.desc()).limit(6)
        )).scalars().all()
        if not rows:
            return await load_preset_suggestions(world_repo)
        recent = "\n".join(
            f"{'用户' if r.role == 'user' else 'AI'}: {r.content[:120]}" for r in reversed(rows)
        )
        from app.ai.llm import chat_completion
        from app.services.world.world_chat_service import _resolve_world_credentials
        api_key, api_base = await _resolve_world_credentials(world_repo, world)
        wai = (await world_repo.execute(select(WorldAI).where(WorldAI.world_id == world.id))).scalar_one_or_none()
        from app.config import settings
        model = (wai.model if wai else None) or settings.default_chat_model
        resp = await chat_completion(
            messages=[
                {"role": "system", "content": '你是对话引导助手。基于以下对话，生成 3-4 个建议给用户（每个 ≤20 字）：可以是问题、陈述性要求或下一步选项，具体、好玩、引导探索。只输出 JSON 数组，如 ["建议1","建议2","建议3"]，不要其它文字。'},
                {"role": "user", "content": recent},
            ],
            model=model, api_base_url=api_base, api_key=api_key,
            temperature=0.9, max_tokens=200,
        )
        text = (resp or {}).get("content") or ""
        arr = json.loads(text.strip().strip("`").lstrip("json").strip())
        if isinstance(arr, list):
            return [str(q).strip()[:40] for q in arr if str(q).strip()][:5]
        return await load_preset_suggestions(world_repo)
    except Exception as e:
        logger.warning(f"🌐 世界 #{world.id} 建议兜底失败（用预设）: {e}")
        return await load_preset_suggestions(world_repo)
