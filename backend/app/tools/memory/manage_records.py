"""
manage_records 工具 — 目录级结构记忆的 AI 操作接口

双重记忆架构的系统2，与向量记忆（store_memory/recall_memory）互补：
- store_memory: "我记不记得这个事实？" → 向量搜索
- manage_records: "学生1的有机化学水平如何？" → 精确键值存取

目录结构：{category}/{sub_key}/{field} → value
每个 AI 有自己的 namespace，通用/半通用 AI 的 record 自动按 per-user 隔离。
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)


class ManageRecords(ToolPlugin):
    name = "manage_records"
    description = (
        "目录级结构记忆。把你的结构化数据按「目录/子目录/字段」三级储存到数据库，"
        "支持精确读写、列出子目录、生成摘要。百万级记录无压力。\n\n"
        "和 store_memory 的区别：\n"
        "- store_memory：存模糊印象、事实、偏好 → 用向量搜索找回\n"
        "- manage_records：存结构化数据（学生档案、项目记录、知识库）→ 用精确 key 查找\n\n"
        "使用示例：\n"
        "- 写: action='set', category='student_profile', sub_key='1', field='有机化学', value='掌握了苯密度...'\n"
        "- 读学生全部信息: action='get', category='student_profile', sub_key='1'\n"
        "- 读单个字段: action='get', category='student_profile', sub_key='1', field='有机化学'\n"
        "- 列出所有学生: action='list', category='student_profile'\n"
        "- 学生快照: action='summary', category='student_profile', sub_key='1'\n"
        "- 查看目录: action='categories'\n"
        "- 删除: action='delete', category='...', sub_key='...', field='...'  (field可选，不填删整个sub_key)"
    )
    segment = "memory"
    parameters = {
        "action": {
            "type": "string",
            "enum": ["set", "get", "list", "summary", "categories", "delete"],
            "description": "操作类型：set=写入，get=读取，list=列子目录，summary=快照，categories=列目录，delete=删除",
        },
        "category": {
            "type": "string",
            "description": "顶层目录名，如 student_profile / project / knowledge_base",
        },
        "sub_key": {
            "type": "string",
            "description": "子目录名（key），如学生ID '1'、项目ID 'physics_hw'。categories 时不需要。",
        },
        "field": {
            "type": "string",
            "description": "字段名。set 时必填。get/summary 时可选（不填返回全部字段）。",
        },
        "value": {
            "type": "string",
            "description": "字段值（仅 set 时使用）",
        },
    }
    required = ["action", "category"]
    states = ["active", "dnd", "inactive"]
    admin_description = "数据库版目录级记忆：按 category/sub_key/field 三级存取结构化数据，百万级无压力。"
    trigger_condition = "AI 需要读写结构化数据时（学生档案、项目记录、知识库等）"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        from app.services.memory.structured_memory_service import (
            sr_set, sr_get, sr_list, sr_summary, sr_categories, sr_delete,
        )

        action = arguments["action"]
        category = arguments.get("category", "").strip()
        sub_key = arguments.get("sub_key", "").strip() or ""
        field = arguments.get("field", "").strip() or None
        value = arguments.get("value", "").strip() if action == "set" else None

        if not category:
            return {"error": True, "message": "category 不能为空"}

        if action == "set":
            if not sub_key:
                return {"error": True, "message": "set 操作需要 sub_key（子目录）"}
            if not field:
                return {"error": True, "message": "set 操作需要 field（字段名）"}
            if not value:
                return {"error": True, "message": "set 操作需要 value（字段值）"}
            result = await sr_set(db, agent_id, category, sub_key, field, value)
            if result["ok"]:
                return {
                    "success": True,
                    "action": result["action"],
                    "message": f"{category}/{sub_key}/{field} {'已更新' if result['action'] == 'updated' else '已创建'}",
                }
            return {"error": True, "message": result.get("error", "写入失败")}

        elif action == "get":
            if not sub_key:
                return {"error": True, "message": "get 操作需要 sub_key"}
            result = await sr_get(db, agent_id, category, sub_key, field)
            return {"success": True, **result}

        elif action == "list":
            result = await sr_list(db, agent_id, category)
            return {"success": True, **result}

        elif action == "summary":
            if not sub_key:
                return {"error": True, "message": "summary 操作需要 sub_key"}
            result = await sr_summary(db, agent_id, category, sub_key)
            return {"success": True, **result}

        elif action == "categories":
            result = await sr_categories(db, agent_id)
            return {"success": True, **result}

        elif action == "delete":
            result = await sr_delete(db, agent_id, category, sub_key=sub_key or None, field=field)
            if result["ok"]:
                return {"success": True, "deleted": result["deleted"],
                        "message": f"已删除 {result['deleted']} 条记录"}
            return {"error": True, "message": result.get("error", "删除失败")}

        return {"error": True, "message": f"未知操作: {action}"}


ToolRegistry.register(ManageRecords)
