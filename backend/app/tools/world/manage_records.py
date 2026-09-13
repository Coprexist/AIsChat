"""manage_records — 结构化记忆

目录级结构记忆（对齐主站 manage_records）。把你的结构化数据按「目录/子目录/字段」三级存到数据库（世界维度），支持精确读写、列子目录、生成摘要。与 store_memory 的区别：store_memor
"""
import json

from app.tools.world.base import WorldToolPlugin, WorldToolContext


def _records_summary(result: dict) -> str:
    """manage_records 动作多、返回字段各异，单独收口，免得主分派函数继续膨胀"""
    if not result.get("success"):
        return f"结构化记忆操作失败：{result.get('error', '未知错误')}"
    action = result.get("action")
    category = result.get("category") or "-"
    sub_key = result.get("sub_key") or ""
    if action == "set":
        state = "已更新" if result.get("updated") else "已写入"
        return f"结构化记忆{state}：{category}/{sub_key}/{result.get('field', '')}"
    if action == "get":
        records = result.get("records") or []
        if not records:
            return f"结构化记忆 {category} 没有匹配记录"
        shown = "、".join(
            f"{r.get('sub_key')}.{r.get('field')}={str(r.get('value'))[:40]}" for r in records[:5]
        )
        return f"结构化记忆 {category} 命中 {len(records)} 条：{shown}"
    if action == "list":
        subs = result.get("sub_keys") or {}
        fields = sum(len(v) for v in subs.values())
        return f"结构化记忆 {category}：{len(subs)} 个子目录 / {fields} 条记录"
    if action == "categories":
        cats = result.get("categories") or []
        if not cats:
            return "结构化记忆还是空的"
        return f"结构化记忆目录（{len(cats)} 个）：" + "、".join(cats[:10])
    if action == "summary":
        return "结构化记忆摘要：" + " ".join((result.get("summary") or "").split())[:120]
    if action == "delete":
        return f"结构化记忆已删除 {result.get('deleted', 0)} 条"
    if action == "rename":
        return f"结构化记忆已重命名（{result.get('level')} → {result.get('new_name')}，{result.get('renamed', 0)} 条）"
    if action == "move":
        return f"结构化记忆已移动到 {result.get('to_category')}（{result.get('moved', 0)} 条）"
    return f"结构化记忆操作完成（{action or '未知动作'}）"


