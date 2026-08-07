"""世界商城商品表 world_market_items

Revision ID: d9e8f7a6b5c4
Revises: d7e8f9a0b1c2
Create Date: 2026-08-07

手写（非 autogenerate）：仅建一张新表，additive 无破坏。
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'd9e8f7a6b5c4'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'world_market_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='world',
                  comment='world=完整世界 | block=积木组件（后置）'),
        sa.Column('title', sa.String(length=100), nullable=False, comment='商品标题'),
        sa.Column('description', sa.Text(), nullable=False, server_default='', comment='商品描述'),
        sa.Column('tags', JSONB(), nullable=True, comment='标签数组'),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, comment='发布者'),
        sa.Column('author_name', sa.String(length=50), nullable=False, server_default='', comment='发布者名（冗余）'),
        sa.Column('source_world_id', sa.Integer(), nullable=True, comment='发布来源世界'),
        sa.Column('package_path', sa.String(length=255), nullable=False, comment='zip 包相对 data/ 路径'),
        sa.Column('package_size', sa.Integer(), nullable=False, server_default='0', comment='zip 字节数'),
        sa.Column('downloads', sa.Integer(), nullable=False, server_default='0', comment='导入次数'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='on', comment='on=在架 | off=下架'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_world_market_items_created', 'world_market_items', ['created_at'])
    op.create_index('ix_world_market_items_kind', 'world_market_items', ['kind'])


def downgrade() -> None:
    op.drop_index('ix_world_market_items_kind', table_name='world_market_items')
    op.drop_index('ix_world_market_items_created', table_name='world_market_items')
    op.drop_table('world_market_items')
