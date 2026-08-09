"""群类型系统：世界按类型分发 + 群助手

Revision ID: f6f7a8b9c0d1
Revises: f5e6f7a8b9c0
Create Date: 2026-08-09

- world_group_types：世界预设群类型（规则/绑定上限/助手模板）
- world_bindings 加 group_type_id（群绑定到哪个类型）
- world_agents 加 group_id / group_type_id（群助手登记：归属群 + 类型）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from typing import Sequence, Union

revision: str = 'f6f7a8b9c0d1'
down_revision: Union[str, None] = 'f5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'world_group_types',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(50), nullable=False, comment='类型名，如 冒险团/商会'),
        sa.Column('description', sa.Text(), nullable=True, comment='类型说明'),
        sa.Column('rules', sa.Text(), nullable=True, comment='世界规则（群主可见；群助手行为继承）'),
        sa.Column('bind_limit', sa.Integer(), nullable=False, server_default='3', comment='该类型可绑定群数上限'),
        sa.Column('assistant_spec', JSONB(), nullable=True, comment='助手模板：{count, need_api, default_name}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.add_column('world_bindings', sa.Column('group_type_id', sa.Integer(),
                                              sa.ForeignKey('world_group_types.id', ondelete='SET NULL'),
                                              nullable=True, comment='群绑定到哪个群类型'))
    op.add_column('world_agents', sa.Column('group_id', sa.Integer(), nullable=True, comment='群助手所属群'))
    op.add_column('world_agents', sa.Column('group_type_id', sa.Integer(), nullable=True, comment='群助手所属类型'))


def downgrade() -> None:
    op.drop_column('world_agents', 'group_type_id')
    op.drop_column('world_agents', 'group_id')
    op.drop_column('world_bindings', 'group_type_id')
    op.drop_table('world_group_types')
