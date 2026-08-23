"""
群邀请服务：纯函数 + 服务编排

邀请人类 → 发特殊 DM 卡片（message_type='group_invitation'），对方点接受才入群。
AI 成员不在此模块处理——直接走 add_member 入群。
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.repositories.invitation_repo import InvitationRepository
from app.models.group import GroupInvitation, GroupMember
from app.models.user import User

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 纯函数：数据变换，无副作用
# ═══════════════════════════════════════════════════════════════

def build_invitation_card_content(
    group_name: str,
    inviter_name: str,
    message: str | None = None,
) -> str:
    """生成邀请卡片 DM 的文本内容（纯函数）"""
    lines = [
        f"📨 **群聊邀请**",
        f"",
        f"**{inviter_name}** 邀请你加入群聊「**{group_name}**」",
    ]
    if message:
        lines.append(f"")
        lines.append(f"> {message}")
    return "\n".join(lines)


def build_invitation_attachments(
    invitation_id: int,
    group_name: str,
    inviter_name: str,
    status: str = "pending",
) -> list[dict]:
    """构建邀请卡片的 attachments 载荷（纯函数）。
    前端据此渲染 InvitationCard 组件。
    """
    return [{
        "type": "group_invitation",
        "invitation_id": invitation_id,
        "group_name": group_name,
        "inviter_name": inviter_name,
        "status": status,
    }]


def _valid_transitions() -> dict[str, set[str]]:
    """邀请状态允许的转换（纯函数）"""
    return {
        "pending": {"accepted", "rejected"},
        "accepted": set(),
        "rejected": set(),
    }


def validate_invitation_transition(current_status: str, new_status: str) -> bool:
    """校验状态转换是否合法（纯函数）"""
    allowed = _valid_transitions().get(current_status, set())
    return new_status in allowed


def format_invitation_for_api(
    invitation: GroupInvitation,
    group_name: str,
    inviter_name: str,
    invitee_name: str,
) -> dict:
    """邀请记录 → API 响应 dict（纯函数）"""
    return {
        "id": invitation.id,
        "group_id": invitation.group_id,
        "group_name": group_name,
        "inviter_id": invitation.inviter_id,
        "inviter_name": inviter_name,
        "invitee_id": invitation.invitee_id,
        "invitee_name": invitee_name,
        "status": invitation.status,
        "message": invitation.message,
        "created_at": str(invitation.created_at) if invitation.created_at else None,
        "resolved_at": str(invitation.resolved_at) if invitation.resolved_at else None,
    }


# ═══════════════════════════════════════════════════════════════
# 服务编排：带副作用
# ═══════════════════════════════════════════════════════════════

async def send_group_invitation(
    invitation_repo: InvitationRepository,
    group_id: int,
    inviter_id: int,
    invitee_id: int,
    message: str | None = None,
) -> dict:
    """发送群邀请：建记录 + 发卡片 DM。

    Args:
        invitation_repo: 群邀请数据访问仓库（不再直接依赖 AsyncSession）。
            跨模块辅助调用（发 DM 卡片）通过 invitation_repo.session 桥接。

    Returns:
        dict with invitation_id and dm_message_id
    """
    from app.chat.dm import get_or_create_dm_session, send_dm_message
    from app.models.group import Group

    # 检查是否已有待处理邀请（幂等防重）
    existing = await invitation_repo.execute(
        select(GroupInvitation).where(
            GroupInvitation.group_id == group_id,
            GroupInvitation.invitee_id == invitee_id,
            GroupInvitation.status == "pending",
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("该用户已有待处理的群邀请，请等待对方处理后再试")

    # 获取群名和邀请人名称
    group_result = await invitation_repo.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()
    if group is None:
        raise ValueError("群聊不存在")

    inviter_result = await invitation_repo.execute(
        select(User.username).where(User.id == inviter_id)
    )
    inviter_row = inviter_result.one_or_none()
    inviter_name = inviter_row[0] if inviter_row else f"用户{inviter_id}"

    # 创建邀请记录
    invitation = GroupInvitation(
        group_id=group_id,
        inviter_id=inviter_id,
        invitee_id=invitee_id,
        status="pending",
        message=message,
    )
    invitation_repo.add(invitation)
    invitation_repo.flush()
    invitation_repo.refresh(invitation)

    # 获取或创建 DM 会话（跳过好友校验——群邀请不要求已是好友）
    dm_session = await get_or_create_dm_session(
        invitation_repo.session, inviter_id, invitee_id, skip_friendship_check=True,
    )

    # 构建卡片 DM
    content = build_invitation_card_content(group.name, inviter_name, message)
    attachments = build_invitation_attachments(
        invitation.id, group.name, inviter_name, status="pending",
    )

    # 发 DM（跳过好友校验）
    dm_msg = await send_dm_message(
        invitation_repo.session,
        session_id=dm_session["session_id"],
        sender_id=inviter_id,
        content=content,
        attachments=attachments,
        message_type="group_invitation",
        skip_friendship_check=True,
    )

    # 回写 DM 关联信息到邀请记录
    invitation.dm_session_id = dm_session["session_id"]
    invitation.dm_message_id = dm_msg["id"]

    # WebSocket 推送给双方——让 DM 列表实时更新
    try:
        from app.routers.ws import manager
        ws_msg = {**dm_msg, "conversation_type": "dm", "session_id": dm_session["session_id"]}
        await manager.send_to_user(invitee_id, {"type": "message", "data": ws_msg})
        await manager.send_to_user(inviter_id, {"type": "message", "data": ws_msg})
    except Exception as e:
        logger.warning(f"  ⚠️ WebSocket 推送邀请卡片失败（非致命）: {e}")

    logger.info(
        f"📨 群邀请 #{invitation.id}: {inviter_name} → user#{invitee_id} "
        f"加入群「{group.name}」"
    )
    return {
        "invitation_id": invitation.id,
        "dm_message_id": dm_msg["id"],
        "dm_session_id": dm_session["session_id"],
    }


async def accept_invitation(
    invitation_repo: InvitationRepository,
    invitation_id: int,
    user_id: int,
) -> dict:
    """接受群邀请：校验 → 入群 → 更新状态 → 更新卡片。

    Returns:
        dict with the updated invitation info
    """
    from app.chat.message import add_member

    invitation = await invitation_repo.get(GroupInvitation, invitation_id)
    if invitation is None:
        raise ValueError("邀请不存在")
    if invitation.invitee_id != user_id:
        raise ValueError("这不是发给你的邀请")
    if not validate_invitation_transition(invitation.status, "accepted"):
        raise ValueError(f"邀请状态为 {invitation.status}，无法接受")

    # 入群
    await add_member(invitation_repo.session, invitation.group_id, "human", user_id)

    # 更新邀请状态
    invitation.status = "accepted"
    invitation.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # 更新 DM 卡片（attachments 中 status → accepted）
    await _update_dm_card(invitation_repo, invitation, "accepted")

    # 获取群名用于日志
    from app.models.group import Group
    group = await invitation_repo.get(Group, invitation.group_id)
    group_name = getattr(group, 'name', f"#{invitation.group_id}")

    logger.info(f"✅ 群邀请 #{invitation_id}: user#{user_id} 接受了「{group_name}」的邀请")

    return {
        "invitation_id": invitation.id,
        "group_id": invitation.group_id,
        "group_name": group_name,
        "status": "accepted",
    }


async def reject_invitation(
    invitation_repo: InvitationRepository,
    invitation_id: int,
    user_id: int,
) -> dict:
    """拒绝群邀请：校验 → 更新状态 → 更新卡片。
    不入群，仅更新卡片。
    """
    invitation = await invitation_repo.get(GroupInvitation, invitation_id)
    if invitation is None:
        raise ValueError("邀请不存在")
    if invitation.invitee_id != user_id:
        raise ValueError("这不是发给你的邀请")
    if not validate_invitation_transition(invitation.status, "rejected"):
        raise ValueError(f"邀请状态为 {invitation.status}，无法拒绝")

    invitation.status = "rejected"
    invitation.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await _update_dm_card(invitation_repo, invitation, "rejected")

    from app.models.group import Group
    group = await invitation_repo.get(Group, invitation.group_id)
    group_name = getattr(group, 'name', f"#{invitation.group_id}")

    logger.info(f"❌ 群邀请 #{invitation_id}: user#{user_id} 拒绝了「{group_name}」的邀请")

    return {
        "invitation_id": invitation.id,
        "group_id": invitation.group_id,
        "group_name": group_name,
        "status": "rejected",
    }


async def list_pending_invitations(
    invitation_repo: InvitationRepository,
    user_id: int,
) -> list[dict]:
    """列出用户的所有待处理邀请"""
    result = await invitation_repo.execute(
        select(GroupInvitation).where(
            GroupInvitation.invitee_id == user_id,
            GroupInvitation.status == "pending",
        ).order_by(GroupInvitation.created_at.desc())
    )
    invitations = result.scalars().all()

    infos = []
    for inv in invitations:
        # 查群名
        from app.models.group import Group
        group = await invitation_repo.get(Group, inv.group_id)
        group_name = getattr(group, 'name', f"群#{inv.group_id}") if group else f"群#{inv.group_id}"

        # 查邀请人名称
        inviter_result = await invitation_repo.execute(
            select(User.username).where(User.id == inv.inviter_id)
        )
        inviter_row = inviter_result.one_or_none()
        inviter_name = inviter_row[0] if inviter_row else f"用户{inv.inviter_id}"

        # 查被邀请人名称
        invitee_result = await invitation_repo.execute(
            select(User.username).where(User.id == inv.invitee_id)
        )
        invitee_row = invitee_result.one_or_none()
        invitee_name = invitee_row[0] if invitee_row else f"用户{inv.invitee_id}"

        infos.append(format_invitation_for_api(inv, group_name, inviter_name, invitee_name))

    return infos


# ═══════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════

async def _update_dm_card(
    invitation_repo: InvitationRepository,
    invitation: GroupInvitation,
    new_status: str,
):
    """更新 DM 卡片消息的 attachments，反映新状态。
    前端收到 WebSocket 消息更新后重新渲染卡片。
    """
    if not invitation.dm_message_id:
        return

    from app.models.dm import DMMessage
    from app.models.group import Group

    dm_msg = await invitation_repo.get(DMMessage, invitation.dm_message_id)
    if dm_msg is None:
        return

    group = await invitation_repo.get(Group, invitation.group_id)
    group_name = getattr(group, 'name', f"群#{invitation.group_id}") if group else f"群#{invitation.group_id}"

    inviter_result = await invitation_repo.execute(
        select(User.username).where(User.id == invitation.inviter_id)
    )
    inviter_row = inviter_result.one_or_none()
    inviter_name = inviter_row[0] if inviter_row else f"用户{invitation.inviter_id}"

    new_attachments = build_invitation_attachments(
        invitation.id, group_name, inviter_name, status=new_status,
    )
    dm_msg.attachments = json.dumps(new_attachments)

    logger.info(f"  📝 DM 卡片 #{dm_msg.id} 状态更新: {invitation.status} → {new_status}")
