"""状态栈摘要上限可配置

Revision ID: f5e6f7a8b9c0
Revises: f4d5e6f7a8b9
Create Date: 2026-08-08

- agents 加 state_stack_max_chars（状态栈摘要长度上限，默认 500，可在 AI 配置页修改）
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = 'f5e6f7a8b9c0'
down_revision: Union[str, None] = 'f4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agents', sa.Column('state_stack_max_chars', sa.Integer(), nullable=False,
                                      server_default=sa.text('500'),
                                      comment='状态栈摘要长度上限（默认 500，AI 配置页可改）'))


def downgrade() -> None:
    op.drop_column('agents', 'state_stack_max_chars')
