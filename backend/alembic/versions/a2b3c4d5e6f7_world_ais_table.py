"""world_ais table + memory owner_type world_ai

世界 AI 实体化：独立表（不再塞 worlds.creator_config JSONB），记忆等共用能力以本表为锚。

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-08-05 00:12:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('world_ais',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('world_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('name', sa.String(length=50), server_default='群视界机器人'),
        sa.Column('system_prompt', sa.Text(), server_default=''),
        sa.Column('model', sa.String(length=50), nullable=True),
        sa.Column('temperature', sa.Float(), server_default='0.8'),
        sa.Column('top_p', sa.Float(), server_default='0.9'),
        sa.Column('thinking', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('max_tool_rounds', sa.Integer(), server_default='50'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['world_id'], ['worlds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # 从 worlds.creator_config 迁数据（老世界）
    op.execute("""
        INSERT INTO world_ais (world_id, name, system_prompt, model, temperature, top_p, thinking, max_tool_rounds)
        SELECT
            id,
            COALESCE(creator_config->>'name', '群视界机器人'),
            COALESCE(creator_config->>'system_prompt', ''),
            creator_config->>'model',
            COALESCE((creator_config->>'temperature')::float, 0.8),
            COALESCE((creator_config->>'top_p')::float, 0.9),
            COALESCE((creator_config->>'thinking')::boolean, false),
            COALESCE((creator_config->>'max_tool_rounds')::int, 50)
        FROM worlds
        WHERE creator_config IS NOT NULL AND creator_config != '{}'::jsonb
    """)


def downgrade() -> None:
    op.drop_table('world_ais')