class ManageRecordsTool(WorldToolPlugin):
    name = 'manage_records'
    label = '结构化记忆'
    segment = 'memory'

    description = (
        '目录级结构记忆（对齐主站 manage_records）。把你的结构化数据按「目录/子目录/字段」三级存到数据库（世界维度），支持精确读写、列子目录、生成摘要。与 store_memory 的区别：'
        'store_memory 存模糊印象/事实，用文本检索找回；manage_records 存结构化数据（项目进度、设定档案、知识库、用户偏好），用精确 key 查找。\n约定：用户个性记忆用 user '
        "目录（如 user/偏好/风格='简洁'，user/偏好/审美='深色'），记录这个用户的偏好/习惯/关系/关键决策习惯。\n使用示例：\n- 写: action='set', category='project', "
        "sub_key='图鉴页面', field='进度', value='已完成收录功能，待优化筛选'\n- 读: action='get', category='project', sub_key='图鉴页面'\n"
        "- 列: action='list', category='project'\n- 快照: action='summary', category='project', sub_key='图鉴页面'\n"
        "- 目录: action='categories'\n- 改名: action='rename', category='project', new_name='设定', level='category'（或 "
        "level='sub_key'/'field' 加 sub_key/field 定位）\n- 移动: action='move', category='project', sub_key='图鉴页面', "
        "to_category='design'（整组移动；加 field 则只移单条）\n- 删: action='delete', category='...', sub_key='...', field='...'（field "
        '可选，不填删整个 sub_key）'
    )

    parameters = {'action': {'type': 'string',
                'enum': ['set', 'get', 'list', 'summary', 'categories', 'delete'],
                'description': '操作类型：set=写入，get=读取，list=列子目录，summary=快照，categories=列目录，delete=删除'},
     'category': {'type': 'string', 'description': '顶层目录名（如 project / setting / knowledge）'},
     'sub_key': {'type': 'string', 'description': '子目录名（key，如项目 id / 页面名）。categories 时不需要。'},
     'field': {'type': 'string', 'description': '字段名。set 必填；get/summary 可选（不填返回全部）'},
     'value': {'type': 'string', 'description': '字段值（仅 set 时使用）'}}

    required = ['action', 'category']

    async def execute(self, ctx: WorldToolContext) -> dict:
        # 目录级结构记忆（对齐主站 manage_records）：{category}/{sub_key}/{field} → value，纯文本不依赖 embedding。
        # 内部直接 commit：即使后续轮次中断/取消，记忆已落库（与 store_memory 不同，可靠性优先）
        try:
            args = ctx.args
            action = str(args.get("action", "")).strip()
            category = str(args.get("category", "")).strip()
            sub_key = str(args.get("sub_key", "")).strip() or ""
            field = str(args.get("field", "")).strip() or None
            value = str(args.get("value", "")).strip() if action == "set" else None
            if not category:
                return {"success": False, "error": "category 不能为空"}
            from app.models.world import WorldStructuredRecord
            from sqlalchemy import select as sa_select, delete as sa_delete
            wid = ctx.world.id

            if action == "set":
                if not sub_key or not field or not value:
                    return {"success": False, "error": "set 需要 sub_key/field/value"}
                existing = (await ctx.world_repo.execute(sa_select(WorldStructuredRecord).where(
                    WorldStructuredRecord.world_id == wid,
                    WorldStructuredRecord.category == category,
                    WorldStructuredRecord.sub_key == sub_key,
                    WorldStructuredRecord.field == field,
                ))).scalars().first()
                if existing:
                    existing.value = value
                else:
                    ctx.world_repo.add(WorldStructuredRecord(world_id=wid, category=category, sub_key=sub_key, field=field, value=value))
                await ctx.world_repo.commit()
                return {"success": True, "action": "set", "category": category, "sub_key": sub_key, "field": field, "updated": existing is not None}

            if action == "get":
                conds = [WorldStructuredRecord.world_id == wid, WorldStructuredRecord.category == category]
                if sub_key:
                    conds.append(WorldStructuredRecord.sub_key == sub_key)
                if field:
                    conds.append(WorldStructuredRecord.field == field)
                rows = (await ctx.world_repo.execute(sa_select(WorldStructuredRecord).where(*conds))).scalars().all()
                return {"success": True, "records": [
                    {"sub_key": r.sub_key, "field": r.field, "value": r.value, "updated_at": str(r.updated_at) if r.updated_at else None}
                    for r in rows
                ]}

            if action == "list":
                rows = (await ctx.world_repo.execute(sa_select(WorldStructuredRecord).where(
                    WorldStructuredRecord.world_id == wid,
                    WorldStructuredRecord.category == category,
                ))).scalars().all()
                subs: dict = {}
                for r in rows:
                    subs.setdefault(r.sub_key, {})[r.field] = r.value
                return {"success": True, "sub_keys": subs}

            if action == "summary":
                conds = [WorldStructuredRecord.world_id == wid, WorldStructuredRecord.category == category]
                if sub_key:
                    conds.append(WorldStructuredRecord.sub_key == sub_key)
                rows = (await ctx.world_repo.execute(sa_select(WorldStructuredRecord).where(*conds))).scalars().all()
                lines = [f"{r.sub_key}.{r.field}: {r.value[:200]}" for r in rows]
                return {"success": True, "summary": chr(10).join(lines) or "（无记录）"}

            if action == "categories":
                rows = (await ctx.world_repo.execute(
                    sa_select(WorldStructuredRecord.category)
                    .where(WorldStructuredRecord.world_id == wid)
                    .distinct()
                )).scalars().all()
                return {"success": True, "categories": list(rows)}

            if action == "delete":
                conds = [WorldStructuredRecord.world_id == wid, WorldStructuredRecord.category == category]
                if sub_key:
                    conds.append(WorldStructuredRecord.sub_key == sub_key)
                if field:
                    conds.append(WorldStructuredRecord.field == field)
                result = await ctx.world_repo.execute(sa_delete(WorldStructuredRecord).where(*conds))
                await ctx.world_repo.commit()
                return {"success": True, "deleted": result.rowcount or 0}

            if action == "rename":
                # 改名：category / sub_key / field 任一级。
                # 参数：category（要改的当前名）+ new_name（新名字）+ level（category|sub_key|field，默认 category）+ sub_key（level=sub_key/field 时定位）
                new_name = str(args.get("new_name", "")).strip()
                level = str(args.get("level", "category")).strip()
                if not new_name:
                    return {"success": False, "error": "rename 需要 new_name"}
                rows = (await ctx.world_repo.execute(sa_select(WorldStructuredRecord).where(
                    WorldStructuredRecord.world_id == wid,
                    WorldStructuredRecord.category == category,
                ))).scalars().all()
                if level == "category":
                    for r in rows:
                        r.category = new_name
                elif level == "sub_key":
                    if not sub_key:
                        return {"success": False, "error": "rename sub_key 需要 sub_key 定位"}
                    hit = [r for r in rows if r.sub_key == sub_key]
                    if not hit:
                        return {"success": False, "error": f"sub_key 不存在: {sub_key}"}
                    for r in hit:
                        r.sub_key = new_name
                elif level == "field":
                    if not sub_key or not field:
                        return {"success": False, "error": "rename field 需要 sub_key + field 定位"}
                    hit = [r for r in rows if r.sub_key == sub_key and r.field == field]
                    if not hit:
                        return {"success": False, "error": f"field 不存在: {sub_key}.{field}"}
                    for r in hit:
                        r.field = new_name
                else:
                    return {"success": False, "error": f"未知 level: {level}（category|sub_key|field）"}
                await ctx.world_repo.commit()
                return {"success": True, "action": "rename", "level": level, "new_name": new_name, "renamed": len(rows)}

            if action == "move":
                # 移动：把 sub_key（整组）或 field（单条）移到另一个 category。
                # 参数：category（当前所在目录）+ to_category（目标目录）+ sub_key（必填）+ field（可选：不填移整个 sub_key）
                to_category = str(args.get("to_category", "")).strip()
                if not to_category:
                    return {"success": False, "error": "move 需要 to_category"}
                if not sub_key:
                    return {"success": False, "error": "move 需要 sub_key 定位"}
                rows = (await ctx.world_repo.execute(sa_select(WorldStructuredRecord).where(
                    WorldStructuredRecord.world_id == wid,
                    WorldStructuredRecord.category == category,
                ))).scalars().all()
                if field:
                    hit = [r for r in rows if r.sub_key == sub_key and r.field == field]
                    if not hit:
                        return {"success": False, "error": f"field 不存在: {sub_key}.{field}"}
                    for r in hit:
                        r.category = to_category
                    moved = len(hit)
                else:
                    hit = [r for r in rows if r.sub_key == sub_key]
                    if not hit:
                        return {"success": False, "error": f"sub_key 不存在: {sub_key}"}
                    for r in hit:
                        r.category = to_category
                    moved = len(hit)
                await ctx.world_repo.commit()
                return {"success": True, "action": "move", "to_category": to_category, "moved": moved}

            return {"success": False, "error": f"未知 action: {action}"}
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        return _records_summary(result)
