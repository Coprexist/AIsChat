"""
目录级结构记忆 Service（双重记忆架构的系统2）

数据库版实现，与文件系统版 memory_index.py 互补：
- 文件系统: 适合经常直接编辑的大文档
- 数据库: 适合频繁 CRUD 的结构化记录，百万级无压力

目录结构: {category}/{sub_key}/{field} → value
"""
import logging
from datetime import datetime, timezone
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.structured_record import StructuredRecord

logger = logging.getLogger(__name__)


async def sr_set(
    db: AsyncSession,
    agent_id: int,
    category: str,
    sub_key: str,
    field: str,
    value: str,
) -> dict:
    """写入一个字段（upsert：同路径重复写入自动覆盖）"""
    try:
        result = await db.execute(
            select(StructuredRecord).where(
                StructuredRecord.agent_id == agent_id,
                StructuredRecord.category == category,
                StructuredRecord.sub_key == sub_key,
                StructuredRecord.field == field,
            )
        )
        existing = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if existing:
            existing.value = value
            existing.updated_at = now
            await db.commit()
            return {"ok": True, "action": "updated", "id": existing.id}
        else:
            record = StructuredRecord(
                agent_id=agent_id,
                category=category,
                sub_key=sub_key,
                field=field,
                value=value,
            )
            db.add(record)
            await db.commit()
            return {"ok": True, "action": "created", "id": record.id}
    except Exception as e:
        await db.rollback()
        logger.error(f"sr_set 失败: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def sr_get(
    db: AsyncSession,
    agent_id: int,
    category: str,
    sub_key: str,
    field: str | None = None,
) -> dict:
    """读取一个子目录的所有字段（field=None 则返回全部），或指定单个字段"""
    try:
        conditions = [
            StructuredRecord.agent_id == agent_id,
            StructuredRecord.category == category,
            StructuredRecord.sub_key == sub_key,
        ]
        if field:
            conditions.append(StructuredRecord.field == field)

        result = await db.execute(
            select(StructuredRecord).where(*conditions)
        )
        records = result.scalars().all()
        if not records:
            return {"fields": {}}

        fields = {}
        for r in records:
            fields[r.field] = r.value

        return {"fields": fields}
    except Exception as e:
        logger.error(f"sr_get 失败: {e}", exc_info=True)
        return {"fields": {}, "error": str(e)}


async def sr_list(
    db: AsyncSession,
    agent_id: int,
    category: str,
) -> dict:
    """列出某个 category 下的所有 sub_key（子目录）及其字段数"""
    try:
        result = await db.execute(
            select(
                StructuredRecord.sub_key,
                func.count(StructuredRecord.id).label("cnt"),
                func.max(StructuredRecord.updated_at).label("last_update"),
            )
            .where(
                StructuredRecord.agent_id == agent_id,
                StructuredRecord.category == category,
            )
            .group_by(StructuredRecord.sub_key)
            .order_by(func.max(StructuredRecord.updated_at).desc())
            .limit(50)
        )
        rows = result.all()
        items = [
            {
                "sub_key": r.sub_key,
                "field_count": r.cnt,
                "last_update": r.last_update.isoformat() if r.last_update else None,
            }
            for r in rows
        ]
        return {"items": items}
    except Exception as e:
        logger.error(f"sr_list 失败: {e}", exc_info=True)
        return {"items": [], "error": str(e)}


async def sr_summary(
    db: AsyncSession,
    agent_id: int,
    category: str,
    sub_key: str,
) -> dict:
    """生成一个子目录的快照摘要（返回字段名 + 简短值预览）"""
    try:
        result = await db.execute(
            select(StructuredRecord).where(
                StructuredRecord.agent_id == agent_id,
                StructuredRecord.category == category,
                StructuredRecord.sub_key == sub_key,
            )
        )
        records = result.scalars().all()
        if not records:
            return {"summary": "（空）", "fields": {}, "total": 0}

        fields = {}
        for r in records:
            preview = r.value[:80] + "..." if len(r.value) > 80 else r.value
            fields[r.field] = preview

        total = len(records)
        field_names = ", ".join(fields.keys())
        summary = f"{total} 个字段：{field_names}"

        return {"summary": summary, "fields": fields, "total": total}
    except Exception as e:
        logger.error(f"sr_summary 失败: {e}", exc_info=True)
        return {"summary": "（出错）", "fields": {}, "total": 0, "error": str(e)}


