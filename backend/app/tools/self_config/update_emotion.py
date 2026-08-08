"""
update_emotion 工具 — AI 更新自己的情感状态（拟人化）

支持三种写法（丰俭由人，AI 自选）：
1. 增量：{"delta": {"anger": "+0.2", "joy": "-0.1"}}  —— 只传要改变的量
2. 完整向量：{"vector": {"joy": 0.8, "sadness": 0.3}} —— 覆盖
3. 概括词：{"word": "平静"} / {"word": "喜极而泣"}   —— 直接传状态词语

情感轴（Plutchik 8 类，独立 0-1，不设对立合并）：
joy 开心 / trust 信任 / fear 恐惧 / surprise 惊讶 / sadness 伤心 / disgust 厌恶 / anger 愤怒 / anticipation 期待

注意：
- 低落可以是 joy 与 sadness 双低；复杂情绪（如喜极而泣）可以 joy/sadness 双高
- 情感随该状态下的调用次数缓慢回归基线（mood homeostasis）
- 未开启"向量化情感"配置时，可用 text 传文字心情描述
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class UpdateEmotion(ToolPlugin):
    name = "update_emotion"
    description = (
        "更新自己当前状态的情感（更拟人）。三种写法任选：\n"
        "1. delta 增量：只传变化的量，如 {\"delta\": {\"anger\": \"+0.2\", \"joy\": \"-0.1\"}}\n"
        "2. vector 完整向量：覆盖各轴强度（0-1），如 {\"vector\": {\"joy\": 0.8, \"sadness\": 0.3}}\n"
        "3. word 概括词：直接传心情词语，如 {\"word\": \"平静\"} / {\"word\": \"喜极而泣\"} / {\"word\": \"焦虑\"}\n\n"
        "情感轴（独立 0-1，可同时多轴非零）：开心 joy / 信任 trust / 恐惧 fear / 惊讶 surprise / 伤心 sadness / 厌恶 disgust / 愤怒 anger / 期待 anticipation\n"
        "提示：低落可以开心和伤心双低；复杂情绪可以双高（如毕业季开心+伤心都高）。\n"
        "切换状态时本状态情感会保留，并附上来源状态的情感。"
    )
    segment = "self_config"
    parameters = {
        "delta": {"type": "object", "description": "增量写法：各轴的变化量（字符串 +0.2 / -0.1）", "nullable": True},
        "vector": {"type": "object", "description": "完整向量写法：各轴强度 0-1（覆盖）", "nullable": True},
        "word": {"type": "string", "description": "概括词写法：如 平静/开心/难过/愤怒/害怕/焦虑/喜极而泣/麻木/百感交集", "nullable": True},
        "text": {"type": "string", "description": "文字心情描述（未向量化配置时用），如「刚写完一段满意的代码，心情不错」", "nullable": True},
    }
    states = ["active", "dnd"]
    admin_description = "AI 更新自己的情感状态（增量/完整向量/概括词三种写法）"
    trigger_condition = "AI 经历情绪变化、状态切换时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.agent.state_stack_service import (
            update_active_emotion, set_active_emotion_text, get_active_emotion,
        )
        update = None
        if arguments.get("word"):
            update = arguments["word"]
        elif arguments.get("vector") is not None:
            update = arguments["vector"]
        elif arguments.get("delta") is not None:
            update = {k: v for k, v in (arguments["delta"] or {}).items()}

        result = {}
        if update is not None:
            emotion = await update_active_emotion(db, agent_id, update)
            result["emotion"] = emotion
        if arguments.get("text"):
            await set_active_emotion_text(db, agent_id, arguments["text"])
            result["emotion_text"] = arguments["text"]

        if not result:
            cur = await get_active_emotion(db, agent_id)
            result = cur
        logger.info(f"Agent({agent_id}) 更新情感: {str(result)[:120]}")
        return {"ok": True, **result}
