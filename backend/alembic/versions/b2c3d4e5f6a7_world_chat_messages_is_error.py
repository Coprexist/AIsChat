"""world_chat_messages add is_error column

工具执行失败标记：刷新后保持红色展示（tool 消息 error 状态落库）。
2026-08-13 新增。

Revision ID: b2c3d4e5f6a7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-13 18:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('world_chat_messages', sa.Column('is_error', sa.Boolean(), nullable=True, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('world_chat_messages', 'is_error')
