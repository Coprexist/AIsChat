"""
记忆服务
自动检索相关记忆注入 prompt、自动存储关键信息
"""
import re
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def _text_search_memories(
    db: AsyncSession,
    agent_id: int,
    query: str,
    top_k: int = 5,
    group_id: int | None = None,
    scope: str | None = None,
    user_id: int | None = None,
    ai_type: str = "resonance",
) -> list[dict]:
    """
    文本关键词回退搜索（当 embedding 不可用或记忆向量为 NULL 时使用）。

    使用 PostgreSQL ILIKE 进行全文模糊匹配，支持中英文混合关键词。
    关键词提取策略：
    1. 全文作为整体匹配
    2. 按中英文标点/空格拆分后的各个片段
    3. 取长度 ≥ 1 的片段去重

    scope 参数：
    - None：检索私有 + 群共享（auto-injection 用）
    - "private"：仅检索该 AI 的私有记忆
    - "group"：仅检索群共享记忆

    v0.4.0: user_id 过滤 — 通用/半通用 AI 仅检索该用户的记忆，
    共振 AI 检索 user_id IS NULL（全部记忆）。
    """
    # 提取关键词：全文 + 拆分片段
    parts = [query.strip()]
    # 按中英文标点和空格拆分
    tokens = re.split(r'[,，。！？、\s\n.!?;；：:()（）""''""【】\[\]]+', query)
    for t in tokens:
        t = t.strip()
        if len(t) >= 1 and t not in parts:
            parts.append(t)

    # 构建 ILIKE 条件（取前 8 个关键词避免 SQL 过长）
    conditions = []
    params: dict = {}
    for i, kw in enumerate(parts[:8]):
        param_key = f"kw{i}"
        conditions.append(
            f"(rm.title ILIKE :{param_key} OR dm.content ILIKE :{param_key})"
        )
        params[param_key] = f"%{kw}%"

    where_parts = ["(" + " OR ".join(conditions) + ")"]

    # v0.4.0: per-user 记忆隔离
    if ai_type == "resonance":
        where_parts.append("rm.user_id IS NULL")
    elif user_id is not None:
        where_parts.append("(rm.user_id = :user_id OR rm.user_id IS NULL)")
        params["user_id"] = user_id

    # 权限过滤
    if scope == "private":
        where_parts.append(
            "(rm.owner_type = 'ai' AND rm.owner_id = :agent_id AND rm.scope = 'private')"
        )
        params["agent_id"] = agent_id
    elif scope == "group":
        where_parts.append(
            "(rm.scope = 'group' AND rm.group_id = :group_id)"
        )
        params["group_id"] = group_id
    elif group_id:
        where_parts.append(
            "((rm.owner_type = 'ai' AND rm.owner_id = :agent_id AND rm.scope = 'private') "
            "OR (rm.scope = 'group' AND rm.group_id = :group_id))"
        )
        params["agent_id"] = agent_id
        params["group_id"] = group_id
    else:
        where_parts.append("(rm.owner_type = 'ai' AND rm.owner_id = :agent_id)")
        params["agent_id"] = agent_id

    where_clause = " AND ".join(where_parts)

    sql = text(f"""
        SELECT rm.id, rm.title, rm.scope, 0.0 AS similarity, dm.content
        FROM rough_memories rm
        LEFT JOIN detail_memories dm ON dm.rough_id = rm.id
        WHERE {where_clause}
        ORDER BY rm.created_at DESC
        LIMIT :top_k
    """)
    params["top_k"] = top_k

    result = await db.execute(sql, params)
    memories = []
    for row in result:
        memories.append({
            "id": row.id,
            "title": row.title,
            "scope": row.scope,
            "similarity": 0.0,  # 文本匹配，无向量相似度
            "content": row.content or "",
            "source": "text",
        })

    if memories:
        logger.info(f"📝 文本回退搜索为 AI agent_id={agent_id} 找到 {len(memories)} 条记忆")

    return memories


