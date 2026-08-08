"""世界商城 GitHub 同步支持

Revision ID: e4f5a6b7c8d9
Revises: d9e8f7a6b5c4
Create Date: 2026-08-08

- world_market_items 加 source / github_path / github_sha（GitHub 缓存商品）
- system_settings 加 market_config JSONB（github_repo/github_token/auto_sync_enabled）
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd9e8f7a6b5c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('world_market_items', sa.Column('source', sa.String(length=10),
                  nullable=False, server_default='local', comment='local=本站发布 | github=GitHub 同步缓存'))
    op.add_column('world_market_items', sa.Column('github_path', sa.String(length=255),
                  nullable=True, comment='GitHub 仓库内目录，如 worlds/world-12'))
    op.add_column('world_market_items', sa.Column('github_sha', sa.String(length=64),
                  nullable=True, comment='GitHub 同步内容 sha'))
    op.add_column('system_settings', sa.Column('market_config', JSONB(), nullable=True,
                  comment='世界商城配置：github_repo/github_token/auto_sync_enabled'))


def downgrade() -> None:
    op.drop_column('system_settings', 'market_config')
    op.drop_column('world_market_items', 'github_sha')
    op.drop_column('world_market_items', 'github_path')
    op.drop_column('world_market_items', 'source')
