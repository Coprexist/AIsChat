"""add compression_threshold to conversation_log_config

Revision ID: e7f8g9h0i1j2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8g9h0i1j2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加压缩阈值列"""
    op.add_column(
        'conversation_log_config',
        sa.Column('compression_threshold', sa.Integer(), server_default='60', nullable=False),
    )


def downgrade() -> None:
    """回滚：删除压缩阈值列"""
    op.drop_column('conversation_log_config', 'compression_threshold')
