"""
roll_dice 工具 — AI 掷骰子（示例：演示自动发现功能）
"""
import random
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class RollDice(ToolPlugin):
    name = "roll_dice"
    description = "掷骰子。指定面数和次数，返回随机结果。适合游戏、抽签、随机决策。"
    segment = "chat_social"
    parameters = {
        "sides": {
            "type": "integer",
            "description": "骰子面数，默认 6",
            "nullable": True,
        },
        "count": {
            "type": "integer",
            "description": "掷几次，默认 1",
            "nullable": True,
        },
    }
    required = []
    states = ["active", "dnd", "inactive"]
    admin_description = "AI 掷骰子做随机决策或玩游戏"
    trigger_condition = "AI 需要随机决策或玩游戏时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        sides = arguments.get("sides", 6)
        count = arguments.get("count", 1)

        if sides < 2:
            return {"error": True, "message": "骰子面数至少为 2"}
        if count < 1 or count > 100:
            return {"error": True, "message": "掷骰次数应在 1-100 之间"}

        results = [random.randint(1, sides) for _ in range(count)]
        total = sum(results)
        summary = f"掷 {count} 个 D{sides} 骰子：{'、'.join(map(str, results))}"
        if count > 1:
            summary += f"，合计 {total}"

        return {
            "success": True,
            "results": results,
            "total": total if count > 1 else results[0],
            "summary": summary,
        }


# 注：不需要手动注册！__init_subclass__ 自动调用 ToolRegistry.register()
# ToolRegistry.register(RollDice)
