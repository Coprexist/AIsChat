"""add user global model overrides

用户级全局默认模型覆盖：global_chat_model / global_work_model。

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-12 13:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('global_chat_model', sa.String(100), nullable=True, comment='用户全局默认聊天模型覆盖'))
    op.add_column('users', sa.Column('global_work_model', sa.String(100), nullable=True, comment='用户全局默认工作模型覆盖'))


def downgrade() -> None:
    op.drop_column('users', 'global_work_model')
    op.drop_column('users', 'global_chat_model')
