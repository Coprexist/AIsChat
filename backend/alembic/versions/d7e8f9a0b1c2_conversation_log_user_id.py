"""conversation_log add user_id

世界 AI 用量记账：不建占位 agent，直接记 user_id（记账人 = 世界 AI 表单的世界主人），
个人 API 用量查询时虚拟聚合为「群视界 agent」。

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-08-06 15:15:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_conversation_logs', sa.Column(
        'user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True,
        comment='记账人（世界 AI 用量 = 世界主人；普通 AI 记录为空，按 agent.owner_id 归属）',
    ))
    op.create_index('ix_ai_conversation_logs_user_id', 'ai_conversation_logs', ['user_id'])
    # 世界 AI 用量记录 agent_id 为空（记账走 user_id，不建占位 agent）
    op.alter_column('ai_conversation_logs', 'agent_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.drop_index('ix_ai_conversation_logs_user_id', table_name='ai_conversation_logs')
    op.drop_column('ai_conversation_logs', 'user_id')
