"""world_data table

每世界 key-value 数据存储（代码/数据分离：结构化数据只经 API 读写；
静态文字类产物放 data/worlds/{id}/content/，不随代码打包）。

Revision ID: a3b4c5d6e7f8
Revises: f6a7b8c9d0e1
Create Date: 2026-08-06 10:35:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'world_data',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id', ondelete='CASCADE'), nullable=False, comment='所属世界'),
        sa.Column('key', sa.String(200), nullable=False, comment='数据键（如 player.position / npc.lihua.relation）'),
        sa.Column('value', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"), comment='数据值（任意 JSON）'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('world_id', 'key', name='uq_world_data_world_key'),
    )
    op.create_index('ix_world_data_world_id', 'world_data', ['world_id'])


def downgrade() -> None:
    op.drop_index('ix_world_data_world_id', table_name='world_data')
    op.drop_table('world_data')
