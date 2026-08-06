"""system_settings add world_preset_suggestions

世界 AI 建议问题预设（"你可以问"按钮：无对话历史/兜底时展示），管理员后台可维护。

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-06 12:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('system_settings', sa.Column(
        'world_preset_suggestions', JSONB(), nullable=True,
        comment='世界 AI 建议问题预设（「你可以问」按钮，无对话历史/兜底时展示）',
    ))


def downgrade() -> None:
    op.drop_column('system_settings', 'world_preset_suggestions')
