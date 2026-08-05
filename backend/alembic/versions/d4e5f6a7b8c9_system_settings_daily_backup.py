"""system_settings daily backup columns

每日数据库备份：管理员开关（daily_backup_enabled）+ 保留份数（daily_backup_keep，超出自动清除）。

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-08-04 09:05:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('system_settings', sa.Column('daily_backup_enabled', sa.Boolean(), nullable=True, server_default=sa.text('false'), comment='每日自动备份开关（管理员控制，默认关）'))
    op.add_column('system_settings', sa.Column('daily_backup_keep', sa.Integer(), nullable=True, server_default=sa.text('7'), comment='备份保留份数，超出自动清除（默认 7）'))


def downgrade() -> None:
    op.drop_column('system_settings', 'daily_backup_keep')
    op.drop_column('system_settings', 'daily_backup_enabled')