async def recall_relevant_memories(
    db: AsyncSession,
    agent_id: int,
    query: str,
    api_base_url: str = "https://api.deepseek.com",
    api_key: str | None = None,
    top_k: int = 5,
    similarity_threshold: float = 0.35,
    group_id: int | None = None,
    user_id: int | None = None,
    ai_type: str = "resonance",
) -> list[dict]:
    """
    检索与当前对话相关的记忆（向量相似度搜索 + 文本关键词回退）。

    检索范围：
    - 该 AI 的私有记忆（scope='private'）
    - 群共享记忆（scope='group'，群内任何 AI 存储的）

    策略：
    1. 优先向量搜索（按余弦相似度排序）
    2. 向量搜索失败或无结果时，自动回退到文本 ILIKE 搜索
    3. 文本搜索可以找到 embedding=NULL 的记忆

    v0.4.0: user_id + ai_type 参数支持 per-user 记忆隔离。
    共振 AI 检索所有记忆（user_id IS NULL），
    通用/半通用 AI 仅检索该用户的记忆。

    返回: [{id, title, content, scope, similarity}]
    """
    from app.utils.embedding import get_embedding

    memories: list[dict] = []

    # ═══ 第一轮：向量搜索 ═══
    try:
        query_embedding = await get_embedding(query, api_base_url=api_base_url, api_key=api_key)
        embedding_str = f"[{','.join(map(str, query_embedding))}]"

        # v0.4.0: 构建 user_id 过滤条件
        if ai_type == "resonance":
            user_filter = "AND rm.user_id IS NULL"
        elif user_id is not None:
            user_filter = "AND (rm.user_id = :user_id OR rm.user_id IS NULL)"
        else:
            user_filter = ""

        if group_id:
            sql = text(f"""
                SELECT rm.id, rm.title, rm.scope,
                       1 - (rm.embedding <=> :embedding) AS similarity,
                       dm.content
                FROM rough_memories rm
                LEFT JOIN detail_memories dm ON dm.rough_id = rm.id
                WHERE rm.embedding IS NOT NULL
                  AND 1 - (rm.embedding <=> :embedding) > :threshold
                  {user_filter}
                  AND (
                      (rm.owner_type = 'ai' AND rm.owner_id = :agent_id AND rm.scope = 'private')
                      OR
                      (rm.scope = 'group' AND rm.group_id = :group_id)
                  )
                ORDER BY rm.embedding <=> :embedding
                LIMIT :top_k
            """)
            params = {
                "embedding": embedding_str,
                "agent_id": agent_id,
                "group_id": group_id,
                "threshold": similarity_threshold,
                "top_k": top_k,
            }
            if user_id is not None and ai_type != "resonance":
                params["user_id"] = user_id
            result = await db.execute(sql, params)
        else:
            sql = text(f"""
                SELECT rm.id, rm.title, rm.scope,
                       1 - (rm.embedding <=> :embedding) AS similarity,
                       dm.content
                FROM rough_memories rm
                LEFT JOIN detail_memories dm ON dm.rough_id = rm.id
                WHERE rm.owner_type = 'ai'
                  AND rm.owner_id = :agent_id
                  {user_filter}
                  AND rm.embedding IS NOT NULL
                  AND 1 - (rm.embedding <=> :embedding) > :threshold
                ORDER BY rm.embedding <=> :embedding
                LIMIT :top_k
            """)
            params = {
                "embedding": embedding_str,
                "agent_id": agent_id,
                "threshold": similarity_threshold,
                "top_k": top_k,
            }
            if user_id is not None and ai_type != "resonance":
                params["user_id"] = user_id
            result = await db.execute(sql, params)

        for row in result:
            memories.append({
                "id": row.id,
                "title": row.title,
                "scope": row.scope,
                "similarity": round(float(row.similarity), 4),
                "content": row.content or "",
            })

        if memories:
            logger.info(f"🔍 向量搜索为 AI agent_id={agent_id} 找到 {len(memories)} 条相关记忆")

    except Exception as e:
        logger.warning(f"记忆检索向量化失败，回退到文本搜索: {e}")

    # ═══ 第二轮：文本关键词回退（向量搜索为空或失败时） ═══
    if not memories:
        memories = await _text_search_memories(
            db, agent_id, query, top_k=top_k, group_id=group_id,
            user_id=user_id, ai_type=ai_type,
        )

    return memories


async def auto_store_memory(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
    title: str,
    content: str,
    scope: str = "private",
    api_base_url: str = "https://api.deepseek.com",
    api_key: str | None = None,
) -> dict:
    """
    自动存储一条记忆（封装 embedding + rough + detail 写入）。

    返回: {"success": bool, "rough_id": int|None}
    """
    from app.models.memory import RoughMemory, DetailMemory
    from app.utils.embedding import get_embedding

    # 向量化标题
    try:
        embedding = await get_embedding(title, api_base_url=api_base_url, api_key=api_key)
    except Exception as e:
        logger.warning(f"自动记忆向量化失败: {e}")
        embedding = None

    rough = RoughMemory(
        owner_type="ai",
        owner_id=agent_id,
        title=title,
        embedding=embedding,
        scope=scope,
        group_id=group_id if scope == "group" else None,
    )
    db.add(rough)
    await db.flush()

    detail = DetailMemory(
        rough_id=rough.id,
        content=content,
    )
    db.add(detail)
    await db.flush()

    logger.info(f"💾 AI agent_id={agent_id} 自动存储记忆: {title}")
    return {"success": True, "rough_id": rough.id, "title": title}


