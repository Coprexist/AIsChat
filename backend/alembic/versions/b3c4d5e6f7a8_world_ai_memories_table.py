"""world_ai_memories table

世界 AI 记忆专属表（阶段 2.6）：复用主站记忆逻辑（store/recall），工具名统一 store_memory/recall_memory。
世界记忆按世界隔离（world_id 归属），不占用主站 rough/detail_memories。

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-05 09:05:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector 扩展（幂等，fresh DB 兜底）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table('world_ai_memories',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('world_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['world_id'], ['worlds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_world_ai_memories_world_id', 'world_ai_memories', ['world_id'])


def downgrade() -> None:
    op.drop_index('ix_world_ai_memories_world_id', table_name='world_ai_memories')
    op.drop_table('world_ai_memories')
