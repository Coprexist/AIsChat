"""
技能管理 API — 设计文档 skill_manager_design.md 十一节

端点：
  GET    /skills                          所有可用技能类型
  GET    /skills/{name}                   技能类型详情
  POST   /skills/{agent_id}/enable/{name} 启用技能
  POST   /skills/{agent_id}/disable/{name} 禁用技能
  POST   /skills/{agent_id}/trigger       创建触发器
  GET    /skills/{agent_id}/triggers      触发器列表
  DELETE /skills/{agent_id}/triggers/{id} 删除触发器
  POST   /skills/{agent_id}/attention     更新注意力设置
  GET    /skills/{agent_id}/attention     获取注意力设置
  GET    /skills/template/list            模板列表
  POST   /skills/template/generate        从模板生成技能代码
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.deps import require_agent_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["技能管理"])


# ═══════════════════════════════════════════════════════════════
# 模型
# ═══════════════════════════════════════════════════════════════

class TriggerRequest(BaseModel):
    """创建触发器请求"""
    trigger_type: str = Field(..., description="time|event|semantic|relational|state|composite")
    task: str = Field(..., min_length=1, description="触发后告诉 AI 要做什么")
    condition: dict = Field(default_factory=dict, description="条件 payload（随类型而异）")
    expires_at: str | None = None
    max_fires: int = Field(default=-1, description="-1=永久，1=一次性")


class AttentionRequest(BaseModel):
    """更新注意力设置请求"""
    group_id: int | None = Field(default=None, description="缺省=全局（所有群）")
    interested_topics: list[str] = Field(default_factory=list)
    interested_users: list[int] = Field(default_factory=list)
    interested_patterns: list[str] = Field(default_factory=list)
    ignored_topics: list[str] = Field(default_factory=list)
    ignored_patterns: list[str] = Field(default_factory=list)
    match_action: str = Field(default="highlight", description="highlight|wake|silent_remember|ignore")


class TemplateGenerateRequest(BaseModel):
    """从模板生成技能代码请求"""
    template_type: str = Field(..., description="trigger_action|role_template|workflow_template")
    config: dict = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# 技能类型
# ═══════════════════════════════════════════════════════════════

@router.get("")
async def list_skill_types():
    """获取所有可用技能类型"""
    from app.utils.pure.skill_registry import SkillRegistry
    return SkillRegistry.get_all_types()


@router.get("/{name}")
async def get_skill_type(name: str):
    """获取技能类型详情"""
    from app.utils.pure.skill_registry import SkillRegistry
    info = SkillRegistry.get_info(name)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"未知技能类型: {name}")
    return info.to_dict()


# ═══════════════════════════════════════════════════════════════
# 技能启停（agent_skill_relations 表）
# ═══════════════════════════════════════════════════════════════

async def _set_skill_enabled(db: AsyncSession, agent_id: int, skill_name: str, enabled: bool) -> dict:
    from sqlalchemy import select
    from app.models.agent_skill_relation import AgentSkillRelation

    result = await db.execute(
        select(AgentSkillRelation).where(
            AgentSkillRelation.agent_id == agent_id,
            AgentSkillRelation.skill_name == skill_name,
        )
    )
    relation = result.scalar_one_or_none()
    if relation is None:
        relation = AgentSkillRelation(agent_id=agent_id, skill_name=skill_name, is_enabled=enabled)
        db.add(relation)
    else:
        relation.is_enabled = enabled
    db.flush()
    return {"agent_id": agent_id, "skill_name": skill_name, "is_enabled": enabled}


@router.post("/{agent_id}/enable/{name}")
async def enable_skill(
    name: str,
    agent=Depends(require_agent_access),
    db: AsyncSession = Depends(get_db),
):
    """启用技能"""
    result = await _set_skill_enabled(db, agent.id, name, True)
    await db.commit()
    return result


@router.post("/{agent_id}/disable/{name}")
async def disable_skill(
    name: str,
    agent=Depends(require_agent_access),
    db: AsyncSession = Depends(get_db),
):
    """禁用技能"""
    result = await _set_skill_enabled(db, agent.id, name, False)
    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════
# 触发器
# ═══════════════════════════════════════════════════════════════

@router.post("/{agent_id}/trigger")
async def create_trigger(
    req: TriggerRequest,
    agent=Depends(require_agent_access),
    db: AsyncSession = Depends(get_db),
):
    """创建触发器（六维：time/event/semantic/relational/state/composite）"""
    from app.services.skill.trigger_engine import trigger_engine

    try:
        created = await trigger_engine.register_trigger(
            db, agent.id, req.model_dump(exclude_none=True)
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return created


@router.get("/{agent_id}/triggers")
async def list_triggers(
    agent=Depends(require_agent_access),
    db: AsyncSession = Depends(get_db),
):
    """获取触发器列表"""
    from app.services.skill.trigger_engine import trigger_engine
    return await trigger_engine.list_triggers(db, agent.id)


@router.delete("/{agent_id}/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: int,
    agent=Depends(require_agent_access),
    db: AsyncSession = Depends(get_db),
):
    """删除触发器"""
    from app.services.skill.trigger_engine import trigger_engine
    await trigger_engine.unregister_trigger(db, agent.id, trigger_id)
    await db.commit()
    return {"success": True, "trigger_id": trigger_id}


# ═══════════════════════════════════════════════════════════════
# 注意力
# ═══════════════════════════════════════════════════════════════

@router.post("/{agent_id}/attention")
async def update_attention(
    req: AttentionRequest,
    agent=Depends(require_agent_access),
    db: AsyncSession = Depends(get_db),
):
    """更新注意力设置（兴趣域声明 + 前置过滤）"""
    from app.services.skill.attention_system import attention_system

    if req.match_action not in ("highlight", "wake", "silent_remember", "ignore"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="match_action 可选: highlight|wake|silent_remember|ignore")

    await attention_system.update_attention(db, agent.id, req.group_id, req.model_dump())
    await db.commit()
    return {"success": True, "agent_id": agent.id, "group_id": req.group_id}


@router.get("/{agent_id}/attention")
async def get_attention(
    group_id: int | None = None,
    agent=Depends(require_agent_access),
    db: AsyncSession = Depends(get_db),
):
    """获取注意力设置"""
    from app.services.skill.attention_system import attention_system
    return await attention_system.get_attention(db, agent.id, group_id)


# ═══════════════════════════════════════════════════════════════
# 模板
# ═══════════════════════════════════════════════════════════════

@router.get("/template/list")
async def list_templates():
    """模板列表（零代码创作入口）"""
    from app.services.skill.template_engine import template_engine
    return {"templates": template_engine.list_templates()}


@router.post("/template/generate")
async def generate_from_template(req: TemplateGenerateRequest):
    """从模板生成技能代码"""
    from app.services.skill.template_engine import template_engine

    try:
        code = template_engine.generate_skill_code(req.template_type, req.config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该模板类型暂未实现代码生成")
    return {"template_type": req.template_type, "code": code}
