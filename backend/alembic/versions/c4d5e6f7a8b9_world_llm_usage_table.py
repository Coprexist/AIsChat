"""world_llm_usage table

世界 AI LLM 调用用量（阶段 2.7）：usage.cached_tokens 落库 → 每世界缓存命中率可观测。
每次 LLM 调用（首轮/工具轮/收尾轮）写一行。

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-05 09:05:30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('world_llm_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('world_id', sa.Integer(), nullable=False),
        sa.Column('turn_id', sa.String(length=32), nullable=True),
        sa.Column('round_no', sa.String(length=10), server_default='0'),
        sa.Column('model', sa.String(length=50), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), server_default='0'),
        sa.Column('reasoning_tokens', sa.Integer(), server_default='0'),
        sa.Column('cached_tokens', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['world_id'], ['worlds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_world_llm_usage_world_id', 'world_llm_usage', ['world_id'])


def downgrade() -> None:
    op.drop_index('ix_world_llm_usage_world_id', table_name='world_llm_usage')
    op.drop_table('world_llm_usage')