async def sr_categories(
    db: AsyncSession,
    agent_id: int,
) -> dict:
    """列出该 AI 使用的所有 category"""
    try:
        result = await db.execute(
            select(
                StructuredRecord.category,
                func.count(StructuredRecord.id).label("record_count"),
                func.count(func.distinct(StructuredRecord.sub_key)).label("sub_count"),
            )
            .where(StructuredRecord.agent_id == agent_id)
            .group_by(StructuredRecord.category)
            .order_by(StructuredRecord.category)
        )
        rows = result.all()
        categories = [
            {
                "name": r.category,
                "record_count": r.record_count,
                "sub_count": r.sub_count,
            }
            for r in rows
        ]
        return {"categories": categories}
    except Exception as e:
        logger.error(f"sr_categories 失败: {e}", exc_info=True)
        return {"categories": [], "error": str(e)}


async def sr_delete(
    db: AsyncSession,
    agent_id: int,
    category: str,
    sub_key: str | None = None,
    field: str | None = None,
) -> dict:
    """删除记录（可按 field 删除单条，或删整个 sub_key，或删整个 category）"""
    try:
        conditions = [StructuredRecord.agent_id == agent_id, StructuredRecord.category == category]
        if sub_key:
            conditions.append(StructuredRecord.sub_key == sub_key)
        if field:
            conditions.append(StructuredRecord.field == field)

        stmt = delete(StructuredRecord).where(*conditions)
        result = await db.execute(stmt)
        await db.commit()
        deleted = result.rowcount
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        await db.rollback()
        logger.error(f"sr_delete 失败: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def format_db_records_for_prompt(db: AsyncSession, agent_id: int) -> str:
    """
    将结构化记录注入系统提示词。

    核心思想：无论空还是不空，始终展示目录结构——像人脑分区一样，
    即使知识为空，框架也清晰可见，引导 AI 按照正确的方式填充经验。

    空时 → 展示推荐目录 + 用法示例
    有数据时 → 展示实际目录 + 字段摘要
    """
    categories = await sr_categories(db, agent_id)
    cat_list = categories.get("categories", [])
    has_data = len(cat_list) > 0

    lines: list[str] = [
        "## 你的记忆索引",
        "",
    ]

    if has_data:
        lines.append("以下是你的长期记忆。按目录组织，越用越丰富。")
    else:
        lines.append("你的记忆目前是空的——像一个空书架，等待你填充。")
        lines.append("用 manage_records 把重要的事记录下来，它们会按目录沉淀为长期记忆。")
    lines.append("")

    # ── 已有数据：展示实际目录 ──
    if has_data:
        for cat in cat_list[:8]:
            name = cat["name"]
            record_count = cat["record_count"]
            sub_count = cat["sub_count"]
            lines.append(f"📋 **{name}/** — {sub_count} 个子目录，{record_count} 条记录")

            try:
                sub_list = await sr_list(db, agent_id, name)
                for item in sub_list.get("items", [])[:5]:
                    sub = item["sub_key"]
                    cnt = item["field_count"]
                    fields_result = await sr_get(db, agent_id, name, sub)
                    field_names = list(fields_result.get("fields", {}).keys())[:3]
                    previews = []
                    for fn in field_names:
                        val = fields_result.get("fields", {}).get(fn, "")
                        short = val[:30] + "..." if len(val) > 30 else val
                        previews.append(f"{fn}: {short}")
                    preview_str = "；".join(previews) if previews else f"{cnt}字段"
                    lines.append(f"  {sub} — {preview_str}")
            except Exception:
                pass
            lines.append("")

    # ── 推荐目录模板（通用，不预设职业或场景）──
    lines.extend([
        "📋 推荐记忆目录（语义化标签，可自创）：",
        "  people/    — 人：重要对象的信息、偏好、习惯、关系",
        "  topics/    — 事：讨论过的话题、学到的知识、形成的观点",
        "  tasks/     — 任务：项目进度、待办追踪、决策记录",
        "  journal/   — 日志：自我反思、成长轨迹、重要事件",
        "",
    ])

    # ── 用法速查（始终展示）──
    lines.extend([
        "---",
        "查详情 → manage_records(action='get', category='...', sub_key='...')",
        "写记录 → manage_records(action='set', category='...', sub_key='...', field='...', value='...')",
        "看概览 → manage_records(action='summary', category='...', sub_key='...')",
        "列目录 → manage_records(action='categories')",
    ])
    return "\n".join(lines)
