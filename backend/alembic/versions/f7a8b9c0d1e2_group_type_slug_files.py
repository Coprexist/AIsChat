"""群类型改为文件定义（随世界打包）：DB 只留绑定状态

Revision ID: f7a8b9c0d1e2
Revises: f6f7a8b9c0d1
Create Date: 2026-08-09

背景：类型定义（规则/上限/助手模板）随世界文件夹 group_types.json 走（打包性），
DB 只存绑定状态。类型用字符串 slug 作稳定 id（打包分发后不变）。

- world_bindings 加 group_type_slug（String）替代 group_type_id
- world_agents 加 group_type_slug（String）
- 退役 world_group_types 表（定义在文件里）
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'f6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('world_bindings', sa.Column('group_type_slug', sa.String(50), nullable=True,
                                              comment='群绑定的类型 slug（定义在 group_types.json）'))
    op.add_column('world_agents', sa.Column('group_type_slug', sa.String(50), nullable=True,
                                            comment='群助手所属类型 slug'))
    op.drop_column('world_bindings', 'group_type_id')
    op.drop_column('world_agents', 'group_type_id')
    op.drop_table('world_group_types')


def downgrade() -> None:
    op.create_table(
        'world_group_types',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('rules', sa.Text(), nullable=True),
        sa.Column('bind_limit', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('assistant_spec', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.add_column('world_agents', sa.Column('group_type_id', sa.Integer(), nullable=True))
    op.add_column('world_bindings', sa.Column('group_type_id', sa.Integer(), nullable=True))
    op.drop_column('world_agents', 'group_type_slug')
    op.drop_column('world_bindings', 'group_type_slug')
