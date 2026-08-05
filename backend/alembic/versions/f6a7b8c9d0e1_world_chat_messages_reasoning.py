"""world_chat_messages add reasoning column

保存世界 AI 思考过程（thinking 模式产生；展示用，不进 LLM 上下文）。

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-04 09:42:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('world_chat_messages', sa.Column('reasoning', sa.Text(), nullable=True, comment='AI 思考过程（thinking 模式产生，展示用，不进上下文）'))


def downgrade() -> None:
    op.drop_column('world_chat_messages', 'reasoning')
