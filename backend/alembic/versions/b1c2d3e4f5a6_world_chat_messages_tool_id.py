"""world_chat_messages add tool_id column

工具执行 id（同 id 多状态 SSE 更新；历史落库只保留最终态）。
2026-08-13 新增：AI 调用工具时先发 running 状态（正在执行 XX），
完成后同 id 发 done——前端按 tool_id 定位气泡原地更新。

Revision ID: b1c2d3e4f5a6
Revises: c8d9e0f1a2b3
Create Date: 2026-08-13 17:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('world_chat_messages', sa.Column('tool_id', sa.String(32), nullable=True))
    op.create_index('ix_world_chat_messages_tool_id', 'world_chat_messages', ['tool_id'])


def downgrade() -> None:
    op.drop_index('ix_world_chat_messages_tool_id', table_name='world_chat_messages')
    op.drop_column('world_chat_messages', 'tool_id')
