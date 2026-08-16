"""plugins and user_plugin_prefs tables

统一插件系统（目录即插件）：plugins 存磁盘扫描到的插件清单 + 管理员全局开关；
user_plugin_prefs 存用户个人启用/停用。

Revision ID: a9b8c7d6e5f4
Revises: e6f7a8b9c0d2
Create Date: 2026-08-17 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'e6f7a8b9c0d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'plugins',
        sa.Column('id', sa.String(80), primary_key=True, comment='插件 id（目录名）'),
        sa.Column('name', sa.String(120), nullable=False, comment='显示名称'),
        sa.Column('description', sa.Text(), nullable=True, default='', comment='描述'),
        sa.Column('category', sa.String(20), nullable=True, default='other', comment='skin | skill | world | other'),
        sa.Column('version', sa.String(20), nullable=True, default='1.0.0'),
        sa.Column('author', sa.String(80), nullable=True, default='', comment='作者'),
        sa.Column('icon', sa.String(40), nullable=True, default='', comment='lucide 图标名'),
        sa.Column('enabled', sa.Boolean(), nullable=True, default=True, comment='管理员全局开关'),
        sa.Column('builtin', sa.Boolean(), nullable=True, default=False, comment='是否内置'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'user_plugin_prefs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plugin_id', sa.String(80), sa.ForeignKey('plugins.id', ondelete='CASCADE'), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True, default=True, comment='用户个人开关'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('user_id', 'plugin_id', name='uq_user_plugin_pref'),
    )


def downgrade() -> None:
    op.drop_table('user_plugin_prefs')
    op.drop_table('plugins')
