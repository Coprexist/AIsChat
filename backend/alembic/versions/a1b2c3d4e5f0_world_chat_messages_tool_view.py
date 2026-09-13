"""world_chat_messages add tool_name / tool_detail

工具卡片：刷新后仍能显示是哪个工具、点开看详情。详情是 UI 专用，不塞进 content
（content 同时是喂给世界 AI 的工具结果，塞详情会污染模型上下文）。

Revision ID: a1b2c3d4e5f0
Revises: e8f9a0b1c2d3
Create Date: 2026-09-14 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f0'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('world_chat_messages', sa.Column('tool_name', sa.String(64), nullable=True))
    op.add_column('world_chat_messages', sa.Column('tool_detail', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('world_chat_messages', 'tool_detail')
    op.drop_column('world_chat_messages', 'tool_name')