async def auto_extract_key_facts(
    db: AsyncSession,
    agent_id: int,
    group_id: int,
    content: str,
    sender_name: str = "",
    api_base_url: str = "https://api.deepseek.com",
    api_key: str | None = None,
) -> bool:
    """
    从消息内容中自动提取关键信息并加入记忆缓冲区（异步批量落盘）。

    触发条件（满足任一）：
    - 明确记忆指令：「记住」「记下」「别忘了」「提醒我」
    - 偏好表达：「我喜欢」「我不喜欢」「我讨厌」「我偏好」
    - 决定声明：「决定了」「就这样」「定下来」「确认」
    - 个人信息：「我是」「我的」「我叫」
    - 任务分配：「你来负责」「交给你」「你的任务是」

    返回: True 如果入队了记忆，False 如果跳过。
    """
    import re
    from app.services.memory_buffer import enqueue_memory
    from app.models.agent import Agent
    from sqlalchemy import select as _sel2

    triggers = [
        (r'(记住|记下|别忘了|提醒我|记住这个)', "显式记忆请求"),
        (r'我(喜欢|不喜欢|讨厌|偏好|爱|恨)', "偏好表达"),
        (r'(决定了|就这样|定下来|确认了|说定了)', "决定"),
        (r'我(是|叫|的|在|做|从事)', "个人信息"),
        (r'(你来负责|交给你|你的任务是|你负责)', "任务分配"),
        (r'(目标|计划是|下一步|里程碑)', "目标/计划"),
    ]

    triggered_category = None
    for pattern, category in triggers:
        if re.search(pattern, content):
            triggered_category = category
            break

    if not triggered_category:
        return False

    # 生成标题（取内容前 60 字符）
    clean_content = content.strip()
    title = clean_content[:60]
    if len(clean_content) > 60:
        title += "..."

    # 获取 AI 类型
    ai_type = "resonance"
    try:
        agent_row = await db.execute(_sel2(Agent).where(Agent.id == agent_id))
        agent_obj = agent_row.scalar_one_or_none()
        if agent_obj:
            ai_type = agent_obj.ai_type or "resonance"
    except Exception:
        pass

    # 自动提取的偏好/简短信息 → low_value
    low_value = triggered_category in ("偏好表达",)

    try:
        await enqueue_memory(
            agent_id=agent_id,
            title=f"[{triggered_category}] {title}",
            content=clean_content[:500],
            scope="private",
            group_id=group_id,
            api_base_url=api_base_url,
            api_key=api_key,
            ai_type=ai_type,
            source="auto_extract",
            low_value=low_value,
        )
        logger.info(f"📝 自动提取记忆入队: [{triggered_category}] {title[:50]} ({'低价值' if low_value else '普通'})")
        return True
    except Exception as e:
        logger.warning(f"自动提取记忆入队失败: {e}")
        return False


def format_memories_for_prompt(memories: list[dict]) -> str:
    """
    将检索到的记忆格式化为可注入 prompt 的文本。

    返回: 格式化后的记忆文本，无记忆时返回空字符串。
    """
    if not memories:
        return ""

    lines = ["## 相关记忆（来自你的长期记忆库）\n"]
    for i, mem in enumerate(memories, 1):
        sim = mem.get("similarity")
        if sim is not None and sim > 0:
            sim_text = f"（相似度: {sim}）"
        elif mem.get("source") == "text":
            sim_text = "（关键词匹配）"
        else:
            sim_text = ""
        lines.append(f"{i}. **{mem['title']}** {sim_text}".rstrip())
        if mem.get("content"):
            # 截断过长内容
            content = mem["content"]
            if len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"   {content}")
        lines.append("")

    # ⚠️ 字符串内如需引用中文名词，用直角引号「」或转义 \"，严禁直接用 ""——
    #    Python 会把第二个 " 当作字符串终止符，导致 SyntaxError 全局炸（worker 崩溃、AI 不回复）
    lines.append("请参考以上记忆来个性化你的回复，但不要刻意提及「记忆库」。\n")
    return "\n".join(lines)
